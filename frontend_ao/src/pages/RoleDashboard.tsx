import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchSummary, type DashboardSummary, type Role } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { Icon, type IconKey } from '../components/Icons'

type Metric = Exclude<keyof DashboardSummary, 'role' | 'headline' | 'focus'>

const METRIC_ICON: Record<Metric, IconKey> = {
  dossiers: 'dossiers',
  dossiers_en_cours: 'progress',
  documents_patrimoine: 'documents',
  documents_dao: 'documents',
  exigences_a_couvrir: 'exigence',
  exports_count: 'export',
}

const PIPELINE = [
  { id: 'draft', label: 'Brouillon', icon: 'dossiers' },
  { id: 'analyzing', label: 'Analyse DAO', icon: 'target' },
  { id: 'generating', label: 'Mémoire', icon: 'documents' },
  { id: 'review', label: 'Revue HITL', icon: 'check' },
  { id: 'export', label: 'Remise', icon: 'export' },
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

function greeting(): string {
  const h = new Date().getHours()
  if (h < 12) return 'Bonjour'
  if (h < 18) return 'Bon après-midi'
  return 'Bonsoir'
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
  const activeStepIndex = data && data.dossiers === 0 ? -1 : data && data.dossiers_en_cours > 0 ? 1 : 0

  return (
    <div className="dash">
      <header className="dash-hero">
        <div className="dash-hero-text">
          <p className="eyebrow">{meta.kicker}</p>
          <h1>{data?.headline ?? `${greeting()}, ${user.first_name}.`}</h1>
          <p className="lede">
            Les compteurs viennent de Postgres (tenant <strong>{user.tenant_slug}</strong>). Ils
            évoluent automatiquement dès qu'un DAO est chargé et analysé.
          </p>
        </div>
        <div className="dash-hero-art" aria-hidden="true">
          <Icon name="compass" />
        </div>
      </header>
      {error ? <p className="form-error">{error}</p> : null}
      <section className="tiles">
        {meta.tiles.map((t, i) => {
          const linkable = t.key === 'dossiers' || t.key === 'dossiers_en_cours'
          const value = data ? data[t.key] : null
          const content = (
            <>
              <span className={`tile-icon tile-icon--${t.key}`}>
                <Icon name={METRIC_ICON[t.key]} />
              </span>
              <span className="tile-body">
                <span className="tile-label">{t.label}</span>
                <strong className="tile-value">{value ?? '—'}</strong>
              </span>
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
      <section className="pipeline-card panel" aria-label="Cycle de vie d’une offre">
        <p className="eyebrow">Cycle de vie d’une offre</p>
        <div className="pipeline">
          {PIPELINE.map((step, i) => (
            <div key={step.id} className={`pipe-step${i <= activeStepIndex ? ' pipe-step--done' : ''}`}>
              <span className="pipe-n">
                <Icon name={step.icon as IconKey} />
              </span>
              <span>{step.label}</span>
              {i < PIPELINE.length - 1 ? <span className="pipe-link" aria-hidden="true" /> : null}
            </div>
          ))}
        </div>
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
          <div className="offer-empty-body">
            <span className="offer-empty-icon" aria-hidden="true">
              <Icon name="dossiers" />
            </span>
            <div>
              <h2>Aucun dossier ouvert pour l’instant</h2>
              <p className="muted">
                Un dossier = un DAO, des exigences à couvrir, un mémoire technique généré depuis le
                patrimoine, puis une revue avant export Word.
              </p>
              <Link to="/app/dossiers" className="btn-primary btn-sm">
                Créer un dossier →
              </Link>
            </div>
          </div>
        )}
      </section>
      <section className="two-col">
        <article className="panel">
          <h2>
            <Icon name="target" className="panel-title-icon" /> Priorités du rôle
          </h2>
          <ul className="focus">
            {(data?.focus ?? []).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </article>
        <article className="panel panel-accent">
          <h2>
            <Icon name="compass" className="panel-title-icon" /> Prochaine étape métier
          </h2>
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
        </article>
      </section>
    </div>
  )
}
