import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { fetchDossiers, downloadDossierExport, type Dossier, type ExportFormat } from '../api/client'

export function DossiersPage() {
  const [rows, setRows] = useState<Dossier[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [fmt, setFmt] = useState<ExportFormat>('docx')
  const navigate = useNavigate()

  useEffect(() => {
    fetchDossiers().then(setRows).catch((e: Error) => setError(e.message))
  }, [])

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
        <h1>Dossiers</h1>
        <p className="lede">
          Un dossier se construit en conversation (sections du mémoire) puis s’exporte en DOCX.
        </p>
      </header>
      {error ? <p className="form-error">{error}</p> : null}
      {rows.length === 0 ? (
        <p className="muted">Aucun dossier. Ouvrez une conversation et rédigez une section du mémoire.</p>
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
