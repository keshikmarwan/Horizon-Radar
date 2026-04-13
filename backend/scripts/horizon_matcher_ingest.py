from app.services.horizon_matcher.ingest import parse_work_programme
from app.services.horizon_matcher.config import get_matcher_config


def main() -> None:
    config = get_matcher_config()
    parse_work_programme(config["pdf_path"])


if __name__ == "__main__":
    main()
