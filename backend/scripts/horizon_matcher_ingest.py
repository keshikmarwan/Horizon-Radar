import sys

from app.services.horizon_matcher.ingest import parse_work_programme, parse_work_programmes
from app.services.horizon_matcher.config import get_matcher_config


def main() -> None:
    config = get_matcher_config()
    cli_args = sys.argv[1:]
    if len(cli_args) > 1:
        parse_work_programmes(cli_args)
        return
    if len(cli_args) == 1:
        parse_work_programme(cli_args[0])
        return
    parse_work_programme(config["pdf_path"])


if __name__ == "__main__":
    main()
