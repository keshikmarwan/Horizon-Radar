import re
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from app.services.connectors.base import NormalizedTopic
from app.services.http_fetcher import HttpFetcher


class FundingTendersConnector:
    source_name = 'eu_funding_tenders'
    topics_url = 'https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-search'

    def __init__(self, fetcher: HttpFetcher):
        self.fetcher = fetcher

    def fetch_topics(self):
        fetched = self.fetcher.fetch(self.topics_url)
        local_path, content_hash = self.fetcher.write_snapshot('snapshots', self.source_name, fetched)
        topics = self.parse_topics_from_html(fetched.content.decode('utf-8', errors='ignore'))
        snapshots = [(self.source_name, self.topics_url, local_path, content_hash)]
        return topics, snapshots

    def fetch_drafts(self):
        return [], []

    def parse_topics_from_html(self, html: str) -> list[NormalizedTopic]:
        soup = BeautifulSoup(html, 'html.parser')
        topics: list[NormalizedTopic] = []

        cards = soup.select('[data-topic-id]')
        if not cards:
            cards = soup.select('.opportunity-card, .topic-card, article, tr')

        for card in cards:
            topic = self._parse_card(card)
            if topic:
                topics.append(topic)

        dedup: dict[str, NormalizedTopic] = {}
        for topic in topics:
            dedup[topic.topic_id] = topic
        return list(dedup.values())

    def _parse_card(self, card: Tag) -> NormalizedTopic | None:
        raw_text = card.get_text(' ', strip=True)
        topic_id = card.get('data-topic-id') or self._extract_topic_id(raw_text)
        if not topic_id:
            return None

        title = self._extract_title(card, topic_id)
        cluster = card.get('data-programme-part') or self._extract_labeled(raw_text, 'Cluster')
        action = card.get('data-action-type') or self._extract_labeled(raw_text, 'Type of action')
        deadline_iso = self._extract_deadline(card, raw_text)
        trl_min, trl_max = self._extract_trl(f'{title} {raw_text}')
        budget = self._extract_budget(raw_text)

        topic_url = self._extract_topic_url(card)
        return NormalizedTopic(
            source=self.source_name,
            topic_id=topic_id,
            title=title,
            cluster=cluster,
            action_type=action,
            trl_min=trl_min,
            trl_max=trl_max,
            expected_outcomes=raw_text[:1200],
            scope=raw_text[:2400],
            budget_total=budget,
            deadline_iso=deadline_iso,
            status='open_or_upcoming',
            topic_url=topic_url,
            metadata_json={'raw_text': raw_text},
        )

    def _extract_title(self, card: Tag, fallback: str) -> str:
        for sel in ['.eui-u-font-m', 'h2', 'h3', '.title', 'td:nth-child(2)']:
            el = card.select_one(sel)
            if el and el.get_text(strip=True):
                return el.get_text(' ', strip=True)
        return fallback

    def _extract_topic_url(self, card: Tag) -> str:
        link = card.select_one('a[href]')
        if link and link.get('href'):
            return urljoin(self.topics_url, link.get('href'))
        return self.topics_url

    def _extract_deadline(self, card: Tag, raw_text: str) -> str | None:
        deadline_text = card.get('data-deadline')
        if not deadline_text:
            m = re.search(r'\b(20\d{2}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}:\d{2})?)\b', raw_text)
            if m:
                deadline_text = m.group(1)
        if not deadline_text:
            return None
        try:
            return datetime.fromisoformat(deadline_text.replace(' ', 'T')).isoformat()
        except ValueError:
            return None

    @staticmethod
    def _extract_topic_id(text: str) -> str | None:
        m = re.search(r'\bHORIZON-[A-Z0-9\-]+\b', text)
        return m.group(0) if m else None

    @staticmethod
    def _extract_labeled(text: str, label: str) -> str | None:
        m = re.search(rf'{re.escape(label)}\s*[:\-]\s*([^|;]+)', text, flags=re.IGNORECASE)
        return m.group(1).strip() if m else None

    @staticmethod
    def _extract_trl(text: str) -> tuple[int | None, int | None]:
        matches = re.findall(r'TRL\s*(\d)(?:\s*[-to]+\s*(\d))?', text, flags=re.IGNORECASE)
        if not matches:
            return None, None
        first = matches[0]
        return int(first[0]), int(first[1]) if first[1] else int(first[0])

    @staticmethod
    def _extract_budget(text: str) -> float | None:
        m = re.search(r'([\d\.,]+)\s*(?:EUR)', text, flags=re.IGNORECASE)
        if not m:
            return None
        value = m.group(1).replace('.', '').replace(',', '.')
        try:
            return float(value)
        except ValueError:
            return None
