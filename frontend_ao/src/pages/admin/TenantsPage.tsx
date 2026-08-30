import { FormEvent, useEffect, useState } from 'react'
import { adminApi, type Tenant } from '../../api/client'

export function TenantsPage() {
  const [rows, setRows] = useState<Tenant[]>([])
  const [error, setError] = useState<string | null>(null)
  const [form, setForm] = useState({ slug: '', name: '', email: '' })

  function refresh() {
    return adminApi.tenants().then(setRows)
  }

  useEffect(() => {
    refresh().catch((e: Error) => setError(e.message))
  }, [])

  async function onCreate(e: FormEvent) {
    e.preventDefault()
    setError(null)
    try {
      await adminApi.createTenant(form)
      setForm({ slug: '', name: '', email: '' })
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Création impossible')
    }
  }

  return (
    <div className="dash">
      <header className="dash-head">
        <p className="eyebrow">Administration</p>
        <h1>Tenants</h1>
        <p className="lede">Une entreprise = un tenant. Les utilisateurs et documents y sont isolés.</p>
      </header>
      {error ? <p className="form-error">{error}</p> : null}
      <form className="card-form" onSubmit={onCreate}>
        <input
          placeholder="slug (ex. durand-tp)"
          value={form.slug}
          onChange={(e) => setForm({ ...form, slug: e.target.value })}
          required
        />
        <input
          placeholder="Raison sociale"
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          required
        />
        <input
          type="email"
          placeholder="Email de contact"
          value={form.email}
          onChange={(e) => setForm({ ...form, email: e.target.value })}
          required
        />
        <button className="btn-primary" type="submit">
          Créer le tenant
        </button>
      </form>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Nom</th>
              <th>Slug</th>
              <th>Contact</th>
              <th>Statut</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((t) => (
              <tr key={t.id}>
                <td>{t.name}</td>
                <td className="mono">{t.slug}</td>
                <td>{t.email}</td>
                <td>{t.status}</td>
                <td>
                  {t.status === 'active' ? (
                    <button
                      type="button"
                      className="btn-ghost"
                      onClick={() => adminApi.patchTenant(t.id, { status: 'suspended' }).then(refresh)}
                    >
                      Suspendre
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="btn-ghost"
                      onClick={() => adminApi.patchTenant(t.id, { status: 'active' }).then(refresh)}
                    >
                      Réactiver
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
