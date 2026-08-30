import { NavLink, Outlet, useMatch, useNavigate } from 'react-router-dom'
import { type FormEvent, useEffect, useRef, useState } from 'react'
import { convApi, type Conversation } from '../api/client'
import { useAuth } from '../auth/AuthContext'

export function ConversationsLayout() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const activeMatch = useMatch('/app/conversations/:id')
  const activeId = activeMatch?.params.id
  const [rows, setRows] = useState<Conversation[]>([])
  const [error, setError] = useState<string | null>(null)
  const [menuOpen, setMenuOpen] = useState<string | null>(null)
  const [renameTarget, setRenameTarget] = useState<Conversation | null>(null)
  const [renameTitle, setRenameTitle] = useState('')
  const [deleteTarget, setDeleteTarget] = useState<Conversation | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [listTick, setListTick] = useState(0)
  const menuRef = useRef<HTMLDivElement>(null)

  function refresh() {
    return convApi.list().then(setRows).catch((e: Error) => setError(e.message))
  }

  useEffect(() => {
    refresh()
  }, [])

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(null)
      }
    }
    document.addEventListener('mousedown', onDocClick)
    return () => document.removeEventListener('mousedown', onDocClick)
  }, [])

  function onCreate() {
    navigate('/app/conversations/new', { replace: true })
  }

  function onBack() {
    navigate(user ? `/app/${user.role}` : '/app')
  }

  function openRename(c: Conversation) {
    setMenuOpen(null)
    setRenameTarget(c)
    setRenameTitle(c.title || '')
  }

  function openDelete(c: Conversation) {
    setMenuOpen(null)
    setDeleteTarget(c)
  }

  async function confirmRename(e: FormEvent) {
    e.preventDefault()
    if (!renameTarget || !renameTitle.trim() || busy) return
    setBusy(renameTarget.id)
    setError(null)
    try {
      await convApi.rename(renameTarget.id, renameTitle.trim())
      setRenameTarget(null)
      await refresh()
      setListTick((t) => t + 1)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Renommage impossible')
    } finally {
      setBusy(null)
    }
  }

  async function confirmDelete() {
    if (!deleteTarget || busy) return
    setBusy(deleteTarget.id)
    setError(null)
    try {
      await convApi.remove(deleteTarget.id)
      const wasActive = activeId === deleteTarget.id
      setDeleteTarget(null)
      await refresh()
      if (wasActive) navigate('/app/conversations')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Suppression impossible')
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="conv-shell">
      <aside className="conv-sidebar">
        <div className="conv-sidebar-head">
          <button type="button" className="btn-ghost btn-back" onClick={onBack}>
            ← Retour au menu
          </button>
          <p className="eyebrow">Conversations</p>
          <button type="button" className="btn-primary btn-block" onClick={() => void onCreate()}>
            Nouvelle conversation
          </button>
        </div>
        {error ? <p className="form-error conv-sidebar-error">{error}</p> : null}
        <ul className="conv-sidebar-list">
          {rows.length === 0 ? (
            <li className="muted conv-sidebar-empty">Aucune conversation</li>
          ) : (
            rows.map((c) => (
              <li key={c.id} className="conv-sidebar-item">
                <NavLink
                  to={`/app/conversations/${c.id}`}
                  className={({ isActive }) => (isActive ? 'conv-nav active' : 'conv-nav')}
                >
                  <strong>{c.title || 'Sans titre'}</strong>
                  <span>{new Date(c.updated_at).toLocaleString('fr-FR')}</span>
                </NavLink>
                <div className="conv-item-menu" ref={menuOpen === c.id ? menuRef : undefined}>
                  <button
                    type="button"
                    className="conv-menu-trigger"
                    aria-label="Actions conversation"
                    aria-expanded={menuOpen === c.id}
                    onClick={(e) => {
                      e.preventDefault()
                      e.stopPropagation()
                      setMenuOpen((prev) => (prev === c.id ? null : c.id))
                    }}
                  >
                    ⋯
                  </button>
                  {menuOpen === c.id ? (
                    <div className="conv-menu-popover" role="menu">
                      <button
                        type="button"
                        role="menuitem"
                        onClick={() => openRename(c)}
                      >
                        Renommer
                      </button>
                      <button
                        type="button"
                        role="menuitem"
                        className="conv-menu-danger"
                        onClick={() => openDelete(c)}
                      >
                        Supprimer
                      </button>
                    </div>
                  ) : null}
                </div>
              </li>
            ))
          )}
        </ul>
      </aside>
      <main className="conv-main">
        <Outlet context={{ refreshList: refresh, listTick }} />
      </main>

      {renameTarget ? (
        <div
          className="modal-backdrop modal-backdrop--front"
          onClick={() => !busy && setRenameTarget(null)}
          role="presentation"
        >
          <form
            className="modal modal--narrow"
            role="dialog"
            aria-modal="true"
            aria-labelledby="rename-modal-title"
            onClick={(e) => e.stopPropagation()}
            onSubmit={(e) => void confirmRename(e)}
          >
            <div className="modal-head">
              <h2 id="rename-modal-title">Renommer la conversation</h2>
            </div>
            <label className="field">
              <span>Titre</span>
              <input
                type="text"
                value={renameTitle}
                maxLength={255}
                autoFocus
                disabled={!!busy}
                onChange={(e) => setRenameTitle(e.target.value)}
              />
            </label>
            <div className="modal-actions">
              <button type="submit" className="btn-primary" disabled={!!busy || !renameTitle.trim()}>
                {busy === renameTarget.id ? 'Enregistrement…' : 'Enregistrer'}
              </button>
              <button
                type="button"
                className="btn-ghost"
                disabled={!!busy}
                onClick={() => setRenameTarget(null)}
              >
                Annuler
              </button>
            </div>
          </form>
        </div>
      ) : null}

      {deleteTarget ? (
        <div
          className="modal-backdrop modal-backdrop--front"
          onClick={() => !busy && setDeleteTarget(null)}
          role="presentation"
        >
          <div
            className="modal modal--narrow"
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-conv-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-head">
              <h2 id="delete-conv-modal-title">Supprimer cette conversation ?</h2>
            </div>
            <p className="modal-copy">
              « {deleteTarget.title || 'Sans titre'} » et tout son historique seront supprimés
              définitivement (messages, sections rédigées, exports associés).
            </p>
            <div className="modal-actions">
              <button
                type="button"
                className="btn-danger"
                disabled={!!busy}
                onClick={() => void confirmDelete()}
              >
                {busy === deleteTarget.id ? 'Suppression…' : 'Supprimer'}
              </button>
              <button
                type="button"
                className="btn-ghost"
                disabled={!!busy}
                onClick={() => setDeleteTarget(null)}
              >
                Annuler
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
