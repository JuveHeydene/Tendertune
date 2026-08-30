-- Schéma V1 (auth + métier). Exécuté au premier start Postgres (volume vide).
-- Référence : Fichier/champsdeBase_et_contraites_workflow.md
-- documents.dossier_origine_id est ajouté APRÈS dossiers (FK circulaire).

CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------------------
-- Auth
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS tenants (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug        VARCHAR(64)  NOT NULL UNIQUE,
    name        VARCHAR(255) NOT NULL,
    email       VARCHAR(255) NOT NULL,
    phone       VARCHAR(20),
    address     TEXT,
    config      JSONB NOT NULL DEFAULT '{}'::jsonb,
    status      VARCHAR(32) NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'suspended')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tenants_slug ON tenants (slug);
CREATE INDEX IF NOT EXISTS idx_tenants_status ON tenants (status);

CREATE TABLE IF NOT EXISTS users (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
    username         VARCHAR(64)  NOT NULL,
    email            VARCHAR(255) NOT NULL,
    hashed_password  VARCHAR(255) NOT NULL,
    first_name       VARCHAR(128),
    last_name        VARCHAR(128),
    phone            VARCHAR(20),
    role             VARCHAR(32) NOT NULL DEFAULT 'redacteur'
                     CHECK (role IN ('admin', 'manager', 'redacteur', 'consultant')),
    permissions      JSONB NOT NULL DEFAULT '{}'::jsonb,
    status           VARCHAR(32) NOT NULL DEFAULT 'active'
                     CHECK (status IN ('active', 'inactive', 'suspended')),
    last_login_at    TIMESTAMPTZ,
    login_attempts   INTEGER NOT NULL DEFAULT 0,
    locked_until     TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT unique_tenant_email UNIQUE (tenant_id, email),
    CONSTRAINT unique_tenant_username UNIQUE (tenant_id, username)
);

CREATE INDEX IF NOT EXISTS idx_users_tenant ON users (tenant_id);
CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);
CREATE INDEX IF NOT EXISTS idx_users_role ON users (tenant_id, role);
CREATE INDEX IF NOT EXISTS idx_users_status ON users (tenant_id, status);

CREATE TABLE IF NOT EXISTS sessions (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    token_hash        VARCHAR(255) NOT NULL UNIQUE,
    user_agent        TEXT,
    ip_address        INET,
    expires_at        TIMESTAMPTZ NOT NULL,
    last_activity_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked           BOOLEAN NOT NULL DEFAULT FALSE,
    revoked_at        TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT session_expires_after_created CHECK (expires_at > created_at)
);

CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions (user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions (token_hash);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions (expires_at);

CREATE TABLE IF NOT EXISTS refresh_tokens (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id  UUID NOT NULL REFERENCES sessions (id) ON DELETE CASCADE,
    token_hash  VARCHAR(255) NOT NULL UNIQUE,
    expires_at  TIMESTAMPTZ NOT NULL,
    revoked     BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT refresh_expires_after_created CHECK (expires_at > created_at)
);

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_session ON refresh_tokens (session_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_token ON refresh_tokens (token_hash);

CREATE TABLE IF NOT EXISTS audit_logs (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
    user_id        UUID REFERENCES users (id) ON DELETE SET NULL,
    action_type    VARCHAR(64) NOT NULL,
    resource_type  VARCHAR(64),
    resource_id    UUID,
    details        JSONB NOT NULL DEFAULT '{}'::jsonb,
    ip_address     INET,
    user_agent     TEXT,
    success        BOOLEAN NOT NULL DEFAULT TRUE,
    error_message  TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_tenant ON audit_logs (tenant_id, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_logs (user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_logs (tenant_id, action_type, created_at);

-- ---------------------------------------------------------------------------
-- Métier
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS documents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
    created_by      UUID REFERENCES users (id) ON DELETE SET NULL,
    object_key      VARCHAR(512) NOT NULL,
    sha             VARCHAR(64) NOT NULL,
    doc_role        VARCHAR(32) NOT NULL
                    CHECK (doc_role IN ('patrimoine', 'dao_courant', 'dao_archive', 'annexe')),
    doc_type        VARCHAR(32)
                    CHECK (doc_type IN (
                        'rc', 'cctp', 'ccap', 'memoire', 'reference',
                        'dpgf', 'bpu', 'administratif', 'autre'
                    )),
    is_dao          BOOLEAN NOT NULL DEFAULT FALSE,
    status          VARCHAR(32) NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'processing', 'ready', 'failed', 'needs_review')),
    -- false = RAG ok possible sans graphe ; true = extract_graph déjà fait pour ce fichier
    graph_extracted BOOLEAN NOT NULL DEFAULT FALSE,
    ingest_error    TEXT,
    filename        VARCHAR(255) NOT NULL,
    size_bytes      BIGINT,
    mime_type       VARCHAR(128),
    ocr_used        BOOLEAN NOT NULL DEFAULT FALSE,
    ocr_confidence  DOUBLE PRECISION CHECK (ocr_confidence >= 0 AND ocr_confidence <= 1),
    page_count      INTEGER,
    archived_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT unique_tenant_sha UNIQUE (tenant_id, sha)
);

CREATE INDEX IF NOT EXISTS idx_documents_tenant_status ON documents (tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_documents_tenant_role ON documents (tenant_id, doc_role);

CREATE TABLE IF NOT EXISTS dossiers (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
    dao_document_id   UUID REFERENCES documents (id) ON DELETE SET NULL,
    client_name       VARCHAR(255),
    project_name      VARCHAR(255),
    dao_reference     VARCHAR(128),
    deadline          TIMESTAMPTZ,
    status            VARCHAR(32) NOT NULL DEFAULT 'draft'
                      CHECK (status IN (
                          'draft', 'analyzing', 'generating', 'review',
                          'ready_export', 'exported', 'archived'
                      )),
    current_version   INTEGER NOT NULL DEFAULT 1,
    created_by        UUID NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT unique_tenant_dao UNIQUE (tenant_id, dao_document_id)
);

CREATE INDEX IF NOT EXISTS idx_dossiers_tenant_status ON dossiers (tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_dossiers_dao ON dossiers (dao_document_id);
CREATE INDEX IF NOT EXISTS idx_dossiers_client ON dossiers (tenant_id, client_name);

ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS dossier_origine_id UUID REFERENCES dossiers (id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_documents_dossier_origine ON documents (dossier_origine_id);

-- V2 — documents "annexe" : pièce d'appoint scopée à UN dossier, jamais dans le
-- patrimoine partagé (Nouvelle_Architecture/base_de_donnees_et_interface.md §1.5)
ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS dossier_id UUID REFERENCES dossiers (id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_documents_dossier ON documents (dossier_id) WHERE dossier_id IS NOT NULL;

ALTER TABLE documents
    ADD CONSTRAINT annexe_requires_dossier
    CHECK ((doc_role = 'annexe') = (dossier_id IS NOT NULL));

CREATE TABLE IF NOT EXISTS chunks (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id   UUID NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    parent_id     UUID REFERENCES chunks (id) ON DELETE CASCADE,
    text          TEXT NOT NULL,
    heading_path  VARCHAR(512),
    page          INTEGER,
    token_count   INTEGER,
    extra         JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- V2 — routage dynamique des experts (§3.1) : signal DOUX, jamais un filtre dur
    section_type  VARCHAR(16)
                  CHECK (section_type IS NULL OR section_type IN
                      ('rc', 'ccap', 'cctp', 'dpgf', 'bpu', 'memoire', 'reference', 'autre')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chunk_not_self_parent CHECK (id <> parent_id)
);

CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks (document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_parent ON chunks (parent_id);
CREATE INDEX IF NOT EXISTS idx_chunks_page ON chunks (document_id, page);
CREATE INDEX IF NOT EXISTS idx_chunks_section_type ON chunks (section_type);

-- V2 — recherche sparse (BM25-like), config française, colonne générée
ALTER TABLE chunks
    ADD COLUMN IF NOT EXISTS text_fts tsvector
    GENERATED ALWAYS AS (to_tsvector('french', coalesce(text, ''))) STORED;

CREATE INDEX IF NOT EXISTS idx_chunks_text_fts ON chunks USING GIN (text_fts);

CREATE TABLE IF NOT EXISTS exigences (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dossier_id       UUID NOT NULL REFERENCES dossiers (id) ON DELETE CASCADE,
    libelle          TEXT NOT NULL,
    type             VARCHAR(32) NOT NULL
                     CHECK (type IN (
                         'eliminatoire', 'technique', 'administrative',
                         'financiere', 'delai', 'reference'
                     )),
    obligatoire      BOOLEAN NOT NULL DEFAULT TRUE,
    page_source      INTEGER,
    reference_dao    VARCHAR(128),
    statut           VARCHAR(32) NOT NULL DEFAULT 'a_couvrir'
                     CHECK (statut IN (
                         'a_couvrir', 'en_cours', 'couverte', 'non_couverte', 'a_revoir'
                     )),
    preuves_chunks   JSONB NOT NULL DEFAULT '[]'::jsonb,
    couverte_at      TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT couverte_after_created CHECK (couverte_at IS NULL OR couverte_at >= created_at)
);

CREATE INDEX IF NOT EXISTS idx_exigences_dossier ON exigences (dossier_id);
CREATE INDEX IF NOT EXISTS idx_exigences_statut ON exigences (dossier_id, statut);
CREATE INDEX IF NOT EXISTS idx_exigences_obligatoire ON exigences (dossier_id, obligatoire, statut);

CREATE TABLE IF NOT EXISTS outline_items (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dossier_id          UUID NOT NULL REFERENCES dossiers (id) ON DELETE CASCADE,
    key                 VARCHAR(128) NOT NULL,
    heading_level       INTEGER NOT NULL CHECK (heading_level IN (1, 2, 3)),
    title               VARCHAR(512) NOT NULL,
    sort_order          INTEGER NOT NULL,
    status              VARCHAR(32) NOT NULL DEFAULT 'todo'
                        CHECK (status IN ('todo', 'generated', 'approved', 'rejected')),
    -- V2 — spécialisation déterministe du prompt de génération (§10)
    archetype           VARCHAR(16) NOT NULL DEFAULT 'factuelle'
                        CHECK (archetype IN ('institutionnelle', 'factuelle', 'narrative', 'conformite')),
    custom_instruction  TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT unique_dossier_key UNIQUE (dossier_id, key)
);

CREATE INDEX IF NOT EXISTS idx_outline_dossier ON outline_items (dossier_id);
CREATE INDEX IF NOT EXISTS idx_outline_status ON outline_items (dossier_id, status);
CREATE INDEX IF NOT EXISTS idx_outline_order ON outline_items (dossier_id, sort_order);

CREATE TABLE IF NOT EXISTS generations (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dossier_id                UUID NOT NULL REFERENCES dossiers (id) ON DELETE CASCADE,
    section_key               VARCHAR(128) NOT NULL,
    content                   JSONB NOT NULL,
    citations                 JSONB NOT NULL DEFAULT '[]'::jsonb,
    context_snapshot          JSONB NOT NULL DEFAULT '{}'::jsonb,
    exigences_couvertes       JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- V2 — résumé de progression du dossier, précalculé à l'approve (§2.3)
    summary_short             TEXT,
    model                     VARCHAR(128),
    version                   INTEGER NOT NULL DEFAULT 1,
    generation_time_seconds   DOUBLE PRECISION,
    tokens_in                 INTEGER,
    tokens_out                INTEGER,
    cost_estimate             DOUBLE PRECISION,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (dossier_id, section_key)
        REFERENCES outline_items (dossier_id, key) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_generations_dossier ON generations (dossier_id);
CREATE INDEX IF NOT EXISTS idx_generations_section ON generations (dossier_id, section_key);
CREATE INDEX IF NOT EXISTS idx_generations_version ON generations (dossier_id, section_key, version);

CREATE TABLE IF NOT EXISTS reviews (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    generation_id         UUID NOT NULL REFERENCES generations (id) ON DELETE CASCADE,
    user_id               UUID NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
    action                VARCHAR(32) NOT NULL
                          CHECK (action IN ('approve', 'edit', 'regen', 'skip')),
    comment               TEXT,
    modified_text         TEXT,
    regen_instruction     TEXT,
    review_time_seconds   DOUBLE PRECISION,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reviews_generation ON reviews (generation_id);
CREATE INDEX IF NOT EXISTS idx_reviews_user ON reviews (user_id);

CREATE TABLE IF NOT EXISTS conversations (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
    user_id     UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    dossier_id  UUID REFERENCES dossiers (id) ON DELETE SET NULL,
    title       VARCHAR(255),
    summary     TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conversations_tenant_user ON conversations (tenant_id, user_id);
CREATE INDEX IF NOT EXISTS idx_conversations_dossier ON conversations (dossier_id);

CREATE TABLE IF NOT EXISTS messages (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id  UUID NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
    role             VARCHAR(32) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content          TEXT NOT NULL,
    query_rewrite    TEXT,
    generation_id    UUID REFERENCES generations (id) ON DELETE SET NULL,
    meta             JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages (conversation_id);
CREATE INDEX IF NOT EXISTS idx_messages_created ON messages (conversation_id, created_at);
CREATE INDEX IF NOT EXISTS idx_messages_generation ON messages (generation_id);

CREATE TABLE IF NOT EXISTS exports (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dossier_id         UUID NOT NULL REFERENCES dossiers (id) ON DELETE CASCADE,
    version            INTEGER NOT NULL,
    format             VARCHAR(16) NOT NULL CHECK (format IN ('docx', 'pdf', 'md', 'txt')),
    object_key         VARCHAR(512) NOT NULL,
    size_bytes         BIGINT,
    sections_included  JSONB NOT NULL DEFAULT '[]'::jsonb,
    exported_by        UUID NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT unique_dossier_version_format UNIQUE (dossier_id, version, format)
);

CREATE INDEX IF NOT EXISTS idx_exports_dossier ON exports (dossier_id);
CREATE INDEX IF NOT EXISTS idx_exports_version ON exports (dossier_id, version);

-- V2 — observabilité de la boucle CRAG + métriques d'évaluation
-- (Nouvelle_Architecture/base_de_donnees_et_interface.md §1.3)
CREATE TABLE IF NOT EXISTS retrieval_traces (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id            UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
    message_id           UUID REFERENCES messages (id) ON DELETE CASCADE,
    generation_id        UUID REFERENCES generations (id) ON DELETE SET NULL,
    sous_question_index  INTEGER NOT NULL DEFAULT 0,
    sous_question_texte  TEXT,
    expert               VARCHAR(16) NOT NULL
                         CHECK (expert IN ('juridique', 'technique', 'financier', 'graphe', 'patrimoine')),
    tentative            INTEGER NOT NULL CHECK (tentative BETWEEN 1 AND 3),
    query_utilisee       TEXT NOT NULL,
    filtres              JSONB NOT NULL DEFAULT '{}'::jsonb,
    grade                VARCHAR(16) CHECK (grade IS NULL OR grade IN ('correct', 'ambigu', 'incorrect')),
    grade_method         VARCHAR(16) CHECK (grade_method IS NULL OR grade_method IN ('seuil', 'llm_juge')),
    chunks_retournes     JSONB NOT NULL DEFAULT '[]'::jsonb,
    abstention           BOOLEAN NOT NULL DEFAULT FALSE,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_traces_message ON retrieval_traces (message_id);
CREATE INDEX IF NOT EXISTS idx_traces_tenant_expert_grade ON retrieval_traces (tenant_id, expert, grade);

-- V2 — checklist du dossier administratif (§5.3)
CREATE TABLE IF NOT EXISTS dossier_pieces (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dossier_id    UUID NOT NULL REFERENCES dossiers (id) ON DELETE CASCADE,
    libelle       VARCHAR(255) NOT NULL,
    obligatoire   BOOLEAN NOT NULL DEFAULT TRUE,
    document_id   UUID REFERENCES documents (id) ON DELETE SET NULL,
    statut        VARCHAR(32) NOT NULL DEFAULT 'manquant'
                  CHECK (statut IN ('manquant', 'trouve_patrimoine', 'a_uploader', 'fourni')),
    source        VARCHAR(16) NOT NULL DEFAULT 'standard' CHECK (source IN ('rc', 'standard')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dossier_pieces_dossier ON dossier_pieces (dossier_id);

-- Tenant initial. L'utilisateur admin n'est PAS inséré ici :
-- le hash bcrypt doit coller à Python (app/services/seed.py au démarrage API).
INSERT INTO tenants (slug, name, email, status)
VALUES ('default', 'Chantier Offres', 'admin@btp.local', 'active')
ON CONFLICT (slug) DO NOTHING;
