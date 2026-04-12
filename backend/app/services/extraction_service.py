"""Structured topic extraction from EU Work Programme PDFs.

Uses PyMuPDF (fitz) to extract text, then sends chunks to Groq
(llama-3.3-70b-versatile) for structured JSON extraction.
Each chunk response is validated via Pydantic before being returned.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
from typing import Any

from app.schemas.extraction import (
    CROSS_CUTTING_ALLOWED,
    ExtractedTopic,
    ExtractionError,
)

logger = logging.getLogger(__name__)

_GROQ_MODEL = "llama-3.3-70b-versatile"

# Maximum characters per chunk sent to Groq.
_MAX_CHUNK_CHARS = 180_000

# Overlap between consecutive chunks, expressed in pages.
_OVERLAP_PAGES = 2

_SYSTEM_PROMPT = """\
You are a structured data extraction engine for EU research funding documents.
Extract all competitive call topics from the provided Work Programme text and \
return a JSON object with a single key "topics" whose value is an array — one object per topic.

Rules:
- Return ONLY a valid JSON object: {"topics": [...]}. No markdown, no explanation, no preamble.
- If a field is not found, use null. Never hallucinate values.
- Skip any "Other Actions not subject to calls for proposals" sections.
- scope_summary: 3-5 sentences, neutral English, no copy-paste from source.
- keywords: concrete terms only (disease names, technologies, methodologies). \
Exclude generic terms like "research", "innovation", "health".
- cross_cutting: only use values from this list: gender, AI, climate, \
open science, rare diseases, AMR, mental health, digitalisation, \
equity, disability, pandemic preparedness.
- For two-stage calls: deadline = stage 1, deadline_stage2 = stage 2.
- Dates in ISO 8601 format (YYYY-MM-DD).
- Budgets in million EUR as decimal numbers.
- If document is not an EU funding document, return: \
{"error": "document_type_not_supported", "detail": "<reason>"}

Schema for each topic object:
{
  "topic_id": string,
  "programme": string,
  "cluster": string,
  "destination": string,
  "title": string,
  "action_type": string,
  "call_id": string,
  "opening_date": string,
  "deadline": string,
  "deadline_stage2": string,
  "total_budget_meur": number,
  "grant_per_project_min_meur": number,
  "grant_per_project_max_meur": number,
  "expected_projects": number,
  "scope_summary": string,
  "expected_outcomes": [string],
  "keywords": [string],
  "target_population": [string],
  "consortium_notes": string,
  "synergies": [string],
  "trl_range": string,
  "cross_cutting": [string],
  "source_pages": string
}
"""

# Regex to strip repeating Work Programme page headers that pdfplumber / PyMuPDF
# inject mid-topic and that can confuse the LLM.
_PAGE_HEADER_RE = re.compile(
    r"\nPart \d+ - Page \d+ of \d+\n[^\n]*Work Programme[^\n]*\n[^\n]{1,60}\n",
    re.IGNORECASE,
)


def _get_groq_client() -> Any:
    """Lazily create and return a Groq client."""
    from groq import Groq  # type: ignore[import-untyped]

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY environment variable is not set. "
            "Get a free key at https://console.groq.com/"
        )
    return Groq(api_key=api_key)


def extract_text_from_pdf(data: bytes) -> tuple[list[str], int]:
    """Extract per-page text from a PDF using PyMuPDF.

    Returns:
        Tuple of (list of page texts, total page count).
    """
    import fitz  # PyMuPDF — imported lazily to avoid crashing the app if not installed

    doc = fitz.open(stream=data, filetype="pdf")
    pages: list[str] = []
    for page in doc:
        pages.append(page.get_text("text") or "")
    doc.close()
    return pages, len(pages)


def _clean_page_text(text: str) -> str:
    """Strip repeated PDF page headers from extracted text."""
    return _PAGE_HEADER_RE.sub("\n", text)


def _build_chunks(pages: list[str]) -> list[tuple[str, int, int]]:
    """Split page texts into chunks respecting the character limit.

    Each chunk contains the concatenated text of a contiguous range of pages.
    Consecutive chunks overlap by ``_OVERLAP_PAGES`` pages so that topics
    sitting on a chunk boundary are not lost.

    Returns:
        List of (chunk_text, start_page_1indexed, end_page_1indexed).
    """
    if not pages:
        return []

    total_chars = sum(len(p) for p in pages)
    if total_chars <= _MAX_CHUNK_CHARS:
        merged = _clean_page_text("\n".join(pages))
        return [(merged, 1, len(pages))]

    chunks: list[tuple[str, int, int]] = []
    start_idx = 0

    while start_idx < len(pages):
        # Greedily extend the chunk until the char budget is exhausted.
        end_idx = start_idx
        current_len = 0
        while end_idx < len(pages):
            page_len = len(pages[end_idx])
            if current_len + page_len > _MAX_CHUNK_CHARS and end_idx > start_idx:
                break
            current_len += page_len
            end_idx += 1

        chunk_text = _clean_page_text("\n".join(pages[start_idx:end_idx]))
        chunks.append((chunk_text, start_idx + 1, end_idx))

        # Advance with overlap.
        start_idx = max(start_idx + 1, end_idx - _OVERLAP_PAGES)

    return chunks


def _call_groq(client: Any, chunk_text: str) -> dict[str, Any]:
    """Send a single chunk to Groq and return the parsed JSON response."""
    response = client.chat.completions.create(
        model=_GROQ_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": chunk_text},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )
    raw = response.choices[0].message.content
    return json.loads(raw)  # type: ignore[no-any-return]


def _sanitize_cross_cutting(tags: list[str] | None) -> list[str] | None:
    """Filter cross_cutting to only allowed values."""
    if tags is None:
        return None
    return [t for t in tags if t in CROSS_CUTTING_ALLOWED] or None


def _validate_topics(raw_topics: list[dict[str, Any]]) -> list[ExtractedTopic]:
    """Validate a list of raw dicts through the Pydantic schema.

    Invalid items are logged and skipped.
    """
    validated: list[ExtractedTopic] = []
    for i, item in enumerate(raw_topics):
        try:
            # Sanitize cross_cutting before validation.
            if "cross_cutting" in item and isinstance(item["cross_cutting"], list):
                item["cross_cutting"] = _sanitize_cross_cutting(item["cross_cutting"])
            topic = ExtractedTopic.model_validate(item)
            validated.append(topic)
        except Exception as exc:
            topic_id = item.get("topic_id", f"index-{i}")
            logger.warning(
                "Skipping invalid topic %s from Groq response: %s",
                topic_id,
                exc,
            )
    return validated


def _dedup_topics(topics: list[ExtractedTopic]) -> list[ExtractedTopic]:
    """Remove duplicate topics (by topic_id), keeping the last occurrence.

    Topics without a topic_id are always kept.
    """
    seen: dict[str, int] = {}
    for i, t in enumerate(topics):
        if t.topic_id:
            seen[t.topic_id] = i

    keep_indices: set[int] = set()
    for i, t in enumerate(topics):
        if t.topic_id is None:
            keep_indices.add(i)
        elif seen.get(t.topic_id) == i:
            keep_indices.add(i)

    return [t for i, t in enumerate(topics) if i in keep_indices]


def extract_topics_from_pdf(
    data: bytes,
    filename: str = "upload.pdf",
) -> dict[str, Any]:
    """Extract structured topics from an EU Work Programme PDF.

    Orchestrates the full pipeline: text extraction → chunking →
    Groq calls → Pydantic validation → deduplication.

    Returns:
        A dict matching the ``ExtractionResponse`` schema, or an
        ``ExtractionError`` dict if the document is not supported.
    """
    pages, page_count = extract_text_from_pdf(data)
    if page_count == 0:
        return ExtractionError(
            detail="PDF contains no pages."
        ).model_dump()

    chunks = _build_chunks(pages)
    client = _get_groq_client()

    all_topics: list[ExtractedTopic] = []
    warnings: list[str] = []

    for chunk_idx, (chunk_text, start_page, end_page) in enumerate(chunks):
        try:
            parsed = _call_groq(client, chunk_text)
        except json.JSONDecodeError as exc:
            msg = f"Chunk {chunk_idx + 1} (pp. {start_page}-{end_page}): Groq returned invalid JSON — {exc}"
            logger.warning(msg)
            warnings.append(msg)
            continue
        except Exception as exc:
            msg = f"Chunk {chunk_idx + 1} (pp. {start_page}-{end_page}): Groq call failed — {exc}"
            logger.warning(msg)
            warnings.append(msg)
            continue

        # Handle "not supported" response from LLM.
        if "error" in parsed and parsed.get("error") == "document_type_not_supported":
            if len(chunks) == 1:
                return ExtractionError(
                    detail=parsed.get("detail", "Unrecognised document type.")
                ).model_dump()
            # For multi-chunk docs, one chunk might look non-EU; skip it.
            msg = f"Chunk {chunk_idx + 1} (pp. {start_page}-{end_page}): LLM flagged as non-EU content, skipped."
            logger.info(msg)
            warnings.append(msg)
            continue

        raw_topics = parsed.get("topics")
        if not isinstance(raw_topics, list):
            msg = f"Chunk {chunk_idx + 1} (pp. {start_page}-{end_page}): response missing 'topics' array."
            logger.warning(msg)
            warnings.append(msg)
            continue

        validated = _validate_topics(raw_topics)
        all_topics.extend(validated)

    deduped = _dedup_topics(all_topics)

    return {
        "filename": filename,
        "pages": page_count,
        "chunks_sent": len(chunks),
        "topics_extracted": len(deduped),
        "topics": [t.model_dump() for t in deduped],
        "warnings": warnings,
    }
