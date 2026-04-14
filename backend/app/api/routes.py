import json
from pathlib import Path
from typing import Any
from collections import Counter

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.core.auth import get_current_user_id
from app.schemas.api import HorizonMatcherScoreIn, HorizonMatcherScoreOut, HorizonMatcherUploadOut
from app.services.horizon_matcher import HorizonMatcherEngine, HorizonMatcherError
from app.services.horizon_matcher.config import get_matcher_config
from app.services.horizon_matcher.embedder import build_index, load_index
from app.services.horizon_matcher.ingest import parse_work_programme, parse_work_programmes

router = APIRouter()
horizon_matcher_engine = HorizonMatcherEngine()

CLUSTER_TO_ID = {
    'Health': 'CL1',
    'Digital': 'CL2',
    'Security': 'CL3',
    'Manufacturing': 'CL4',
    'Climate': 'CL5',
    'Food': 'CL6',
}


async def _persist_uploaded_pdfs(
    files: list[UploadFile],
    uploads_dir: Path,
) -> list[tuple[str, Path]]:
    """
    Salva i PDF caricati in una cartella dedicata e ritorna (filename, path).
    """
    uploads_dir.mkdir(parents=True, exist_ok=True)
    persisted: list[tuple[str, Path]] = []

    for idx, file in enumerate(files, start=1):
        filename = (file.filename or f"work_programme_{idx}.pdf").strip() or f"work_programme_{idx}.pdf"
        if not filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail=f"File non valido: {filename}. Carica solo PDF.")

        data = await file.read()
        if not data:
            raise HTTPException(status_code=400, detail=f"Il PDF '{filename}' è vuoto.")

        safe_name = filename.replace("/", "_").replace("\\", "_")
        target_path = uploads_dir / f"{idx:02d}_{safe_name}"
        target_path.write_bytes(data)
        persisted.append((filename, target_path))

    return persisted


def _load_quality_summary(config: dict[str, Any]) -> dict[str, Any]:
    qa_path = Path(config["qa_report"])
    if not qa_path.exists():
        return {}
    try:
        data = json.loads(qa_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {
        "missing_counts": data.get("missing_counts", {}),
        "anomaly_counts": data.get("anomaly_counts", {}),
    }


@router.get('/health')
def health() -> dict[str, str]:
    return {'status': 'ok'}


@router.get('/horizon-matcher/status')
def horizon_matcher_status() -> dict[str, Any]:
    return horizon_matcher_engine.status()


@router.post('/horizon-matcher/score', response_model=HorizonMatcherScoreOut)
def horizon_matcher_score(
    payload: HorizonMatcherScoreIn,
    _current_user_id: str = Depends(get_current_user_id),
):
    try:
        return horizon_matcher_engine.score(profile=payload.profile.model_dump(), top_n=payload.top_n)
    except HorizonMatcherError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/horizon-matcher/upload-pdf', response_model=HorizonMatcherUploadOut)
async def horizon_matcher_upload_pdf(
    file: UploadFile = File(...),
    _current_user_id: str = Depends(get_current_user_id),
):
    filename = (file.filename or 'work_programme.pdf').strip() or 'work_programme.pdf'
    if not filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail='Carica un file PDF valido.')

    try:
        config = get_matcher_config()
        pdf_path = Path(config['pdf_path'])
        pdf_path.parent.mkdir(parents=True, exist_ok=True)

        data = await file.read()
        if not data:
            raise HTTPException(status_code=400, detail='Il PDF è vuoto.')
        pdf_path.write_bytes(data)

        calls = parse_work_programme(str(pdf_path))
        build_index(calls_path=config['calls_json'], config=config)
        index, _ = load_index(config=config)
        cluster_counter = Counter(
            str(call.get('cluster', 'Unknown')).strip() or 'Unknown'
            for call in calls
        )
        cluster_distribution = {
            key: int(value)
            for key, value in sorted(cluster_counter.items(), key=lambda item: item[1], reverse=True)
        }
        detected_cluster = next(iter(cluster_distribution.keys()), None)
        suggested_cluster_id = CLUSTER_TO_ID.get(detected_cluster or '')

        return {
            'filename': filename,
            'files_processed': 1,
            'calls_parsed': len(calls),
            'indexed_vectors': int(index.ntotal),
            'detected_cluster': detected_cluster,
            'suggested_cluster_id': suggested_cluster_id,
            'cluster_distribution': cluster_distribution,
            'quality_summary': _load_quality_summary(config),
            'status': horizon_matcher_engine.status(),
        }
    except HorizonMatcherError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f'Errore durante ingestione PDF matcher: {exc}') from exc


@router.post('/horizon-matcher/upload-pdfs', response_model=HorizonMatcherUploadOut)
async def horizon_matcher_upload_pdfs(
    files: list[UploadFile] = File(...),
    _current_user_id: str = Depends(get_current_user_id),
):
    if not files:
        raise HTTPException(status_code=400, detail='Nessun file ricevuto.')

    try:
        config = get_matcher_config()
        pdf_dir = Path(config['pdf_path']).parent
        uploads_dir = pdf_dir / 'uploads'

        persisted = await _persist_uploaded_pdfs(files, uploads_dir)
        calls = parse_work_programmes([str(path) for _, path in persisted])
        build_index(calls_path=config['calls_json'], config=config)
        index, _ = load_index(config=config)

        cluster_counter = Counter(
            str(call.get('cluster', 'Unknown')).strip() or 'Unknown'
            for call in calls
        )
        cluster_distribution = {
            key: int(value)
            for key, value in sorted(cluster_counter.items(), key=lambda item: item[1], reverse=True)
        }
        detected_cluster = next(iter(cluster_distribution.keys()), None)
        suggested_cluster_id = CLUSTER_TO_ID.get(detected_cluster or '')

        return {
            'filename': ', '.join(name for name, _ in persisted),
            'files_processed': len(persisted),
            'calls_parsed': len(calls),
            'indexed_vectors': int(index.ntotal),
            'detected_cluster': detected_cluster,
            'suggested_cluster_id': suggested_cluster_id,
            'cluster_distribution': cluster_distribution,
            'quality_summary': _load_quality_summary(config),
            'status': horizon_matcher_engine.status(),
        }
    except HorizonMatcherError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f'Errore durante ingestione multipla PDF matcher: {exc}') from exc
