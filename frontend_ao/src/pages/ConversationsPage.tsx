import { type FormEvent, useEffect, useRef, useState } from 'react'
import { useNavigate, useOutletContext, useParams } from 'react-router-dom'
import {
  convApi,
  docsApi,
  downloadDossierExport,
  type Conversation,
  type ExportFormat,
} from '../api/client'
import { MarkdownPreview } from '../components/MarkdownPreview'
import { useAuth } from '../auth/AuthContext'

type LayoutCtx = { refreshList: () => Promise<void>; listTick: number }

type Msg = NonNullable<Conversation['messages']>[number]

function emptyDraftConv(): Conversation {
  return {
    id: 'new',
    title: 'Nouvelle conversation',
    dossier_id: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    messages: [],
    sections: [],
    can_export: false,
  }
}

type AttachPhase = 'idle' | 'uploading' | 'processing' | 'ready' | 'failed'

type AttachJob = {
  documentId: string
  filename: string
  phase: AttachPhase
  status: string
  graphExtracted?: boolean
  error?: string
}

/** Titre d'une entrée d'aperçu à partir du message assistant et de la question utilisateur. */
function previewTitleForMessage(messages: Msg[], index: number, m: Msg): string {
  const intent = m.meta?.intent as string | undefined
  if (intent === 'run_section') {
    return (m.meta?.section_title as string) || 'Section'
  }
  for (let j = index - 1; j >= 0; j--) {
    const prev = messages[j]
    if (prev.role !== 'user' || prev.meta?.upload) continue
    const t = prev.content?.trim()
    if (t) return t.length > 80 ? `${t.slice(0, 77)}…` : t
  }
  return 'Réponse'
}

/** Aperçu document = sections DB, preview_markdown API, puis messages assistant rédigés. */
function previewFromMessages(messages: Msg[]): string {
  const parts: string[] = []
  const seen = new Set<string>()
  for (let i = 0; i < messages.length; i++) {
    const m = messages[i]
    if (m.role !== 'assistant') continue
    const intent = m.meta?.intent as string | undefined
    if (intent !== 'run_section' && intent !== 'hybrid_rag') continue
    const mdRaw = m.meta?.markdown
    let md = typeof mdRaw === 'string' ? mdRaw.trim() : ''
    if (!md && (m.content?.trim().length ?? 0) > 120) {
      md = m.content.trim()
    }
    if (!md) continue
    const sk =
      intent === 'run_section' ? String(m.meta?.section_key ?? m.id) : String(m.id)
    if (seen.has(sk)) continue
    seen.add(sk)
    const title = previewTitleForMessage(messages, i, m)
    const body = md
    parts.push(body.startsWith('##') ? body : `## ${title}\n\n${body}`)
  }
  return parts.join('\n\n---\n\n')
}

function buildDocumentPreview(c: Conversation): string {
  const fromSections = (c.sections ?? [])
    .filter((s) => s.markdown?.trim())
    .map((s) => `## ${s.title}\n\n${s.markdown}`)
    .join('\n\n---\n\n')
  const fromMessages = previewFromMessages(c.messages ?? [])
  const fromApi = c.preview_markdown?.trim() ?? ''

  const candidates = [fromSections, fromApi, fromMessages].filter(Boolean)
  if (candidates.length === 0) return ''
  return candidates.reduce((best, cur) => (cur.length >= best.length ? cur : best))
}

async function waitForDocumentReady(
  documentId: string,
  onTick: (doc: Awaited<ReturnType<typeof docsApi.get>>) => void,
  maxMs = 300_000,
): Promise<Awaited<ReturnType<typeof docsApi.get>>> {
  const start = Date.now()
  while (Date.now() - start < maxMs) {
    const doc = await docsApi.get(documentId)
    onTick(doc)
    if (doc.status === 'ready' || doc.status === 'failed') return doc
    await new Promise((r) => window.setTimeout(r, 2500))
  }
  throw new Error('Délai dépassé — l’indexation prend plus de temps que prévu.')
}

function AssistantBubble({
  message,
  streaming,
  streamDraft,
}: {
  message: Msg
  streaming?: boolean
  streamDraft?: string
}) {
  if (streaming) {
    return (
      <article className="bubble bubble-assistant bubble-streaming">
        <MarkdownPreview
          markdown={streamDraft ?? ''}
          streaming
          variant="chat"
          emptyLabel="Génération en cours…"
        />
      </article>
    )
  }

  const intent = message.meta?.intent as string | undefined
  const md = typeof message.meta?.markdown === 'string' ? message.meta.markdown : null
  const showLead = intent === 'run_section' || intent === 'export' || message.meta?.export

  return (
    <article className="bubble bubble-assistant">
      {showLead && message.content ? <p className="bubble-lead">{message.content}</p> : null}
      {md ? (
        <MarkdownPreview markdown={md} variant="chat" />
      ) : (
        <p>{message.content}</p>
      )}
    </article>
  )
}

export function ConversationThread() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { user } = useAuth()
  const { refreshList, listTick } = useOutletContext<LayoutCtx>()
  const isDraft = !id || id === 'new'
  const pendingSendRef = useRef(false)
  const composerRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [conv, setConv] = useState<Conversation | null>(() => (isDraft ? emptyDraftConv() : null))
  const [text, setText] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [docPreview, setDocPreview] = useState('')
  const [streamDraft, setStreamDraft] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [exportFmt, setExportFmt] = useState<ExportFormat>('docx')
  const [previewOpen, setPreviewOpen] = useState(false)
  const [attachJob, setAttachJob] = useState<AttachJob | null>(null)
  const [pendingFile, setPendingFile] = useState<File | null>(null)
  const [pendingRole, setPendingRole] = useState<'annexe' | 'patrimoine'>('annexe')
  const messagesEndRef = useRef<HTMLDivElement>(null)

  function applyPreview(c: Conversation, keepPreviousIfEmpty = false) {
    const next = buildDocumentPreview(c)
    if (next) {
      setDocPreview(next)
      return
    }
    if (keepPreviousIfEmpty) return
    setDocPreview('')
  }

  function load(idStr: string) {
    return convApi.get(idStr).then((c) => {
      setConv(c)
      applyPreview(c, pendingSendRef.current || busy || streaming)
      setStreamDraft('')
    })
  }

  useEffect(() => {
    if (!isDraft) return
    setError(null)
    setConv(emptyDraftConv())
    setDocPreview('')
    setStreamDraft('')
    composerRef.current?.focus()
  }, [id, isDraft])

  useEffect(() => {
    if (isDraft || !id) return
    if (pendingSendRef.current || busy || streaming) return
    load(id).catch((e: Error) => setError(e.message))
  }, [id, isDraft, listTick, busy, streaming])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: streaming ? 'auto' : 'smooth' })
  }, [conv?.messages, streamDraft, streaming])

  useEffect(() => {
    if (!previewOpen) return
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setPreviewOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [previewOpen])

  async function onSend(e: FormEvent) {
    e.preventDefault()
    if (!text.trim() || busy || attachBlocking) return
    if (!isDraft && !id) return
    const userText = text.trim()
    setText('')
    setBusy(true)
    setStreaming(true)
    setError(null)
    setStreamDraft('')

    const assistantId = `tmp-a-${Date.now()}`
    const optimistic: Conversation = {
      ...(conv || {
        id,
        title: 'Nouvelle conversation',
        dossier_id: null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      }),
      messages: [
        ...(conv?.messages ?? []),
        {
          id: `tmp-u-${Date.now()}`,
          role: 'user',
          content: userText,
          created_at: new Date().toISOString(),
        },
        {
          id: assistantId,
          role: 'assistant',
          content: '',
          created_at: new Date().toISOString(),
        },
      ],
    }
    setConv(optimistic)

    let convId = id && id !== 'new' ? id : ''
    try {
      if (isDraft || !convId) {
        pendingSendRef.current = true
        const created = await convApi.create()
        convId = created.id
        setConv((prev) =>
          prev
            ? { ...prev, id: created.id, can_export: created.can_export ?? false }
            : created,
        )
        navigate(`/app/conversations/${created.id}`, { replace: true })
      }

      await convApi.sendStream(convId, userText, {
        onToken: (t) => {
          setStreamDraft((prev) => prev + t)
        },
        onExportReady: (fmt, dossierId) => {
          void downloadDossierExport(dossierId, fmt)
        },
      })
      const fresh = await convApi.get(convId)
      setConv(fresh)
      applyPreview(fresh)
      await refreshList()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Envoi impossible')
      if (convId) await load(convId).catch(() => undefined)
    } finally {
      pendingSendRef.current = false
      setBusy(false)
      setStreaming(false)
      setStreamDraft('')
    }
  }

  async function onExport() {
    if (!id || id === 'new' || busy) return
    setBusy(true)
    setError(null)
    try {
      const next = await convApi.exportDoc(id, exportFmt)
      setConv(next)
      setDocPreview(buildDocumentPreview(next))
      if (next.dossier_id) await downloadDossierExport(next.dossier_id, exportFmt)
      await refreshList()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Export impossible')
    } finally {
      setBusy(false)
    }
  }

  function onFileSelected(file: File) {
    // §1.5/§3.7 — le choix annexe/patrimoine n'a de sens QUE si cette
    // conversation est déjà liée à un dossier (sinon rien à scoper) : dans
    // ce cas, on demande explicitement plutôt que de figer le rôle en
    // silence (c'était le bug V1 : doc_role toujours "patrimoine").
    if (conv?.dossier_id) {
      setPendingRole('annexe')
      setPendingFile(file)
      return
    }
    void onAttach(file, 'patrimoine')
  }

  async function onAttach(file: File, role: 'annexe' | 'patrimoine') {
    if (busy || attachJob?.phase === 'uploading' || attachJob?.phase === 'processing') return
    if (user?.role === 'consultant') return
    setError(null)
    setPendingFile(null)
    setAttachJob({ documentId: '', filename: file.name, phase: 'uploading', status: 'upload' })
    let convId = id
    try {
      if (isDraft || !convId || convId === 'new') {
        pendingSendRef.current = true
        setBusy(true)
        const created = await convApi.create()
        convId = created.id
        navigate(`/app/conversations/${created.id}`, { replace: true })
      }

      const next = await convApi.uploadDocument(convId!, file, role)
      setConv(next)
      await refreshList()

      const uploadMsg = [...(next.messages ?? [])].reverse().find((m) => m.meta?.upload)
      const documentId = uploadMsg?.meta?.document_id as string | undefined
      if (!documentId) {
        setAttachJob(null)
        return
      }

      const initialStatus = (uploadMsg.meta?.doc_status as string) || 'pending'
      if (uploadMsg.meta?.duplicate && initialStatus === 'ready') {
        setAttachJob({
          documentId,
          filename: file.name,
          phase: 'ready',
          status: 'ready',
          graphExtracted: true,
        })
        composerRef.current?.focus()
        return
      }

      setAttachJob({
        documentId,
        filename: file.name,
        phase: 'processing',
        status: initialStatus,
      })

      const finalDoc = await waitForDocumentReady(documentId, (doc) => {
        setAttachJob({
          documentId,
          filename: file.name,
          phase: doc.status === 'ready' ? 'ready' : doc.status === 'failed' ? 'failed' : 'processing',
          status: doc.status,
          graphExtracted: doc.graph_extracted,
          error: doc.ingest_error ?? undefined,
        })
      })

      if (finalDoc.status === 'failed') {
        setError(finalDoc.ingest_error || 'Indexation du document échouée.')
      } else {
        composerRef.current?.focus()
      }
      if (convId) await load(convId).catch(() => undefined)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload impossible')
      setAttachJob((prev) =>
        prev ? { ...prev, phase: 'failed', error: err instanceof Error ? err.message : 'Erreur' } : null,
      )
    } finally {
      pendingSendRef.current = false
      setBusy(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  function dismissAttachReady() {
    setAttachJob(null)
  }

  const attachBlocking = attachJob?.phase === 'uploading' || attachJob?.phase === 'processing'
  const canUpload = user?.role !== 'consultant'
  const composerLocked = busy || streaming || attachBlocking

  if (!conv) {
    return <p className="muted conv-loading">{error || (isDraft ? '…' : 'Chargement…')}</p>
  }

  const messages = conv.messages ?? []
  const last = messages[messages.length - 1]
  const showStreamBubble = streaming && last?.role === 'assistant'

  return (
    <div className="conv-workspace">
      <section className="conv-chat">
        <header className="conv-chat-head">
          <h1>{conv.title}</h1>
          {error ? <p className="form-error conv-head-error">{error}</p> : null}
        </header>

        <div className="conv-chat-scroll">
          <div className="messages">
            {attachJob ? (
              <article
                className={`attach-status attach-status--${attachJob.phase}`}
                aria-live="polite"
              >
                <p className="attach-status-title">📎 {attachJob.filename}</p>
                {attachJob.phase === 'uploading' ? (
                  <p className="muted">Envoi du fichier vers le serveur…</p>
                ) : null}
                {attachJob.phase === 'processing' ? (
                  <>
                    <p className="muted">
                      Indexation en cours — statut : <strong>{attachJob.status}</strong>
                      {attachJob.status === 'processing' ? ' (parse, chunks, embeddings…)' : ''}
                    </p>
                    <p className="attach-status-hint">
                      Patientez : le champ de question sera activé quand le document sera prêt.
                    </p>
                  </>
                ) : null}
                {attachJob.phase === 'ready' ? (
                  <>
                    <p className="attach-status-ok">
                      Document indexé et prêt — vous pouvez poser votre question.
                      {attachJob.graphExtracted ? ' Graphe Neo4j extrait.' : ''}
                    </p>
                    <button type="button" className="btn-ghost attach-dismiss" onClick={dismissAttachReady}>
                      OK, continuer
                    </button>
                  </>
                ) : null}
                {attachJob.phase === 'failed' ? (
                  <>
                    <p className="form-error attach-status-err">
                      {attachJob.error || 'Échec du traitement du document.'}
                    </p>
                    <button type="button" className="btn-ghost attach-dismiss" onClick={dismissAttachReady}>
                      Fermer
                    </button>
                  </>
                ) : null}
              </article>
            ) : null}
            {messages.length === 0 && !attachJob ? (
              <p className="muted conv-draft-hint">
                Écrivez votre premier message pour démarrer cette conversation.
              </p>
            ) : null}
            {messages.map((m, i) => {
              if (m.role === 'user') {
                const isUpload = m.meta?.upload
                return (
                  <article
                    key={m.id}
                    className={`bubble bubble-user${isUpload ? ' bubble-upload' : ''}`}
                  >
                    {isUpload ? <p className="bubble-upload-tag">📎 Document</p> : null}
                    <p>{m.content}</p>
                  </article>
                )
              }
              return (
                <AssistantBubble
                  key={m.id}
                  message={m}
                  streaming={showStreamBubble && i === messages.length - 1}
                  streamDraft={streamDraft}
                />
              )
            })}
            <div ref={messagesEndRef} />
          </div>
        </div>

        {pendingFile ? (
          <article className="attach-choice" aria-live="polite">
            <p className="attach-status-title">📎 {pendingFile.name}</p>
            <p className="muted">Comment utiliser ce document ?</p>
            <label className="attach-choice-option">
              <input
                type="radio"
                name="attach-role"
                checked={pendingRole === 'annexe'}
                onChange={() => setPendingRole('annexe')}
              />
              <span>
                <strong>Aide ponctuelle pour ce dossier uniquement</strong>
                <br />
                <span className="muted">
                  Sert à vous aider à rédiger ce dossier. Invisible depuis les autres dossiers, non
                  conservé dans le patrimoine.
                </span>
              </span>
            </label>
            <label className="attach-choice-option">
              <input
                type="radio"
                name="attach-role"
                checked={pendingRole === 'patrimoine'}
                onChange={() => setPendingRole('patrimoine')}
              />
              <span>
                <strong>Ajouter au patrimoine de l'entreprise</strong>
                <br />
                <span className="muted">
                  Utilisable pour TOUS les futurs dossiers. À réserver aux documents de référence validés
                  (méthodo, certifications, CV...).
                </span>
              </span>
            </label>
            <div className="attach-choice-actions">
              <button type="button" className="btn-ghost" onClick={() => setPendingFile(null)}>
                Annuler
              </button>
              <button type="button" className="btn-primary" onClick={() => onAttach(pendingFile, pendingRole)}>
                Confirmer
              </button>
            </div>
          </article>
        ) : null}

        <form className="conv-composer" onSubmit={onSend}>
          <div className="conv-composer-row">
            {canUpload ? (
              <div className="conv-composer-tools">
                <input
                  ref={fileInputRef}
                  type="file"
                  className="conv-file-input"
                  disabled={composerLocked}
                  onChange={(e) => {
                    const f = e.target.files?.[0]
                    if (f) onFileSelected(f)
                  }}
                />
                <button
                  type="button"
                  className="btn-ghost conv-attach-btn"
                  disabled={composerLocked}
                  title="Joindre un document de référence (indexé dans le patrimoine)"
                  onClick={() => fileInputRef.current?.click()}
                >
                  Joindre un document
                </button>
              </div>
            ) : null}
            <textarea
              ref={composerRef}
              rows={3}
              value={text}
              disabled={composerLocked}
              onChange={(e) => setText(e.target.value)}
              placeholder={
                attachBlocking
                  ? 'Indexation en cours — patientez avant de poser votre question…'
                  : 'Question ou « rédige la présentation de l’entreprise »…'
              }
            />
          </div>
          <button className="btn-primary" disabled={composerLocked} type="submit">
            {busy && streaming ? 'Génération…' : attachBlocking ? 'Indexation…' : 'Envoyer'}
          </button>
        </form>
      </section>

      <aside className="preview-panel">
        <header className="preview-head">
          <div className="preview-head-row">
            <div>
              <h2>Aperçu document</h2>
              <p className="muted preview-hint">
                Synthèse de toutes les sections déjà générées. Cliquez pour agrandir.
              </p>
            </div>
            {docPreview ? (
              <button
                type="button"
                className="btn-ghost btn-preview-expand"
                onClick={() => setPreviewOpen(true)}
              >
                Agrandir
              </button>
            ) : null}
          </div>
        </header>

        <div
          className={`preview-doc-scroll${docPreview ? ' preview-doc-clickable' : ''}`}
          role={docPreview ? 'button' : undefined}
          tabIndex={docPreview ? 0 : undefined}
          aria-label={docPreview ? 'Ouvrir l’aperçu document en plein écran' : undefined}
          onClick={() => docPreview && setPreviewOpen(true)}
          onKeyDown={(e) => {
            if (docPreview && (e.key === 'Enter' || e.key === ' ')) {
              e.preventDefault()
              setPreviewOpen(true)
            }
          }}
        >
          <div className="doc-page">
            <MarkdownPreview
              key={docPreview ? `doc-${docPreview.length}` : 'doc-empty'}
              markdown={docPreview}
              variant="document"
              emptyLabel="Aucun contenu pour l’instant — questions, réponses et sections générées s’accumulent ici."
            />
          </div>
        </div>

        <footer className="preview-foot">
          {conv.can_export ? (
            <div className="export-block">
              <h3>Exporter le document</h3>
              <select
                value={exportFmt}
                disabled={busy}
                onChange={(e) => setExportFmt(e.target.value as ExportFormat)}
              >
                <option value="docx">Word (.docx)</option>
                <option value="pdf">PDF (.pdf)</option>
                <option value="md">Markdown (.md)</option>
                <option value="txt">Texte (.txt)</option>
              </select>
              <button
                type="button"
                className="btn-primary btn-block"
                disabled={busy || !docPreview}
                onClick={() => void onExport()}
              >
                {busy ? 'Export…' : 'Exporter'}
              </button>
            </div>
          ) : (
            <p className="muted">Export réservé au rédacteur, manager ou admin.</p>
          )}
        </footer>
      </aside>

      {previewOpen ? (
        <div
          className="modal-backdrop modal-backdrop--front"
          onClick={() => setPreviewOpen(false)}
          role="presentation"
        >
          <div
            className="modal modal--preview"
            role="dialog"
            aria-modal="true"
            aria-labelledby="preview-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-head">
              <h2 id="preview-modal-title">Aperçu du mémoire</h2>
              <button type="button" className="btn-ghost" onClick={() => setPreviewOpen(false)}>
                Fermer
              </button>
            </div>
            <div className="preview-expand-scroll">
              <div className="doc-page doc-page--wide">
                <MarkdownPreview markdown={docPreview} variant="document" />
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
