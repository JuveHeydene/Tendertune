"""Conversations : RAG stream + export multi-format."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.auth import get_current_user
from app.models.sql import Conversation, Message, User
from app.services.chat_pipeline import can_write, process_message_sync, stream_message
from app.services.dossier_workflow import EXPORT_FORMATS, ensure_dossier, export_document, latest_sections
from app.services.document_upload import store_document
from app.services.purge_conversation import purge_conversation
from app.services.db_client import get_session

log = logging.getLogger("btp.chat")

router = APIRouter(prefix="/conversations", tags=["conversations"])


class ConversationCreate(BaseModel):
    title: str | None = None
    dossier_id: UUID | None = None


class ConversationUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=255)


class MessageIn(BaseModel):
    text: str = Field(min_length=1)


class ExportIn(BaseModel):
    format: str = Field(default="docx", pattern="^(docx|pdf|md|txt)$")


class MessageOut(BaseModel):
    id: UUID
    role: str
    content: str
    created_at: datetime
    meta: dict = Field(default_factory=dict)


class SectionOut(BaseModel):
    key: str
    title: str
    status: str
    markdown: str | None = None


class ConversationOut(BaseModel):
    id: UUID
    title: str | None
    dossier_id: UUID | None
    created_at: datetime
    updated_at: datetime
    messages: list[MessageOut] = []
    sections: list[SectionOut] = []
    preview_markdown: str | None = None
    can_export: bool = False


async def _sections_for(session: AsyncSession, dossier_id: UUID | None) -> list[SectionOut]:
    if dossier_id is None:
        return []
    pairs = await latest_sections(session, dossier_id)
    out = []
    for item, gen in pairs:
        md = None
        if gen and isinstance(gen.content, dict):
            md = gen.content.get("texte") or None
        out.append(
            SectionOut(key=item.key, title=item.title, status=item.status, markdown=md)
        )
    return out


def _preview_from_sections(sections: list[SectionOut]) -> str | None:
    parts = []
    for s in sections:
        if s.markdown:
            parts.append(f"## {s.title}\n\n{s.markdown}")
    return "\n\n---\n\n".join(parts) if parts else None


def _user_prompt_before(msgs: list, idx: int) -> str:
    for j in range(idx - 1, -1, -1):
        m = msgs[j]
        if m.role != "user":
            continue
        meta = m.meta or {}
        if meta.get("upload"):
            continue
        text = (m.content or "").strip()
        if text:
            return text[:80] + ("…" if len(text) > 80 else "")
    return "Réponse"


def _preview_from_messages(msgs: list) -> str | None:
    """Reconstitue l'aperçu depuis les messages assistant (sections + réponses RAG)."""
    ordered = sorted(msgs, key=lambda x: x.created_at)
    parts: list[str] = []
    seen: set[str] = set()
    for idx, m in enumerate(ordered):
        if m.role != "assistant":
            continue
        meta = m.meta or {}
        intent = meta.get("intent")
        if intent not in ("run_section", "hybrid_rag"):
            continue
        md = meta.get("markdown")
        if not isinstance(md, str) or not md.strip():
            fallback = (m.content or "").strip()
            if len(fallback) > 120:
                md = fallback
            else:
                continue
        if intent == "run_section":
            sk = str(meta.get("section_key") or m.id)
            title = meta.get("section_title") or "Section"
        else:
            sk = str(m.id)
            title = _user_prompt_before(ordered, idx)
        if sk in seen:
            continue
        seen.add(sk)
        body = md.strip()
        if body.startswith("##"):
            parts.append(body)
        else:
            parts.append(f"## {title}\n\n{body}")
    return "\n\n---\n\n".join(parts) if parts else None


def _merge_preview(sections: list[SectionOut], msgs: list) -> str | None:
    from_db = _preview_from_sections(sections)
    from_msgs = _preview_from_messages(msgs)
    if from_db and from_msgs:
        if from_db.strip() == from_msgs.strip():
            return from_db
        if from_db in from_msgs:
            return from_msgs
        if from_msgs in from_db:
            return from_db
        return from_msgs if len(from_msgs) >= len(from_db) else from_db
    return from_db or from_msgs


async def _to_out(session: AsyncSession, conv: Conversation, user: User) -> ConversationOut:
    if conv.messages is None:
        conv = (
            await session.execute(
                select(Conversation)
                .options(selectinload(Conversation.messages))
                .where(Conversation.id == conv.id)
            )
        ).scalar_one()
    msgs = sorted(conv.messages, key=lambda m: m.created_at)
    sections = await _sections_for(session, conv.dossier_id)
    preview = _merge_preview(sections, msgs)
    return ConversationOut(
        id=conv.id,
        title=conv.title,
        dossier_id=conv.dossier_id,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        messages=[
            MessageOut(
                id=m.id,
                role=m.role,
                content=m.content,
                created_at=m.created_at,
                meta=m.meta or {},
            )
            for m in msgs
        ],
        sections=sections,
        preview_markdown=preview,
        can_export=can_write(user),
    )


@router.get("", response_model=list[ConversationOut])
async def list_conversations(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    q = select(Conversation).where(
        Conversation.tenant_id == user.tenant_id,
        exists(select(Message.id).where(Message.conversation_id == Conversation.id)),
    )
    if user.role != "admin":
        q = q.where(Conversation.user_id == user.id)
    rows = (await session.execute(q.order_by(Conversation.updated_at.desc()))).scalars().all()
    return [
        ConversationOut(
            id=c.id,
            title=c.title,
            dossier_id=c.dossier_id,
            created_at=c.created_at,
            updated_at=c.updated_at,
            can_export=can_write(user),
        )
        for c in rows
    ]


@router.post("", response_model=ConversationOut)
async def create_conversation(
    body: ConversationCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    conv = Conversation(
        tenant_id=user.tenant_id,
        user_id=user.id,
        dossier_id=body.dossier_id,
        title=body.title or "Nouvelle conversation",
    )
    session.add(conv)
    await session.commit()
    await session.refresh(conv)
    return ConversationOut(
        id=conv.id,
        title=conv.title,
        dossier_id=conv.dossier_id,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        messages=[],
        can_export=can_write(user),
    )


async def _load_conv(session: AsyncSession, conversation_id: UUID, user: User) -> Conversation:
    conv = (
        await session.execute(
            select(Conversation)
            .options(selectinload(Conversation.messages))
            .where(Conversation.id == conversation_id)
        )
    ).scalar_one_or_none()
    if conv is None or conv.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Conversation introuvable")
    if user.role != "admin" and conv.user_id != user.id:
        raise HTTPException(status_code=403, detail="Accès refusé")
    return conv


@router.get("/{conversation_id}", response_model=ConversationOut)
async def get_conversation(
    conversation_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    conv = await _load_conv(session, conversation_id, user)
    return await _to_out(session, conv, user)


@router.patch("/{conversation_id}", response_model=ConversationOut)
async def update_conversation(
    conversation_id: UUID,
    body: ConversationUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    conv = await _load_conv(session, conversation_id, user)
    conv.title = body.title.strip()
    conv.updated_at = datetime.now(UTC)
    await session.commit()
    conv = await _load_conv(session, conversation_id, user)
    return await _to_out(session, conv, user)


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    conv = await _load_conv(session, conversation_id, user)
    await purge_conversation(session, conv)


@router.post("/{conversation_id}/documents", response_model=ConversationOut)
async def upload_conversation_document(
    conversation_id: UUID,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if user.role == "consultant":
        raise HTTPException(status_code=403, detail="Le consultant ne dépose pas de pièces")
    conv = await _load_conv(session, conversation_id, user)
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Fichier vide")
    filename = file.filename or "document.bin"
    dossier_id = conv.dossier_id
    if can_write(user) and dossier_id is None:
        doss = await ensure_dossier(session, conv, user)
        dossier_id = doss.id
    doc, duplicate = await store_document(
        session,
        user,
        data,
        filename,
        doc_role="patrimoine",
        doc_type="reference",
        content_type=file.content_type,
        dossier_origine_id=dossier_id,
    )
    note = (
        f"Document déjà indexé : {filename}"
        if duplicate and doc.status == "ready"
        else (
            f"Document déjà présent : {filename} (statut {doc.status})."
            if duplicate
            else f"Document déposé : {filename}"
        )
    )
    session.add(
        Message(
            conversation_id=conv.id,
            role="user",
            content=note,
            meta={
                "upload": True,
                "document_id": str(doc.id),
                "filename": filename,
                "duplicate": duplicate,
                "doc_status": doc.status,
            },
        )
    )
    conv.updated_at = datetime.now(UTC)
    await session.commit()
    conv = await _load_conv(session, conversation_id, user)
    return await _to_out(session, conv, user)


@router.post("/{conversation_id}/messages", response_model=ConversationOut)
async def post_message(
    conversation_id: UUID,
    body: MessageIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    conv = await _load_conv(session, conversation_id, user)
    session.add(Message(conversation_id=conv.id, role="user", content=body.text))
    await session.flush()
    answer, meta, generation_id = await process_message_sync(session, conv, user, body.text)
    session.add(
        Message(
            conversation_id=conv.id,
            role="assistant",
            content=answer,
            generation_id=generation_id,
            meta=meta,
        )
    )
    conv.updated_at = datetime.now(UTC)
    if conv.title == "Nouvelle conversation":
        conv.title = body.text[:80]
    await session.commit()
    conv = await _load_conv(session, conversation_id, user)
    return await _to_out(session, conv, user)


@router.post("/{conversation_id}/messages/stream")
async def post_message_stream(
    conversation_id: UUID,
    body: MessageIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    conv = await _load_conv(session, conversation_id, user)

    async def event_gen():
        async for chunk in stream_message(session, conv, user, body.text):
            yield chunk

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{conversation_id}/export", response_model=ConversationOut)
async def export_conversation(
    conversation_id: UUID,
    body: ExportIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if body.format not in EXPORT_FORMATS:
        raise HTTPException(status_code=400, detail=f"Format invalide : {body.format}")
    if not can_write(user):
        raise HTTPException(status_code=403, detail="Export réservé au rédacteur, manager ou admin")
    conv = await _load_conv(session, conversation_id, user)
    doss = await ensure_dossier(session, conv, user)
    msgs = sorted(conv.messages or [], key=lambda m: m.created_at)
    notes = "\n\n".join(f"{m.role}: {m.content}" for m in msgs[-12:])
    try:
        rec, _ = await export_document(
            session, dossier=doss, user=user, fmt=body.format, transcript=notes
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    msg = f"Document exporté en {body.format.upper()} (v{rec.version})."
    session.add(
        Message(
            conversation_id=conv.id,
            role="assistant",
            content=msg,
            meta={"intent": "export", "export": True, "format": body.format, "version": rec.version},
        )
    )
    conv.updated_at = datetime.now(UTC)
    await session.commit()
    conv = await _load_conv(session, conversation_id, user)
    return await _to_out(session, conv, user)
