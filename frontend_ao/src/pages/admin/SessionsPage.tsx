import { useEffect, useState } from 'react'
import { adminApi, type UserSession } from '../../api/client'

export function SessionsPage() {
  const [rows, setRows] = useState<UserSession[]>([])
  const [error, setError] = useState<string | null>(null)

  function refresh() {
    return adminApi.sessions().then(setRows)
  }

  useEffect(() => {
    refresh().catch((e: Error) => setError(e.message))
  }, [])

  return (
    <div className="dash">
      <header className="dash-head">
        <p className="eyebrow">Administration</p>
        <h1>Sessions</h1>
        <p className="lede">Révoquer un jeton JWT en base : l’utilisateur devra se reconnecter.</p>
      </header>
      {error ? <p className="form-error">{error}</p> : null}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Compte</th>
              <th>Ouverte</th>
              <th>Activité</th>
              <th>Expire</th>
              <th>État</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((s) => (
              <tr key={s.id}>
                <td>
                  {s.username}
                  <div className="muted">{s.email}</div>
                </td>
                <td>{new Date(s.created_at).toLocaleString('fr-FR')}</td>
                <td>{new Date(s.last_activity_at).toLocaleString('fr-FR')}</td>
                <td>{new Date(s.expires_at).toLocaleString('fr-FR')}</td>
                <td>{s.revoked ? 'révoquée' : 'active'}</td>
                <td>
                  {!s.revoked ? (
                    <button
                      type="button"
                      className="btn-ghost"
                      onClick={() => adminApi.revokeSession(s.id).then(refresh)}
                    >
                      Révoquer
                    </button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
