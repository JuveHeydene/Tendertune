"""Horodatage des phases du pipeline de traitement d'un document (§ détail
document dans l'interface) — partagé entre app/workers/ingest.py (parse,
chunk, classify, embed, index) et app/graph/extract.py (graph)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm.attributes import flag_modified

from app.models.sql import Document

PIPELINE_PHASES = ("parse", "chunk", "classify", "embed", "index", "graph")


def mark_stage(
    doc: Document,
    stage: str,
    *,
    started: bool = False,
    finished: bool = False,
    error: str | None = None,
) -> None:
    stages = dict(doc.pipeline_stages or {})
    entry = dict(stages.get(stage) or {})
    now = datetime.now(UTC).isoformat()
    if started:
        entry["started_at"] = now
        entry.pop("finished_at", None)
        entry.pop("error", None)
    if finished:
        entry["finished_at"] = now
    if error:
        entry["error"] = error[:500]
    stages[stage] = entry
    doc.pipeline_stages = stages
    # SQLAlchemy compare la nouvelle valeur à l'ancienne PAR VALEUR pour un
    # JSONB simple ; sans flag_modified, un cas où le dict reconstruit est
    # égal à celui déjà chargé en mémoire (ex. deux relances rapprochées)
    # ferait silencieusement disparaître la colonne de l'UPDATE — bug réel
    # rencontré sur ocr_progress, voir app/workers/ingest.py.
    flag_modified(doc, "pipeline_stages")


def mark_failed_stage(doc: Document, error: str) -> None:
    """Attache le message d'erreur à la phase restée `started` sans `finished`
    (donc celle en cours au moment du crash)."""
    stages = dict(doc.pipeline_stages or {})
    for phase in PIPELINE_PHASES:
        entry = stages.get(phase)
        if entry and entry.get("started_at") and not entry.get("finished_at"):
            mark_stage(doc, phase, error=error)
            return
