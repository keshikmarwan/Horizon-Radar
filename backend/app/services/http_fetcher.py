import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx


@dataclass
class FetchResult:
    url: str
    content: bytes
    content_type: str
    status_code: int


class HttpFetcher:
    def __init__(self, timeout: float = 30.0, per_domain_delay_sec: float = 1.0) -> None:
        self.timeout = timeout
        self.per_domain_delay_sec = per_domain_delay_sec
        self._last_request_ts: dict[str, float] = {}
        self._robots_cache: dict[str, RobotFileParser] = {}

    def _respect_rate_limit(self, domain: str) -> None:
        last = self._last_request_ts.get(domain)
        if last is None:
            return
        elapsed = time.time() - last
        if elapsed < self.per_domain_delay_sec:
            time.sleep(self.per_domain_delay_sec - elapsed)

    def _can_fetch(self, url: str, user_agent: str = 'HorizonRadarBot/1.0') -> bool:
        parsed = urlparse(url)
        domain = f'{parsed.scheme}://{parsed.netloc}'
        robots_url = f'{domain}/robots.txt'
        parser = self._robots_cache.get(domain)
        if parser is None:
            parser = RobotFileParser()
            parser.set_url(robots_url)
            try:
                parser.read()
            except Exception:
                # Fallback if robots is unavailable.
                return True
            self._robots_cache[domain] = parser
        return parser.can_fetch(user_agent, url)

    def fetch(self, url: str) -> FetchResult:
        parsed = urlparse(url)
        domain = parsed.netloc
        if not self._can_fetch(url):
            raise PermissionError(f'Blocked by robots.txt: {url}')
        self._respect_rate_limit(domain)
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            response = client.get(url, headers={'User-Agent': 'HorizonRadarBot/1.0'})
        self._last_request_ts[domain] = time.time()
        return FetchResult(
            url=url,
            content=response.content,
            content_type=response.headers.get('Content-Type', ''),
            status_code=response.status_code,
        )

    @staticmethod
    def write_snapshot(snapshot_dir: str, source: str, fetched: FetchResult) -> tuple[str, str]:
        source_dir = Path(snapshot_dir) / source
        source_dir.mkdir(parents=True, exist_ok=True)
        content_hash = hashlib.sha256(fetched.content).hexdigest()
        suffix = '.pdf' if 'pdf' in fetched.content_type.lower() else '.html'
        target = source_dir / f'{content_hash}{suffix}'
        if not target.exists():
            target.write_bytes(fetched.content)
        return str(target), content_hash
