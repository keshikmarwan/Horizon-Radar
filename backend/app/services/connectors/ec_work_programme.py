from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.services.connectors.base import DraftDocCandidate
from app.services.http_fetcher import HttpFetcher


class ECWorkProgrammeConnector:
    source_name = 'ec_work_programmes'
    wp_url = 'https://research-and-innovation.ec.europa.eu/funding/funding-opportunities/funding-programmes-and-open-calls/horizon-europe/horizon-europe-work-programmes_en'

    def __init__(self, fetcher: HttpFetcher):
        self.fetcher = fetcher

    def fetch_topics(self):
        return [], []

    def fetch_drafts(self):
        fetched = self.fetcher.fetch(self.wp_url)
        local_path, content_hash = self.fetcher.write_snapshot('snapshots', self.source_name, fetched)
        docs = self.parse_drafts_from_html(fetched.content.decode('utf-8', errors='ignore'))
        snapshots = [(self.source_name, self.wp_url, local_path, content_hash)]
        return docs, snapshots

    def parse_drafts_from_html(self, html: str) -> list[DraftDocCandidate]:
        soup = BeautifulSoup(html, 'html.parser')
        docs: list[DraftDocCandidate] = []
        for link in soup.select('a[href$=".pdf"], a[href*=".pdf?"]'):
            href = link.get('href')
            title = link.get_text(strip=True) or 'Horizon Europe work programme document'
            docs.append(
                DraftDocCandidate(
                    source=self.source_name,
                    title=title,
                    source_url=self.wp_url,
                    file_url=urljoin(self.wp_url, href) if href else None,
                    version_label=None,
                    metadata_json={'anchor_text': title},
                )
            )
        return docs
