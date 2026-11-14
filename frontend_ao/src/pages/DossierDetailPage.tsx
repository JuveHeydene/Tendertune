import { useEffect, useState } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import {
  dossierApi,
  docsApi,
  downloadDossierPieces,
  ApiError,
  type Dossier,
  type Exigence,
  type SectionExigenceLink,
  type OutlineItemApi,
  type SectionDetail,
  type ReviewApi,
  type DossierPieceApi,
  type DocItem,
  type RetrievalTraceEntry,
  type ExigencePreuve,
} from '../api/client'
import { MarkdownPreview } from '../components/MarkdownPreview'
import { TracesModal } from '../components/TracesModal'
import { PreuvesModal } from '../components/PreuvesModal'

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

const VALID_TABS: Tab[] = ['exigences', 'plan', 'sections', 'documents', 'historique']

export function DossierDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [dossier, setDossier] = useState<Dossier | null>(null)
  const tabParam = searchParams.get('tab') as Tab | null
  const [tab, setTab] = useState<Tab>(tabParam && VALID_TABS.includes(tabParam) ? tabParam : 'exigences')
  const [openSectionKey, setOpenSectionKey] = useState<string | null>(searchParams.get('section'))
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [editing, setEditing] = useState(false)
  const [editBusy, setEditBusy] = useState(false)
  const [editError, setEditError] = useState<string | null>(null)

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

  // Un DAO scanné passe par l'OCR (PaddleOCR) — l'ingestion peut rester en
  // "pending"/"processing" plusieurs minutes, et l'extraction exigences/plan
  // (status="analyzing") tourne aussi en tâche de fond après que le POST
  // /analyser ait déjà répondu (job juste enqueued, pas terminé). Sans ce
  // polling, `busy` retombe à false dès la réponse HTTP — le bouton
  // redevient cliquable alors que l'analyse tourne encore en vrai, ce qui a
  // permis un double-clic / deux analyses concurrentes (§bug corrigé).
  useEffect(() => {
    const daoBusy = dossier?.dao_status && dossier.dao_status !== 'ready' && dossier.dao_status !== 'failed'
    const analysing = dossier?.status === 'analyzing'
    if (!daoBusy && !analysing) return
    const t = window.setInterval(() => reload(), 3000)
    return () => window.clearInterval(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dossier?.dao_status, dossier?.status])

  if (!id) return null

  const daoReady = dossier?.dao_status === 'ready'
  const daoProcessing = dossier?.has_dao && !daoReady && dossier?.dao_status !== 'failed'
  const daoFailed = dossier?.dao_status === 'failed'

  return (
    <div className="dash">
      <header className="dash-head">
        <p className="eyebrow">Dossier</p>
        {editing ? (
          <form
            className="card-form dossier-edit-form"
            onSubmit={async (e) => {
              e.preventDefault()
              if (!id) return
              const form = new FormData(e.currentTarget)
              setEditBusy(true)
              setEditError(null)
              try {
                const updated = await dossierApi.update(id, {
                  project_name: String(form.get('project_name') || ''),
                  client_name: String(form.get('client_name') || ''),
                  dao_reference: String(form.get('dao_reference') || ''),
                })
                setDossier(updated)
                setEditing(false)
              } catch (err) {
                setEditError(err instanceof Error ? err.message : String(err))
              } finally {
                setEditBusy(false)
              }
            }}
          >
            <input type="text" name="project_name" defaultValue={dossier?.project_name ?? ''} required placeholder="Nom du projet *" />
            <input type="text" name="client_name" defaultValue={dossier?.client_name ?? ''} placeholder="Client / maître d’ouvrage" />
            <input type="text" name="dao_reference" defaultValue={dossier?.dao_reference ?? ''} placeholder="Référence DAO" />
            <button type="submit" className="btn-primary" disabled={editBusy}>
              {editBusy ? 'Enregistrement…' : 'Enregistrer'}
            </button>
            <button type="button" className="btn-ghost" onClick={() => { setEditing(false); setEditError(null) }}>
              Annuler
            </button>
            {editError ? <p className="form-error">{editError}</p> : null}
          </form>
        ) : (
          <>
            <h1>{dossier?.project_name || '—'}</h1>
            <p className="lede">
              {dossier?.client_name ? `Client : ${dossier.client_name}` : 'Client non renseigné'}
              {dossier?.dao_reference ? ` · Réf. ${dossier.dao_reference}` : ''}
              {dossier ? ` · Statut : ${dossier.status}` : ''}
            </p>
          </>
        )}
        <div className="dossier-actions">
          <button type="button" className="btn-ghost" onClick={() => navigate('/app/dossiers')}>
            ← Retour aux dossiers
          </button>
          {!editing ? (
            <button type="button" className="btn-ghost" onClick={() => setEditing(true)}>
              ✎ Modifier le dossier
            </button>
          ) : null}
          <button
            type="button"
            className="btn-primary"
            disabled={busy || !daoReady || dossier?.status === 'analyzing'}
            title={
              !dossier?.has_dao
                ? 'Chargez d’abord le DAO dans l’onglet Documents & pièces'
                : daoProcessing
                  ? 'Lecture du DAO en cours (OCR pour un scan) — patientez'
                  : daoFailed
                    ? 'La lecture du DAO a échoué — rechargez le fichier'
                    : dossier?.status === 'analyzing'
                      ? 'Extraction des exigences et du plan en cours — patientez'
                      : undefined
            }
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
            {busy || dossier?.status === 'analyzing' ? 'Analyse en cours…' : 'Analyser le DAO'}
          </button>
        </div>
      </header>

      {error ? <p className="form-error">{error}</p> : null}

      {dossier && !dossier.has_dao ? (
        <div className="alert-banner alert-warn">
          Aucun DAO chargé pour ce dossier. Ouvrez l’onglet « Documents &amp; pièces » pour déposer le DAO
          (PDF texte ou scanné — l’OCR est automatique), puis cliquez sur « Analyser le DAO ».
        </div>
      ) : null}

      {daoProcessing ? (
        <div className="alert-banner alert-warn">
          ⏳ Lecture du DAO « {dossier?.dao_filename} » en cours — statut : {dossier?.dao_status}. Si c’est un
          PDF scanné, l’OCR peut prendre plusieurs minutes selon le nombre de pages. Le bouton « Analyser le
          DAO » se débloque automatiquement dès que c’est prêt.
        </div>
      ) : null}

      {daoFailed ? (
        <div className="alert-banner alert-danger">
          ❌ La lecture du DAO « {dossier?.dao_filename} » a échoué : {dossier?.dao_ingest_error || 'erreur inconnue'}.
          Rechargez le fichier dans l’onglet Documents &amp; pièces (un scan de mauvaise qualité peut nécessiter
          une nouvelle numérisation).
        </div>
      ) : null}

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
      {tab === 'plan' ? (
        <PlanTab
          dossierId={id}
          onOpenSection={(key) => {
            setOpenSectionKey(key)
            setTab('sections')
          }}
        />
      ) : null}
      {tab === 'sections' ? <SectionsTab dossierId={id} initialKey={openSectionKey} /> : null}
      {tab === 'documents' ? <DocumentsTab dossierId={id} dossier={dossier} onDaoChange={reload} /> : null}
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
  // Feedback immédiat au clic, le temps que la requête HTTP parte — la
  // vérité sur "est-ce que ça tourne encore" vient ensuite de e.statut
  // (posé de façon synchrone par le backend avant même de répondre), pas
  // de cet état local.
  const [relance, setRelance] = useState<string | null>(null)
  const [preuveOpen, setPreuveOpen] = useState<Exigence | null>(null)
  const [preuves, setPreuves] = useState<ExigencePreuve[]>([])
  const [preuvesLoading, setPreuvesLoading] = useState(false)
  const [preuvesError, setPreuvesError] = useState<string | null>(null)

  async function openPreuves(e: Exigence) {
    setPreuveOpen(e)
    setPreuves([])
    setPreuvesError(null)
    setPreuvesLoading(true)
    try {
      setPreuves(await dossierApi.preuvesExigence(dossierId, e.id))
    } catch (err) {
      setPreuvesError(err instanceof Error ? err.message : String(err))
    } finally {
      setPreuvesLoading(false)
    }
  }

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

  // La recherche CRAG (jusqu'à 3 itérations LLM) tourne en tâche de fond
  // côté serveur bien après que la requête POST ait répondu — sans ce
  // polling, le résultat final (couverte / non_couverte / a_revoir)
  // n'apparaît jamais tant qu'on ne quitte/revient pas sur l'onglet.
  useEffect(() => {
    const anyRunning = rows.some((r) => r.statut === 'en_cours')
    if (!anyRunning) return
    const t = window.setInterval(() => load(), 2500)
    return () => window.clearInterval(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows])

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
                <td>
                  {e.preuves_chunks.length ? (
                    <button type="button" className="btn-link" onClick={() => void openPreuves(e)}>
                      {e.preuves_chunks.length}
                    </button>
                  ) : (
                    '—'
                  )}
                </td>
                <td>
                  <button
                    type="button"
                    className="btn-ghost"
                    disabled={relance === e.id || e.statut === 'en_cours'}
                    onClick={async () => {
                      setRelance(e.id)
                      setError(null)
                      try {
                        await dossierApi.relancerRechercheExigence(dossierId, e.id)
                        await load()
                      } catch (err) {
                        // 409 = déjà en cours (double-clic rattrapé côté
                        // serveur) — pas une vraie erreur à afficher en rouge,
                        // juste un signe que le polling va bientôt reprendre.
                        if (!(err instanceof ApiError) || err.status !== 409) {
                          setError(err instanceof Error ? err.message : String(err))
                        }
                        await load()
                      } finally {
                        setRelance(null)
                      }
                    }}
                  >
                    {relance === e.id ? 'Lancement…' : e.statut === 'en_cours' ? 'Recherche en cours…' : 'Relancer la recherche'}
                  </button>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>

      {preuveOpen ? (
        <PreuvesModal
          libelle={preuveOpen.libelle}
          preuves={preuves}
          loading={preuvesLoading}
          error={preuvesError}
          onClose={() => setPreuveOpen(null)}
        />
      ) : null}
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

function SectionsTab({ dossierId, initialKey }: { dossierId: string; initialKey?: string | null }) {
  const [outline, setOutline] = useState<OutlineItemApi[]>([])
  const [selected, setSelected] = useState<string | null>(initialKey ?? null)
  const [detail, setDetail] = useState<SectionDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [regenComment, setRegenComment] = useState('')
  const [editText, setEditText] = useState('')
  const [editing, setEditing] = useState(false)

  // Exigences liées à la section sélectionnée (§ liaison exigences/sections).
  const [sectionExigences, setSectionExigences] = useState<SectionExigenceLink[]>([])
  const [exigencesError, setExigencesError] = useState<string | null>(null)
  const [linkBusy, setLinkBusy] = useState<string | null>(null)
  const [allExigences, setAllExigences] = useState<Exigence[]>([])
  const [addExigenceId, setAddExigenceId] = useState('')
  // Parité avec l'onglet Exigences : relancer la recherche et consulter les
  // preuves directement depuis la section, pas seulement confirmer/retirer.
  const [exigenceRelance, setExigenceRelance] = useState<string | null>(null)
  const [preuveOpen, setPreuveOpen] = useState<SectionExigenceLink | null>(null)
  const [preuves, setPreuves] = useState<ExigencePreuve[]>([])
  const [preuvesLoading, setPreuvesLoading] = useState(false)
  const [preuvesError, setPreuvesError] = useState<string | null>(null)
  // Statut du job global de classification (bouton en haut de l'onglet).
  const [classifStatus, setClassifStatus] = useState<string | null>(null)
  const [classifBusy, setClassifBusy] = useState(false)
  const [classifError, setClassifError] = useState<string | null>(null)

  // "Pourquoi ce contenu ?" (§ traçabilité retrieval_traces).
  const [tracesOpen, setTracesOpen] = useState(false)
  const [traces, setTraces] = useState<RetrievalTraceEntry[]>([])
  const [tracesLoading, setTracesLoading] = useState(false)
  const [tracesError, setTracesError] = useState<string | null>(null)

  useEffect(() => {
    dossierApi
      .outline(dossierId)
      .then((rows) => {
        setOutline(rows)
        if (rows.length && !selected) setSelected(initialKey ?? rows[0].key)
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
    dossierApi.exigences(dossierId).then(setAllExigences).catch(() => {})
    dossierApi.get(dossierId).then((d) => setClassifStatus(d.classification_status)).catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dossierId])

  // Le job de classification tourne en tâche de fond (ARQ) — sans ce
  // polling, "running" resterait affiché indéfiniment après la fin réelle
  // du job (même bug de principe que la relance de recherche d'exigence).
  useEffect(() => {
    if (classifStatus !== 'running') return
    const t = window.setInterval(() => {
      dossierApi
        .get(dossierId)
        .then((d) => {
          setClassifStatus(d.classification_status)
          // Le job vient de terminer : les liens exigence/section de la
          // section actuellement ouverte ont pu changer sans qu'on le sache.
          if (d.classification_status !== 'running' && selected) loadSectionExigences(selected)
        })
        .catch(() => {})
    }, 3000)
    return () => window.clearInterval(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dossierId, classifStatus, selected])

  useEffect(() => {
    if (!selected) return
    dossierApi
      .getSection(dossierId, selected)
      .then((d) => {
        setDetail(d)
        setEditText(d.markdown || '')
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
    loadSectionExigences(selected)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dossierId, selected])

  // Même besoin qu'onglet Exigences : la recherche CRAG tourne en tâche de
  // fond côté serveur bien après la réponse HTTP — sans ce polling, le
  // résultat final n'apparaît jamais tant qu'on ne change pas d'onglet.
  useEffect(() => {
    if (!selected) return
    const anyRunning = sectionExigences.some((r) => r.statut_couverture === 'en_cours')
    if (!anyRunning) return
    const t = window.setInterval(() => loadSectionExigences(selected), 2500)
    return () => window.clearInterval(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sectionExigences, selected])

  async function openSectionPreuve(se: SectionExigenceLink) {
    setPreuveOpen(se)
    setPreuves([])
    setPreuvesError(null)
    setPreuvesLoading(true)
    try {
      setPreuves(await dossierApi.preuvesExigence(dossierId, se.exigence_id))
    } catch (e) {
      setPreuvesError(e instanceof Error ? e.message : String(e))
    } finally {
      setPreuvesLoading(false)
    }
  }

  async function loadSectionExigences(key: string) {
    setExigencesError(null)
    try {
      setSectionExigences(await dossierApi.sectionExigences(dossierId, key))
    } catch (e) {
      setExigencesError(e instanceof Error ? e.message : String(e))
    }
  }

  async function refreshDetail() {
    if (!selected) return
    const d = await dossierApi.getSection(dossierId, selected)
    setDetail(d)
    setEditText(d.markdown || '')
  }

  const item = outline.find((o) => o.key === selected)
  const linkedIds = new Set(sectionExigences.map((s) => s.exigence_id))
  const addableExigences = allExigences.filter((e) => !linkedIds.has(e.id))

  return (
    <div className="sections-tab">
      <div className="sections-toolbar">
        <button
          type="button"
          className="btn-ghost"
          disabled={classifBusy || classifStatus === 'running'}
          onClick={async () => {
            setClassifBusy(true)
            setClassifError(null)
            try {
              await dossierApi.classifierSections(dossierId)
              setClassifStatus('running')
            } catch (e) {
              setClassifError(e instanceof Error ? e.message : String(e))
            } finally {
              setClassifBusy(false)
            }
          }}
        >
          {classifStatus === 'running' ? 'Classification en cours…' : '🤖 Classer les exigences par section'}
        </button>
        {classifStatus === 'ready' ? (
          <span className="muted docs-relaunch-hint">Dernière classification terminée.</span>
        ) : null}
        {classifStatus === 'failed' ? <span className="form-error">La classification a échoué.</span> : null}
        {classifError ? <span className="form-error">{classifError}</span> : null}
      </div>
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
              {detail?.markdown ? (
                <>
                  {' · '}
                  <button
                    type="button"
                    className="btn-link"
                    onClick={async () => {
                      setTracesOpen(true)
                      setTracesLoading(true)
                      setTracesError(null)
                      try {
                        setTraces(await dossierApi.sectionTraces(dossierId, item.key))
                      } catch (e) {
                        setTracesError(e instanceof Error ? e.message : String(e))
                      } finally {
                        setTracesLoading(false)
                      }
                    }}
                  >
                    Pourquoi ce contenu ?
                  </button>
                </>
              ) : null}
            </p>

            <div className="section-exigences">
              <p className="docs-timeline-title">Exigences liées à cette section</p>
              {exigencesError ? <p className="form-error">{exigencesError}</p> : null}
              {sectionExigences.length === 0 ? (
                <p className="muted">
                  Aucune exigence associée — classez automatiquement (bouton en haut) ou ajoutez-en une ci-dessous.
                </p>
              ) : (
                <ul className="section-exigences-list">
                  {sectionExigences.map((se) => (
                    <li key={se.exigence_id} className="section-exigence-item">
                      <span className={STATUT_CLASS[se.statut_couverture] || 'pill'}>
                        {STATUT_LABEL[se.statut_couverture] || se.statut_couverture}
                      </span>
                      <span className="section-exigence-libelle">
                        {se.libelle}
                        {se.obligatoire ? ' *' : ''}
                      </span>
                      {se.origine === 'llm' && se.statut_lien === 'proposee' ? (
                        <span className="pill pill-muted">proposée par l'IA</span>
                      ) : null}
                      {se.preuves_chunks.length ? (
                        <button type="button" className="btn-link" onClick={() => void openSectionPreuve(se)}>
                          {se.preuves_chunks.length} preuve{se.preuves_chunks.length > 1 ? 's' : ''}
                        </button>
                      ) : null}
                      <span className="row-actions">
                        <button
                          type="button"
                          className="btn-ghost btn-sm"
                          disabled={exigenceRelance === se.exigence_id || se.statut_couverture === 'en_cours'}
                          onClick={async () => {
                            setExigenceRelance(se.exigence_id)
                            setExigencesError(null)
                            try {
                              await dossierApi.relancerRechercheExigence(dossierId, se.exigence_id)
                              if (selected) await loadSectionExigences(selected)
                            } catch (err) {
                              if (!(err instanceof ApiError) || err.status !== 409) {
                                setExigencesError(err instanceof Error ? err.message : String(err))
                              }
                              if (selected) await loadSectionExigences(selected)
                            } finally {
                              setExigenceRelance(null)
                            }
                          }}
                        >
                          {exigenceRelance === se.exigence_id
                            ? 'Lancement…'
                            : se.statut_couverture === 'en_cours'
                              ? 'Recherche en cours…'
                              : 'Relancer la recherche'}
                        </button>
                        {se.origine === 'llm' && se.statut_lien === 'proposee' ? (
                          <button
                            type="button"
                            className="btn-ghost btn-sm"
                            disabled={linkBusy === se.exigence_id}
                            onClick={async () => {
                              if (!selected) return
                              setLinkBusy(se.exigence_id)
                              try {
                                await dossierApi.confirmSectionExigence(dossierId, selected, se.exigence_id)
                                await loadSectionExigences(selected)
                              } catch (e) {
                                setExigencesError(e instanceof Error ? e.message : String(e))
                              } finally {
                                setLinkBusy(null)
                              }
                            }}
                          >
                            Confirmer
                          </button>
                        ) : null}
                        <button
                          type="button"
                          className="btn-ghost btn-sm"
                          disabled={linkBusy === se.exigence_id}
                          onClick={async () => {
                            if (!selected) return
                            setLinkBusy(se.exigence_id)
                            try {
                              await dossierApi.unlinkSectionExigence(dossierId, selected, se.exigence_id)
                              await loadSectionExigences(selected)
                            } catch (e) {
                              setExigencesError(e instanceof Error ? e.message : String(e))
                            } finally {
                              setLinkBusy(null)
                            }
                          }}
                        >
                          Retirer
                        </button>
                      </span>
                    </li>
                  ))}
                </ul>
              )}
              {addableExigences.length > 0 ? (
                <div className="section-exigence-add">
                  <select value={addExigenceId} onChange={(e) => setAddExigenceId(e.target.value)}>
                    <option value="">+ Associer une exigence…</option>
                    {addableExigences.map((e) => (
                      <option key={e.id} value={e.id}>
                        {e.libelle.slice(0, 80)}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    className="btn-ghost btn-sm"
                    disabled={!addExigenceId || linkBusy === addExigenceId}
                    onClick={async () => {
                      if (!selected || !addExigenceId) return
                      setLinkBusy(addExigenceId)
                      try {
                        await dossierApi.linkSectionExigence(dossierId, selected, addExigenceId)
                        setAddExigenceId('')
                        await loadSectionExigences(selected)
                      } catch (e) {
                        setExigencesError(e instanceof Error ? e.message : String(e))
                      } finally {
                        setLinkBusy(null)
                      }
                    }}
                  >
                    Ajouter
                  </button>
                </div>
              ) : null}
            </div>

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
              // Rendu sur fond papier : la variante "document" écrit en encre
              // sombre, illisible directement sur le panneau sombre.
              <div className="section-doc-scroll">
                <div className="doc-page">
                  <MarkdownPreview markdown={detail.markdown} variant="document" />
                </div>
              </div>
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
      {tracesOpen ? (
        <TracesModal
          title={item?.title || ''}
          traces={traces}
          loading={tracesLoading}
          error={tracesError}
          onClose={() => setTracesOpen(false)}
        />
      ) : null}
      {preuveOpen ? (
        <PreuvesModal
          libelle={preuveOpen.libelle}
          preuves={preuves}
          loading={preuvesLoading}
          error={preuvesError}
          onClose={() => setPreuveOpen(null)}
        />
      ) : null}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Documents (annexes) — §3.7
// ---------------------------------------------------------------------------

const DAO_STATUS_LABEL: Record<string, string> = {
  pending: 'En file d’attente…',
  processing: 'Lecture en cours (OCR si scan)…',
  ready: 'Prêt',
  failed: 'Échec',
}

function DocumentsTab({
  dossierId,
  dossier,
  onDaoChange,
}: {
  dossierId: string
  dossier: Dossier | null
  onDaoChange: () => Promise<void>
}) {
  const [rows, setRows] = useState<DocItem[]>([])
  const [error, setError] = useState<string | null>(null)
  const [daoError, setDaoError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [daoBusy, setDaoBusy] = useState(false)

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
      <h3>DAO de ce dossier</h3>
      <p className="muted">
        Le document de consultation (RC/CCTP/CCAP…) à partir duquel l'analyse (§9) extrait les exigences et
        le plan. PDF texte natif OU PDF scanné (OCR automatique via PaddleOCR) — même formulaire, même
        traitement, seul le temps de lecture diffère. Un seul DAO courant par dossier — un nouveau dépôt
        remplace le lien.
      </p>
      {dossier?.has_dao ? (
        <p>
          📄 <strong>{dossier.dao_filename}</strong> — statut :{' '}
          <span className={`pill ${dossier.dao_status === 'ready' ? 'pill-ok' : dossier.dao_status === 'failed' ? 'pill-danger' : 'pill-warn'}`}>
            {DAO_STATUS_LABEL[dossier.dao_status || ''] || dossier.dao_status}
          </span>
          {dossier.dao_status === 'failed' && dossier.dao_ingest_error ? (
            <span className="form-error"> — {dossier.dao_ingest_error}</span>
          ) : null}
        </p>
      ) : (
        <p className="muted">Aucun DAO chargé pour l’instant.</p>
      )}
      <form
        className="card-form"
        onSubmit={async (e) => {
          e.preventDefault()
          const input = (e.currentTarget.elements.namedItem('daofile') as HTMLInputElement) || null
          const file = input?.files?.[0]
          if (!file) return
          setDaoBusy(true)
          setDaoError(null)
          try {
            await docsApi.upload(file, 'dao_courant', 'rc', dossierId)
            if (input) input.value = ''
            await onDaoChange()
          } catch (err) {
            setDaoError(err instanceof Error ? err.message : String(err))
          } finally {
            setDaoBusy(false)
          }
        }}
      >
        <input
          type="file"
          name="daofile"
          accept=".pdf,.docx,.txt,.md,.jpg,.jpeg,.png,.tiff,.webp"
          required
        />
        <button type="submit" className="btn-primary" disabled={daoBusy}>
          {daoBusy ? 'Envoi…' : dossier?.has_dao ? 'Remplacer le DAO' : 'Charger le DAO'}
        </button>
      </form>
      {daoError ? <p className="form-error">{daoError}</p> : null}

      <h3>Annexes — aide ponctuelle</h3>
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

      <PiecesChecklist dossierId={dossierId} projectName={dossier?.project_name} allDocs={rows} />
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

function PiecesChecklist({
  dossierId,
  projectName,
  allDocs,
}: {
  dossierId: string
  projectName?: string | null
  allDocs: DocItem[]
}) {
  const [pieces, setPieces] = useState<DossierPieceApi[]>([])
  const [patrimoineDocs, setPatrimoineDocs] = useState<DocItem[]>([])
  const [error, setError] = useState<string | null>(null)
  const [newLibelle, setNewLibelle] = useState('')
  const [newObligatoire, setNewObligatoire] = useState(true)
  const [addBusy, setAddBusy] = useState(false)
  const [uploadBusy, setUploadBusy] = useState<string | null>(null)
  const [exportBusy, setExportBusy] = useState(false)

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
      <div className="pieces-head">
        <div>
          <h3>Checklist administrative</h3>
          <p className="muted">
            Pièces attendues — issues du règlement de consultation, d'une liste standard, ou ajoutées à la
            main ci-dessous. Déposez le fichier directement sur sa ligne, ou choisissez un document déjà en
            patrimoine.
          </p>
        </div>
        <button
          type="button"
          className="btn-primary btn-sm"
          disabled={exportBusy || pieces.length === 0}
          onClick={async () => {
            setExportBusy(true)
            setError(null)
            try {
              await downloadDossierPieces(dossierId, projectName || undefined)
            } catch (e) {
              setError(e instanceof Error ? e.message : String(e))
            } finally {
              setExportBusy(false)
            }
          }}
        >
          {exportBusy ? 'Génération…' : '⬇ Exporter le dossier administratif (PDF)'}
        </button>
      </div>

      <form
        className="pieces-add-form"
        onSubmit={async (e) => {
          e.preventDefault()
          const libelle = newLibelle.trim()
          if (!libelle) return
          setAddBusy(true)
          setError(null)
          try {
            await dossierApi.creerPiece(dossierId, libelle, newObligatoire)
            setNewLibelle('')
            setNewObligatoire(true)
            await load()
          } catch (err) {
            setError(err instanceof Error ? err.message : String(err))
          } finally {
            setAddBusy(false)
          }
        }}
      >
        <input
          type="text"
          placeholder="Nom de la rubrique (ex. Certificat ISO 9001)"
          value={newLibelle}
          onChange={(e) => setNewLibelle(e.target.value)}
        />
        <label className="pieces-add-checkbox">
          <input type="checkbox" checked={newObligatoire} onChange={(e) => setNewObligatoire(e.target.checked)} />
          Obligatoire
        </label>
        <button type="submit" className="btn-ghost" disabled={addBusy || !newLibelle.trim()}>
          {addBusy ? 'Ajout…' : '+ Ajouter une rubrique'}
        </button>
      </form>

      {error ? <p className="form-error">{error}</p> : null}
      <table>
        <thead>
          <tr>
            <th>Pièce</th>
            <th>Statut</th>
            <th>Déposer un fichier</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {pieces.length === 0 ? (
            <tr>
              <td colSpan={4} className="muted">
                Aucune checklist — lancez « Analyser le DAO » pour la générer, ou ajoutez une rubrique
                ci-dessus.
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
                  <input
                    type="file"
                    className="pieces-file-input"
                    disabled={uploadBusy === p.id}
                    onChange={async (e) => {
                      const file = e.target.files?.[0]
                      if (!file) return
                      setUploadBusy(p.id)
                      setError(null)
                      try {
                        await dossierApi.uploadPiece(dossierId, p.id, file)
                        await load()
                      } catch (err) {
                        setError(err instanceof Error ? err.message : String(err))
                      } finally {
                        setUploadBusy(null)
                        e.target.value = ''
                      }
                    }}
                  />
                  {uploadBusy === p.id ? <span className="muted"> envoi…</span> : null}
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
                    <option value="">…ou choisir un document existant</option>
                    {[...allDocs, ...patrimoineDocs].map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.filename}
                      </option>
                    ))}
                  </select>
                </td>
                <td>
                  {p.source === 'manuel' ? (
                    <button
                      type="button"
                      className="btn-ghost btn-sm"
                      onClick={async () => {
                        try {
                          await dossierApi.retirerPiece(dossierId, p.id)
                          await load()
                        } catch (err) {
                          setError(err instanceof Error ? err.message : String(err))
                        }
                      }}
                    >
                      Retirer
                    </button>
                  ) : null}
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
