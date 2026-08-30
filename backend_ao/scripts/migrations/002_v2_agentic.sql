-- Migration V2 — architecture agentique (SMA)
-- Toutes les décisions validées dans Nouvelle_Architecture/*.md
-- Additive uniquement : aucune colonne supprimée, aucune donnée perdue.
-- Idempotent (IF NOT EXISTS / DROP ... IF EXISTS) pour pouvoir être rejoué sans casse.

BEGIN;

-- ============================================================
-- 1. chunks.section_type — routage dynamique des experts (§3.1)
-- ============================================================
ALTER TABLE chunks
    ADD COLUMN IF NOT EXISTS section_type VARCHAR(16);

ALTER TABLE chunks DROP CONSTRAINT IF EXISTS chunks_section_type_check;
ALTER TABLE chunks ADD CONSTRAINT chunks_section_type_check
    CHECK (section_type IS NULL OR section_type IN
        ('rc', 'ccap', 'cctp', 'dpgf', 'bpu', 'memoire', 'reference', 'autre'));

CREATE INDEX IF NOT EXISTS idx_chunks_section_type ON chunks (section_type);

-- Recherche sparse (BM25-like) — Postgres full-text, config française.
-- Colonne générée : recalculée automatiquement par Postgres à chaque
-- UPDATE de `text`, jamais écrite manuellement par l'application.
ALTER TABLE chunks
    ADD COLUMN IF NOT EXISTS text_fts tsvector
    GENERATED ALWAYS AS (to_tsvector('french', coalesce(text, ''))) STORED;

CREATE INDEX IF NOT EXISTS idx_chunks_text_fts ON chunks USING GIN (text_fts);

-- ============================================================
-- 2. generations.summary_short — résumé de dossier précalculé (§2.3)
-- ============================================================
ALTER TABLE generations
    ADD COLUMN IF NOT EXISTS summary_short TEXT;

-- ============================================================
-- 3. retrieval_traces — observabilité + métriques d'évaluation (§1.3)
-- ============================================================
CREATE TABLE IF NOT EXISTS retrieval_traces (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    message_id          UUID REFERENCES messages(id) ON DELETE CASCADE,
    generation_id       UUID REFERENCES generations(id) ON DELETE SET NULL,
    sous_question_index INTEGER NOT NULL DEFAULT 0,
    sous_question_texte TEXT,
    expert              VARCHAR(16) NOT NULL,
    tentative           INTEGER NOT NULL,
    query_utilisee      TEXT NOT NULL,
    filtres             JSONB NOT NULL DEFAULT '{}'::jsonb,
    grade               VARCHAR(16),
    grade_method        VARCHAR(16),
    chunks_retournes    JSONB NOT NULL DEFAULT '[]'::jsonb,
    abstention          BOOLEAN NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT retrieval_traces_expert_check
        CHECK (expert IN ('juridique', 'technique', 'financier', 'graphe', 'patrimoine')),
    CONSTRAINT retrieval_traces_tentative_check CHECK (tentative BETWEEN 1 AND 3),
    CONSTRAINT retrieval_traces_grade_check
        CHECK (grade IS NULL OR grade IN ('correct', 'ambigu', 'incorrect')),
    CONSTRAINT retrieval_traces_grade_method_check
        CHECK (grade_method IS NULL OR grade_method IN ('seuil', 'llm_juge'))
);

CREATE INDEX IF NOT EXISTS idx_traces_message ON retrieval_traces (message_id);
CREATE INDEX IF NOT EXISTS idx_traces_tenant_expert_grade ON retrieval_traces (tenant_id, expert, grade);

-- ============================================================
-- 4. documents.dossier_id + doc_role='annexe' (§1.5)
-- ============================================================
ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS dossier_id UUID REFERENCES dossiers(id) ON DELETE CASCADE;

ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_doc_role_check;
ALTER TABLE documents ADD CONSTRAINT documents_doc_role_check
    CHECK (doc_role IN ('patrimoine', 'dao_courant', 'dao_archive', 'annexe'));

ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_doc_type_check;
ALTER TABLE documents ADD CONSTRAINT documents_doc_type_check
    CHECK (doc_type IS NULL OR doc_type IN
        ('rc', 'cctp', 'ccap', 'memoire', 'reference', 'dpgf', 'bpu', 'administratif', 'autre'));

ALTER TABLE documents DROP CONSTRAINT IF EXISTS annexe_requires_dossier;
ALTER TABLE documents ADD CONSTRAINT annexe_requires_dossier
    CHECK ((doc_role = 'annexe') = (dossier_id IS NOT NULL));

CREATE INDEX IF NOT EXISTS idx_documents_dossier ON documents (dossier_id) WHERE dossier_id IS NOT NULL;

-- ============================================================
-- 5. outline_items.archetype — spécialisation du prompt de génération (§10)
-- ============================================================
ALTER TABLE outline_items
    ADD COLUMN IF NOT EXISTS archetype VARCHAR(16) NOT NULL DEFAULT 'factuelle';

ALTER TABLE outline_items DROP CONSTRAINT IF EXISTS outline_items_archetype_check;
ALTER TABLE outline_items ADD CONSTRAINT outline_items_archetype_check
    CHECK (archetype IN ('institutionnelle', 'factuelle', 'narrative', 'conformite'));

-- ============================================================
-- 6. dossier_pieces — checklist administrative (§5.3)
-- ============================================================
CREATE TABLE IF NOT EXISTS dossier_pieces (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dossier_id    UUID NOT NULL REFERENCES dossiers(id) ON DELETE CASCADE,
    libelle       VARCHAR(255) NOT NULL,
    obligatoire   BOOLEAN NOT NULL DEFAULT TRUE,
    document_id   UUID REFERENCES documents(id) ON DELETE SET NULL,
    statut        VARCHAR(32) NOT NULL DEFAULT 'manquant',
    source        VARCHAR(16) NOT NULL DEFAULT 'standard',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT dossier_pieces_statut_check
        CHECK (statut IN ('manquant', 'trouve_patrimoine', 'a_uploader', 'fourni')),
    CONSTRAINT dossier_pieces_source_check CHECK (source IN ('rc', 'standard'))
);

CREATE INDEX IF NOT EXISTS idx_dossier_pieces_dossier ON dossier_pieces (dossier_id);

COMMIT;
