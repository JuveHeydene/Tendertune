"""Job ARQ ingest_document : MinIO → parse → chunks Postgres → Qdrant → enqueue graphe."""

from __future__ import annotations

import asyncio
import logging
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from app.config import get_settings
from app.ingest.chunk import chunk_document
from app.ingest.classify_section import classify_section_type_heuristic, classify_section_type_llm
from app.ingest.index_qdrant import delete_by_document, embed_texts, ensure_collection, upsert_chunks
from app.ingest.parse import parse_file
from app.models.sql import ChunkRow, Document
from app.services.db_client import session_factory
from app.services.minio_client import get_minio
from app.services.pipeline_stages import mark_failed_stage
from app.services.pipeline_stages import mark_stage as _mark_stage

log = logging.getLogger("btp.ingest")

# Plafond d'appels LLM de repli pour la classification section_type (§3.1) —
# signal doux, une classification manquée est tolérée (auto-correction en
# boucle CRAG). Sans plafond, un DAO de centaines de pages sans mots-clés
# canoniques dans les titres enchaîne autant d'appels LLM séquentiels
# bloquants, potentiellement des heures.
MAX_LLM_CLASSIFICATIONS_PER_DOC = 40


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
        main_loop = asyncio.get_running_loop()
        resume_progress = dict(doc.ocr_progress or {})
        doc_id = doc.id

        def _persist_ocr_page(page_num: int, text: str, confidence: float | None) -> None:
            """Rappelée depuis le thread d'OCR (asyncio.to_thread) après CHAQUE
            page — persiste tout de suite plutôt qu'en mémoire, pour qu'une
            page déjà traitée ne soit jamais refaite après une interruption
            (timeout de tâche sur un gros scan, crash worker)."""

            async def _do() -> None:
                async with factory() as page_session:
                    page_doc = await page_session.get(Document, doc_id)
                    if page_doc is None:
                        return
                    progress = dict(page_doc.ocr_progress or {})
                    pages = dict(progress.get("pages") or {})
                    pages[str(page_num)] = {"text": text, "confidence": confidence}
                    progress["pages"] = pages
                    progress["resume_page"] = page_num
                    page_doc.ocr_progress = progress
                    flag_modified(page_doc, "ocr_progress")
                    page_doc.updated_at = datetime.now(UTC)
                    await page_session.commit()

            try:
                asyncio.run_coroutine_threadsafe(_do(), main_loop).result(timeout=20)
            except Exception:
                log.exception("progression OCR non persistée pour la page %s (document=%s)", page_num, doc_id)

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

            log.info(
                "[B] PARSE DÉBUT fichier=%s mime=%s reprise=%s pages déjà connues",
                doc.filename,
                doc.mime_type,
                len((resume_progress.get("pages") or {})),
            )
            _mark_stage(doc, "parse", started=True)
            await session.commit()
            # Bloquant (OCR : plusieurs minutes sur un gros scan) — dans un
            # thread pour ne pas geler la boucle asyncio du worker (autres
            # tâches, battements de vie ARQ) pendant toute la durée du parse.
            parsed = await asyncio.to_thread(
                parse_file,
                tmp.name,
                doc.filename,
                doc.mime_type,
                resume_progress=resume_progress,
                on_page_done=_persist_ocr_page,
            )
            n_chars = sum(len(p.text or "") for p in parsed.pages)
            log.info(
                "[B] PARSE FIN — parser=%s pages=%s ocr=%s confiance=%s caractères=%s — on passe au chunking",
                parsed.parser,
                parsed.page_count,
                parsed.ocr_used,
                parsed.ocr_confidence,
                n_chars,
            )
            _mark_stage(doc, "parse", finished=True)
            await session.commit()

            log.info("[C] CHUNKING DÉBUT")
            _mark_stage(doc, "chunk", started=True)
            drafts = chunk_document(parsed)
            n_parent = sum(1 for d in drafts if d.parent_id is None)
            n_child = len(drafts) - n_parent
            _mark_stage(doc, "chunk", finished=True)
            await session.commit()
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
            _mark_stage(doc, "classify", started=True)
            await session.commit()
            section_type_by_parent: dict = {}
            llm_calls_used = 0
            llm_skipped_cap = 0
            if doc.doc_role != "annexe":
                for d in drafts:
                    if d.parent_id is not None:
                        continue
                    heuristic = classify_section_type_heuristic(d.heading_path, d.text)
                    if heuristic is not None:
                        section_type_by_parent[d.id] = heuristic
                        d.extra = {**(d.extra or {}), "section_type_method": "heuristic"}
                        continue
                    if llm_calls_used >= MAX_LLM_CLASSIFICATIONS_PER_DOC:
                        # section_type est un signal DOUX (§3.1, jamais un filtre
                        # bloquant) : au-delà du plafond, on laisse vide plutôt que
                        # d'enchaîner des centaines d'appels LLM bloquants
                        # séquentiels sur un très gros document (observé : un DAO
                        # de 739 parents bloquait toute l'ingestion des heures).
                        section_type_by_parent[d.id] = None
                        d.extra = {**(d.extra or {}), "section_type_method": "skipped_cap"}
                        llm_skipped_cap += 1
                        continue
                    llm_calls_used += 1
                    value = await asyncio.to_thread(classify_section_type_llm, d.text)
                    section_type_by_parent[d.id] = value
                    d.extra = {**(d.extra or {}), "section_type_method": "llm" if value else "none"}
            n_classified = sum(1 for v in section_type_by_parent.values() if v)
            _mark_stage(doc, "classify", finished=True)
            await session.commit()
            log.info(
                "[C2] CLASSIFICATION FIN — %s/%s parents classés (%s appels LLM, %s ignorés au-delà du plafond de %s)",
                n_classified,
                len(section_type_by_parent),
                llm_calls_used,
                llm_skipped_cap,
                MAX_LLM_CLASSIFICATIONS_PER_DOC,
            )

            chunk_section_types: dict = {}
            for d in drafts:
                parent_key = d.id if d.parent_id is None else d.parent_id
                section_type_value = section_type_by_parent.get(parent_key)
                chunk_section_types[d.id] = section_type_value
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
                        section_type=section_type_value,
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
                _mark_stage(doc, "embed", started=True)
                await session.commit()
                log.info(
                    "[E] OLLAMA EMBEDDINGS DÉBUT model=%s url=%s n_textes=%s",
                    settings.embed_model,
                    settings.ollama_base_url,
                    len(embeddable),
                )
                vectors = await asyncio.to_thread(embed_texts, [_embed_text(d, doc.doc_type) for d in embeddable])
                _mark_stage(doc, "embed", finished=True)
                log.info(
                    "[E] OLLAMA EMBEDDINGS FIN — %s vecteurs dim=%s — on passe à Qdrant",
                    len(vectors),
                    len(vectors[0]) if vectors else 0,
                )

                _mark_stage(doc, "index", started=True)
                await session.commit()
                log.info(
                    "[F] QDRANT DÉBUT collection=%s url=%s points=%s",
                    settings.qdrant_collection,
                    settings.qdrant_url,
                    len(embeddable),
                )
                client = ensure_collection()
                # Purge les points d'une éventuelle tentative précédente AVANT
                # de réindexer : les chunks ont de nouveaux id à chaque parse
                # (chunk_document régénère des UUID), donc sans cette purge,
                # une ré-ingestion (relance manuelle, reprise après échec)
                # laissait les anciens vecteurs orphelins — contenu dupliqué
                # en recherche, jamais nettoyé.
                await asyncio.to_thread(delete_by_document, client, doc.id)
                await asyncio.to_thread(
                    upsert_chunks,
                    client=client,
                    tenant_id=doc.tenant_id,
                    document_id=doc.id,
                    doc_role=doc.doc_role,
                    chunks=embeddable,
                    vectors=vectors,
                    section_types=chunk_section_types,
                    dossier_id=doc.dossier_id,
                )
                _mark_stage(doc, "index", finished=True)
                log.info("[F] QDRANT FIN — vecteurs stockés")

            doc.ocr_used = parsed.ocr_used
            doc.ocr_confidence = parsed.ocr_confidence
            doc.page_count = parsed.page_count
            doc.status = "ready"
            doc.ingest_error = None
            # Reprise consommée : plus besoin une fois l'ingestion réussie.
            # flag_modified est indispensable ici : `doc` a été chargé en début
            # de job avec ocr_progress={} (cas normal, sans reprise), et les
            # pages OCR ont été persistées entre-temps via des sessions
            # séparées (_persist_ocr_page ci-dessus) sans jamais toucher cet
            # objet `doc`. Sans flag_modified, SQLAlchemy compare par valeur
            # ({} == {} en mémoire) et n'inclut PAS la colonne dans l'UPDATE,
            # laissant les pages OCR (écrites par les sessions séparées)
            # intactes en base malgré cette affectation.
            doc.ocr_progress = {}
            flag_modified(doc, "ocr_progress")
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
                # La phase en cours au moment du crash est celle avec un
                # started_at mais pas de finished_at (les phases précédentes
                # ont déjà survécu au rollback, committées au fur et à mesure).
                mark_failed_stage(doc, err)
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
