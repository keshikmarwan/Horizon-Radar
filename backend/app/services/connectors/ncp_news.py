from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from app.services.connectors.base import DraftDocCandidate
from app.services.http_fetcher import HttpFetcher


class NCPNewsConnector:
    source_name = 'ncp_news'
    news_url = 'https://horizoneuropencpportal.eu/news'

    def __init__(self, fetcher: HttpFetcher):
        self.fetcher = fetcher

    def fetch_topics(self):
        return [], []

    def fetch_drafts(self):
        fetched = self.fetcher.fetch(self.news_url)
        local_path, content_hash = self.fetcher.write_snapshot('snapshots', self.source_name, fetched)
        docs = self.parse_drafts_from_html(fetched.content.decode('utf-8', errors='ignore'))
        snapshots = [(self.source_name, self.news_url, local_path, content_hash)]
        return docs, snapshots

    def parse_drafts_from_html(self, html: str) -> list[DraftDocCandidate]:
        soup = BeautifulSoup(html, 'html.parser')
        candidates = soup.select('article, .views-row, li, .news-item')
        docs: list[DraftDocCandidate] = []

        for block in candidates:
            doc = self._parse_block(block)
            if doc:
                docs.append(doc)

        unique: dict[str, DraftDocCandidate] = {}
        for d in docs:
            key = f'{d.title}|{d.source_url}'
            unique[key] = d
        return list(unique.values())

    def _parse_block(self, block: Tag) -> DraftDocCandidate | None:
        title_el = block.select_one('h1, h2, h3, h4, a')
        if not title_el:
            return None

        title = title_el.get_text(' ', strip=True)
        raw = block.get_text(' ', strip=True)
        scan_text = f'{title} {raw}'.lower()
        if not self._is_draft_related(scan_text):
            return None

        pdf = block.select_one('a[href$=".pdf"], a[href*=".pdf?"]')
        permalink = block.select_one('a[href]')
        source_url = urljoin(self.news_url, permalink.get('href')) if permalink and permalink.get('href') else self.news_url
        file_url = urljoin(self.news_url, pdf.get('href')) if pdf and pdf.get('href') else None

        return DraftDocCandidate(
            source=self.source_name,
            title=title,
            source_url=source_url,
            file_url=file_url,
            version_label=None,
            metadata_json={'raw': raw[:1200]},
        )

    @staticmethod
    def _is_draft_related(text: str) -> bool:
        keys = ['draft', 'work programme', 'work program', 'horizon papers']
        return any(k in text for k in keys)
