import { type FormEvent, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { docsApi, exportsApi, type DocItem, type ExportItem } from '../api/client'
import { useAuth } from '../auth/AuthContext'

const LABELS: { key: keyof DocItem; label: string }[] = [
  { key: 'id', label: 'id' },
  { key: 'tenant_id', label: 'tenant_id' },
  { key: 'created_by', label: 'created_by' },
  { key: 'filename', label: 'filename' },
  { key: 'doc_role', label: 'doc_role' },
  { key: 'doc_type', label: 'doc_type' },
  { key: 'is_dao', label: 'is_dao' },
  { key: 'dossier_origine_id', label: 'dossier_origine_id' },
  { key: 'status', label: 'status' },
  { key: 'graph_extracted', label: 'graph_extracted' },
  { key: 'ingest_error', label: 'ingest_error' },
  { key: 'object_key', label: 'object_key (MinIO)' },
  { key: 'sha', label: 'sha' },
  { key: 'size_bytes', label: 'size_bytes' },
  { key: 'mime_type', label: 'mime_type' },
  { key: 'ocr_used', label: 'ocr_used' },
  { key: 'ocr_confidence', label: 'ocr_confidence' },
  { key: 'page_count', label: 'page_count' },
  { key: 'archived_at', label: 'archived_at' },
  { key: 'created_at', label: 'created_at' },
  { key: 'updated_at', label: 'updated_at' },
]

function fmt(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  return String(value)
}

function statusClass(status: string): string {
  if (status === 'ready') return 'doc-badge doc-badge--ready'
  if (status === 'processing' || status === 'pending') return 'doc-badge doc-badge--live'
  if (status === 'failed') return 'doc-badge doc-badge--failed'
  return 'doc-badge'
}

function formatBytes(n: number | null | undefined): string {
  if (!n) return '—'
  if (n < 1024) return `${n} o`
  if (n < 1024 * 1024) return `${Math.round(n / 1024)} ko`
  return `${(n / (1024 * 1024)).toFixed(1)} Mo`
}

export function DocumentsPage() {
  const { user } = useAuth()
  const [rows, setRows] = useState<DocItem[]>([])
  const [exports, setExports] = useState<ExportItem[]>([])
  const [error, setError] = useState<string | null>(null)
  const [exportsError, setExportsError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [downloading, setDownloading] = useState<string | null>(null)
  const [role, setRole] = useState('patrimoine')
  const [type, setType] = useState('autre')
  const [open, setOpen] = useState<DocItem | null>(null)
  const [pendingDelete, setPendingDelete] = useState<DocItem | null>(null)
  const [deleting, setDeleting] = useState<string | null>(null)
  const [filter, setFilter] = useState<'all' | 'ready' | 'live' | 'failed'>('all')
  const [tick, setTick] = useState(0)

  async function refresh(silent = false) {
    if (!silent) setLoading(true)
    const docsP = docsApi
      .list()
      .then((list) => {
        setRows(list)
        setError(null)
      })
      .catch((e: Error) => setError(e.message))
    const expP = exportsApi
      .list()
      .then((list) => {
        setExports(list)
        setExportsError(null)
      })
      .catch((e: Error) => setExportsError(e.message))
    await Promise.allSettled([docsP, expP])
    setLoading(false)
    setTick((t) => t + 1)
  }

  useEffect(() => {
    void refresh()
    const id = window.setInterval(() => {
      void refresh(true)
    }, 4000)
    return () => window.clearInterval(id)
  }, [])

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key !== 'Escape') return
      if (pendingDelete) {
        setPendingDelete(null)
        return
      }
      if (open) setOpen(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, pendingDelete])

  const stats = useMemo(() => {
    const ready = rows.filter((d) => d.status === 'ready').length
    const live = rows.filter((d) => d.status === 'processing' || d.status === 'pending').length
    const failed = rows.filter((d) => d.status === 'failed').length
    return { total: rows.length, ready, live, failed, exports: exports.length }
  }, [rows, exports])

  const filtered = useMemo(() => {
    if (filter === 'all') return rows
    if (filter === 'ready') return rows.filter((d) => d.status === 'ready')
    if (filter === 'live') return rows.filter((d) => d.status === 'processing' || d.status === 'pending')
    return rows.filter((d) => d.status === 'failed')
  }, [rows, filter])

  async function onUpload(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const input = e.currentTarget.elements.namedItem('file') as HTMLInputElement
    const file = input.files?.[0]
    if (!file) return
    setBusy(true)
    setError(null)
    try {
      const doc = await docsApi.upload(file, role, type)
      if (doc.duplicate) setError('Fichier déjà présent (même empreinte SHA).')
      input.value = ''
      await refresh(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload impossible')
    } finally {
      setBusy(false)
    }
  }

  async function onDownloadExport(item: ExportItem) {
    setDownloading(item.id)
    setExportsError(null)
    try {
      await exportsApi.download(item.id, item.download_name)
    } catch (err) {
      setExportsError(err instanceof Error ? err.message : 'Téléchargement impossible')
    } finally {
      setDownloading(null)
    }
  }

  const canUpload = user?.role !== 'consultant'
  const canDelete = user?.role === 'admin' || user?.role === 'manager'

  function askDelete(d: DocItem) {
    setPendingDelete(d)
  }

  function cancelDelete() {
    setPendingDelete(null)
  }

  async function confirmDelete() {
    if (!pendingDelete) return
    const d = pendingDelete
    setDeleting(d.id)
    setError(null)
    try {
      await docsApi.remove(d.id)
      setPendingDelete(null)
      if (open?.id === d.id) setOpen(null)
      await refresh(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Suppression impossible')
    } finally {
      setDeleting(null)
    }
  }

  return (
    <div className="dash docs-page">
      <header className="dash-head">
        <p className="eyebrow">Mémoire documentaire</p>
        <h1>Documents</h1>
        <p className="lede">
          Dépôt MinIO → worker (Docling / Paddle / pypdf) → chunks Postgres + Qdrant → graphe Neo4j.
          Les mémoires exportés depuis Conversations apparaissent plus bas (bucket ao-exports).
        </p>
        <p className="docs-pulse muted" aria-live="polite">
          {loading && rows.length === 0
            ? 'Chargement…'
            : `Actualisé · ${stats.total} fichier${stats.total > 1 ? 's' : ''} · ${stats.exports} export${stats.exports > 1 ? 's' : ''}`}
          {stats.live > 0 ? (
            <span className="docs-pulse-dot" title="Ingestion en cours">
              {' '}
              · {stats.live} en cours
            </span>
          ) : null}
        </p>
      </header>

      <section className="docs-stats" aria-label="Compteurs">
        <button
          type="button"
          className={`docs-stat${filter === 'all' ? ' docs-stat--active' : ''}`}
          onClick={() => setFilter('all')}
        >
          <span>Total</span>
          <strong key={`t-${tick}-${stats.total}`}>{stats.total}</strong>
        </button>
        <button
          type="button"
          className={`docs-stat docs-stat--ready${filter === 'ready' ? ' docs-stat--active' : ''}`}
          onClick={() => setFilter('ready')}
        >
          <span>Prêts</span>
          <strong key={`r-${tick}-${stats.ready}`}>{stats.ready}</strong>
        </button>
        <button
          type="button"
          className={`docs-stat docs-stat--live${filter === 'live' ? ' docs-stat--active' : ''}`}
          onClick={() => setFilter('live')}
        >
          <span>En cours</span>
          <strong key={`l-${tick}-${stats.live}`}>{stats.live}</strong>
        </button>
        <button
          type="button"
          className={`docs-stat docs-stat--failed${filter === 'failed' ? ' docs-stat--active' : ''}`}
          onClick={() => setFilter('failed')}
        >
          <span>Échecs</span>
          <strong key={`f-${tick}-${stats.failed}`}>{stats.failed}</strong>
        </button>
        <a className="docs-stat docs-stat--exports" href="#exports-section">
          <span>Exports MinIO</span>
          <strong key={`e-${tick}-${stats.exports}`}>{stats.exports}</strong>
        </a>
      </section>

      {error ? <p className="form-error">{error}</p> : null}

      {canUpload ? (
        <form className="card-form docs-upload" onSubmit={onUpload}>
          <div className="docs-upload-main">
            <input type="file" name="file" required />
            <select value={role} onChange={(e) => setRole(e.target.value)}>
              <option value="patrimoine">Patrimoine (références)</option>
              <option value="dao_courant">DAO courant</option>
              <option value="dao_archive">DAO archive</option>
            </select>
            <select value={type} onChange={(e) => setType(e.target.value)}>
              <option value="autre">Type : autre</option>
              <option value="rc">RC</option>
              <option value="cctp">CCTP</option>
              <option value="ccap">CCAP</option>
              <option value="memoire">Mémoire</option>
              <option value="reference">Référence</option>
              <option value="dpgf">DPGF</option>
              <option value="bpu">BPU</option>
            </select>
          </div>
          <button className="btn-primary" disabled={busy} type="submit">
            {busy ? 'Envoi…' : 'Déposer dans MinIO'}
          </button>
        </form>
      ) : (
        <p className="muted">Consultation seule — pas de dépôt pour le rôle consultant.</p>
      )}

      <div className="table-wrap docs-table">
        <table>
          <thead>
            <tr>
              <th>Fichier</th>
              <th>Rôle</th>
              <th>Type</th>
              <th>Statut</th>
              <th>Graphe</th>
              <th>Taille</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={7} className="muted docs-empty">
                  {rows.length === 0
                    ? 'Aucun document pour ce tenant — déposez un PDF, DOCX ou XLSX.'
                    : 'Aucun document pour ce filtre.'}
                </td>
              </tr>
            ) : (
              filtered.map((d, i) => (
                <tr
                  key={d.id}
                  className={`docs-row${d.status === 'processing' || d.status === 'pending' ? ' docs-row--live' : ''}`}
                  style={{ animationDelay: `${Math.min(i, 8) * 40}ms` }}
                >
                  <td>
                    <span className="docs-filename">{d.filename}</span>
                  </td>
                  <td>{d.doc_role}</td>
                  <td>{d.doc_type ?? '—'}</td>
                  <td>
                    <span className={statusClass(d.status)}>
                      {d.status}
                      {d.ocr_used ? ' · OCR' : ''}
                    </span>
                    {d.status === 'failed' && d.ingest_error ? (
                      <span className="docs-err-hint" title={d.ingest_error}>
                        {d.ingest_error.slice(0, 48)}
                        {d.ingest_error.length > 48 ? '…' : ''}
                      </span>
                    ) : null}
                  </td>
                  <td>
                    {d.graph_extracted ? (
                      <span className="doc-badge doc-badge--ready">oui</span>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td>{formatBytes(d.size_bytes)}</td>
                  <td>
                    <div className="row-actions">
                      <button type="button" className="btn-ghost" onClick={() => setOpen(d)}>
                        Détails
                      </button>
                      {canDelete ? (
                        <button
                          type="button"
                          className="btn-danger"
                          disabled={deleting === d.id}
                          onClick={() => askDelete(d)}
                        >
                          {deleting === d.id ? 'Suppression…' : 'Supprimer'}
                        </button>
                      ) : null}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <header className="dash-head section-gap" id="exports-section">
        <p className="eyebrow">Exports mémoire</p>
        <h2>Documents exportés</h2>
        <p className="lede">
          Fichiers générés depuis Conversations (DOCX, PDF, MD, TXT) — index Postgres + objets MinIO{' '}
          <code>ao-exports</code>.
        </p>
      </header>
      {exportsError ? <p className="form-error">{exportsError}</p> : null}
      <div className="table-wrap docs-table">
        <table>
          <thead>
            <tr>
              <th>Projet</th>
              <th>Format</th>
              <th>Version</th>
              <th>Taille</th>
              <th>Date</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {exports.length === 0 ? (
              <tr>
                <td colSpan={6} className="muted docs-empty">
                  Aucun export encore.{' '}
                  <Link to="/app/conversations">Ouvrir Conversations</Link> → rédiger des sections →
                  Exporter.
                </td>
              </tr>
            ) : (
              exports.map((x, i) => (
                <tr
                  key={x.id}
                  className="docs-row"
                  style={{ animationDelay: `${Math.min(i, 8) * 40}ms` }}
                >
                  <td>{x.project_name || x.dossier_id.slice(0, 8)}</td>
                  <td>
                    <span className={`fmt-badge fmt-badge--${x.format}`}>{x.format.toUpperCase()}</span>
                  </td>
                  <td>v{x.version}</td>
                  <td>{formatBytes(x.size_bytes)}</td>
                  <td>{new Date(x.created_at).toLocaleString('fr-FR')}</td>
                  <td>
                    <button
                      type="button"
                      className="btn-primary btn-sm"
                      disabled={downloading === x.id}
                      onClick={() => void onDownloadExport(x)}
                    >
                      {downloading === x.id ? 'Téléchargement…' : 'Télécharger'}
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {open ? (
        <div className="modal-backdrop" onClick={() => setOpen(null)} role="presentation">
          <div
            className="modal modal--doc-details"
            role="dialog"
            aria-modal="true"
            aria-labelledby="doc-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-head">
              <h2 id="doc-modal-title">{open.filename}</h2>
              <div className="row-actions">
                {canDelete ? (
                  <button
                    type="button"
                    className="btn-danger"
                    disabled={deleting === open.id}
                    onClick={() => askDelete(open)}
                  >
                    {deleting === open.id ? 'Suppression…' : 'Supprimer'}
                  </button>
                ) : null}
                <button type="button" className="btn-ghost" onClick={() => setOpen(null)}>
                  Fermer
                </button>
              </div>
            </div>
            <p className="modal-copy">
              <span className={statusClass(open.status)}>{open.status}</span>
              {open.ocr_used ? ' · OCR' : ''}
              {open.graph_extracted ? ' · graphe Neo4j' : ''}
            </p>
            <dl className="attr-grid attr-grid--scroll">
              {LABELS.map(({ key, label }) => (
                <div key={key} className="attr-row">
                  <dt>{label}</dt>
                  <dd>{fmt(open[key])}</dd>
                </div>
              ))}
            </dl>
          </div>
        </div>
      ) : null}

      {pendingDelete ? (
        <div
          className="modal-backdrop modal-backdrop--front"
          onClick={cancelDelete}
          role="presentation"
        >
          <div
            className="modal modal--narrow"
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-head">
              <h2 id="delete-modal-title">Supprimer ce document ?</h2>
            </div>
            <p className="modal-copy">
              « {pendingDelete.filename} » sera retiré de MinIO, Postgres, Qdrant et Neo4j. Cette
              action est définitive.
            </p>
            <div className="modal-actions">
              <button
                type="button"
                className="btn-danger"
                disabled={deleting === pendingDelete.id}
                onClick={() => void confirmDelete()}
              >
                {deleting === pendingDelete.id ? 'Suppression…' : 'Oui'}
              </button>
              <button type="button" className="btn-ghost" disabled={!!deleting} onClick={cancelDelete}>
                Annuler
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
