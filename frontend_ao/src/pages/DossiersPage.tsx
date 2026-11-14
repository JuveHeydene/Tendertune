import { type FormEvent, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { fetchDossiers, downloadDossierExport, dossierApi, type Dossier, type ExportFormat } from '../api/client'

export function DossiersPage() {
  const [rows, setRows] = useState<Dossier[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [fmt, setFmt] = useState<ExportFormat>('docx')
  const [showCreate, setShowCreate] = useState(false)
  const [createBusy, setCreateBusy] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const navigate = useNavigate()

  function reload() {
    return fetchDossiers().then(setRows).catch((e: Error) => setError(e.message))
  }

  useEffect(() => {
    reload()
  }, [])

  async function onCreate(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const form = new FormData(e.currentTarget)
    const project_name = String(form.get('project_name') || '').trim()
    const client_name = String(form.get('client_name') || '').trim()
    const dao_reference = String(form.get('dao_reference') || '').trim()
    if (!project_name) {
      setCreateError('Le nom du projet est requis')
      return
    }
    setCreateBusy(true)
    setCreateError(null)
    try {
      const created = await dossierApi.create({
        project_name,
        client_name: client_name || undefined,
        dao_reference: dao_reference || undefined,
      })
      navigate(`/app/dossiers/${created.id}`)
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : 'Création impossible')
    } finally {
      setCreateBusy(false)
    }
  }

  // §3.1 — groupement par client (l'entité maître d'ouvrage pour qui le
  // DAO a été émis), pas par tenant (déjà isolé par l'auth).
  const groups = useMemo(() => {
    const map = new Map<string, Dossier[]>()
    for (const d of rows) {
      const key = d.client_name || 'Client non renseigné'
      if (!map.has(key)) map.set(key, [])
      map.get(key)!.push(d)
    }
    return Array.from(map.entries()).sort((a, b) => a[0].localeCompare(b[0]))
  }, [rows])

  return (
    <div className="dash">
      <header className="dash-head">
        <p className="eyebrow">Appels d’offres</p>
        <div className="dash-head-row">
          <h1>Dossiers</h1>
          <button type="button" className="btn-primary" onClick={() => setShowCreate((v) => !v)}>
            {showCreate ? 'Annuler' : '+ Nouveau dossier'}
          </button>
        </div>
        <p className="lede">
          Un dossier existe avant toute conversation : créez-le, chargez son DAO, analysez-le (exigences +
          plan), puis rédigez depuis une conversation dédiée à ce dossier.
        </p>
      </header>
      {showCreate ? (
        <form className="card-form" onSubmit={onCreate}>
          <input type="text" name="project_name" required placeholder="Nom du projet *" />
          <input type="text" name="client_name" placeholder="Client / maître d’ouvrage" />
          <input type="text" name="dao_reference" placeholder="Référence DAO (ex. AO-2026-042)" />
          <button type="submit" className="btn-primary" disabled={createBusy}>
            {createBusy ? 'Création…' : 'Créer le dossier'}
          </button>
          {createError ? <p className="form-error">{createError}</p> : null}
          <p className="muted docs-upload-hint">
            Après création, vous serez redirigé vers le dossier pour y charger le DAO (onglet Documents) et
            lancer l’analyse — les exigences et le plan viennent de cette analyse, pas d’un modèle générique.
          </p>
        </form>
      ) : null}
      {error ? <p className="form-error">{error}</p> : null}
      {rows.length === 0 ? (
        <p className="muted">Aucun dossier pour l’instant. Créez-en un pour commencer.</p>
      ) : (
        groups.map(([client, dossiers]) => (
          <section key={client} className="dossier-group">
            <h2 className="dossier-group-title">
              {client} <span className="muted">({dossiers.length})</span>
            </h2>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Projet</th>
                    <th>Réf. DAO</th>
                    <th>Statut</th>
                    <th>Exigences</th>
                    <th>Sections</th>
                    <th>Échéance</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {dossiers.map((d) => {
                    const alerte = d.exigences_eliminatoires_non_couvertes > 0
                    return (
                      <tr key={d.id} className={alerte ? 'row-danger' : ''}>
                        <td>
                          <button type="button" className="link-btn" onClick={() => navigate(`/app/dossiers/${d.id}`)}>
                            {d.project_name ?? '—'}
                          </button>
                        </td>
                        <td>{d.dao_reference ?? '—'}</td>
                        <td>{d.status}</td>
                        <td>
                          {d.exigences_couvertes}/{d.exigences_total}
                          {alerte ? ' ⚠️' : ''}
                        </td>
                        <td>
                          {d.sections_approuvees}/{d.sections_total}
                        </td>
                        <td>{d.deadline ? new Date(d.deadline).toLocaleDateString('fr-FR') : '—'}</td>
                        <td>
                          <select
                            value={fmt}
                            className="export-select"
                            onChange={(e) => setFmt(e.target.value as ExportFormat)}
                          >
                            <option value="docx">docx</option>
                            <option value="pdf">pdf</option>
                            <option value="md">md</option>
                            <option value="txt">txt</option>
                          </select>
                          <button
                            type="button"
                            className="btn-ghost"
                            disabled={busy === d.id}
                            onClick={() => {
                              setBusy(d.id)
                              setError(null)
                              downloadDossierExport(d.id, fmt)
                                .catch((e: Error) => setError(e.message))
                                .finally(() => setBusy(null))
                            }}
                          >
                            {busy === d.id ? '…' : 'Télécharger'}
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </section>
        ))
      )}
    </div>
  )
}
