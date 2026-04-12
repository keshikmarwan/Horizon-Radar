from dataclasses import dataclass
from typing import Protocol


@dataclass
class NormalizedTopic:
    source: str
    topic_id: str
    title: str
    cluster: str | None
    action_type: str | None
    trl_min: int | None
    trl_max: int | None
    expected_outcomes: str | None
    scope: str | None
    budget_total: float | None
    deadline_iso: str | None
    status: str | None
    topic_url: str | None
    metadata_json: dict


@dataclass
class DraftDocCandidate:
    source: str
    title: str
    source_url: str
    file_url: str | None
    version_label: str | None
    metadata_json: dict


class SourceConnector(Protocol):
    source_name: str

    def fetch_topics(self) -> tuple[list[NormalizedTopic], list[tuple[str, str, str, str]]]:
        ...

    def fetch_drafts(self) -> tuple[list[DraftDocCandidate], list[tuple[str, str, str, str]]]:
        ...
