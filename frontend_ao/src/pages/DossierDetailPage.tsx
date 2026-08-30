import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  dossierApi,
  docsApi,
  type Dossier,
  type Exigence,
  type OutlineItemApi,
  type SectionDetail,
  type ReviewApi,
  type DossierPieceApi,
  type DocItem,
} from '../api/client'
import { MarkdownPreview } from '../components/MarkdownPreview'

type Tab = 'exigences' | 'plan' | 'sections' | 'documents' | 'historique'

const STATUT_LABEL: Record<string, string> = {
  a_couvrir: 'À couvrir',
  en_cours: 'Recherche en cours…',
  couverte: 'Couverte',
  non_couverte: 'Non couverte',
  a_revoir: 'À revoir',
}

const STATUT_CLASS: Record<string, string> = {
  a_couvrir: 'pill pill-muted',
  en_cours: 'pill pill-info',
  couverte: 'pill pill-ok',
  non_couverte: 'pill pill-danger',
  a_revoir: 'pill pill-warn',
}

const OUTLINE_STATUT_LABEL: Record<string, string> = {
  todo: 'À faire',
  generated: 'Générée — en attente de revue',
  approved: 'Approuvée',
  rejected: 'Rejetée',
}

const OUTLINE_STATUT_CLASS: Record<string, string> = {
  todo: 'pill pill-muted',
  generated: 'pill pill-warn',
  approved: 'pill pill-ok',
  rejected: 'pill pill-danger',
}

export function DossierDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [dossier, setDossier] = useState<Dossier | null>(null)
  const [tab, setTab] = useState<Tab>('exigences')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function reload() {
    if (!id) return
    try {
      setDossier(await dossierApi.get(id))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  useEffect(() => {
    reload()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  if (!id) return null

  return (
    <div className="dash">
      <header className="dash-head">
        <p className="eyebrow">Dossier</p>
        <h1>{dossier?.project_name || '—'}</h1>
        <p className="lede">
          {dossier?.client_name ? `Client : ${dossier.client_name}` : 'Client non renseigné'}
          {dossier?.dao_reference ? ` · Réf. ${dossier.dao_reference}` : ''}
          {dossier ? ` · Statut : ${dossier.status}` : ''}
        </p>
        <div className="dossier-actions">
          <button type="button" className="btn-ghost" onClick={() => navigate('/app/dossiers')}>
            ← Retour aux dossiers
          </button>
          <button
            type="button"
            className="btn-primary"
            disabled={busy}
            onClick={async () => {
              setBusy(true)
              setError(null)
              try {
                await dossierApi.analyser(id)
                await reload()
              } catch (e) {
                setError(e instanceof Error ? e.message : String(e))
              } finally {
                setBusy(false)
              }
            }}
          >
            {busy ? 'Analyse en cours…' : 'Analyser le DAO'}
          </button>
        </div>
      </header>

      {error ? <p className="form-error">{error}</p> : null}

      {dossier && dossier.exigences_eliminatoires_non_couvertes > 0 ? (
        <div className="alert-banner alert-danger">
          ⚠️ {dossier.exigences_eliminatoires_non_couvertes} exigence(s) obligatoire(s) non couverte(s) —
          risque d'élimination du marché.
        </div>
      ) : null}

      <nav className="tabs">
        {(
          [
            ['exigences', `Exigences${dossier ? ` (${dossier.exigences_couvertes}/${dossier.exigences_total})` : ''}`],
            ['plan', 'Plan'],
            ['sections', 'Sections'],
            ['documents', 'Documents & pièces'],
            ['historique', 'Historique'],
          ] as [Tab, string][]
        ).map(([key, label]) => (
          <button
            key={key}
            type="button"
            className={`tab-btn ${tab === key ? 'tab-btn-active' : ''}`}
            onClick={() => setTab(key)}
          >
            {label}
          </button>
        ))}
      </nav>

      {tab === 'exigences' ? <ExigencesTab dossierId={id} /> : null}
      {tab === 'plan' ? <PlanTab dossierId={id} onOpenSection={() => setTab('sections')} /> : null}
      {tab === 'sections' ? <SectionsTab dossierId={id} /> : null}
      {tab === 'documents' ? <DocumentsTab dossierId={id} /> : null}
      {tab === 'historique' ? <HistoriqueTab dossierId={id} /> : null}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Exigences (§3.3)
// ---------------------------------------------------------------------------

function ExigencesTab({ dossierId }: { dossierId: string }) {
  const [rows, setRows] = useState<Exigence[]>([])
  const [error, setError] = useState<string | null>(null)
  const [relance, setRelance] = useState<string | null>(null)

  async function load() {
    try {
      setRows(await dossierApi.exigences(dossierId))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dossierId])

  return (
    <div className="table-wrap">
      {error ? <p className="form-error">{error}</p> : null}
      <table>
        <thead>
          <tr>
            <th>Libellé</th>
            <th>Type</th>
            <th>Oblig.</th>
            <th>Statut</th>
            <th>Preuves</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={6} className="muted">
                Aucune exigence — lancez « Analyser le DAO » pour les extraire.
              </td>
            </tr>
          ) : (
            rows.map((e) => (
              <tr key={e.id} className={e.obligatoire && e.statut === 'non_couverte' ? 'row-danger' : ''}>
                <td>{e.libelle}</td>
                <td>{e.type}</td>
                <td>{e.obligatoire ? '✓' : ''}</td>
                <td>
                  <span className={STATUT_CLASS[e.statut] || 'pill'}>{STATUT_LABEL[e.statut] || e.statut}</span>
                </td>
                <td>{e.preuves_chunks.length || '—'}</td>
                <td>
                  <button
                    type="button"
                    className="btn-ghost"
                    disabled={relance === e.id}
                    onClick={async () => {
                      setRelance(e.id)
                      try {
                        await dossierApi.relancerRechercheExigence(dossierId, e.id)
                        await load()
                      } catch (err) {
                        setError(err instanceof Error ? err.message : String(err))
                      } finally {
                        setRelance(null)
                      }
                    }}
                  >
                    {relance === e.id ? '…' : 'Relancer la recherche'}
                  </button>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Plan (§3.4)
// ---------------------------------------------------------------------------

function PlanTab({ dossierId, onOpenSection }: { dossierId: string; onOpenSection: (key: string) => void }) {
  const [rows, setRows] = useState<OutlineItemApi[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    dossierApi
      .outline(dossierId)
      .then(setRows)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [dossierId])

  return (
    <div className="table-wrap">
      {error ? <p className="form-error">{error}</p> : null}
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Titre</th>
            <th>Archétype</th>
            <th>Statut</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((o) => (
            <tr key={o.id}>
              <td>{o.sort_order + 1}</td>
              <td>{o.title}</td>
              <td className="muted">{o.archetype}</td>
              <td>
                <span className={OUTLINE_STATUT_CLASS[o.status] || 'pill'}>
                  {OUTLINE_STATUT_LABEL[o.status] || o.status}
                </span>
              </td>
              <td>
                <button type="button" className="btn-ghost" onClick={() => onOpenSection(o.key)}>
                  Ouvrir
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Sections — revue HITL (§3.5)
// ---------------------------------------------------------------------------

function SectionsTab({ dossierId }: { dossierId: string }) {
  const [outline, setOutline] = useState<OutlineItemApi[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [detail, setDetail] = useState<SectionDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [regenComment, setRegenComment] = useState('')
  const [editText, setEditText] = useState('')
  const [editing, setEditing] = useState(false)

  useEffect(() => {
    dossierApi
      .outline(dossierId)
      .then((rows) => {
        setOutline(rows)
        if (rows.length && !selected) setSelected(rows[0].key)
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dossierId])

  useEffect(() => {
    if (!selected) return
    dossierApi
      .getSection(dossierId, selected)
      .then((d) => {
        setDetail(d)
        setEditText(d.markdown || '')
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [dossierId, selected])

  async function refreshDetail() {
    if (!selected) return
    const d = await dossierApi.getSection(dossierId, selected)
    setDetail(d)
    setEditText(d.markdown || '')
  }

  const item = outline.find((o) => o.key === selected)

  return (
    <div className="sections-layout">
      <aside className="sections-list">
        {outline.map((o) => (
          <button
            key={o.key}
            type="button"
            className={`section-list-item ${selected === o.key ? 'section-list-item-active' : ''}`}
            onClick={() => setSelected(o.key)}
          >
            <span className={OUTLINE_STATUT_CLASS[o.status] || 'pill'} style={{ marginRight: '0.5rem' }} />
            {o.title}
          </button>
        ))}
      </aside>
      <section className="section-detail">
        {error ? <p className="form-error">{error}</p> : null}
        {!item ? (
          <p className="muted">Sélectionnez une section.</p>
        ) : (
          <>
            <h2>{item.title}</h2>
            <p className="muted">
              Statut : {OUTLINE_STATUT_LABEL[item.status] || item.status}
              {detail?.version ? ` · version ${detail.version}` : ''}
            </p>

            {!detail?.markdown ? (
              <button
                type="button"
                className="btn-primary"
                disabled={busy}
                onClick={async () => {
                  setBusy(true)
                  setError(null)
                  try {
                    await dossierApi.generateSection(dossierId, item.key)
                    await refreshDetail()
                    setOutline(await dossierApi.outline(dossierId))
                  } catch (e) {
                    setError(e instanceof Error ? e.message : String(e))
                  } finally {
                    setBusy(false)
                  }
                }}
              >
                {busy ? 'Génération en cours…' : 'Générer cette section'}
              </button>
            ) : editing ? (
              <textarea
                className="section-edit-textarea"
                value={editText}
                onChange={(e) => setEditText(e.target.value)}
                rows={16}
              />
            ) : (
              <MarkdownPreview markdown={detail.markdown} variant="document" />
            )}

            {detail?.abstentions && detail.abstentions.length > 0 ? (
              <div className="alert-banner alert-warn">
                <strong>⚠️ Points non couverts par la recherche :</strong>
                <ul>
                  {detail.abstentions.map((a, i) => (
                    <li key={i}>{a}</li>
                  ))}
                </ul>
              </div>
            ) : null}

            {detail?.markdown ? (
              <div className="section-review-actions">
                {editing ? (
                  <>
                    <button
                      type="button"
                      className="btn-primary"
                      disabled={busy}
                      onClick={async () => {
                        setBusy(true)
                        try {
                          await dossierApi.reviewSection(dossierId, item.key, { action: 'edit', text: editText })
                          setEditing(false)
                          await refreshDetail()
                          setOutline(await dossierApi.outline(dossierId))
                        } catch (e) {
                          setError(e instanceof Error ? e.message : String(e))
                        } finally {
                          setBusy(false)
                        }
                      }}
                    >
                      Enregistrer et approuver
                    </button>
                    <button type="button" className="btn-ghost" onClick={() => setEditing(false)}>
                      Annuler
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      type="button"
                      className="btn-primary"
                      disabled={busy}
                      onClick={async () => {
                        setBusy(true)
                        try {
                          await dossierApi.reviewSection(dossierId, item.key, { action: 'approve' })
                          setOutline(await dossierApi.outline(dossierId))
                        } catch (e) {
                          setError(e instanceof Error ? e.message : String(e))
                        } finally {
                          setBusy(false)
                        }
                      }}
                    >
                      Approuver
                    </button>
                    <button type="button" className="btn-ghost" onClick={() => setEditing(true)}>
                      Modifier le texte
                    </button>
                    <input
                      className="regen-input"
                      placeholder="Consigne de régénération (ex. « insiste sur les grues 50t »)"
                      value={regenComment}
                      onChange={(e) => setRegenComment(e.target.value)}
                    />
                    <button
                      type="button"
                      className="btn-ghost"
                      disabled={busy}
                      onClick={async () => {
                        setBusy(true)
                        try {
                          await dossierApi.reviewSection(dossierId, item.key, {
                            action: 'regen',
                            comment: regenComment,
                          })
                          setRegenComment('')
                          await refreshDetail()
                          setOutline(await dossierApi.outline(dossierId))
                        } catch (e) {
                          setError(e instanceof Error ? e.message : String(e))
                        } finally {
                          setBusy(false)
                        }
                      }}
                    >
                      Régénérer…
                    </button>
                  </>
                )}
              </div>
            ) : null}
          </>
        )}
      </section>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Documents (annexes) — §3.7
// ---------------------------------------------------------------------------

function DocumentsTab({ dossierId }: { dossierId: string }) {
  const [rows, setRows] = useState<DocItem[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function load() {
    try {
      setRows(await docsApi.list(dossierId))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dossierId])

  return (
    <div className="table-wrap">
      <p className="muted">
        Documents d'appoint pour CE dossier uniquement — jamais visibles depuis un autre dossier, jamais dans
        le patrimoine général sauf promotion explicite.
      </p>
      <form
        className="card-form"
        onSubmit={async (e) => {
          e.preventDefault()
          const input = (e.currentTarget.elements.namedItem('file') as HTMLInputElement) || null
          const file = input?.files?.[0]
          if (!file) return
          setBusy(true)
          setError(null)
          try {
            await docsApi.upload(file, 'annexe', '', dossierId)
            if (input) input.value = ''
            await load()
          } catch (err) {
            setError(err instanceof Error ? err.message : String(err))
          } finally {
            setBusy(false)
          }
        }}
      >
        <input type="file" name="file" accept=".pdf,.docx,.xlsx,.txt,.md,.jpg,.jpeg,.png,.tiff,.webp" />
        <button type="submit" className="btn-primary" disabled={busy}>
          {busy ? 'Envoi…' : 'Ajouter une annexe'}
        </button>
      </form>
      {error ? <p className="form-error">{error}</p> : null}
      <table>
        <thead>
          <tr>
            <th>Fichier</th>
            <th>Statut</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={3} className="muted">
                Aucune annexe pour ce dossier.
              </td>
            </tr>
          ) : (
            rows.map((d) => (
              <tr key={d.id}>
                <td>{d.filename}</td>
                <td>{d.status}</td>
                <td>
                  <button
                    type="button"
                    className="btn-ghost"
                    onClick={async () => {
                      try {
                        await docsApi.promote(d.id)
                        await load()
                      } catch (err) {
                        setError(err instanceof Error ? err.message : String(err))
                      }
                    }}
                  >
                    ↑ Promouvoir au patrimoine
                  </button>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>

      <PiecesChecklist dossierId={dossierId} allDocs={rows} />
    </div>
  )
}

const PIECE_STATUT_LABEL: Record<string, string> = {
  manquant: 'Manquant',
  trouve_patrimoine: 'Trouvé en patrimoine',
  a_uploader: 'À uploader',
  fourni: 'Fourni',
}

const PIECE_STATUT_CLASS: Record<string, string> = {
  manquant: 'pill pill-danger',
  trouve_patrimoine: 'pill pill-warn',
  a_uploader: 'pill pill-warn',
  fourni: 'pill pill-ok',
}

function PiecesChecklist({ dossierId, allDocs }: { dossierId: string; allDocs: DocItem[] }) {
  const [pieces, setPieces] = useState<DossierPieceApi[]>([])
  const [patrimoineDocs, setPatrimoineDocs] = useState<DocItem[]>([])
  const [error, setError] = useState<string | null>(null)

  async function load() {
    try {
      setPieces(await dossierApi.pieces(dossierId))
      setPatrimoineDocs((await docsApi.list()).filter((d) => d.doc_type === 'administratif'))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dossierId])

  return (
    <div className="pieces-checklist">
      <h3>Checklist administrative</h3>
      <p className="muted">
        Pièces attendues pour le dossier administratif — issues du règlement de consultation ou d'une liste
        standard (§5.3). Choisissez un document déjà en patrimoine, ou déposez-le comme annexe ci-dessus.
      </p>
      {error ? <p className="form-error">{error}</p> : null}
      <table>
        <thead>
          <tr>
            <th>Pièce</th>
            <th>Statut</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {pieces.length === 0 ? (
            <tr>
              <td colSpan={3} className="muted">
                Aucune checklist — lancez « Analyser le DAO » pour la générer.
              </td>
            </tr>
          ) : (
            pieces.map((p) => (
              <tr key={p.id}>
                <td>
                  {p.libelle}
                  {p.obligatoire ? '' : ' (optionnel)'}
                </td>
                <td>
                  <span className={PIECE_STATUT_CLASS[p.statut] || 'pill'}>
                    {PIECE_STATUT_LABEL[p.statut] || p.statut}
                  </span>
                </td>
                <td>
                  <select
                    className="select-dark"
                    defaultValue=""
                    onChange={async (e) => {
                      if (!e.target.value) return
                      try {
                        await dossierApi.choisirPiece(dossierId, p.id, e.target.value)
                        await load()
                      } catch (err) {
                        setError(err instanceof Error ? err.message : String(err))
                      }
                    }}
                  >
                    <option value="">Choisir un document…</option>
                    {[...allDocs, ...patrimoineDocs].map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.filename}
                      </option>
                    ))}
                  </select>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Historique (§3.6)
// ---------------------------------------------------------------------------

function HistoriqueTab({ dossierId }: { dossierId: string }) {
  const [outline, setOutline] = useState<OutlineItemApi[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [reviews, setReviews] = useState<ReviewApi[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    dossierApi
      .outline(dossierId)
      .then((rows) => {
        setOutline(rows)
        if (rows.length) setSelected(rows[0].key)
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [dossierId])

  useEffect(() => {
    if (!selected) return
    dossierApi
      .historique(dossierId, selected)
      .then(setReviews)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [dossierId, selected])

  return (
    <div>
      <label className="muted" htmlFor="historique-select">
        Section :{' '}
      </label>
      <select
        id="historique-select"
        className="select-dark"
        value={selected || ''}
        onChange={(e) => setSelected(e.target.value)}
      >
        {outline.map((o) => (
          <option key={o.key} value={o.key}>
            {o.title}
          </option>
        ))}
      </select>
      {error ? <p className="form-error">{error}</p> : null}
      <ul className="historique-list">
        {reviews.length === 0 ? (
          <li className="muted">Aucune décision enregistrée pour cette section.</li>
        ) : (
          reviews.map((r) => (
            <li key={r.id}>
              v{r.version} → <strong>{r.action}</strong> ({new Date(r.created_at).toLocaleString('fr-FR')})
              {r.comment ? ` — "${r.comment}"` : ''}
            </li>
          ))
        )}
      </ul>
    </div>
  )
}
