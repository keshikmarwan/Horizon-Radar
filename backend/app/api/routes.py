import json
import math
import re
from pathlib import Path
from typing import Any
from collections import Counter
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.core.auth import get_current_user_id
from app.schemas.api import (
    HorizonMatcherExportPdfIn,
    HorizonMatcherScoreIn,
    HorizonMatcherScoreOut,
    HorizonMatcherUploadOut,
)
from app.services.horizon_matcher import HorizonMatcherEngine, HorizonMatcherError
from app.services.horizon_matcher.config import get_matcher_config
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
ID_TO_CLUSTER = {v: k for k, v in CLUSTER_TO_ID.items()}
CLUSTER_FULL_LABEL = {
    "CL1": "Cluster 1 – Health",
    "CL2": "Cluster 2 – Culture, Creativity and Inclusive Society",
    "CL3": "Cluster 3 – Civil Security for Society",
    "CL4": "Cluster 4 – Digital, Industry and Space",
    "CL5": "Cluster 5 – Climate, Energy and Mobility",
    "CL6": "Cluster 6 – Food, Bioeconomy, Natural Resources, Agriculture and Environment",
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


def _safe_filename_fragment(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", value.strip())
    return cleaned.strip("-") or "report"


def _normalize_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "", value).upper()


def _recommendation(score_100: float) -> str:
    if score_100 >= 55:
        return "GO"
    if score_100 >= 30:
        return "WATCH"
    return "NO-GO"


def _rec_badge_class(rec: str) -> str:
    if rec == "GO":
        return "go"
    if rec == "WATCH":
        return "watch"
    return "nogo"


def _score_payload_with_all_calls(profile: dict[str, Any]) -> dict[str, Any]:
    # Top_n alto per includere tutto il ranking anche per export completo.
    return horizon_matcher_engine.score(profile=profile, top_n=2000)


def _to_pct_from_spider(value_1_to_5: float) -> float:
    return max(0.0, min(100.0, ((value_1_to_5 - 1.0) / 4.0) * 100.0))


def _radar_svg(values: dict[str, float], size: int = 260, color: str = "#003399") -> str:
    labels = [
        ("TRL", values.get("trl_alignment", 1.0)),
        ("Impact", values.get("impact_policy", 1.0)),
        ("Scope", values.get("scope_methodology", 1.0)),
        ("Consortium", values.get("consortium_stakeholders", 1.0)),
        ("FAIR", values.get("fair_compliance", 1.0)),
        ("Ethics", values.get("inclusion_ethics", 1.0)),
    ]
    cx = size / 2
    cy = size / 2
    outer = size * 0.34
    n = len(labels)

    def polar(i: int, radius: float) -> tuple[float, float]:
        angle = -math.pi / 2 + i * 2 * math.pi / n
        return cx + math.cos(angle) * radius, cy + math.sin(angle) * radius

    polygons: list[str] = []
    for ratio in (0.25, 0.5, 0.75, 1.0):
        points = " ".join(f"{x:.2f},{y:.2f}" for i in range(n) for x, y in [polar(i, outer * ratio)])
        polygons.append(f'<polygon points="{points}" fill="none" stroke="#d9e1f2" stroke-width="1" />')

    axes = []
    labels_svg = []
    shape_points = []
    for i, (label, v) in enumerate(labels):
        x, y = polar(i, outer)
        axes.append(f'<line x1="{cx:.2f}" y1="{cy:.2f}" x2="{x:.2f}" y2="{y:.2f}" stroke="#d9e1f2" stroke-width="1" />')
        lx, ly = polar(i, outer + 18)
        labels_svg.append(f'<text x="{lx:.2f}" y="{ly:.2f}" font-size="10" fill="#4b5563" text-anchor="middle">{label}</text>')
        pct = _to_pct_from_spider(float(v))
        px, py = polar(i, outer * (pct / 100.0))
        shape_points.append(f"{px:.2f},{py:.2f}")

    shape = " ".join(shape_points)
    return (
        f'<svg viewBox="0 0 {size} {size}" width="{size}" height="{size}" xmlns="http://www.w3.org/2000/svg">'
        f'{"".join(polygons)}{"".join(axes)}'
        f'<polygon points="{shape}" fill="{color}" fill-opacity="0.20" stroke="{color}" stroke-width="2" />'
        f'{"".join(labels_svg)}'
        f"</svg>"
    )


def _pie_weights_svg(weights: dict[str, float], size: int = 180) -> str:
    items = [
        ("Excellence", float(weights.get("excellence", 0.0)), "#003399"),
        ("Impact", float(weights.get("impact", 0.0)), "#1d4ed8"),
        ("Implementation", float(weights.get("implementation", 0.0)), "#6b7280"),
        ("Tech Fit", float(weights.get("tech_fit", 0.0)), "#60a5fa"),
    ]
    total = sum(v for _, v, _ in items) or 1.0
    cx = size / 2
    cy = size / 2
    r = size * 0.36
    start = -math.pi / 2
    paths = []
    legend = []
    for idx, (name, value, color) in enumerate(items):
        angle = (value / total) * 2 * math.pi
        end = start + angle
        x1 = cx + r * math.cos(start)
        y1 = cy + r * math.sin(start)
        x2 = cx + r * math.cos(end)
        y2 = cy + r * math.sin(end)
        large = 1 if angle > math.pi else 0
        paths.append(
            f'<path d="M {cx:.2f} {cy:.2f} L {x1:.2f} {y1:.2f} A {r:.2f} {r:.2f} 0 {large} 1 {x2:.2f} {y2:.2f} Z" '
            f'fill="{color}" stroke="#ffffff" stroke-width="1"/>'
        )
        legend_y = size - 58 + idx * 12
        legend.append(f'<rect x="8" y="{legend_y}" width="8" height="8" fill="{color}" rx="2" />')
        legend.append(f'<text x="22" y="{legend_y + 7}" font-size="9" fill="#374151">{name} {(value * 100):.1f}%</text>')
        start = end
    return (
        f'<svg viewBox="0 0 {size} {size}" width="{size}" height="{size}" xmlns="http://www.w3.org/2000/svg">'
        f'{"".join(paths)}{"".join(legend)}</svg>'
    )


def _clean_text_block(value: Any) -> str:
    text = str(value or "").replace("\r\n", "\n").strip()
    if not text:
        return "n/d"

    seen: set[str] = set()
    cleaned_lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            if cleaned_lines and cleaned_lines[-1] != "":
                cleaned_lines.append("")
            continue
        key = re.sub(r"\s+", " ", line).strip().lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned_lines.append(line)

    result = "\n".join(cleaned_lines).strip()
    return result or "n/d"


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


@router.post('/horizon-matcher/export-pdf')
@router.post('/export-pdf')
def horizon_matcher_export_pdf(
    payload: HorizonMatcherExportPdfIn,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        from weasyprint import HTML
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Export PDF non disponibile: installa `weasyprint` e dipendenze di sistema richieste.",
        ) from exc
    try:
        from jinja2 import Environment, FileSystemLoader, select_autoescape
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Export PDF non disponibile: installa `jinja2` nel backend.",
        ) from exc

    try:
        scored = _score_payload_with_all_calls(payload.profile.model_dump())
    except HorizonMatcherError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Impossibile generare il report: il motore richiede Gurobi operativo e una licenza valida, "
                f"oppure dataset/indice non disponibili ({exc})."
            ),
        ) from exc

    all_results = [*(scored.get("results") or []), *(scored.get("other_results") or [])]
    cluster_id = payload.clusterId.upper()
    cluster_name = ID_TO_CLUSTER.get(cluster_id, cluster_id)

    base_filtered = [r for r in all_results if (r.get("cluster") or "").strip().lower() == cluster_name.lower()]
    if not base_filtered:
        base_filtered = all_results

    if not base_filtered:
        raise HTTPException(status_code=400, detail="Nessuna call disponibile per generare il report PDF.")

    selected = base_filtered
    if payload.callIds:
        wanted_raw = [cid.strip() for cid in payload.callIds if cid and cid.strip()]
        wanted_set = {w.upper() for w in wanted_raw}
        wanted_norm = {_normalize_id(w) for w in wanted_raw}

        exact = [r for r in base_filtered if str(r.get("call_id", "")).upper() in wanted_set]
        if exact:
            selected = exact
        else:
            fuzzy = [
                r for r in base_filtered
                if _normalize_id(str(r.get("call_id", ""))) in wanted_norm
                or any(_normalize_id(str(r.get("call_id", ""))).find(w) >= 0 for w in wanted_norm)
            ]
            selected = fuzzy if fuzzy else base_filtered[: max(1, min(payload.top_n, 15))]

    selected.sort(key=lambda item: float(item.get("fit_score", 0.0)), reverse=True)
    if not payload.include_all_calls and not payload.callIds:
        selected = selected[:payload.top_n]

    now = datetime.now()
    username = payload.username or current_user_id
    avg_score = sum(float(r.get("fit_score_100", 0.0)) for r in selected) / len(selected)
    chart_values = [round(float(r.get("fit_score_100", 0.0)), 1) for r in selected[:10]]
    chart_max = max(chart_values) if chart_values else 1.0

    spider_keys = [
        "trl_alignment",
        "impact_policy",
        "scope_methodology",
        "consortium_stakeholders",
        "fair_compliance",
        "inclusion_ethics",
    ]
    overall_spider = {
        key: (
            sum(float((row.get("spider_axes") or {}).get(key, 1.0)) for row in selected[:10])
            / max(1, len(selected[:10]))
        )
        for key in spider_keys
    }
    overall_radar_svg = _radar_svg(overall_spider, size=290)

    top3 = []
    for idx, row in enumerate(selected[:3], start=1):
        rec = _recommendation(float(row.get("fit_score_100", 0.0)))
        top3.append({
            "rank": idx,
            "call_id": row.get("call_id", ""),
            "title_short": str(row.get("title", "")).strip()[:90] + ("…" if len(str(row.get("title", "")).strip()) > 90 else ""),
            "fit_score_100": float(row.get("fit_score_100", 0.0)),
            "recommendation": rec,
            "rec_class": _rec_badge_class(rec),
        })

    calls_detail = []
    for idx, row in enumerate(selected, start=1):
        breakdown = row.get("score_breakdown") or {}
        explanation = row.get("explanation") or {}
        clear = explanation.get("clear_explanation") or {}
        rec = _recommendation(float(row.get("fit_score_100", 0.0)))
        calls_detail.append({
            "call": row,
            "rank": idx,
            "recommendation": rec,
            "rec_class": _rec_badge_class(rec),
            "title": row.get("title", ""),
            "call_id": row.get("call_id", ""),
            "fit_score_100": float(row.get("fit_score_100", 0.0)),
            "justification_text": clear.get("testo_semplice") or row.get("justification", ""),
            "quotes": (clear.get("citazioni_dirette") or [])[:3],
            "gaps": (clear.get("gap_principali") or [])[:8],
            "actions": (clear.get("azioni_concrete") or [])[:8],
            "consistency_label": "Matrice consistente" if breakdown.get("consistency_ok") else "Da rivedere",
            "spider_svg": _radar_svg(row.get("spider_axes") or {}, size=260),
            "weights_pie_svg": _pie_weights_svg(breakdown.get("weights") or {}),
            "breakdown": breakdown,
            "call_data": {
                **(row.get("call_data") or {}),
                "expected_outcomes": _clean_text_block((row.get("call_data") or {}).get("expected_outcomes")),
                "scope": _clean_text_block((row.get("call_data") or {}).get("scope")),
            },
        })

    executive_summary = {
        "average_fit": round(avg_score, 2),
        "total_calls": len(selected),
        "top3": top3,
        "chart_values": chart_values,
        "chart_max": chart_max,
        "overall_radar_svg": overall_radar_svg,
    }

    profile_dump = payload.profile.model_dump()
    repo_root = Path(__file__).resolve().parents[3]
    template_dir = Path(__file__).resolve().parents[2] / "templates" / "pdf"
    ec_logo_src = (template_dir / "logo-ec--mute.svg").resolve().as_uri()
    hr_logo_src = (template_dir / "logo-horizon-radar.svg").resolve().as_uri()
    gb_logo_src = (repo_root / "frontend" / "public" / "images" / "logo.png").resolve().as_uri()
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template("report.html")
    html_text = template.render(
        title="Analisi Strategica Fit Horizon Europe 2026-2027",
        cluster_id=cluster_id,
        cluster_full_label=CLUSTER_FULL_LABEL.get(cluster_id, cluster_id),
        cluster_name=cluster_name,
        generated_at=now.strftime("%d/%m/%Y %H:%M"),
        generated_by=username,
        generated_date_iso=now.strftime("%Y-%m-%d"),
        executive_summary=executive_summary,
        calls_detail=calls_detail,
        profile=profile_dump,
        ec_logo_src=ec_logo_src,
        hr_logo_src=hr_logo_src,
        gb_logo_src=gb_logo_src,
        recommendation_fn=_recommendation,
    )

    exports_dir = Path(__file__).resolve().parents[2] / "data" / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = now.strftime("%Y%m%d-%H%M%S")
    file_name = f"Generative-Bionics-Horizon-Report-{_safe_filename_fragment(cluster_id)}-{timestamp}.pdf"
    output_path = exports_dir / file_name

    try:
        try:
            HTML(string=html_text, base_url=str(template_dir)).write_pdf(
                str(output_path),
                optimize_images=False,
                jpeg_quality=95,
                dpi=300,
            )
        except TypeError:
            HTML(string=html_text, base_url=str(template_dir)).write_pdf(str(output_path))
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Errore durante la generazione PDF: {exc}",
        ) from exc

    return FileResponse(
        path=str(output_path),
        media_type="application/pdf",
        filename=file_name,
    )


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
            'indexed_vectors': 0,
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
            'indexed_vectors': 0,
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
