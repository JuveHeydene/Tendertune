import type { RetrievalTraceEntry } from '../api/client'

const GRADE_LABEL: Record<string, string> = {
  correct: 'Correct',
  ambigu: 'Ambigu',
  incorrect: 'Incorrect',
}

const GRADE_CLASS: Record<string, string> = {
  correct: 'pill pill-ok',
  ambigu: 'pill pill-warn',
  incorrect: 'pill pill-danger',
}

function groupBySousQuestion(traces: RetrievalTraceEntry[]): Map<number, RetrievalTraceEntry[]> {
  const groups = new Map<number, RetrievalTraceEntry[]>()
  for (const t of traces) {
    const list = groups.get(t.sous_question_index) || []
    list.push(t)
    groups.set(t.sous_question_index, list)
  }
  return groups
}

export function TracesModal({
  title,
  traces,
  loading,
  error,
  onClose,
}: {
  title: string
  traces: RetrievalTraceEntry[]
  loading: boolean
  error: string | null
  onClose: () => void
}) {
  const groups = groupBySousQuestion(traces)

  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div
        className="modal modal--doc-details"
        role="dialog"
        aria-modal="true"
        aria-labelledby="traces-modal-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-head">
          <h2 id="traces-modal-title">Pourquoi cette réponse ? — {title}</h2>
          <button type="button" className="btn-ghost" onClick={onClose}>
            Fermer
          </button>
        </div>
        <p className="modal-copy">
          Chaque tentative de recherche (requête utilisée, filtres, note de pertinence, chunks
          retournés) qui a nourri ce contenu.
        </p>
        {error ? <p className="form-error">{error}</p> : null}
        <div className="attr-grid--scroll">
          {loading ? (
            <p className="muted">Chargement…</p>
          ) : traces.length === 0 ? (
            <p className="muted">
              Aucune trace disponible — soit rien n'a été cherché (réponse conversationnelle), soit
              ce contenu date d'avant l'activation de cette traçabilité.
            </p>
          ) : (
            Array.from(groups.entries()).map(([idx, attempts]) => (
              <div key={idx} className="trace-group">
                <p className="docs-timeline-title">
                  Sous-question {idx + 1}
                  {attempts[0]?.sous_question_texte ? ` — ${attempts[0].sous_question_texte}` : ''}
                </p>
                {attempts.map((t, i) => (
                  <div key={i} className="trace-attempt">
                    <div className="trace-attempt-head">
                      <span className="pill pill-muted">{t.expert}</span>
                      <span className="muted">tentative {t.tentative}</span>
                      {t.grade ? (
                        <span className={GRADE_CLASS[t.grade] || 'pill'}>{GRADE_LABEL[t.grade] || t.grade}</span>
                      ) : (
                        <span className="pill pill-muted">non gradé</span>
                      )}
                      {t.abstention ? <span className="pill pill-danger">abstention</span> : null}
                    </div>
                    <p className="trace-query">« {t.query_utilisee} »</p>
                    {t.filtres && Object.keys(t.filtres).length > 0 ? (
                      <p className="muted trace-filtres">
                        Filtres : {Object.entries(t.filtres).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(' · ')}
                      </p>
                    ) : null}
                    <p className="muted">
                      {t.chunks_retournes.length} extrait{t.chunks_retournes.length > 1 ? 's' : ''} retourné
                      {t.chunks_retournes.length > 1 ? 's' : ''}
                      {t.chunks_retournes.length > 0
                        ? ' · scores : ' +
                          t.chunks_retournes
                            .slice(0, 5)
                            .map((c) => (typeof c.score === 'number' ? c.score.toFixed(2) : '?'))
                            .join(', ')
                        : ''}
                    </p>
                  </div>
                ))}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
