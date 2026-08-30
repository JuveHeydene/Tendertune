"""Pipeline chat : route, retrieve, génération (sync + stream)."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.models.pydantic import Intent
from app.models.sql import Conversation, Message, User
from app.services.chat_history import format_history
from app.services.dossier_workflow import ensure_dossier, export_document, save_generation
from app.services.ollama_llm import ollama_generate_stream
from app.workflow.agentic_pipeline import run_agentic_retrieval
from app.workflow.graph import compiled_graph
from app.workflow.nodes.generate_section import generate_section, section_to_markdown
from app.workflow.nodes.route import route as route_node
from app.workflow.nodes.retrieve import retrieve as retrieve_node
from app.workflow.sections import DEFAULT_OUTLINE, archetype_for_key, pick_section

log = logging.getLogger("btp.chat")

WRITE_ROLES = {"admin", "manager", "redacteur"}


def can_write(user: User) -> bool:
    return user.role in WRITE_ROLES


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def _message_history(conv: Conversation) -> list[dict]:
    msgs = sorted(conv.messages or [], key=lambda m: m.created_at)
    return [{"role": m.role, "content": m.content, "meta": m.meta or {}} for m in msgs]


def _run_graph(query: str, tenant_id: UUID, history: list[dict] | None = None) -> dict:
    log.info("horloge B DÉBUT query_car=%s history=%s", len(query), len(history or []))
    result = compiled_graph().invoke(
        {
            "query": query,
            "tenant_id": str(tenant_id),
            "messages": [{"role": "user", "content": query}],
            "history": history or [],
        }
    )
    log.info("horloge B FIN intent=%s", result.get("intent"))
    return result


def _route_retrieve(query: str, tenant_id: UUID, history: list[dict] | None = None) -> dict:
    state: dict = {
        "query": query,
        "tenant_id": str(tenant_id),
        "messages": [{"role": "user", "content": query}],
        "history": history or [],
    }
    state = route_node(state)
    intent = state.get("intent") or "hybrid_rag"
    if intent == "run_section":
        from app.workflow.sections import pick_section

        key, title, all_flag = pick_section(query)
        state["section_key"] = key
        state["section_title"] = title
        state["generate_all"] = all_flag
    if intent in ("hybrid_rag", "run_section"):
        state = retrieve_node(state)
    return state


async def _iter_ollama_tokens(prompt: str) -> AsyncIterator[str]:
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[tuple[str, str | None]] = asyncio.Queue()

    def worker() -> None:
        try:
            for token in ollama_generate_stream(prompt):
                loop.call_soon_threadsafe(queue.put_nowait, ("token", token))
            loop.call_soon_threadsafe(queue.put_nowait, ("done", None))
        except Exception as exc:
            loop.call_soon_threadsafe(queue.put_nowait, ("error", str(exc)))

    threading.Thread(target=worker, daemon=True).start()
    while True:
        kind, payload = await queue.get()
        if kind == "done":
            break
        if kind == "error":
            raise RuntimeError(payload or "Ollama stream échec")
        if payload:
            yield payload


def _short_reply(intent: str, *, section_title: str | None = None, export_fmt: str | None = None) -> str:
    if intent == "run_section" and section_title:
        return f"Section « {section_title} » rédigée."
    if intent == "export" and export_fmt:
        return f"Document exporté en {export_fmt.upper()}."
    if intent == "smalltalk":
        return (
            "Bonjour. Posez une question sur le patrimoine, demandez de rédiger une section "
            "ou exportez le document."
        )
    return "Voici ma réponse :"


def _chunk_text(text: str, size: int = 120) -> list[str]:
    """Découpe un texte déjà généré en morceaux pour l'émission SSE `token`.
    Pas un vrai streaming Ollama token-par-token (impossible ici : la sortie
    JSON contrainte doit être complète et validée avant tout affichage,
    §10/§1 étape 9) — juste une émission progressive plutôt qu'un seul bloc,
    sans délai artificiel (aucun bénéfice réel à ralentir la réponse)."""
    if not text:
        return []
    words = text.split(" ")
    out: list[str] = []
    buf = ""
    for w in words:
        candidate = f"{buf} {w}".strip()
        if len(candidate) > size and buf:
            out.append(buf + " ")
            buf = w
        else:
            buf = candidate
    if buf:
        out.append(buf)
    return out


async def _persist_section_v2(
    session: AsyncSession,
    conv: Conversation,
    user: User,
    *,
    section_key: str,
    section_title: str,
    section,  # SectionGeneree
    citations: list,
    context_snapshot: dict,
) -> UUID | None:
    """Persistance V2 : contenu structuré complet (blocs, abstentions), pas
    seulement un pavé de texte — §1 étape 8/9."""
    if not can_write(user):
        return None
    doss = await ensure_dossier(session, conv, user)
    model = get_settings().llm_model
    rendered = section_to_markdown(section)
    gen = await save_generation(
        session,
        dossier=doss,
        section_key=section_key,
        title=section_title,
        texte=rendered,
        citations=citations,
        model=model,
        content={**section.model_dump(), "texte": rendered},
        context_snapshot=context_snapshot,
        exigences_couvertes=section.exigences_couvertes,
    )
    return gen.id


async def _persist_sections(
    session: AsyncSession,
    conv: Conversation,
    user: User,
    state: dict,
    *,
    section_texts: dict[str, str] | None = None,
) -> UUID | None:
    if not can_write(user):
        return None
    doss = await ensure_dossier(session, conv, user)
    citations = [
        {"chunk_id": h.get("chunk_id"), "page": h.get("page")}
        for h in (state.get("retrieved") or [])[:8]
    ]
    model = get_settings().llm_model
    section_texts = section_texts or {}
    key = state.get("section_key") or "notes_travail"
    title = state.get("section_title") or "Notes de travail"
    texte = section_texts.get(key) or state.get("answer") or ""
    gen = await save_generation(
        session,
        dossier=doss,
        section_key=key,
        title=title,
        texte=texte,
        citations=citations,
        model=model,
    )
    if state.get("generate_all"):
        done = {key}
        for sk, _lvl, stitle in DEFAULT_OUTLINE:
            if sk in done:
                continue
            if sk in section_texts:
                await save_generation(
                    session,
                    dossier=doss,
                    section_key=sk,
                    title=stitle,
                    texte=section_texts[sk],
                    citations=citations,
                    model=model,
                )
                continue
            from app.workflow.nodes.generate import generate as generate_node

            extra = await asyncio.to_thread(
                generate_node,
                {**state, "intent": "run_section", "query": f"Rédige la section : {stitle}"},
            )
            await save_generation(
                session,
                dossier=doss,
                section_key=extra.get("section_key") or sk,
                title=extra.get("section_title") or stitle,
                texte=extra.get("answer") or "",
                citations=citations,
                model=model,
            )
    return gen.id


async def process_message_sync(
    session: AsyncSession,
    conv: Conversation,
    user: User,
    text: str,
) -> tuple[str, dict, UUID | None]:
    """Retourne (réponse courte chat, meta, generation_id)."""
    history = _message_history(conv)
    try:
        state = await asyncio.to_thread(_run_graph, text, user.tenant_id, history)
    except Exception as exc:
        log.exception("horloge B échec")
        return f"Erreur : {exc}", {"intent": "error"}, None

    intent = state.get("intent") or "hybrid_rag"
    meta: dict = {
        "intent": intent,
        "citations": state.get("citations") or [],
        "markdown": state.get("answer") or "",
    }
    generation_id = None

    if intent == "export":
        if not can_write(user):
            return "Export réservé au rédacteur, manager ou admin.", meta, None
        fmt = "docx"
        lowered = text.lower()
        for candidate in ("pdf", "markdown", "md", "txt", "text", "docx"):
            if candidate in lowered:
                if candidate in ("markdown", "md"):
                    fmt = "md"
                elif candidate in ("text", "txt"):
                    fmt = "txt"
                else:
                    fmt = candidate if candidate != "markdown" else "md"
                break
        doss = await ensure_dossier(session, conv, user)
        msgs = sorted(conv.messages or [], key=lambda m: m.created_at)
        notes = "\n\n".join(f"{m.role}: {m.content}" for m in msgs[-12:])
        rec, _ = await export_document(session, dossier=doss, user=user, fmt=fmt, transcript=notes)
        meta["export"] = True
        meta["format"] = fmt
        return _short_reply("export", export_fmt=fmt) + f" (v{rec.version})", meta, None

    if intent == "run_section":
        if not can_write(user):
            return (
                "Rédaction réservée au rédacteur, manager ou admin.",
                meta,
                None,
            )
        generation_id = await _persist_sections(session, conv, user, state)
        meta["generation_id"] = str(generation_id) if generation_id else None
        meta["section_key"] = state.get("section_key")
        meta["section_title"] = state.get("section_title")
        if state.get("generate_all"):
            return (
                "Mémoire complet rédigé.",
                meta,
                generation_id,
            )
        return _short_reply("run_section", section_title=state.get("section_title")), meta, generation_id

    if intent == "smalltalk":
        meta["markdown"] = state.get("answer") or _short_reply("smalltalk")
        return _short_reply("smalltalk"), meta, None

    return _short_reply("hybrid_rag"), meta, None


async def stream_message(
    session: AsyncSession,
    conv: Conversation,
    user: User,
    text: str,
) -> AsyncIterator[str]:
    """Chemin SSE V2 : rewrite → Superviseur → experts/CRAG (§5) → agrégation
    (§5.4) → génération (§10). Remplace le route/retrieve mots-clés par le
    pipeline agentique — voir Nouvelle_Architecture/diagrammes_sequence_v2.txt
    Diagramme 2 pour la séquence complète."""
    history = _message_history(conv)
    user_msg = Message(conversation_id=conv.id, role="user", content=text)
    session.add(user_msg)
    await session.flush()
    yield _sse("user", {"content": text})

    try:
        query_clean, superviseur_output, aggregated = await run_agentic_retrieval(
            text,
            history,
            tenant_id=user.tenant_id,
            dossier_id=conv.dossier_id,
            message_id=user_msg.id,
        )
    except Exception as exc:
        log.exception("pipeline agentique échec")
        yield _sse("error", {"message": str(exc)})
        return

    intent = superviseur_output.intent.value
    yield _sse("intent", {"intent": intent})
    user_msg.meta = {
        **(user_msg.meta or {}),
        "query_clean": query_clean,
        "superviseur": superviseur_output.model_dump(mode="json"),
    }

    if intent == "smalltalk":
        md = (
            "Bonjour. Posez une question sur le patrimoine, demandez de rédiger une section "
            "ou exportez le document."
        )
        yield _sse("token", {"t": md})
        yield _sse("preview", {"markdown": md})
        session.add(
            Message(
                conversation_id=conv.id, role="assistant", content=_short_reply("smalltalk"),
                meta={"intent": intent, "markdown": md},
            )
        )
        conv.updated_at = datetime.now(UTC)
        if conv.title == "Nouvelle conversation":
            conv.title = text[:80]
        await session.commit()
        yield _sse("done", {"ok": True})
        return

    if intent == "clarification_needed":
        msg = superviseur_output.message_clarification or "Pouvez-vous préciser votre demande ?"
        yield _sse("token", {"t": msg})
        yield _sse("preview", {"markdown": msg})
        session.add(
            Message(conversation_id=conv.id, role="assistant", content=msg, meta={"intent": intent})
        )
        conv.updated_at = datetime.now(UTC)
        await session.commit()
        yield _sse("done", {"ok": True})
        return

    if intent == "export":
        fmt = "docx"
        lowered = text.lower()
        for candidate in ("pdf", "markdown", "md", "txt", "text", "docx"):
            if candidate in lowered:
                fmt = "md" if candidate in ("markdown", "md") else ("txt" if candidate in ("text", "txt") else candidate)
                break
        if not can_write(user):
            yield _sse("error", {"message": "Export réservé au rédacteur, manager ou admin."})
            return
        try:
            doss = await ensure_dossier(session, conv, user)
            msgs = sorted(conv.messages or [], key=lambda m: m.created_at)
            notes = "\n\n".join(f"{m.role}: {m.content}" for m in msgs[-12:])
            rec, _ = await export_document(session, dossier=doss, user=user, fmt=fmt, transcript=notes)
            msg = _short_reply("export", export_fmt=fmt) + f" (v{rec.version})"
            session.add(
                Message(
                    conversation_id=conv.id, role="assistant", content=msg,
                    meta={"intent": "export", "export": True, "format": fmt, "version": rec.version},
                )
            )
            conv.updated_at = datetime.now(UTC)
            await session.commit()
            yield _sse("export_ready", {"format": fmt, "dossier_id": str(doss.id), "version": rec.version})
            yield _sse("done", {"ok": True, "message": msg})
        except Exception as exc:
            log.exception("export stream échec")
            yield _sse("error", {"message": str(exc)})
        return

    if intent == "run_section" and not can_write(user):
        msg = "Rédaction réservée au rédacteur, manager ou admin."
        session.add(Message(conversation_id=conv.id, role="assistant", content=msg, meta={"intent": intent}))
        await session.commit()
        yield _sse("error", {"message": msg})
        return

    # ------------------------------------------------------------------
    # hybrid_rag : réponse conversationnelle, streaming réel token-par-token
    # (pas de contrat JSON à valider ici — rien n'empêche le vrai streaming
    # Ollama, contrairement à run_section ci-dessous).
    # ------------------------------------------------------------------
    if intent == Intent.hybrid_rag.value:
        yield _sse("section_start", {"key": "__chat__", "title": "Réponse"})
        history_block = format_history(history)
        prompt = (
            "Tu es un assistant BTP pour préparer un dossier d'appel d'offres. Français.\n"
            "Réponds en Markdown, pas de titre H1. Pas d'invention de montants, SIRET ou dates.\n"
            "Utilise UNIQUEMENT les extraits numérotés. Cite [1], [2]... quand tu t'appuies dessus.\n"
            "Si les extraits ne suffisent pas, dis-le explicitement plutôt que d'inventer.\n"
            f"{history_block}"
            f"Question :\n{query_clean}\n\nExtraits :\n{aggregated.context_text}\n\nRéponse Markdown :"
        )
        buf: list[str] = []
        try:
            async for token in _iter_ollama_tokens(prompt):
                buf.append(token)
                yield _sse("token", {"t": token, "section_key": "__chat__"})
        except Exception as exc:
            yield _sse("error", {"message": str(exc)})
            return
        md = "".join(buf)
        yield _sse("section_end", {"key": "__chat__", "title": "Réponse", "markdown": md})
        yield _sse("preview", {"markdown": md})

        chat_msg = _short_reply("hybrid_rag")
        meta = {
            "intent": intent,
            "markdown": md,
            "citations": [{"chunk_id": c} for c in aggregated.citations[:8]],
            "abstentions": aggregated.abstentions,
            "experts_par_citation": aggregated.experts_par_citation,
        }
        session.add(Message(conversation_id=conv.id, role="assistant", content=chat_msg, meta=meta))
        conv.updated_at = datetime.now(UTC)
        if conv.title == "Nouvelle conversation":
            conv.title = text[:80]
        await session.commit()
        yield _sse("done", {"ok": True, "message": chat_msg})
        return

    # ------------------------------------------------------------------
    # run_section : génération JSON contrainte (§10), pas de streaming
    # token-par-token réel — la sortie doit être complète et validée avant
    # tout affichage (retry borné à 2 essais si invalide, §1 étape 9).
    # ------------------------------------------------------------------
    generate_all = any(
        w in query_clean.lower()
        for w in ("tout le mémoire", "tout le memoire", "toutes les sections", "le mémoire complet")
    )
    if generate_all:
        sections_to_run = [(k, t) for k, _lvl, t in DEFAULT_OUTLINE]
    else:
        key, title, _all_flag = pick_section(query_clean)
        sections_to_run = [(key, title)]

    preview_parts: list[str] = []
    last_generation_id: UUID | None = None
    last_section_key = sections_to_run[0][0]
    last_section_title = sections_to_run[0][1]

    for sk, stitle in sections_to_run:
        yield _sse("section_start", {"key": sk, "title": stitle})

        if sk == sections_to_run[0][0] and not generate_all:
            # Réutilise le contexte déjà agrégé pour la demande initiale.
            section_aggregated = aggregated
        else:
            # §9 / §5.5 : chaque section mérite sa PROPRE recherche — ne pas
            # réutiliser aveuglément le contexte d'une autre section.
            _q, _sup, section_aggregated = await run_agentic_retrieval(
                f"Rédige la section : {stitle}", history,
                tenant_id=user.tenant_id, dossier_id=conv.dossier_id, message_id=user_msg.id,
            )
            section_aggregated = section_aggregated or aggregated

        section = await generate_section(
            section_key=sk,
            titre=stitle,
            archetype=archetype_for_key(sk),
            aggregated=section_aggregated,
            history=history,
        )
        md = section_to_markdown(section)
        for piece in _chunk_text(md):
            yield _sse("token", {"t": piece, "section_key": sk})
        preview_parts.append(f"## {stitle}\n\n{md}")
        yield _sse("section_end", {"key": sk, "title": stitle, "markdown": md})

        last_generation_id = await _persist_section_v2(
            session, conv, user,
            section_key=sk, section_title=stitle, section=section,
            citations=section.citations,
            context_snapshot={"extraits": section_aggregated.context_text[:20000]},
        )
        last_section_key, last_section_title = sk, stitle

    full_preview = "\n\n---\n\n".join(preview_parts)
    yield _sse("preview", {"markdown": full_preview})

    chat_msg = (
        "Mémoire complet rédigé." if generate_all
        else _short_reply("run_section", section_title=last_section_title)
    )
    meta = {
        "intent": intent,
        "markdown": full_preview,
        "generation_id": str(last_generation_id) if last_generation_id else None,
        "section_key": last_section_key,
        "section_title": last_section_title,
        "abstentions": aggregated.abstentions if aggregated else [],
    }
    session.add(
        Message(
            conversation_id=conv.id, role="assistant", content=chat_msg,
            generation_id=last_generation_id, meta=meta,
        )
    )
    conv.updated_at = datetime.now(UTC)
    if conv.title == "Nouvelle conversation":
        conv.title = text[:80]
    await session.commit()
    yield _sse("done", {"ok": True, "message": chat_msg})
