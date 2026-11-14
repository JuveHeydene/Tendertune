import { FormEvent, useEffect, useState } from 'react'
import { adminApi, type ManagedUser, type Role, type Tenant } from '../../api/client'

const ROLES: Role[] = ['admin', 'manager', 'redacteur', 'consultant']

export function UsersPage() {
  const [users, setUsers] = useState<ManagedUser[]>([])
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [error, setError] = useState<string | null>(null)
  const [form, setForm] = useState({
    tenant_id: '',
    username: '',
    email: '',
    password: '',
    role: 'redacteur' as Role,
    first_name: '',
    last_name: '',
  })
  const [resetTarget, setResetTarget] = useState<ManagedUser | null>(null)
  const [newPassword, setNewPassword] = useState('')
  const [resetBusy, setResetBusy] = useState(false)
  const [resetError, setResetError] = useState<string | null>(null)
  const [resetOk, setResetOk] = useState<string | null>(null)

  async function refresh() {
    const [u, t] = await Promise.all([adminApi.users(), adminApi.tenants()])
    setUsers(u)
    setTenants(t)
    setForm((f) => ({ ...f, tenant_id: f.tenant_id || t[0]?.id || '' }))
  }

  useEffect(() => {
    refresh().catch((e: Error) => setError(e.message))
  }, [])

  async function onCreate(e: FormEvent) {
    e.preventDefault()
    setError(null)
    try {
      await adminApi.createUser(form)
      setForm((f) => ({ ...f, username: '', email: '', password: '', first_name: '', last_name: '' }))
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Création impossible')
    }
  }

  async function setStatus(id: string, status: string) {
    await adminApi.patchUser(id, { status })
    await refresh()
  }

  async function setRole(id: string, role: string) {
    await adminApi.patchUser(id, { role })
    await refresh()
  }

  function openReset(u: ManagedUser) {
    setResetTarget(u)
    setNewPassword('')
    setResetError(null)
    setResetOk(null)
  }

  async function confirmReset(e: FormEvent) {
    e.preventDefault()
    if (!resetTarget || newPassword.length < 8) return
    setResetBusy(true)
    setResetError(null)
    try {
      await adminApi.patchUser(resetTarget.id, { password: newPassword })
      setResetOk(`Mot de passe changé pour ${resetTarget.email}.`)
      setNewPassword('')
    } catch (err) {
      setResetError(err instanceof Error ? err.message : 'Échec de la réinitialisation')
    } finally {
      setResetBusy(false)
    }
  }

  return (
    <div className="dash">
      <header className="dash-head">
        <p className="eyebrow">Administration</p>
        <h1>Utilisateurs</h1>
        <p className="lede">Créer un compte, changer le rôle, suspendre, révoquer toutes les sessions.</p>
      </header>
      {error ? <p className="form-error">{error}</p> : null}
      <form className="card-form" onSubmit={onCreate}>
        <select
          value={form.tenant_id}
          onChange={(e) => setForm({ ...form, tenant_id: e.target.value })}
          required
        >
          {tenants.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name} ({t.slug})
            </option>
          ))}
        </select>
        <input
          placeholder="Prénom"
          value={form.first_name}
          onChange={(e) => setForm({ ...form, first_name: e.target.value })}
        />
        <input
          placeholder="Nom"
          value={form.last_name}
          onChange={(e) => setForm({ ...form, last_name: e.target.value })}
        />
        <input
          placeholder="Identifiant"
          value={form.username}
          onChange={(e) => setForm({ ...form, username: e.target.value })}
          required
        />
        <input
          type="email"
          placeholder="Email"
          value={form.email}
          onChange={(e) => setForm({ ...form, email: e.target.value })}
          required
        />
        <input
          type="password"
          placeholder="Mot de passe (8 car. min)"
          value={form.password}
          onChange={(e) => setForm({ ...form, password: e.target.value })}
          required
          minLength={8}
        />
        <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as Role })}>
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>
        <button className="btn-primary" type="submit">
          Créer l’utilisateur
        </button>
      </form>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Personne</th>
              <th>Tenant</th>
              <th>Rôle</th>
              <th>Statut</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id}>
                <td>
                  <strong>
                    {u.first_name} {u.last_name}
                  </strong>
                  <div className="muted">{u.email}</div>
                </td>
                <td>{u.tenant_slug}</td>
                <td>
                  <select value={u.role} onChange={(e) => setRole(u.id, e.target.value)}>
                    {ROLES.map((r) => (
                      <option key={r} value={r}>
                        {r}
                      </option>
                    ))}
                  </select>
                </td>
                <td>{u.status}</td>
                <td className="row-actions">
                  {u.status === 'active' ? (
                    <button type="button" className="btn-ghost" onClick={() => setStatus(u.id, 'suspended')}>
                      Suspendre
                    </button>
                  ) : (
                    <button type="button" className="btn-ghost" onClick={() => setStatus(u.id, 'active')}>
                      Réactiver
                    </button>
                  )}
                  <button
                    type="button"
                    className="btn-ghost"
                    onClick={() => adminApi.revokeUserSessions(u.id).then(refresh)}
                  >
                    Révoquer sessions
                  </button>
                  <button type="button" className="btn-ghost" onClick={() => openReset(u)}>
                    Changer le mot de passe
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {resetTarget ? (
        <div
          className="modal-backdrop"
          onClick={() => !resetBusy && setResetTarget(null)}
          role="presentation"
        >
          <form
            className="modal modal--narrow"
            role="dialog"
            aria-modal="true"
            aria-labelledby="reset-pw-title"
            onClick={(e) => e.stopPropagation()}
            onSubmit={confirmReset}
          >
            <div className="modal-head">
              <h2 id="reset-pw-title">Changer le mot de passe</h2>
            </div>
            <p className="modal-copy">
              Pour <strong>{resetTarget.email}</strong> — en cas d'oubli. L'utilisateur devra utiliser ce
              nouveau mot de passe à sa prochaine connexion ; ses sessions actuelles restent valides.
            </p>
            {resetOk ? <p className="attach-status-ok">{resetOk}</p> : null}
            {resetError ? <p className="form-error">{resetError}</p> : null}
            <label className="field">
              <span>Nouveau mot de passe (8 caractères min.)</span>
              <input
                type="password"
                value={newPassword}
                minLength={8}
                autoFocus
                disabled={resetBusy}
                onChange={(e) => setNewPassword(e.target.value)}
              />
            </label>
            <div className="modal-actions">
              <button type="submit" className="btn-primary" disabled={resetBusy || newPassword.length < 8}>
                {resetBusy ? 'Enregistrement…' : 'Changer le mot de passe'}
              </button>
              <button
                type="button"
                className="btn-ghost"
                disabled={resetBusy}
                onClick={() => setResetTarget(null)}
              >
                Fermer
              </button>
            </div>
          </form>
        </div>
      ) : null}
    </div>
  )
}
