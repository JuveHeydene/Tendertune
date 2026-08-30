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
from app.models.sql import Conversation, Message, User
from app.services.chat_history import format_history
from app.services.dossier_workflow import ensure_dossier, export_document, save_generation
from app.services.ollama_llm import ollama_generate_stream
from app.workflow.graph import compiled_graph
from app.workflow.nodes.generate import build_prompt
from app.workflow.nodes.route import route as route_node
from app.workflow.nodes.retrieve import retrieve as retrieve_node
from app.workflow.sections import DEFAULT_OUTLINE

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
    history = _message_history(conv)
    user_msg = Message(conversation_id=conv.id, role="user", content=text)
    session.add(user_msg)
    await session.flush()
    yield _sse("user", {"content": text})

    try:
        state = await asyncio.to_thread(_route_retrieve, text, user.tenant_id, history)
    except Exception as exc:
        log.exception("route/retrieve échec")
        yield _sse("error", {"message": str(exc)})
        return

    intent = state.get("intent") or "hybrid_rag"
    yield _sse("intent", {"intent": intent})

    if intent == "smalltalk":
        from app.workflow.nodes.chitchat import chitchat

        out = chitchat(state)
        md = out.get("answer") or ""
        yield _sse("token", {"t": md})
        yield _sse("preview", {"markdown": md})
        assistant = Message(
            conversation_id=conv.id,
            role="assistant",
            content=_short_reply("smalltalk"),
            meta={"intent": intent, "markdown": md},
        )
        session.add(assistant)
        conv.updated_at = datetime.now(UTC)
        if conv.title == "Nouvelle conversation":
            conv.title = text[:80]
        await session.commit()
        yield _sse("done", {"ok": True})
        return

    if intent == "export":
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
        if not can_write(user):
            yield _sse("error", {"message": "Export réservé au rédacteur, manager ou admin."})
            return
        try:
            doss = await ensure_dossier(session, conv, user)
            msgs = sorted(conv.messages or [], key=lambda m: m.created_at)
            notes = "\n\n".join(f"{m.role}: {m.content}" for m in msgs[-12:])
            rec, _ = await export_document(
                session, dossier=doss, user=user, fmt=fmt, transcript=notes
            )
            msg = _short_reply("export", export_fmt=fmt) + f" (v{rec.version})"
            session.add(
                Message(
                    conversation_id=conv.id,
                    role="assistant",
                    content=msg,
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

    sections_to_run: list[tuple[str, str]] = []
    if intent == "run_section":
        if state.get("generate_all"):
            sections_to_run = [(k, t) for k, _l, t in DEFAULT_OUTLINE]
        else:
            sections_to_run = [(state["section_key"], state["section_title"])]
    else:
        sections_to_run = [("__chat__", "Réponse")]

    section_texts: dict[str, str] = {}
    preview_parts: list[str] = []

    for sk, stitle in sections_to_run:
        yield _sse("section_start", {"key": sk, "title": stitle})
        run_state = {**state, "intent": "run_section" if sk != "__chat__" else "hybrid_rag"}
        if sk != "__chat__":
            run_state["query"] = f"Rédige la section : {stitle}"
            run_state["section_key"] = sk
            run_state["section_title"] = stitle
        prompt, _extra = build_prompt(run_state)
        buf: list[str] = []
        try:
            async for token in _iter_ollama_tokens(prompt):
                buf.append(token)
                yield _sse("token", {"t": token, "section_key": sk})
        except Exception as exc:
            yield _sse("error", {"message": str(exc)})
            return
        md = "".join(buf)
        section_texts[sk] = md
        preview_parts.append(f"## {stitle}\n\n{md}" if sk != "__chat__" else md)
        yield _sse("section_end", {"key": sk, "title": stitle, "markdown": md})

    full_preview = "\n\n---\n\n".join(preview_parts)
    yield _sse("preview", {"markdown": full_preview})

    state["answer"] = section_texts.get(state.get("section_key") or "", full_preview)
    generation_id = None
    if intent == "run_section":
        state["section_key"] = sections_to_run[0][0]
        state["section_title"] = sections_to_run[0][1]
        if len(sections_to_run) > 1:
            state["generate_all"] = True
        generation_id = await _persist_sections(
            session, conv, user, state, section_texts={
                k: v for k, v in section_texts.items() if k != "__chat__"
            }
        )
        chat_msg = (
            "Mémoire complet rédigé."
            if state.get("generate_all")
            else _short_reply("run_section", section_title=sections_to_run[0][1])
        )
    else:
        chat_msg = _short_reply("hybrid_rag")
        state["citations"] = [
            {"chunk_id": h.get("chunk_id"), "page": h.get("page"), "score": h.get("score")}
            for h in (state.get("retrieved") or [])[:6]
        ]

    meta = {
        "intent": intent,
        "markdown": full_preview,
        "citations": state.get("citations") or [],
        "generation_id": str(generation_id) if generation_id else None,
    }
    if intent == "run_section":
        meta["section_key"] = state.get("section_key")
        meta["section_title"] = state.get("section_title")
    session.add(
        Message(
            conversation_id=conv.id,
            role="assistant",
            content=chat_msg,
            generation_id=generation_id,
            meta=meta,
        )
    )
    conv.updated_at = datetime.now(UTC)
    if conv.title == "Nouvelle conversation":
        conv.title = text[:80]
    await session.commit()
    yield _sse("done", {"ok": True, "message": chat_msg})
