from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.services.connectors.base import DraftDocCandidate
from app.services.http_fetcher import HttpFetcher


class ScienceBusinessConnector:
    source_name = 'science_business'
    papers_url = 'https://sciencebusiness.net/horizon-papers'

    def __init__(self, fetcher: HttpFetcher):
        self.fetcher = fetcher

    def fetch_topics(self):
        return [], []

    def fetch_drafts(self):
        fetched = self.fetcher.fetch(self.papers_url)
        local_path, content_hash = self.fetcher.write_snapshot('snapshots', self.source_name, fetched)
        docs = self.parse_drafts_from_html(fetched.content.decode('utf-8', errors='ignore'))
        snapshots = [(self.source_name, self.papers_url, local_path, content_hash)]
        return docs, snapshots

    def parse_drafts_from_html(self, html: str) -> list[DraftDocCandidate]:
        soup = BeautifulSoup(html, 'html.parser')
        docs: list[DraftDocCandidate] = []
        for item in soup.select('article, .view-content .views-row, .node'):
            link = item.select_one('a[href]')
            if not link:
                continue
            title = link.get_text(' ', strip=True)
            if not self._is_relevant(title, item.get_text(' ', strip=True)):
                continue
            href = link.get('href')
            docs.append(
                DraftDocCandidate(
                    source=self.source_name,
                    title=title,
                    source_url=urljoin(self.papers_url, href) if href else self.papers_url,
                    file_url=None,
                    version_label=None,
                    metadata_json={'raw': item.get_text(' ', strip=True)[:1200]},
                )
            )
        return docs

    @staticmethod
    def _is_relevant(title: str, raw: str) -> bool:
        text = f'{title} {raw}'.lower()
        keys = ['horizon papers', 'draft', 'work programme', 'work program']
        return any(k in text for k in keys)
