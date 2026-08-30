"""Expert Graphe — Diagramme 4, §4.7. Active enfin la lecture de Neo4j en
horloge B (écrit en A par extract_graph, jamais lu en B jusqu'ici).

Procédure : LLM extrait les entités de la question (même famille que
l'extraction d'ingestion) → fuzzy_resolve_entity (RÉUTILISE entity_match.py,
outil partagé horloge A/B) → templates Cypher fixes (jamais de Cypher
généré librement) → chunks source pour la citation.
"""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.graph.cypher import BOUNDED_TWO_HOP, CONFORMITE_REL_TYPES, ONE_HOP
from app.graph.entity_match import EntityMatchIndex
from app.graph.extract import ENTITY_TYPES, load_tenant_index, neo4j_driver
from app.models.pydantic import Expert, ExtraitCite, ResultatExpert, SourceContexte
from app.models.sql import ChunkRow
from app.services.ollama_llm import ollama_generate_json

log = logging.getLogger("btp.graph_expert")

_EXTRACT_PROMPT = """Tu extraies les entités mentionnées dans une question,
pour chercher leurs relations dans un graphe de connaissances BTP.
Types d'entités autorisés uniquement : {types}
Réponds UNIQUEMENT en JSON :
{{"entities":[{{"type":"...","name":"..."}}]}}
Pas d'entité si rien de clair. Question :
{query}
"""


async def _extract_query_entities(query: str) -> list[dict]:
    prompt = _EXTRACT_PROMPT.format(types=", ".join(ENTITY_TYPES), query=query)
    try:
        body = await asyncio.to_thread(ollama_generate_json, prompt, timeout=60)
    except Exception as exc:
        log.warning("graph_expert — extraction d'entités échouée : %s", exc)
        return []
    entities = body.get("entities") or []
    return [e for e in entities if str(e.get("type", "")).upper() in ENTITY_TYPES and e.get("name")]


async def run_graph_expert(
    session: AsyncSession,
    query: str,
    *,
    tenant_id: UUID,
) -> ResultatExpert:
    entities = await _extract_query_entities(query)
    if not entities:
        return ResultatExpert(
            expert=Expert.graphe,
            source=SourceContexte.abstention,
            raison_abstention="Aucune entité identifiable dans la question.",
            tentatives=1,
        )

    def _resolve_and_query() -> tuple[list[dict], list[str]]:
        driver = neo4j_driver()
        try:
            with driver.session() as neo:
                index: EntityMatchIndex = load_tenant_index(neo, tenant_id)
                resolved_keys: list[str] = []
                for ent in entities:
                    hit = index.resolve(str(ent["name"]))
                    if hit is not None:
                        resolved_keys.append(hit.key)
                if not resolved_keys:
                    return [], []

                records: list[dict] = []
                if len(resolved_keys) >= 2:
                    key1, key2 = resolved_keys[0], resolved_keys[1]
                    from app.graph.cypher import TWO_ANCHORS

                    for rec in neo.run(TWO_ANCHORS, key1=key1, key2=key2):
                        records.append(dict(rec))
                if not records:
                    for key in resolved_keys:
                        for rec in neo.run(
                            BOUNDED_TWO_HOP, key=key, rel_types=CONFORMITE_REL_TYPES
                        ):
                            records.append(dict(rec))
                        if not records:
                            for rec in neo.run(ONE_HOP, key=key):
                                records.append(dict(rec))
                return records, resolved_keys
        finally:
            driver.close()

    try:
        records, resolved_keys = await asyncio.to_thread(_resolve_and_query)
    except Exception as exc:
        log.warning("graph_expert — Neo4j indisponible : %s", exc)
        return ResultatExpert(
            expert=Expert.graphe, source=SourceContexte.abstention,
            raison_abstention=f"Erreur graphe : {exc}", tentatives=1,
        )

    if not resolved_keys:
        return ResultatExpert(
            expert=Expert.graphe,
            source=SourceContexte.abstention,
            raison_abstention="Aucune entité de la question n'a pu être résolue dans le graphe.",
            tentatives=1,
        )
    if not records:
        return ResultatExpert(
            expert=Expert.graphe,
            source=SourceContexte.abstention,
            raison_abstention="Entités résolues mais aucune relation trouvée (1-2 sauts).",
            tentatives=1,
        )

    # Traçabilité obligatoire : un fait de graphe ne se cite jamais sans le
    # chunk texte qui le prouve (source_chunk_id, écrit à l'extraction, §3).
    chunk_ids: set[str] = set()
    for rec in records:
        for key in ("source_chunk_id", "source_chunk_ids"):
            val = rec.get(key)
            if isinstance(val, list):
                chunk_ids.update(v for v in val if v)
            elif val:
                chunk_ids.add(val)

    chunks: list[ExtraitCite] = []
    if chunk_ids:
        rows = (
            await session.execute(select(ChunkRow).where(ChunkRow.id.in_(list(chunk_ids)[:25])))
        ).scalars().all()
        chunks = [
            ExtraitCite(chunk_id=str(r.id), score=1.0, page=r.page, texte=r.text, heading_path=r.heading_path)
            for r in rows
        ]

    return ResultatExpert(
        expert=Expert.graphe,
        source=SourceContexte.retrieval,
        chunks=chunks,
        relations_graphe=records,
        tentatives=1,
    )
