from app.services.horizon_matcher.config import get_matcher_config
from app.services.horizon_matcher.embedder import build_index


def main() -> None:
    config = get_matcher_config()
    build_index(calls_path=config["calls_json"], config=config)


if __name__ == "__main__":
    main()
