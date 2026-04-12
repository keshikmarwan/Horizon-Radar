import difflib
from pathlib import Path

import pdfplumber
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.draft_document import DraftDocument
from app.models.fetch_snapshot import FetchSnapshot
from app.services.connectors import build_connectors
from app.services.http_fetcher import HttpFetcher

settings = get_settings()


def _extract_pdf_text(path: str) -> str:
    text_parts = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages[:20]:
            text_parts.append(page.extract_text() or '')
    return '\n'.join(text_parts)


def _diff_summary(old_text: str, new_text: str) -> str:
    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()
    diff = list(difflib.unified_diff(old_lines, new_lines, lineterm=''))
    if not diff:
        return 'No textual change detected.'
    changed = [line for line in diff if line.startswith('+') or line.startswith('-')]
    return f'{len(changed)} changed lines detected between versions.'


def run_draft_hunter(db: Session) -> dict:
    total_new = 0
    snapshots_saved = 0
    fetcher = HttpFetcher()

    for connector in build_connectors():
        docs, snapshots = connector.fetch_drafts()
        for source, source_url, local_path, content_hash in snapshots:
            db.add(FetchSnapshot(
                source=source,
                source_url=source_url,
                local_path=local_path,
                content_hash=content_hash,
                content_type='text/html',
            ))
            snapshots_saved += 1

        for doc in docs:
            existing = db.scalars(
                select(DraftDocument)
                .where(DraftDocument.source == doc.source)
                .where(DraftDocument.title == doc.title)
                .order_by(DraftDocument.discovered_at.desc())
            ).first()

            local_pdf_path = None
            excerpt = None
            diff_summary = None
            if doc.file_url:
                try:
                    fetched = fetcher.fetch(doc.file_url)
                    local_pdf_path, _ = fetcher.write_snapshot(settings.snapshot_dir, doc.source, fetched)
                    if local_pdf_path.endswith('.pdf'):
                        excerpt = _extract_pdf_text(local_pdf_path)[:3000]
                        if existing and existing.local_pdf_path and Path(existing.local_pdf_path).exists():
                            old = _extract_pdf_text(existing.local_pdf_path)[:8000]
                            diff_summary = _diff_summary(old, excerpt)
                except Exception as exc:
                    diff_summary = f'PDF fetch/parse issue: {exc}'

            # Skip duplicate versions by same url and version label.
            duplicate = db.scalars(
                select(DraftDocument)
                .where(DraftDocument.source == doc.source)
                .where(DraftDocument.source_url == doc.source_url)
                .where(DraftDocument.version_label == doc.version_label)
            ).first()
            if duplicate:
                continue

            draft = DraftDocument(
                source=doc.source,
                title=doc.title,
                source_url=doc.source_url,
                file_url=doc.file_url,
                version_label=doc.version_label,
                local_pdf_path=local_pdf_path,
                text_excerpt=excerpt,
                diff_summary=diff_summary,
                metadata_json=doc.metadata_json,
            )
            db.add(draft)
            total_new += 1

    db.commit()
    return {'draft_updates': total_new, 'snapshots_saved': snapshots_saved}
