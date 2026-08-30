"""Job ARQ ingest_document : MinIO → parse → chunks Postgres → Qdrant → enqueue graphe."""

from __future__ import annotations

import logging
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from app.config import get_settings
from app.ingest.chunk import chunk_document
from app.ingest.classify_section import classify_section_type
from app.ingest.index_qdrant import embed_texts, ensure_collection, upsert_chunks
from app.ingest.parse import parse_file
from app.models.sql import ChunkRow, Document
from app.services.db_client import session_factory
from app.services.minio_client import get_minio

log = logging.getLogger("btp.ingest")


async def ingest_document(ctx: dict, document_id: str) -> str:
    log.info("======== INGEST DÉBUT document_id=%s ========", document_id)
    factory = session_factory()
    async with factory() as session:
        doc = await session.get(Document, UUID(document_id))
        if doc is None:
            log.error("STOP — document introuvable en base id=%s", document_id)
            return f"missing:{document_id}"
        log.info(
            "fiche : fichier=%s rôle=%s type=%s taille=%s minio_key=%s statut_actuel=%s",
            doc.filename,
            doc.doc_role,
            doc.doc_type,
            doc.size_bytes,
            doc.object_key,
            doc.status,
        )
        doc.status = "processing"
        doc.ingest_error = None
        doc.updated_at = datetime.now(UTC)
        await session.commit()
        log.info("STATUT → processing (traitement commencé)")

        settings = get_settings()
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=Path(doc.filename).suffix)
        try:
            log.info("[A] MinIO GET DÉBUT bucket=%s object=%s", settings.minio_bucket_raw, doc.object_key)
            response = get_minio().get_object(settings.minio_bucket_raw, doc.object_key)
            try:
                payload = response.read()
            finally:
                response.close()
                response.release_conn()
            tmp.write(payload)
            tmp.close()
            log.info("[A] MinIO GET FIN — %s octets lus, fichier temporaire prêt — on passe au parse", len(payload))

            log.info("[B] PARSE DÉBUT fichier=%s mime=%s", doc.filename, doc.mime_type)
            parsed = parse_file(tmp.name, doc.filename, doc.mime_type)
            n_chars = sum(len(p.text or "") for p in parsed.pages)
            log.info(
                "[B] PARSE FIN — parser=%s pages=%s ocr=%s confiance=%s caractères=%s — on passe au chunking",
                parsed.parser,
                parsed.page_count,
                parsed.ocr_used,
                parsed.ocr_confidence,
                n_chars,
            )

            log.info("[C] CHUNKING DÉBUT")
            drafts = chunk_document(parsed)
            n_parent = sum(1 for d in drafts if d.parent_id is None)
            n_child = len(drafts) - n_parent
            log.info(
                "[C] CHUNKING FIN — total=%s parents=%s enfants=%s — on passe au stockage Postgres",
                len(drafts),
                n_parent,
                n_child,
            )

            existing = (
                await session.execute(select(ChunkRow).where(ChunkRow.document_id == doc.id))
            ).scalars().all()
            log.info("[D] POSTGRES CHUNKS DÉBUT (remplacement de %s anciennes lignes)", len(existing))
            for row in existing:
                await session.delete(row)
            await session.flush()

            # [C2] Classification section_type — UNE fois par parent (§3.1),
            # propagée à ses enfants (le filtre expert s'applique aux enfants,
            # même granularité que le dense/sparse — §4.4). Annexes exclues :
            # pas de section_type utile pour une pièce d'appoint ponctuelle.
            log.info("[C2] CLASSIFICATION section_type DÉBUT")
            section_type_by_parent: dict = {}
            if doc.doc_role != "annexe":
                for d in drafts:
                    if d.parent_id is not None:
                        continue
                    value, method = classify_section_type(d.heading_path, d.text)
                    section_type_by_parent[d.id] = value
                    d.extra = {**(d.extra or {}), "section_type_method": method}
            n_classified = sum(1 for v in section_type_by_parent.values() if v)
            log.info(
                "[C2] CLASSIFICATION FIN — %s/%s parents classés",
                n_classified,
                len(section_type_by_parent),
            )

            for d in drafts:
                parent_key = d.id if d.parent_id is None else d.parent_id
                session.add(
                    ChunkRow(
                        id=d.id,
                        document_id=doc.id,
                        parent_id=d.parent_id,
                        text=d.text,
                        heading_path=d.heading_path,
                        page=d.page,
                        token_count=d.token_count,
                        extra=d.extra,
                        section_type=section_type_by_parent.get(parent_key),
                    )
                )
            await session.flush()
            log.info("[D] POSTGRES CHUNKS FIN — %s lignes en base — on passe à Ollama (embeddings)", len(drafts))

            embeddable = [d for d in drafts if d.parent_id is not None] or drafts
            if not embeddable:
                # Actif visuel (image sans texte OCR exploitable, §5.2) : 0 chunk,
                # rien à embedder ni à indexer — on ne sollicite pas Ollama/Qdrant
                # pour rien. Le document reste "ready" (voir plus bas).
                log.info("[E/F] Aucun chunk à indexer (actif visuel) — Ollama/Qdrant sautés")
            else:
                log.info(
                    "[E] OLLAMA EMBEDDINGS DÉBUT model=%s url=%s n_textes=%s",
                    settings.embed_model,
                    settings.ollama_base_url,
                    len(embeddable),
                )
                vectors = embed_texts([_embed_text(d, doc.doc_type) for d in embeddable])
                log.info(
                    "[E] OLLAMA EMBEDDINGS FIN — %s vecteurs dim=%s — on passe à Qdrant",
                    len(vectors),
                    len(vectors[0]) if vectors else 0,
                )

                log.info(
                    "[F] QDRANT DÉBUT collection=%s url=%s points=%s",
                    settings.qdrant_collection,
                    settings.qdrant_url,
                    len(embeddable),
                )
                client = ensure_collection()
                upsert_chunks(
                    client=client,
                    tenant_id=doc.tenant_id,
                    document_id=doc.id,
                    doc_role=doc.doc_role,
                    chunks=embeddable,
                    vectors=vectors,
                )
                log.info("[F] QDRANT FIN — vecteurs stockés")

            doc.ocr_used = parsed.ocr_used
            doc.ocr_confidence = parsed.ocr_confidence
            doc.page_count = parsed.page_count
            doc.status = "ready"
            doc.ingest_error = None
            doc.updated_at = datetime.now(UTC)
            await session.commit()
            log.info("STATUT → ready (ingest terminé) document_id=%s fichier=%s", document_id, doc.filename)
        except Exception as exc:
            await session.rollback()
            doc = await session.get(Document, UUID(document_id))
            err = f"{type(exc).__name__}: {exc}"
            if doc is not None:
                doc.status = "failed"
                doc.ingest_error = err[:4000]
                doc.updated_at = datetime.now(UTC)
                await session.commit()
                log.error("STATUT → failed document_id=%s", document_id)
            log.exception("======== INGEST ÉCHEC (arrêté) document_id=%s : %s ========", document_id, err)
            return f"failed:{document_id}"
        finally:
            Path(tmp.name).unlink(missing_ok=True)

    log.info("[G] FILE GRAPHE DÉBUT extract_graph document_id=%s", document_id)
    await ctx["redis"].enqueue_job("extract_graph", document_id)
    log.info("[G] FILE GRAPHE FIN — job Neo4j/Ollama en file")
    log.info("======== INGEST ENCHAÎNÉ VERS GRAPHE document_id=%s ========", document_id)
    return f"ready:{document_id}"


def _embed_text(draft, doc_type: str | None) -> str:
    head = f"[{doc_type or 'doc'}] [{draft.heading_path or ''}] [p.{draft.page or '?'}]\n"
    return head + draft.text
