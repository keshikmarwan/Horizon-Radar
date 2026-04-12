"""Pydantic models for the structured topic extraction pipeline.

These schemas validate the JSON produced by the Groq LLM extraction
and define the API response contract for POST /api/ingest/extract-topics.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# Allowed values for cross_cutting tags.
CROSS_CUTTING_ALLOWED = frozenset([
    "gender", "AI", "climate", "open science", "rare diseases",
    "AMR", "mental health", "digitalisation", "equity",
    "disability", "pandemic preparedness",
])


class ExtractedTopic(BaseModel):
    """One competitive call topic extracted from an EU Work Programme PDF."""

    topic_id: str | None = None
    programme: str | None = None
    cluster: str | None = None
    destination: str | None = None
    title: str | None = None
    action_type: str | None = None
    call_id: str | None = None
    opening_date: str | None = None
    deadline: str | None = None
    deadline_stage2: str | None = None
    total_budget_meur: float | None = None
    grant_per_project_min_meur: float | None = None
    grant_per_project_max_meur: float | None = None
    expected_projects: int | None = None
    scope_summary: str | None = None
    expected_outcomes: list[str] | None = None
    keywords: list[str] | None = None
    target_population: list[str] | None = None
    consortium_notes: str | None = None
    synergies: list[str] | None = None
    trl_range: str | None = None
    cross_cutting: list[str] | None = None
    source_pages: str | None = None


class ExtractionError(BaseModel):
    """Returned when the document is not a supported EU funding document."""

    error: str = "document_type_not_supported"
    detail: str


class ExtractionResponse(BaseModel):
    """Top-level response for POST /api/ingest/extract-topics."""

    filename: str
    pages: int
    chunks_sent: int
    topics_extracted: int
    topics: list[ExtractedTopic] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
