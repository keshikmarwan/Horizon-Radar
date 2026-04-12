from app.services.http_fetcher import HttpFetcher
from app.services.connectors.funding_tenders import FundingTendersConnector
from app.services.connectors.ec_work_programme import ECWorkProgrammeConnector
from app.services.connectors.ncp_news import NCPNewsConnector
from app.services.connectors.science_business import ScienceBusinessConnector


def build_connectors() -> list:
    fetcher = HttpFetcher()
    return [
        FundingTendersConnector(fetcher),
        ECWorkProgrammeConnector(fetcher),
        NCPNewsConnector(fetcher),
        ScienceBusinessConnector(fetcher),
    ]
