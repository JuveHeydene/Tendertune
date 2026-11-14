import type { ExigencePreuve } from '../api/client'

export function PreuvesModal({
  libelle,
  preuves,
  loading,
  error,
  onClose,
}: {
  libelle: string
  preuves: ExigencePreuve[]
  loading: boolean
  error: string | null
  onClose: () => void
}) {
  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div
        className="modal modal--doc-details"
        role="dialog"
        aria-modal="true"
        aria-labelledby="preuves-modal-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-head">
          <h2 id="preuves-modal-title">Preuves — {libelle}</h2>
          <button type="button" className="btn-ghost" onClick={onClose}>
            Fermer
          </button>
        </div>
        <p className="modal-copy">
          Extraits du patrimoine jugés pertinents par la recherche (du plus au moins pertinent).
        </p>
        {error ? <p className="form-error">{error}</p> : null}
        <div className="attr-grid--scroll">
          {loading ? (
            <p className="muted">Chargement…</p>
          ) : preuves.length === 0 ? (
            <p className="muted">Aucune preuve trouvée (peut-être supprimée depuis).</p>
          ) : (
            preuves.map((p) => (
              <div key={p.chunk_id} className="preuve-card">
                <p className="preuve-source">
                  {p.document_filename || 'Document inconnu'}
                  {p.page ? ` · p.${p.page}` : ''}
                  {p.heading_path ? ` · ${p.heading_path}` : ''}
                </p>
                <p className="preuve-text">{p.text}</p>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
