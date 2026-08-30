import { useEffect, useState } from 'react'
import { fetchDossiers, downloadDossierExport, type Dossier, type ExportFormat } from '../api/client'

export function DossiersPage() {
  const [rows, setRows] = useState<Dossier[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [fmt, setFmt] = useState<ExportFormat>('docx')

  useEffect(() => {
    fetchDossiers().then(setRows).catch((e: Error) => setError(e.message))
  }, [])

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
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Projet</th>
              <th>Client</th>
              <th>Réf. DAO</th>
              <th>Statut</th>
              <th>Échéance</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={6} className="muted">
                  Aucun dossier. Ouvrez une conversation et rédigez une section du mémoire.
                </td>
              </tr>
            ) : (
              rows.map((d) => (
                <tr key={d.id}>
                  <td>{d.project_name ?? '—'}</td>
                  <td>{d.client_name ?? '—'}</td>
                  <td>{d.dao_reference ?? '—'}</td>
                  <td>{d.status}</td>
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
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
