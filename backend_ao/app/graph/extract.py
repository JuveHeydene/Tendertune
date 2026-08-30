"""Job extract_graph : chunks parents → Ollama JSON → MERGE Neo4j (+ fuzzy match)."""

from __future__ import annotations

import json
import logging
import urllib.request
from datetime import UTC, datetime
from uuid import UUID

from neo4j import GraphDatabase
from sqlalchemy import select

from app.config import get_settings
from app.graph.entity_match import EntityMatchIndex, norm_name, resolve_entity_key
from app.models.sql import ChunkRow, Document
from app.services.db_client import session_factory

log = logging.getLogger("btp.graph")

ENTITY_TYPES = (
    "ENTREPRISE",
    "PROJET",
    "CLIENT",
    "CERTIFICATION",
    "PERSONNE",
    "EXIGENCE",
    "LOT",
    "SITE",
)
REL_TYPES = (
    "A_TRAVAILLE_SUR",
    "PORTE",
    "CONCERNE",
    "SITUE_A",
    "SATISFAITE_PAR",
    "CONTIENT",
)

PROMPT = """Tu extraies des entités BTP depuis le texte.
Types d'entités autorisés uniquement : {types}
Types de relations autorisés uniquement : {rels}
Pour les relations, réutilise autant que possible les noms EXACTS des entités listées.
Réponds UNIQUEMENT en JSON :
{{"entities":[{{"type":"PROJET","name":"..."}}],"relations":[{{"type":"CONCERNE","from":"...","to":"..."}}]}}
Pas d'entité si rien de clair. Texte :
"""


def _ollama_json(text: str) -> dict:
    s = get_settings()
    prompt = (
        PROMPT.format(types=", ".join(ENTITY_TYPES), rels=", ".join(REL_TYPES))
        + text[:3500]
    )
    payload = json.dumps(
        {"model": s.llm_model, "prompt": prompt, "stream": False, "format": "json"}
    ).encode()
    req = urllib.request.Request(
        f"{s.ollama_base_url.rstrip('/')}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        raw = json.loads(resp.read().decode())
    body = raw.get("response") or "{}"
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return {"entities": [], "relations": []}


def _driver():
    s = get_settings()
    return GraphDatabase.driver(s.neo4j_uri, auth=(s.neo4j_user, s.neo4j_password))


def _ensure_indexes(driver) -> None:
    with driver.session() as neo:
        neo.run(
            "CREATE CONSTRAINT entity_key IF NOT EXISTS "
            "FOR (e:Entity) REQUIRE e.key IS UNIQUE"
        )


def _load_tenant_index(neo, tenant_id: UUID) -> EntityMatchIndex:
    """Charge les entités déjà en Neo4j pour le tenant (rapprochement inter-docs)."""
    index = EntityMatchIndex(use_embeddings=True)
    rows = neo.run(
        "MATCH (e:Entity {tenant_id: $tenant_id}) RETURN e.key AS key, e.name AS name, e.type AS type",
        tenant_id=str(tenant_id),
    )
    n = 0
    for rec in rows:
        name = rec.get("name") or ""
        key = rec.get("key") or ""
        if name and key:
            index.add(name, key)
            n += 1
    log.info("GRAPH fuzzy : %s entités tenant déjà en Neo4j", n)
    return index


def _canonical_key(
    index: EntityMatchIndex,
    *,
    tenant_id: UUID,
    etype: str,
    name: str,
) -> str:
    """Réutilise une clé existante (fuzzy) ou crée tenant:TYPE:nom_norm."""
    hit = index.resolve(name)
    if hit is not None:
        # Ne rattacher que si le type dans la clé correspond (évite ENTREPRISE↔PROJET)
        if f":{etype}:" in hit.key:
            if hit.method != "exact":
                log.info(
                    "GRAPH entity fuzzy %s score=%.1f  %r → %s",
                    hit.method,
                    hit.score,
                    name,
                    hit.key,
                )
            return hit.key
    return f"{tenant_id}:{etype}:{norm_name(name)}"


async def extract_graph(ctx: dict, document_id: str) -> str:
    log.info("======== GRAPH DÉBUT document_id=%s ========", document_id)
    factory = session_factory()
    async with factory() as session:
        doc = await session.get(Document, UUID(document_id))
        if doc is None or doc.status != "ready":
            log.warning("GRAPH STOP — doc absent ou pas ready (statut ≠ ready) id=%s", document_id)
            return f"skip:{document_id}"
        if doc.graph_extracted:
            log.info("GRAPH déjà extrait — rien à faire id=%s", document_id)
            return f"already:{document_id}"
        parents = (
            await session.execute(
                select(ChunkRow).where(
                    ChunkRow.document_id == doc.id,
                    ChunkRow.parent_id.is_(None),
                )
            )
        ).scalars().all()

        to_do = parents[:12]
        log.info(
            "GRAPH Ollama+Neo4j : %s parents en base, on traite %s, llm=%s",
            len(parents),
            len(to_do),
            get_settings().llm_model,
        )
        driver = None
        try:
            driver = _driver()
            _ensure_indexes(driver)
            log.info("GRAPH Neo4j : contrainte Entity.key OK")
            n_ent = 0
            n_rel = 0
            n_rel_dropped = 0
            with driver.session() as neo:
                index = _load_tenant_index(neo, doc.tenant_id)
                for i, chunk in enumerate(to_do, start=1):
                    extra = dict(chunk.extra or {})
                    try:
                        log.info("GRAPH Ollama DÉBUT chunk %s/%s id=%s", i, len(to_do), chunk.id)
                        data = _ollama_json(chunk.text)
                        log.info(
                            "GRAPH Ollama FIN chunk %s/%s entités_brutes=%s relations_brutes=%s",
                            i,
                            len(to_do),
                            len(data.get("entities") or []),
                            len(data.get("relations") or []),
                        )
                    except Exception as exc:
                        extra["graph_extract_failed"] = str(exc)[:300]
                        chunk.extra = extra
                        log.exception("GRAPH Ollama ÉCHEC chunk %s/%s id=%s : %s", i, len(to_do), chunk.id, exc)
                        continue
                    entities = data.get("entities") or []
                    relations = data.get("relations") or []
                    chunk_index = EntityMatchIndex(use_embeddings=True)
                    # pré-remplir avec le patrimoine tenant (variantes inter-docs)
                    for cand_name, key in index.candidates:
                        chunk_index.add(cand_name, key)
                    for ent in entities:
                        etype = str(ent.get("type", "")).upper()
                        name = str(ent.get("name", "")).strip()
                        if etype not in ENTITY_TYPES or not name:
                            continue
                        key = _canonical_key(
                            index,
                            tenant_id=doc.tenant_id,
                            etype=etype,
                            name=name,
                        )
                        index.add(name, key)
                        chunk_index.add(name, key)
                        neo.run(
                            "MERGE (e:Entity {key: $key}) "
                            "SET e.name = coalesce(e.name, $name), e.type = $type, e.tenant_id = $tenant_id",
                            key=key,
                            name=name,
                            type=etype,
                            tenant_id=str(doc.tenant_id),
                        )
                        n_ent += 1
                    for rel in relations:
                        rtype = str(rel.get("type", "")).upper()
                        if rtype not in REL_TYPES:
                            continue
                        src_raw = str(rel.get("from", "")).strip()
                        dst_raw = str(rel.get("to", "")).strip()
                        src = resolve_entity_key(chunk_index, src_raw)
                        dst = resolve_entity_key(chunk_index, dst_raw)
                        if not src or not dst:
                            n_rel_dropped += 1
                            log.info(
                                "GRAPH relation droppée (pas de match fuzzy) type=%s from=%r to=%r",
                                rtype,
                                src_raw,
                                dst_raw,
                            )
                            continue
                        neo.run(
                            "MATCH (a:Entity {key: $src}), (b:Entity {key: $dst}) "
                            "MERGE (a)-[r:REL {type: $type}]->(b) "
                            "SET r.source_chunk_id = $chunk_id",
                            src=src,
                            dst=dst,
                            type=rtype,
                            chunk_id=str(chunk.id),
                        )
                        n_rel += 1
                    log.info(
                        "GRAPH Neo4j MERGE chunk %s/%s — totaux cumulés entités=%s relations=%s droppées=%s",
                        i,
                        len(to_do),
                        n_ent,
                        n_rel,
                        n_rel_dropped,
                    )
            doc.graph_extracted = True
            doc.updated_at = datetime.now(UTC)
            await session.commit()
            log.info(
                "======== GRAPH FINI document_id=%s graph_extracted=true MERGE entités=%s relations=%s droppées=%s ========",
                document_id,
                n_ent,
                n_rel,
                n_rel_dropped,
            )
        except Exception as exc:
            log.exception("======== GRAPH ÉCHEC document_id=%s : %s ========", document_id, exc)
            return f"graph_failed:{document_id}"
        finally:
            try:
                if driver is not None:
                    driver.close()
            except Exception:
                pass
    return f"graph:{document_id}"
