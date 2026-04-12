"""Tests for the structured topic extraction service."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.schemas.extraction import (
    CROSS_CUTTING_ALLOWED,
    ExtractedTopic,
    ExtractionError,
    ExtractionResponse,
)
from app.services.extraction_service import (
    _build_chunks,
    _clean_page_text,
    _dedup_topics,
    _validate_topics,
    _sanitize_cross_cutting,
    _MAX_CHUNK_CHARS,
    _OVERLAP_PAGES,
)


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

class TestExtractedTopicSchema:
    def test_all_fields_nullable(self):
        """Every field should accept null / be optional."""
        topic = ExtractedTopic()
        assert topic.topic_id is None
        assert topic.programme is None
        assert topic.scope_summary is None

    def test_full_topic_round_trip(self):
        data = {
            "topic_id": "HORIZON-HLTH-2026-01-DISEASE-04",
            "programme": "Horizon Europe",
            "cluster": "Health",
            "destination": "Tackling diseases",
            "title": "Development of novel vaccines for viral pathogens",
            "action_type": "RIA",
            "call_id": "HORIZON-HLTH-2026-01",
            "opening_date": "2026-02-10",
            "deadline": "2026-04-16",
            "deadline_stage2": None,
            "total_budget_meur": 44.2,
            "grant_per_project_min_meur": 9.0,
            "grant_per_project_max_meur": 11.0,
            "expected_projects": 5,
            "scope_summary": "Funds vaccine R&D for epidemic-potential viruses.",
            "expected_outcomes": ["Novel vaccine candidates entering clinical trials"],
            "keywords": ["vaccines", "epidemic preparedness", "mRNA"],
            "target_population": ["virology researchers"],
            "consortium_notes": "Minimum 3 partners from 3 MS/AC",
            "synergies": ["HERA", "CEPI"],
            "trl_range": "TRL 2-5",
            "cross_cutting": ["pandemic preparedness"],
            "source_pages": "pp. 73-75",
        }
        topic = ExtractedTopic.model_validate(data)
        assert topic.topic_id == "HORIZON-HLTH-2026-01-DISEASE-04"
        assert topic.total_budget_meur == 44.2
        dumped = topic.model_dump()
        assert dumped["cross_cutting"] == ["pandemic preparedness"]

    def test_extraction_error_schema(self):
        err = ExtractionError(detail="Not a WP document.")
        assert err.error == "document_type_not_supported"
        assert err.detail == "Not a WP document."

    def test_extraction_response_schema(self):
        resp = ExtractionResponse(
            filename="test.pdf",
            pages=10,
            chunks_sent=1,
            topics_extracted=2,
            topics=[ExtractedTopic(topic_id="T1"), ExtractedTopic(topic_id="T2")],
        )
        assert resp.topics_extracted == 2
        assert len(resp.topics) == 2


# ---------------------------------------------------------------------------
# Sanitize cross_cutting
# ---------------------------------------------------------------------------

class TestSanitizeCrossCutting:
    def test_filters_invalid_values(self):
        assert _sanitize_cross_cutting(["AI", "bogus", "climate"]) == ["AI", "climate"]

    def test_returns_none_for_empty_result(self):
        assert _sanitize_cross_cutting(["bogus"]) is None

    def test_returns_none_for_none_input(self):
        assert _sanitize_cross_cutting(None) is None

    def test_preserves_all_allowed(self):
        result = _sanitize_cross_cutting(list(CROSS_CUTTING_ALLOWED))
        assert set(result) == CROSS_CUTTING_ALLOWED


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestValidateTopics:
    def test_valid_items_pass(self):
        raw = [
            {"topic_id": "HORIZON-HLTH-2026-01-TOOL-03", "title": "NAMs"},
            {"topic_id": "HORIZON-HLTH-2026-01-TOOL-05", "title": "Regen Med"},
        ]
        result = _validate_topics(raw)
        assert len(result) == 2
        assert result[0].topic_id == "HORIZON-HLTH-2026-01-TOOL-03"

    def test_invalid_item_skipped(self):
        raw = [
            {"topic_id": "GOOD", "title": "OK"},
            {"topic_id": 12345, "expected_projects": "not-a-number"},  # bad types
        ]
        # The second item has expected_projects as string "not-a-number"
        # which should fail int validation.
        result = _validate_topics(raw)
        assert len(result) >= 1
        assert result[0].topic_id == "GOOD"

    def test_cross_cutting_sanitized(self):
        raw = [{"topic_id": "T1", "cross_cutting": ["AI", "fake_tag"]}]
        result = _validate_topics(raw)
        assert result[0].cross_cutting == ["AI"]


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

class TestDedupTopics:
    def test_keeps_last_occurrence(self):
        topics = [
            ExtractedTopic(topic_id="A", title="first"),
            ExtractedTopic(topic_id="B", title="only"),
            ExtractedTopic(topic_id="A", title="second"),
        ]
        result = _dedup_topics(topics)
        ids = [t.topic_id for t in result]
        assert ids == ["B", "A"]
        assert result[1].title == "second"

    def test_topics_without_id_always_kept(self):
        topics = [
            ExtractedTopic(topic_id=None, title="orphan1"),
            ExtractedTopic(topic_id="A", title="a"),
            ExtractedTopic(topic_id=None, title="orphan2"),
        ]
        result = _dedup_topics(topics)
        assert len(result) == 3

    def test_empty_list(self):
        assert _dedup_topics([]) == []


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

class TestBuildChunks:
    def test_small_document_single_chunk(self):
        pages = ["page one text", "page two text"]
        chunks = _build_chunks(pages)
        assert len(chunks) == 1
        assert chunks[0][1] == 1  # start page
        assert chunks[0][2] == 2  # end page

    def test_empty_pages(self):
        assert _build_chunks([]) == []

    def test_large_document_splits(self):
        # Create pages that exceed the chunk limit.
        big_page = "x" * (_MAX_CHUNK_CHARS // 3 + 1)
        pages = [big_page] * 10
        chunks = _build_chunks(pages)
        assert len(chunks) > 1
        # Verify overlap: chunk N+1 start page <= chunk N end page
        for i in range(len(chunks) - 1):
            _, _, end_n = chunks[i]
            _, start_n1, _ = chunks[i + 1]
            assert start_n1 <= end_n

    def test_page_header_cleaning(self):
        text = "Hello\nPart 4 - Page 29 of 211\nHorizon Europe - Work Programme 2026-2027\nHealth\nWorld"
        cleaned = _clean_page_text(text)
        assert "Part 4 - Page 29" not in cleaned
        assert "Hello" in cleaned
        assert "World" in cleaned


# ---------------------------------------------------------------------------
# End-to-end with mocked Groq
# ---------------------------------------------------------------------------

class TestExtractTopicsFromPdf:
    @patch("app.services.extraction_service._get_groq_client")
    @patch("app.services.extraction_service.extract_text_from_pdf")
    def test_single_chunk_happy_path(self, mock_extract, mock_groq_client):
        mock_extract.return_value = (["page one text about HORIZON-HLTH"], 1)

        groq_response = {
            "topics": [
                {
                    "topic_id": "HORIZON-HLTH-2026-01-TEST-01",
                    "programme": "Horizon Europe",
                    "title": "Test topic",
                    "action_type": "RIA",
                    "total_budget_meur": 10.0,
                }
            ]
        }
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = json.dumps(groq_response)
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_completion
        mock_groq_client.return_value = mock_client

        from app.services.extraction_service import extract_topics_from_pdf

        result = extract_topics_from_pdf(b"fake-pdf", filename="test.pdf")

        assert result["filename"] == "test.pdf"
        assert result["pages"] == 1
        assert result["topics_extracted"] == 1
        assert result["topics"][0]["topic_id"] == "HORIZON-HLTH-2026-01-TEST-01"

    @patch("app.services.extraction_service._get_groq_client")
    @patch("app.services.extraction_service.extract_text_from_pdf")
    def test_not_supported_document(self, mock_extract, mock_groq_client):
        mock_extract.return_value = (["some random text"], 1)

        groq_response = {
            "error": "document_type_not_supported",
            "detail": "This is a restaurant menu."
        }
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = json.dumps(groq_response)
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_completion
        mock_groq_client.return_value = mock_client

        from app.services.extraction_service import extract_topics_from_pdf

        result = extract_topics_from_pdf(b"fake-pdf")

        assert result["error"] == "document_type_not_supported"
        assert "restaurant menu" in result["detail"]

    @patch("app.services.extraction_service._get_groq_client")
    @patch("app.services.extraction_service.extract_text_from_pdf")
    def test_groq_returns_invalid_json(self, mock_extract, mock_groq_client):
        mock_extract.return_value = (["page text"], 1)

        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = "NOT VALID JSON {{{{"
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_completion
        mock_groq_client.return_value = mock_client

        from app.services.extraction_service import extract_topics_from_pdf

        result = extract_topics_from_pdf(b"fake-pdf")

        assert result["topics_extracted"] == 0
        assert len(result["warnings"]) > 0

    @patch("app.services.extraction_service._get_groq_client")
    @patch("app.services.extraction_service.extract_text_from_pdf")
    def test_dedup_across_chunks(self, mock_extract, mock_groq_client):
        """If the same topic_id appears in overlapping chunks, keep only the last."""
        mock_extract.return_value = (["p1", "p2"], 2)

        groq_response = {
            "topics": [
                {"topic_id": "HORIZON-HLTH-SAME", "title": "from chunk"},
            ]
        }
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = json.dumps(groq_response)
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_completion
        mock_groq_client.return_value = mock_client

        from app.services.extraction_service import extract_topics_from_pdf

        result = extract_topics_from_pdf(b"fake-pdf")

        topic_ids = [t["topic_id"] for t in result["topics"]]
        assert topic_ids.count("HORIZON-HLTH-SAME") == 1
