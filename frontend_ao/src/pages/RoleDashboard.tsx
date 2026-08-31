import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchSummary, type DashboardSummary, type Role } from '../api/client'
import { useAuth } from '../auth/AuthContext'

type Metric = Exclude<keyof DashboardSummary, 'role' | 'headline' | 'focus'>

const PIPELINE = [
  { id: 'draft', label: 'Brouillon' },
  { id: 'analyzing', label: 'Analyse DAO' },
  { id: 'generating', label: 'Mémoire' },
  { id: 'review', label: 'Revue HITL' },
  { id: 'export', label: 'Remise' },
] as const

const COPY: Record<
  Role,
  { kicker: string; tiles: { label: string; key: Metric }[] }
> = {
  admin: {
    kicker: 'Gouvernance du tenant',
    tiles: [
      { label: 'Dossiers AO', key: 'dossiers' },
      { label: 'En cours', key: 'dossiers_en_cours' },
      { label: 'Pièces patrimoine', key: 'documents_patrimoine' },
      { label: 'Exports MinIO', key: 'exports_count' },
    ],
  },
  manager: {
    kicker: 'Portefeuille de consultations',
    tiles: [
      { label: 'Offres ouvertes', key: 'dossiers_en_cours' },
      { label: 'Dossiers total', key: 'dossiers' },
      { label: 'Exigences à couvrir', key: 'exigences_a_couvrir' },
      { label: 'Exports MinIO', key: 'exports_count' },
    ],
  },
  redacteur: {
    kicker: 'Atelier de mémoire technique',
    tiles: [
      { label: 'Dossiers', key: 'dossiers' },
      { label: 'À rédiger', key: 'dossiers_en_cours' },
      { label: 'Références patrimoine', key: 'documents_patrimoine' },
      { label: 'Exports MinIO', key: 'exports_count' },
    ],
  },
  consultant: {
    kicker: 'Revue & conformité',
    tiles: [
      { label: 'Dossiers visibles', key: 'dossiers' },
      { label: 'En revue', key: 'dossiers_en_cours' },
      { label: 'DAO', key: 'documents_dao' },
      { label: 'Exports MinIO', key: 'exports_count' },
    ],
  },
}

export function RoleDashboard() {
  const { user } = useAuth()
  const [data, setData] = useState<DashboardSummary | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchSummary()
      .then(setData)
      .catch((e: Error) => setError(e.message))
  }, [])

  if (!user) return null
  const meta = COPY[user.role]

  return (
    <div className="dash">
      <header className="dash-head">
        <p className="eyebrow">{meta.kicker}</p>
        <h1>{data?.headline ?? 'Chargement…'}</h1>
        <p className="lede">
          Bonjour {user.first_name}. Les compteurs viennent de Postgres (tenant{' '}
          <strong>{user.tenant_slug}</strong>). Ils resteront à zéro tant qu’aucun DAO n’est
          ingéré.
        </p>
      </header>
      {error ? <p className="form-error">{error}</p> : null}
      <section className="tiles">
        {meta.tiles.map((t, i) => {
          const linkable = t.key === 'dossiers' || t.key === 'dossiers_en_cours'
          const content = (
            <>
              <p>{t.label}</p>
              <strong>{data ? data[t.key] : '—'}</strong>
            </>
          )
          return linkable ? (
            <Link
              key={t.label}
              to="/app/dossiers"
              className="tile tile--enter tile--link"
              style={{ animationDelay: `${i * 70}ms` }}
            >
              {content}
            </Link>
          ) : (
            <article key={t.label} className="tile tile--enter" style={{ animationDelay: `${i * 70}ms` }}>
              {content}
            </article>
          )
        })}
      </section>
      {data && data.exports_count > 0 ? (
        <p className="dash-exports-hint muted">
          {data.exports_count} mémoire{data.exports_count > 1 ? 's' : ''} exporté
          {data.exports_count > 1 ? 's' : ''} dans MinIO — voir{' '}
          <Link to="/app/documents#exports-section">Documents → Exports</Link>.
        </p>
      ) : null}
      <section className="pipeline" aria-label="Cycle de vie d’une offre">
        {PIPELINE.map((step, i) => (
          <div key={step.id} className="pipe-step">
            <span className="pipe-n">{i + 1}</span>
            <span>{step.label}</span>
          </div>
        ))}
      </section>
      <section className="offer-empty panel">
        <p className="eyebrow">Portefeuille d’offres</p>
        {data && data.dossiers > 0 ? (
          <>
            <h2>
              {data.dossiers} dossier{data.dossiers > 1 ? 's' : ''}
              {data.dossiers_en_cours > 0 ? ` · ${data.dossiers_en_cours} en cours` : ''}
            </h2>
            <p className="muted">
              Exigences, plan, sections et revue humaine se gèrent depuis la page de chaque dossier.
            </p>
            <Link to="/app/dossiers" className="btn-ghost">
              Voir les dossiers →
            </Link>
          </>
        ) : (
          <>
            <h2>Aucun dossier ouvert pour l’instant</h2>
            <p className="muted">
              Un dossier = un DAO, des exigences à couvrir, un mémoire technique généré depuis le
              patrimoine, puis une revue avant export Word. Il se crée automatiquement dès qu'une
              conversation génère une première section.
            </p>
          </>
        )}
      </section>
      <section className="two-col">
        <article className="panel">
          <h2>Priorités du rôle</h2>
          <ul className="focus">
            {(data?.focus ?? []).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </article>
        <article className="panel panel-accent">
          <h2>Prochaine étape métier</h2>
          {user.role === 'admin' && (
            <p>Inviter l’équipe, surveiller l’ingestion MinIO / Qdrant, garder l’audit propre.</p>
          )}
          {user.role === 'manager' && (
            <p>
              Ouvrir un dossier de réponse, coller l’échéance de remise, suivre le taux de
              couverture des exigences.
            </p>
          )}
          {user.role === 'redacteur' && (
            <p>
              Choisir une section du plan (moyens, références, QSE), générer depuis le patrimoine,
              citer les chunks, envoyer en revue.
            </p>
          )}
          {user.role === 'consultant' && (
            <p>
              Relire les sections générées, approve / edit / regen. Pas de modification du
              patrimoine.
            </p>
          )}
          <p className="muted">La génération LangGraph et l’upload DAO arriveront sur ces mêmes écrans.</p>
        </article>
      </section>
    </div>
  )
}
