from datetime import datetime
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from dateutil.relativedelta import relativedelta
from dateutil import parser as dt_parser
from app.services.connectors import build_connectors
from app.services.http_fetcher import HttpFetcher

BROKERAGE_SOURCE_URLS = [
    'https://horizoneuropencpportal.eu/stage',
    'https://horizoneuropencpportal.eu/news/upcoming-events-2026',
    'https://horizoneuropencpportal.eu/cluster-1',
    'https://horizoneuropencpportal.eu/cluster-2',
    'https://horizoneuropencpportal.eu/cluster-3',
    'https://horizoneuropencpportal.eu/cluster-4',
    'https://horizoneuropencpportal.eu/cluster-5',
    'https://horizoneuropencpportal.eu/cluster-6',
    'https://www.b2match.com/explore',
]

OFFICIAL_CALL_SOURCE_URLS = [
    'https://cinea.ec.europa.eu/funding-opportunities/calls-proposals/horizon-europe-eu1767-million-projects-supporting-cross-sectoral-solutions-climate-transition-and_en',
    'https://cinea.ec.europa.eu/funding-opportunities/calls-proposals/horizon-europe-eur-235-million-projects-supporting-sustainable-secure-and-competitive-energy-supply_en',
    'https://cinea.ec.europa.eu/funding-opportunities/calls-proposals/horizon-europe-eu45-million-projects-advancing-science-fair-transition-climate-neutral-and-resilient_en',
    'https://cinea.ec.europa.eu/funding-opportunities/calls-proposals/horizon-europe-eu138-million-available-projects-supporting-clean-and-competitive-solutions-all_en',
    'https://cinea.ec.europa.eu/funding-opportunities/calls-proposals/horizon-europe-eur-225-million-available-projects-supporting-clean-and-competitve-solutions-all_en',
    'https://cinea.ec.europa.eu/funding-opportunities/calls-proposals/horizon-europe-eu-mission-eu11-million-projects-under-eu-missions_en',
    'https://rea.ec.europa.eu/funding-and-grants/horizon-europe-cluster-6-food-bioeconomy-natural-resources-agriculture-and-environment/soil-mission_en',
    'https://european-research-area.ec.europa.eu/news/horizon-europe-work-programme-2026-2027-published-new-funding-opportunities-widening-and-era',
]


def _collect_draft_updates() -> list[dict]:
    drafts: list[dict] = []
    for connector in build_connectors():
        try:
            docs, _ = connector.fetch_drafts()
        except Exception:
            continue
        for doc in docs:
            drafts.append({
                'source': doc.source,
                'title': doc.title,
                'link': doc.source_url,
                'file_url': doc.file_url,
            })

    unique: dict[str, dict] = {}
    for item in drafts:
        key = f"{item['title']}|{item['link']}|{item.get('file_url') or ''}"
        unique[key] = item
    return list(unique.values())[:50]


def _collect_brokerage_events() -> list[dict]:
    fetcher = HttpFetcher()
    events: list[dict] = []

    for source_url in BROKERAGE_SOURCE_URLS:
        try:
            fetched = fetcher.fetch(source_url)
        except Exception:
            continue

        soup = BeautifulSoup(fetched.content.decode('utf-8', errors='ignore'), 'html.parser')
        blocks = soup.select('article, .views-row, .node, .event, .news-item, li')
        for block in blocks:
            text = block.get_text(' ', strip=True)
            text_lower = text.lower()
            is_ncp_stage = 'horizoneuropencpportal.eu/stage' in source_url
            is_b2match = 'b2match.com' in source_url

            if is_ncp_stage:
                if not text:
                    continue
            elif is_b2match:
                if not any(k in text_lower for k in ['horizon', 'europe', 'brokerage', 'matchmaking', 'cluster', 'consortium']):
                    continue
            elif 'brokerage' not in text_lower and 'matchmaking' not in text_lower and 'consortium' not in text_lower:
                continue

            link = block.select_one('a[href]')
            if not link or not link.get('href'):
                continue

            title = link.get_text(' ', strip=True) or text[:180]
            date_match = re.search(
                r'(\d{1,2}[/-]\d{1,2}[/-]\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}\s*[–-]\s*\d{1,2}\s+[A-Za-z]+\s+\d{4}|\d{1,2}\s+[A-Za-z]+\s+\d{4})',
                text,
            )
            location = None
            if 'brussels' in text_lower:
                location = 'Brussels'
            elif 'online' in text_lower or 'on-line' in text_lower:
                location = 'Online'

            events.append({
                'title': title,
                'link': urljoin(source_url, link.get('href')),
                'date': _normalize_event_date(date_match.group(1)) if date_match else None,
                'location': location,
                'source': source_url,
            })

    unique: dict[str, dict] = {}
    for item in events:
        key = item['link']
        unique[key] = item
    return sorted(unique.values(), key=lambda x: (x.get('date') or '9999', x['title']))[:80]


def _collect_deadline_alerts() -> list[dict]:
    alerts: list[dict] = []
    for connector in build_connectors():
        try:
            topics, _ = connector.fetch_topics()
        except Exception:
            continue

        for topic in topics:
            if not topic.deadline_iso:
                continue
            explanation_parts = []
            if topic.cluster:
                explanation_parts.append(f'Cluster: {topic.cluster}')
            if topic.action_type:
                explanation_parts.append(f'Azione: {topic.action_type}')
            if topic.trl_min is not None:
                if topic.trl_max is not None and topic.trl_max != topic.trl_min:
                    explanation_parts.append(f'TRL: {topic.trl_min}-{topic.trl_max}')
                else:
                    explanation_parts.append(f'TRL: {topic.trl_min}')
            if topic.budget_total is not None:
                explanation_parts.append(f'Budget: EUR {topic.budget_total:,.0f}')

            alerts.append({
                'source': topic.source,
                'title': topic.title,
                'topic_id': topic.topic_id,
                'deadline': topic.deadline_iso,
                'status': topic.status,
                'link': topic.topic_url,
                'explanation': ' | '.join(explanation_parts) if explanation_parts else 'Deadline rilevata dalla fonte topic.',
            })

    unique: dict[str, dict] = {}
    for item in alerts:
        key = f"{item['topic_id']}|{item['deadline']}"
        unique[key] = item

    news_alerts = _collect_call_news_alerts()
    for item in news_alerts:
        key = f"{item['topic_id']}|{item['deadline']}"
        unique[key] = item

    official_alerts = _collect_official_call_alerts()
    for item in official_alerts:
        key = f"{item['topic_id']}|{item['deadline']}"
        unique[key] = item

    return sorted(unique.values(), key=lambda x: x['deadline'])[:120]


def collect_draft_report_items() -> list[dict]:
    return _collect_draft_updates()


def collect_brokerage_report_items() -> list[dict]:
    items = _collect_brokerage_events()
    now = datetime.utcnow()
    limit = now + relativedelta(months=5)
    filtered = []
    for item in items:
      date_text = item.get('date')
      if not date_text:
          filtered.append(item)
          continue
      parsed = _try_parse_event_date(date_text)
      if parsed is None or (parsed >= now and parsed <= limit):
          filtered.append(item)
    return filtered


def collect_deadline_alert_items() -> list[dict]:
    return _collect_deadline_alerts()


def _try_parse_event_date(value: str) -> datetime | None:
    for fmt in ('%d/%m/%Y', '%d-%m-%Y', '%d %B %Y', '%d %b %Y'):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _collect_call_news_alerts() -> list[dict]:
    fetcher = HttpFetcher()
    try:
        fetched = fetcher.fetch('https://horizoneuropencpportal.eu/news')
    except Exception:
        return []

    soup = BeautifulSoup(fetched.content.decode('utf-8', errors='ignore'), 'html.parser')
    items: list[dict] = []
    for index, block in enumerate(soup.select('article, .views-row, li, .news-item')):
        title_el = block.select_one('h1, h2, h3, h4, a[href]')
        if not title_el:
            continue
        title = title_el.get_text(' ', strip=True)
        raw = block.get_text(' ', strip=True)
        text = f'{title} {raw}'
        text_lower = text.lower()
        if not any(key in text_lower for key in ['deadline', 'call', 'opening', 'opens', 'submission', 'topic', 'open until', 'call launch']):
            continue

        permalink = block.select_one('a[href]')
        link = urljoin('https://horizoneuropencpportal.eu/news', permalink.get('href')) if permalink and permalink.get('href') else None

        parsed = _extract_deadline_from_news_text(text)
        if parsed is None:
            continue

        items.append({
            'source': 'ncp_news',
            'title': title,
            'topic_id': f'NCP-NEWS-{index + 1}',
            'deadline': parsed.isoformat(),
            'status': 'news_signal',
            'link': link,
            'explanation': 'Deadline o apertura call rilevata da news NCP Portal.',
        })
    return items


def _collect_official_call_alerts() -> list[dict]:
    fetcher = HttpFetcher()
    items: list[dict] = []
    for url in OFFICIAL_CALL_SOURCE_URLS:
        try:
            fetched = fetcher.fetch(url)
        except Exception:
            continue
        html = fetched.content.decode('utf-8', errors='ignore')
        soup = BeautifulSoup(html, 'html.parser')
        text = soup.get_text(' ', strip=True)

        title_el = soup.select_one('h1')
        title = title_el.get_text(' ', strip=True) if title_el else url

        call_ref_match = re.search(r'(HORIZON-[A-Z0-9\-]+)', text)
        topic_id = call_ref_match.group(1) if call_ref_match else re.sub(r'^https?://', '', url)[:80]

        status = None
        status_match = re.search(r'Status\s+([A-Za-z][A-Za-z ]+?)\s+(Publication date|Opening date|Deadline)', text, flags=re.IGNORECASE)
        if status_match:
            status = status_match.group(1).strip()

        explanation_parts = []
        deadline_matches = re.findall(
            r'(?:Deadline date|Deadline dates|closes on|deadline for submissions is)\s*([0-9]{1,2}\s+[A-Za-z]+\s+[0-9]{4}|[0-9]{1,2}\s+[A-Za-z]+\s+[0-9]{4},\s*[0-9:]{4,5}|[0-9]{1,2}\s*[A-Za-z]{3}\s*[0-9]{4})',
            text,
            flags=re.IGNORECASE,
        )
        if not deadline_matches:
            deadline_matches = re.findall(r'([0-9]{1,2}\s+[A-Za-z]+\s+20[0-9]{2})', text)

        opening_match = re.search(r'Opening date\s+([0-9]{1,2}\s+[A-Za-z]+\s+20[0-9]{2})', text, flags=re.IGNORECASE)
        if opening_match:
            explanation_parts.append(f'Opening: {opening_match.group(1)}')
        if status:
            explanation_parts.append(f'Stato: {status}')

        for raw_deadline in deadline_matches[:2]:
            parsed = _parse_flexible_date(raw_deadline)
            if not parsed:
                continue
            items.append({
                'source': 'official_call_pages',
                'title': title,
                'topic_id': topic_id,
                'deadline': parsed.isoformat(),
                'status': status or 'official_page',
                'link': url,
                'explanation': ' | '.join(explanation_parts) if explanation_parts else 'Deadline rilevata da pagina ufficiale call.',
            })
    return items


def _parse_flexible_date(value: str) -> datetime | None:
    try:
        return dt_parser.parse(value, dayfirst=True)
    except Exception:
        return None


def _extract_deadline_from_news_text(text: str) -> datetime | None:
    patterns = [
        r'open until\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})',
        r'submission deadline\s*[:\-]?\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4})',
        r'deadline\s*[:\-]?\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4})',
        r'close on\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})',
        r'close[s]?\s+on\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})',
        r'call launch\s*[:\-]?\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4})',
        r'opens?\s+on\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})',
        r'(\d{1,2}[/-]\d{1,2}[/-]\d{4})',
        r'(\d{4}-\d{2}-\d{2})',
    ]
    lower = text.lower()
    for pattern in patterns:
        match = re.search(pattern, lower, flags=re.IGNORECASE)
        if not match:
            continue
        parsed = _parse_flexible_date(match.group(1))
        if parsed:
            return parsed
    return None


def _normalize_event_date(value: str) -> str:
    clean = re.sub(r'\s+', ' ', value).strip()
    range_match = re.search(r'(\d{1,2})\s*[–-]\s*(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})', clean)
    if range_match:
      return f"{range_match.group(1)}-{range_match.group(2)} {range_match.group(3)} {range_match.group(4)}"
    return clean
