import { useEffect, useState } from 'react'
import { adminApi, type AuditLogEntry } from '../../api/client'

const ACTION_LABEL: Record<string, string> = {
  login: 'Connexion',
  logout: 'Déconnexion',
  create: 'Création',
  update: 'Modification',
  delete: 'Suppression',
  revoke: 'Révocation',
}

const RESOURCE_LABEL: Record<string, string> = {
  user: 'Utilisateur',
  tenant: 'Tenant',
  session: 'Session',
  document: 'Document',
}

function formatDetails(details: Record<string, unknown>): string {
  const entries = Object.entries(details)
  if (entries.length === 0) return '—'
  return entries
    .map(([k, v]) => `${k}: ${typeof v === 'object' ? JSON.stringify(v) : String(v)}`)
    .join(' · ')
}

export function AuditLogsPage() {
  const [rows, setRows] = useState<AuditLogEntry[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [actionFilter, setActionFilter] = useState('')
  const [resourceFilter, setResourceFilter] = useState('')
  const [successFilter, setSuccessFilter] = useState<'' | 'true' | 'false'>('')

  function refresh() {
    setLoading(true)
    return adminApi
      .auditLogs({
        action_type: actionFilter || undefined,
        resource_type: resourceFilter || undefined,
        success: successFilter === '' ? undefined : successFilter === 'true',
      })
      .then(setRows)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [actionFilter, resourceFilter, successFilter])

  return (
    <div className="dash">
      <header className="dash-head">
        <p className="eyebrow">Administration</p>
        <h1>Journal d'audit</h1>
        <p className="lede">
          Connexions, suppressions, changements de rôle/statut, révocations de session — qui a fait
          quoi, quand, depuis où.
        </p>
      </header>

      <div className="audit-filters">
        <select value={actionFilter} onChange={(e) => setActionFilter(e.target.value)}>
          <option value="">Toutes les actions</option>
          <option value="login">Connexion</option>
          <option value="logout">Déconnexion</option>
          <option value="create">Création</option>
          <option value="update">Modification</option>
          <option value="delete">Suppression</option>
          <option value="revoke">Révocation</option>
        </select>
        <select value={resourceFilter} onChange={(e) => setResourceFilter(e.target.value)}>
          <option value="">Toutes les ressources</option>
          <option value="user">Utilisateur</option>
          <option value="tenant">Tenant</option>
          <option value="session">Session</option>
          <option value="document">Document</option>
        </select>
        <select value={successFilter} onChange={(e) => setSuccessFilter(e.target.value as '' | 'true' | 'false')}>
          <option value="">Succès et échecs</option>
          <option value="true">Succès seulement</option>
          <option value="false">Échecs seulement</option>
        </select>
      </div>

      {error ? <p className="form-error">{error}</p> : null}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Date</th>
              <th>Acteur</th>
              <th>Action</th>
              <th>Détails</th>
              <th>Origine</th>
              <th>Résultat</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={6} className="muted docs-empty">
                  {loading ? 'Chargement…' : 'Aucune entrée pour ce filtre.'}
                </td>
              </tr>
            ) : (
              rows.map((a) => (
                <tr key={a.id}>
                  <td>{new Date(a.created_at).toLocaleString('fr-FR')}</td>
                  <td>{a.user_email || <span className="muted">—</span>}</td>
                  <td>
                    {ACTION_LABEL[a.action_type] || a.action_type}
                    {a.resource_type ? ` · ${RESOURCE_LABEL[a.resource_type] || a.resource_type}` : ''}
                  </td>
                  <td className="muted">{formatDetails(a.details)}</td>
                  <td className="muted">
                    {a.ip_address || '—'}
                    {a.user_agent ? (
                      <span className="docs-err-hint" title={a.user_agent}>
                        {a.user_agent.slice(0, 40)}…
                      </span>
                    ) : null}
                  </td>
                  <td>
                    {a.success ? (
                      <span className="doc-badge doc-badge--ready">ok</span>
                    ) : (
                      <span className="doc-badge doc-badge--failed" title={a.error_message || ''}>
                        échec
                      </span>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
