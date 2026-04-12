from pathlib import Path

from app.services.connectors.ec_work_programme import ECWorkProgrammeConnector
from app.services.connectors.funding_tenders import FundingTendersConnector
from app.services.connectors.ncp_news import NCPNewsConnector


FIXTURES = Path(__file__).parent / 'fixtures'


class DummyFetched:
    def __init__(self, content: bytes, content_type: str = 'text/html'):
        self.content = content
        self.content_type = content_type


class DummyFetcher:
    def __init__(self, html: str):
        self.html = html

    def fetch(self, url: str):
        return DummyFetched(self.html.encode('utf-8'))

    @staticmethod
    def write_snapshot(snapshot_dir: str, source: str, fetched):
        return 'snapshots/dummy.html', 'hash123'


def test_funding_connector_parses_topics_from_fixture():
    html = (FIXTURES / 'funding_topics.html').read_text(encoding='utf-8')
    connector = FundingTendersConnector(DummyFetcher(html))
    topics = connector.parse_topics_from_html(html)

    assert len(topics) == 2
    assert topics[0].topic_id.startswith('HORIZON-')
    assert any(t.trl_min == 5 and t.trl_max == 7 for t in topics)
    assert any(t.budget_total for t in topics)


def test_funding_connector_fetch_topics_works_with_dummy_fetcher():
    html = """
    <div data-topic-id='HORIZON-CL4-2026-01' data-programme-part='CL4' data-action-type='RIA' data-deadline='2026-11-01T17:00:00'>
      <span class='eui-u-font-m'>AI for resilient factories TRL 5-7</span>
      <p>Expected outcomes include flexible manufacturing.</p>
    </div>
    """
    connector = FundingTendersConnector(DummyFetcher(html))
    topics, snaps = connector.fetch_topics()

    assert len(topics) == 1
    assert topics[0].topic_id == 'HORIZON-CL4-2026-01'
    assert topics[0].trl_min == 5
    assert topics[0].trl_max == 7
    assert len(snaps) == 1


def test_ncp_connector_filters_draft_related_news():
    html = (FIXTURES / 'ncp_drafts.html').read_text(encoding='utf-8')
    connector = NCPNewsConnector(DummyFetcher(html))
    docs = connector.parse_drafts_from_html(html)

    assert len(docs) == 2
    assert any(d.file_url and d.file_url.endswith('.pdf') for d in docs)


def test_ec_wp_connector_collects_pdf_links():
    html = (FIXTURES / 'ec_wp.html').read_text(encoding='utf-8')
    connector = ECWorkProgrammeConnector(DummyFetcher(html))
    docs = connector.parse_drafts_from_html(html)

    assert len(docs) == 2
    assert all(d.file_url and '.pdf' in d.file_url for d in docs)


def test_extract_trl_no_match():
    trl_min, trl_max = FundingTendersConnector._extract_trl('No TRL present')
    assert trl_min is None
    assert trl_max is None
