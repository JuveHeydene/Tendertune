Voici la spécification complète et détaillée (V1) : tables métier, authentification simplifiée, contraintes de workflow.

**Auth V1 :** `tenants`, `users`, `sessions`, `refresh_tokens`, `audit_logs`.  
**Pas en V1 :** `api_keys`, `user_invitations`, rôle `'api'`. Ajout d’utilisateurs = formulaire admin + mot de passe temporaire.

`tenant_id` et `user_id` des tables métier sont des **UUID** vers `tenants` / `users` (plus de VARCHAR libre). Le slug lisible (`vinci`) est sur `tenants.slug`, pas recopié partout.

---

## 1. Authentification et isolation (V1)

### 1.1. Table `tenants` — Entreprises clientes

Une ligne = une entreprise (isolation des données). Toutes les requêtes métier filtrent sur `tenants.id`.

```sql
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Identifiant lisible (URLs, MinIO prefix, logs) : 'vinci', 'bouygues'
    slug VARCHAR(64) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL,
    phone VARCHAR(20),
    address TEXT,
    -- Overrides optionnels (LLM, template). V1 locale : ollama / llama3 / nomic-embed-text
    config JSONB DEFAULT '{}'::jsonb,
    status VARCHAR(32) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'suspended')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_tenants_slug ON tenants(slug);
CREATE INDEX idx_tenants_status ON tenants(status);
```

| Attribut | Rôle |
|----------|------|
| `id` | PK. C’est **ce** UUID qui va dans `documents.tenant_id`, etc. |
| `slug` | Clé humaine unique. Pas d’espaces. Sert de préfixe MinIO (`vinci/...`). |
| `name` | Raison sociale affichée. |
| `email` | Contact principal du tenant (souvent l’admin). |
| `phone` / `address` | Infos légères V1 (SIRET / APE plus tard). |
| `config` | JSON : modèle LLM, template Word par défaut, quotas. Pas de secrets en clair. |
| `status` | `active` = API OK. `suspended` → 403 même si le JWT est valide. |
| `created_at` / `updated_at` | Audit. |

Pas de `created_by` vers `users` en V1 (référence circulaire au seed). L’admin est créé juste après le tenant.

---

### 1.2. Table `users` — Comptes humains

Un utilisateur appartient **à un seul** tenant. Email et username uniques **par tenant** (le même email peut exister chez un autre client).

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    username VARCHAR(64) NOT NULL,
    email VARCHAR(255) NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    first_name VARCHAR(128),
    last_name VARCHAR(128),
    phone VARCHAR(20),
    role VARCHAR(32) NOT NULL DEFAULT 'redacteur'
        CHECK (role IN ('admin', 'manager', 'redacteur', 'consultant')),
    permissions JSONB NOT NULL DEFAULT '{}'::jsonb,
    status VARCHAR(32) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'inactive', 'suspended')),
    last_login_at TIMESTAMPTZ,
    login_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT unique_tenant_email UNIQUE (tenant_id, email),
    CONSTRAINT unique_tenant_username UNIQUE (tenant_id, username)
);

CREATE INDEX idx_users_tenant ON users(tenant_id);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_role ON users(tenant_id, role);
CREATE INDEX idx_users_status ON users(tenant_id, status);
```

| Attribut | Rôle |
|----------|------|
| `id` | PK. Injecté dans le JWT (`sub`) et dans `reviews.user_id`, `created_by`, etc. |
| `tenant_id` | FK. Isolation : un user Vinci ne voit jamais Bouygues. |
| `username` | Identifiant court dans le tenant. |
| `email` | Login. Unique **dans** le tenant. |
| `hashed_password` | Hash (argon2/bcrypt). **Jamais** le mot de passe en clair. |
| `first_name` / `last_name` / `phone` | Affichage. |
| `role` | `admin` (tout le tenant), `manager` (dossiers + users), `redacteur` (créer/modifier), `consultant` (lecture). Pas de rôle `api` en V1. |
| `permissions` | Overrides JSON, ex. `{"can_export": true, "can_delete": false}`. |
| `status` | `active` peut se connecter. `inactive` / `suspended` → login refusé. |
| `last_login_at` | Dernière connexion réussie. |
| `login_attempts` / `locked_until` | Anti brute-force. |

---

### 1.3. Table `sessions` — Sessions JWT (accès)

On stocke le **hash** du access token, jamais le JWT en clair.

```sql
CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) NOT NULL UNIQUE,
    user_agent TEXT,
    ip_address INET,
    expires_at TIMESTAMPTZ NOT NULL,
    last_activity_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked BOOLEAN NOT NULL DEFAULT FALSE,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT session_expires_after_created CHECK (expires_at > created_at)
);

CREATE INDEX idx_sessions_user ON sessions(user_id);
CREATE INDEX idx_sessions_token ON sessions(token_hash);
CREATE INDEX idx_sessions_expires ON sessions(expires_at);
```

| Attribut | Rôle |
|----------|------|
| `id` | PK session. Parent de `refresh_tokens`. |
| `user_id` | Qui est connecté. |
| `token_hash` | SHA-256 du access token. Lookup à chaque requête authentifiée. |
| `user_agent` / `ip_address` | Traçabilité, révocation d’un device. |
| `expires_at` | Fin de vie du access token (ex. 24 h). |
| `last_activity_at` | Idle timeout possible. |
| `revoked` / `revoked_at` | Logout ou invalidation admin. |

---

### 1.4. Table `refresh_tokens`

Durée plus longue que le access token (ex. 7 jours). Rotation à chaque refresh.

```sql
CREATE TABLE refresh_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT refresh_expires_after_created CHECK (expires_at > created_at)
);

CREATE INDEX idx_refresh_tokens_session ON refresh_tokens(session_id);
CREATE INDEX idx_refresh_tokens_token ON refresh_tokens(token_hash);
```

| Attribut | Rôle |
|----------|------|
| `session_id` | Lie le refresh à une session web. |
| `token_hash` | Hash du refresh token envoyé au client. |
| `expires_at` | Au-delà → reconnecter. |
| `revoked` | Logout / vol de token. |

---

### 1.5. Table `audit_logs` — Journal des actions sensibles

Recommandé dès la V1 (AO = traçabilité). Pas de partitionnement mensuel en V1.

```sql
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    action_type VARCHAR(64) NOT NULL,
    resource_type VARCHAR(64),
    resource_id UUID,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    ip_address INET,
    user_agent TEXT,
    success BOOLEAN NOT NULL DEFAULT TRUE,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_tenant ON audit_logs(tenant_id, created_at);
CREATE INDEX idx_audit_user ON audit_logs(user_id, created_at);
CREATE INDEX idx_audit_action ON audit_logs(tenant_id, action_type, created_at);
```

| Attribut | Rôle |
|----------|------|
| `tenant_id` | Isolation des logs. |
| `user_id` | Auteur. `NULL` si user supprimé (on garde le log). |
| `action_type` | Ex. `login`, `logout`, `create_document`, `generate_section`, `approve_section`, `export_document`, `user_create`. |
| `resource_type` / `resource_id` | Cible (`document`, `dossier`, `user`, …). |
| `details` | JSON libre (pas de mot de passe). |
| `success` / `error_message` | Échec login, 403, etc. |

---

### 1.6. Hors V1 (volontairement)

| Table / notion | Pourquoi plus tard |
|----------------|-------------------|
| `api_keys` | Accès machine (ERP). Tout est manuel en V1. |
| Rôle `api` | Sans clés API, inutile. |
| `user_invitations` | L’admin crée le compte + mot de passe temporaire. |

**Seed V1 :** un tenant `slug=default` + un user `admin` / mot de passe à changer. Hash argon2 ou bcrypt, **pas** SHA-256 seul.

---

## 2. Schéma SQL métier

### 2.1. Table `documents` — Les fichiers uploadés

```sql
CREATE TABLE documents (
    -- Identifiant unique du document
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Isolation : UUID du tenant (pas le slug)
    -- ⚠️ TOUTES les requêtes doivent filtrer sur ce champ
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    -- Auteur de l'upload
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    
    -- Chemin dans MinIO : ex: 'vinci/123e4567/CCTP.pdf'
    object_key VARCHAR(512) NOT NULL,
    
    -- Empreinte SHA-256 du fichier (calculée automatiquement)
    -- ⚠️ Contrainte UNIQUE avec tenant_id : éviter les doublons
    sha VARCHAR(64) NOT NULL,
    
    -- Rôle du document (DÉTERMINE COMMENT IL EST UTILISÉ)
    -- 'patrimoine'     → Document de référence (anciens dossiers, CV, certifs)
    -- 'dao_courant'    → DAO de l'appel d'offres en cours (extraction exigences)
    -- 'dao_archive'    → DAO ancien (plus d'extraction, mais reste en RAG)
    doc_role VARCHAR(32) NOT NULL CHECK (doc_role IN ('patrimoine', 'dao_courant', 'dao_archive')),
    
    -- Type métier du document (pour filtrage fin)
    -- 'rc'        → Règlement de Consultation
    -- 'cctp'      → Cahier des Clauses Techniques Particulières
    -- 'ccap'      → Cahier des Clauses Administratives Particulières
    -- 'memoire'   → Mémoire technique (réponse)
    -- 'reference' → Document de référence (CV, certif, etc.)
    -- 'dpgf'      → Décomposition du Prix Global et Forfaitaire
    -- 'bpu'       → Bordereau des Prix Unitaires
    -- 'autre'     → Autre type
    doc_type VARCHAR(32) CHECK (doc_type IN ('rc', 'cctp', 'ccap', 'memoire', 'reference', 'dpgf', 'bpu', 'autre')),
    
    -- ⚠️ Indique si ce document EST ou ÉTAIT un DAO
    -- true  → Ce document est un DAO (ou l'a été)
    -- false → Ce document n'est pas un DAO
    is_dao BOOLEAN DEFAULT FALSE,
    
    -- ⚠️ Si c'est un DAO, à quel dossier il est lié
    -- Permet de tracer : "Ce DAO a servi à répondre au dossier X"
    dossier_origine_id UUID REFERENCES dossiers(id) ON DELETE SET NULL,
    
    -- État du traitement du document
    -- 'pending'      → En attente d'ingestion
    -- 'processing'   → En cours d'ingestion (OCR, chunking, embedding)
    -- 'ready'        → Prêt pour la recherche (RAG)
    -- 'failed'       → Échec de l'ingestion
    -- 'needs_review' → Nécessite une intervention humaine (OCR < 70%)
    status VARCHAR(32) DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'ready', 'failed', 'needs_review')),

    -- graph_extracted : le graphe d'entités a-t-il été écrit pour CE document ?
    -- Ce n'est PAS le même signal que status :
    --   status = 'ready'        → parse + chunks + index vectoriel OK (RAG hybride utilisable)
    --   graph_extracted = false → graphe pas encore (ou pas du tout) alimenté
    --   graph_extracted = true  → job extract_graph terminé (nœuds/arêtes + source_chunk_id)
    -- Utilité :
    --   1. Ne pas relancer l'extraction : worker = ready AND graph_extracted = false
    --   2. V1 sans graphe : tout peut rester false ; le RAG marche quand même
    --   3. Horloge B : question relationnelle + false → fallback RAG ou « graphe pas prêt »
    --   4. Retry : remettre à false pour forcer refresh_graph
    -- Drapeau technique de pipeline (comme ocr_used), pas un champ métier UI.
    graph_extracted BOOLEAN NOT NULL DEFAULT FALSE,
    
    -- Nom original du fichier (pour affichage)
    filename VARCHAR(255) NOT NULL,
    
    -- Taille du fichier en octets
    size_bytes BIGINT,
    
    -- Type MIME du fichier (ex: 'application/pdf')
    mime_type VARCHAR(128),
    
    -- Indique si l'OCR a été utilisé (true pour les scans)
    ocr_used BOOLEAN DEFAULT FALSE,
    
    -- Confiance moyenne de l'OCR (0.0 à 1.0)
    -- Si < 0.7 → status = 'needs_review'
    ocr_confidence FLOAT CHECK (ocr_confidence >= 0 AND ocr_confidence <= 1),
    
    -- Nombre de pages du document
    page_count INTEGER,
    
    -- ⚠️ Date d'archivage (pour les dao_archive)
    -- Permet de savoir quand le DAO a été archivé
    archived_at TIMESTAMPTZ,
    
    -- Dates automatiques
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- ⚠️ Contrainte UNIQUE : même tenant + même empreinte = doublon
    -- Empêche d'uploader deux fois le même fichier
    CONSTRAINT unique_tenant_sha UNIQUE (tenant_id, sha)
);

-- ⚠️ Index pour les recherches fréquentes
CREATE INDEX idx_documents_tenant_status ON documents(tenant_id, status);
CREATE INDEX idx_documents_tenant_role ON documents(tenant_id, doc_role);
CREATE INDEX idx_documents_dossier_origine ON documents(dossier_origine_id);
```

---

### 2.2. Table `chunks` — Le texte découpé des documents

```sql
CREATE TABLE chunks (
    -- Identifiant unique du chunk
    -- ⚠️ Cet ID est identique à celui utilisé dans Qdrant
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Document source
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    
    -- ⚠️ Parent-Child : Si ce chunk est un child, lien vers son parent
    -- NULL = ce chunk est lui-même un parent (article entier)
    parent_id UUID REFERENCES chunks(id) ON DELETE CASCADE,
    
    -- Contenu textuel du chunk
    -- ⚠️ INCLUT un préfixe métier pour l'embedding :
    -- "[CCAP] [Article 8 — Pénalités] [Page 14] Le texte..."
    text TEXT NOT NULL,
    
    -- Fil d'Ariane structurel (ex: 'CCAP > Article 8 > Pénalités')
    heading_path VARCHAR(512),
    
    -- Numéro de page dans le document source
    page INTEGER,
    
    -- Taille en tokens (estimée ou réelle)
    token_count INTEGER,
    
    -- ⚠️ Métadonnées flexibles (stockées en JSON)
    -- Exemple : {"article_id": "8", "lot": "03", "year": 2024}
    extra JSONB DEFAULT '{}'::jsonb,
    
    -- Dates automatiques
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- ⚠️ Contrainte : le parent ne peut pas être lui-même
    CONSTRAINT chunk_not_self_parent CHECK (id != parent_id)
);

-- ⚠️ Index pour les recherches de citations
CREATE INDEX idx_chunks_document ON chunks(document_id);
CREATE INDEX idx_chunks_parent ON chunks(parent_id);
CREATE INDEX idx_chunks_page ON chunks(document_id, page);
```

---

### 2.3. Table `dossiers` — Les réponses aux appels d'offres

```sql
CREATE TABLE dossiers (
    -- Identifiant unique du dossier
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Isolation : UUID du tenant
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    
    -- ⚠️ Le DAO de cet appel d'offres (document source des exigences)
    -- Peut être NULL si le dossier est créé sans DAO (ex: réponse spontanée)
    dao_document_id UUID REFERENCES documents(id) ON DELETE SET NULL,
    
    -- ⚠️ Le client / maître d'ouvrage (ex: 'SNCF', 'RATP')
    client_name VARCHAR(255),
    
    -- ⚠️ Nom du projet (ex: 'Gare de Nantes')
    project_name VARCHAR(255),
    
    -- ⚠️ Numéro de référence du DAO (ex: '2024-045')
    dao_reference VARCHAR(128),
    
    -- ⚠️ Date limite de remise des offres
    deadline TIMESTAMPTZ,
    
    -- État du dossier
    -- 'draft'          → Brouillon (pas encore commencé)
    -- 'analyzing'      → En cours d'analyse du DAO
    -- 'generating'     → En cours de génération des sections
    -- 'review'         → En attente de relecture humaine
    -- 'ready_export'   → Prêt pour l'export
    -- 'exported'       → Exporté
    -- 'archived'       → Archivé (soumis)
    status VARCHAR(32) DEFAULT 'draft' CHECK (status IN ('draft', 'analyzing', 'generating', 'review', 'ready_export', 'exported', 'archived')),
    
    -- ⚠️ Version actuelle du dossier (incrémentée à chaque export)
    current_version INTEGER DEFAULT 1,
    
    -- Métadonnées
    created_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- ⚠️ Contrainte : un tenant ne peut avoir qu'un seul dossier par DAO
    -- (on ne peut pas répondre deux fois au même AO)
    CONSTRAINT unique_tenant_dao UNIQUE (tenant_id, dao_document_id)
);

-- Index
CREATE INDEX idx_dossiers_tenant_status ON dossiers(tenant_id, status);
CREATE INDEX idx_dossiers_dao ON dossiers(dao_document_id);
CREATE INDEX idx_dossiers_client ON dossiers(tenant_id, client_name);
```

---

### 2.4. Table `exigences` — Les critères extraits du DAO

```sql
CREATE TABLE exigences (
    -- Identifiant unique de l'exigence
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Dossier concerné
    dossier_id UUID NOT NULL REFERENCES dossiers(id) ON DELETE CASCADE,
    
    -- ⚠️ Énoncé de l'exigence (ex: "Certification ISO 9001 obligatoire")
    libelle TEXT NOT NULL,
    
    -- Type d'exigence
    -- 'eliminatoire'  → Si non satisfaite, dossier rejeté
    -- 'technique'     → Exigence technique
    -- 'administrative'→ Exigence administrative
    -- 'financiere'    → Exigence financière
    -- 'delai'         → Exigence de délai
    -- 'reference'     → Exigence de référence
    type VARCHAR(32) NOT NULL CHECK (type IN ('eliminatoire', 'technique', 'administrative', 'financiere', 'delai', 'reference')),
    
    -- ⚠️ Indique si l'exigence est OBLIGATOIRE
    -- Si true et aucune preuve trouvée → le validateur bloque
    obligatoire BOOLEAN DEFAULT TRUE,
    
    -- Page du DAO où se trouve l'exigence (traçabilité)
    page_source INTEGER,
    
    -- ⚠️ Référence dans le DAO (ex: 'Article 4.2')
    reference_dao VARCHAR(128),
    
    -- État de couverture
    -- 'a_couvrir'    → Pas encore couverte
    -- 'en_cours'     → En cours de recherche de preuves
    -- 'couverte'     → Preuve trouvée
    -- 'non_couverte' → Preuve non trouvée (⚠️ si obligatoire, alerte)
    -- 'a_revoir'     → À revoir manuellement
    statut VARCHAR(32) DEFAULT 'a_couvrir' CHECK (statut IN ('a_couvrir', 'en_cours', 'couverte', 'non_couverte', 'a_revoir')),
    
    -- ⚠️ ID des chunks qui couvrent cette exigence (preuves)
    -- Stocké en JSON : ["chunk-001", "chunk-045"]
    preuves_chunks JSONB DEFAULT '[]'::jsonb,
    
    -- Date de couverture (quand la preuve a été trouvée)
    couverte_at TIMESTAMPTZ,
    
    -- Dates
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- ⚠️ Contrainte : une exigence ne peut pas être couverte avant sa création
    CONSTRAINT couverte_after_created CHECK (couverte_at IS NULL OR couverte_at >= created_at)
);

-- Index
CREATE INDEX idx_exigences_dossier ON exigences(dossier_id);
CREATE INDEX idx_exigences_statut ON exigences(dossier_id, statut);
CREATE INDEX idx_exigences_obligatoire ON exigences(dossier_id, obligatoire, statut);
```

---

### 2.5. Table `outline_items` — Le plan du dossier (canevas)

```sql
CREATE TABLE outline_items (
    -- Identifiant unique de la rubrique
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Dossier concerné
    dossier_id UUID NOT NULL REFERENCES dossiers(id) ON DELETE CASCADE,
    
    -- ⚠️ Clé stable UNIQUE par dossier (ex: 'moyens_materiels')
    -- Permet de lier les générations à ce plan
    key VARCHAR(128) NOT NULL,
    
    -- ⚠️ Niveau de titre (1 = Titre 1 Word, 2 = Titre 2)
    -- Le LLM n'a PAS le droit de changer ce niveau
    heading_level INTEGER NOT NULL CHECK (heading_level IN (1, 2, 3)),
    
    -- ⚠️ Titre affiché (ex: '4. Moyens matériels')
    -- Le LLM doit COPIER ce titre, pas l'inventer
    title VARCHAR(512) NOT NULL,
    
    -- ⚠️ Ordre d'apparition dans le document final
    sort_order INTEGER NOT NULL,
    
    -- État de la rubrique
    -- 'todo'      → Pas encore générée
    -- 'generated' → Générée (en attente de validation)
    -- 'approved'  → Approuvée par l'humain
    -- 'rejected'  → Rejetée (à régénérer)
    status VARCHAR(32) DEFAULT 'todo' CHECK (status IN ('todo', 'generated', 'approved', 'rejected')),
    
    -- ⚠️ Consigne spécifique pour cette section (ex: 'Insister sur les grues 50t')
    -- Peut être modifiée par l'utilisateur
    custom_instruction TEXT,
    
    -- Dates
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- ⚠️ Contrainte UNIQUE : une seule rubrique par clé par dossier
    CONSTRAINT unique_dossier_key UNIQUE (dossier_id, key)
);

-- Index
CREATE INDEX idx_outline_dossier ON outline_items(dossier_id);
CREATE INDEX idx_outline_status ON outline_items(dossier_id, status);
CREATE INDEX idx_outline_order ON outline_items(dossier_id, sort_order);
```

---

### 2.6. Table `generations` — Les versions des sections rédigées

```sql
CREATE TABLE generations (
    -- Identifiant unique de la génération
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Dossier concerné
    dossier_id UUID NOT NULL REFERENCES dossiers(id) ON DELETE CASCADE,
    
    -- ⚠️ Correspond à outline_items.key
    -- Permet de savoir quelle rubrique a été générée
    section_key VARCHAR(128) NOT NULL,
    
    -- ⚠️ Contenu STRUCTURÉ de la section (JSON)
    -- Format:
    -- {
    --   "blocs": [
    --     {"type": "paragraphe", "texte": "..."},
    --     {"type": "liste", "texte": "- item1\n- item2"},
    --     {"type": "sous_titre", "texte": "3.1 Parc de grues"}
    --   ]
    -- }
    -- Le LLM ne produit PAS de texte libre, il remplit ce JSON
    content JSONB NOT NULL,
    
    -- ⚠️ Liste des IDs des chunks utilisés comme sources
    -- ['chunk-001', 'chunk-045', 'chunk-078']
    citations JSONB DEFAULT '[]'::jsonb,
    
    -- ⚠️ SNAPSHOT du contexte envoyé au LLM (pour audit)
    -- Contient les extraits collés + le prompt
    context_snapshot JSONB DEFAULT '{}'::jsonb,
    
    -- ⚠️ Exigences couvertes par cette section
    -- ['ex-001', 'ex-003', 'ex-007']
    exigences_couvertes JSONB DEFAULT '[]'::jsonb,
    
    -- Modèle LLM utilisé (ex: 'claude-3.5-sonnet', 'gpt-4')
    model VARCHAR(128),
    
    -- ⚠️ Numéro de version (incrémenté à chaque régénération)
    version INTEGER DEFAULT 1,
    
    -- ⚠️ Temps de génération (en secondes)
    generation_time_seconds FLOAT,
    
    -- ⚠️ Nombre de tokens utilisés
    tokens_in INTEGER,  -- Tokens du prompt
    tokens_out INTEGER, -- Tokens de la réponse
    
    -- Coût estimé de la génération (en USD)
    cost_estimate FLOAT,
    
    -- Dates
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- ⚠️ Contrainte : on ne peut pas générer une section sans plan
    -- Vérifiée au niveau application, pas en base
    FOREIGN KEY (dossier_id, section_key) REFERENCES outline_items(dossier_id, key) ON DELETE CASCADE
);

-- Index
CREATE INDEX idx_generations_dossier ON generations(dossier_id);
CREATE INDEX idx_generations_section ON generations(dossier_id, section_key);
CREATE INDEX idx_generations_version ON generations(dossier_id, section_key, version);
```

---

### 2.7. Table `reviews` — Les décisions humaines (HITL)

```sql
CREATE TABLE reviews (
    -- Identifiant unique de la revue
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Génération concernée
    generation_id UUID NOT NULL REFERENCES generations(id) ON DELETE CASCADE,
    
    -- Utilisateur qui a fait la revue
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    
    -- ⚠️ Action de l'humain
    -- 'approve' → La section est approuvée (status = approved)
    -- 'edit'    → L'humain a modifié manuellement le texte
    -- 'regen'   → Demande de régénération (status = rejected)
    -- 'skip'    → Ignorer (pour les sections non obligatoires)
    action VARCHAR(32) NOT NULL CHECK (action IN ('approve', 'edit', 'regen', 'skip')),
    
    -- Commentaire de l'humain (ex: 'Ajouter les grues de 50 tonnes')
    comment TEXT,
    
    -- ⚠️ Si action = 'edit', contient le texte modifié par l'humain
    modified_text TEXT,
    
    -- ⚠️ Si action = 'regen', nouvelle consigne pour la régénération
    regen_instruction TEXT,
    
    -- Durée de la revue (en secondes)
    review_time_seconds FLOAT,
    
    -- Dates
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index
CREATE INDEX idx_reviews_generation ON reviews(generation_id);
CREATE INDEX idx_reviews_user ON reviews(user_id);
```

---

### 2.8. Table `conversations` — Les fils de discussion

```sql
CREATE TABLE conversations (
    -- Identifiant unique de la conversation
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Isolation : UUID du tenant
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    
    -- Auteur du fil
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- ⚠️ Dossier lié à cette conversation (optionnel)
    -- NULL = conversation libre (questions générales)
    dossier_id UUID REFERENCES dossiers(id) ON DELETE SET NULL,
    
    -- ⚠️ Titre de la conversation (généré automatiquement par l'IA)
    title VARCHAR(255),
    
    -- ⚠️ Résumé de la conversation (pour le contexte)
    -- Mis à jour périodiquement par l'IA
    summary TEXT,
    
    -- Métadonnées
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Contrainte : une conversation ne peut être liée qu'à un dossier du même tenant
    -- Vérifiée au niveau application
    CHECK (tenant_id IS NOT NULL)
);

-- Index
CREATE INDEX idx_conversations_tenant_user ON conversations(tenant_id, user_id);
CREATE INDEX idx_conversations_dossier ON conversations(dossier_id);
```

---

### 2.9. Table `messages` — Les messages individuels

```sql
CREATE TABLE messages (
    -- Identifiant unique du message
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Conversation parente
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    
    -- Rôle de l'émetteur
    -- 'user'      → Message de l'utilisateur
    -- 'assistant' → Message de l'IA
    -- 'system'    → Message système (rare)
    role VARCHAR(32) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    
    -- Contenu du message
    content TEXT NOT NULL,
    
    -- ⚠️ Version "nettoyée" de la question (après rewrite)
    -- Permet de tracer comment la question a été interprétée
    -- Ex: "et la pénalité ?" → "clause de pénalité contrat Dupont"
    query_rewrite TEXT,
    
    -- ⚠️ ID de la génération déclenchée par ce message (si applicable)
    -- Permet de lier "message → génération"
    generation_id UUID REFERENCES generations(id) ON DELETE SET NULL,
    
    -- ⚠️ Métadonnées du message (stockées en JSON)
    -- Ex: {"intent": "hybrid_rag", "section_key": "references"}
    meta JSONB DEFAULT '{}'::jsonb,
    
    -- Dates
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Index pour l'ordre chronologique
    -- ⚠️ On utilisera created_at pour l'ordre
    CONSTRAINT messages_order CHECK (created_at IS NOT NULL)
);

-- Index
CREATE INDEX idx_messages_conversation ON messages(conversation_id);
CREATE INDEX idx_messages_created ON messages(conversation_id, created_at);
CREATE INDEX idx_messages_generation ON messages(generation_id);
```

---

### 2.10. Table `exports` — Les fichiers générés

```sql
CREATE TABLE exports (
    -- Identifiant unique de l'export
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Dossier concerné
    dossier_id UUID NOT NULL REFERENCES dossiers(id) ON DELETE CASCADE,
    
    -- ⚠️ Numéro de version (correspond à dossiers.current_version)
    version INTEGER NOT NULL,
    
    -- Format du fichier
    -- 'docx' → Document Word
    -- 'pdf'  → Document PDF
    format VARCHAR(16) NOT NULL CHECK (format IN ('docx', 'pdf')),
    
    -- ⚠️ Chemin dans MinIO (ex: 'vinci/exports/dossier-789/v1.docx')
    object_key VARCHAR(512) NOT NULL,
    
    -- Taille du fichier en octets
    size_bytes BIGINT,
    
    -- ⚠️ Snapshot des sections incluses dans l'export
    -- Stocke les IDs des générations qui composent ce fichier
    sections_included JSONB DEFAULT '[]'::jsonb,
    
    -- Utilisateur qui a demandé l'export
    exported_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    
    -- Dates
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- ⚠️ Contrainte UNIQUE : une seule version par format par dossier
    CONSTRAINT unique_dossier_version_format UNIQUE (dossier_id, version, format)
);

-- Index
CREATE INDEX idx_exports_dossier ON exports(dossier_id);
CREATE INDEX idx_exports_version ON exports(dossier_id, version);
```

---

### 2.11. ENUM / CHOICES

| Table | Champ | Valeurs possibles |
|-------|-------|-------------------|
| `tenants` | `status` | `'active'`, `'suspended'` |
| `users` | `role` | `'admin'`, `'manager'`, `'redacteur'`, `'consultant'` |
| `users` | `status` | `'active'`, `'inactive'`, `'suspended'` |
| `documents` | `doc_role` | `'patrimoine'`, `'dao_courant'`, `'dao_archive'` |
| `documents` | `doc_type` | `'rc'`, `'cctp'`, `'ccap'`, `'memoire'`, `'reference'`, `'dpgf'`, `'bpu'`, `'autre'` |
| `documents` | `status` | `'pending'`, `'processing'`, `'ready'`, `'failed'`, `'needs_review'` |
| `documents` | `graph_extracted` | `false` (RAG seul / extraction pas faite), `true` (graphe écrit pour ce fichier) |
| `dossiers` | `status` | `'draft'`, `'analyzing'`, `'generating'`, `'review'`, `'ready_export'`, `'exported'`, `'archived'` |
| `exigences` | `type` | `'eliminatoire'`, `'technique'`, `'administrative'`, `'financiere'`, `'delai'`, `'reference'` |
| `exigences` | `statut` | `'a_couvrir'`, `'en_cours'`, `'couverte'`, `'non_couverte'`, `'a_revoir'` |
| `outline_items` | `heading_level` | `1`, `2`, `3` |
| `outline_items` | `status` | `'todo'`, `'generated'`, `'approved'`, `'rejected'` |
| `reviews` | `action` | `'approve'`, `'edit'`, `'regen'`, `'skip'` |
| `messages` | `role` | `'user'`, `'assistant'`, `'system'` |
| `exports` | `format` | `'docx'`, `'pdf'` |

---

## 3. Relations entre tables et workflow chronologique

### Diagramme des relations (auth + métier)

```text
  TENANTS 1──< USERS 1──< SESSIONS 1──< REFRESH_TOKENS
                 │
                 ├── documents.created_by
                 ├── dossiers.created_by
                 ├── conversations.user_id
                 ├── reviews.user_id
                 └── exports.exported_by

  TENANTS 1──< documents, dossiers, conversations, audit_logs
                      │
                      └── chunks / exigences / outline / generations / messages / exports
```

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│  ┌─────────────┐                                                            │
│  │  documents  │─────────────────────────────────────────────────────┐     │
│  │  (fichiers) │                                                     │     │
│  └──────┬──────┘                                                     │     │
│         │ 1                                                          │     │
│         │                                                            │     │
│         │ N                                                          │     │
│  ┌──────▼──────┐                                                     │     │
│  │   chunks    │                                                     │     │
│  │  (découpage)│                                                     │     │
│  └──────┬──────┘                                                     │     │
│         │                                                            │     │
│         │ (citations)                                                │     │
│         ▼                                                            │     │
│  ┌─────────────────────────────────────────────────────────────┐    │     │
│  │                                                             │    │     │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │    │     │
│  │  │  dossiers   │──│ exigences   │  │ outline_items│        │    │     │
│  │  │  (réponses) │  │ (critères)  │  │   (plan)    │        │    │     │
│  │  └──────┬──────┘  └─────────────┘  └──────┬──────┘        │    │     │
│  │         │ 1                               │ 1               │    │     │
│  │         │                                 │                  │    │     │
│  │         │ N                               │ N                │    │     │
│  │  ┌──────▼──────┐                  ┌──────▼──────┐          │    │     │
│  │  │ generations │                  │ generations │          │    │     │
│  │  │  (versions) │                  │  (versions) │          │    │     │
│  │  └──────┬──────┘                  └─────────────┘          │    │     │
│  │         │                                                  │    │     │
│  │         │ N                                                │    │     │
│  │  ┌──────▼──────┐                                           │    │     │
│  │  │   reviews   │                                           │    │     │
│  │  │ (décisions) │                                           │    │     │
│  │  └─────────────┘                                           │    │     │
│  │                                                             │    │     │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │    │     │
│  │  │conversations│──│  messages   │  │   exports   │        │    │     │
│  │  │  (chats)    │  │  (messages) │  │  (fichiers) │        │    │     │
│  │  └─────────────┘  └─────────────┘  └─────────────┘        │    │     │
│  │                                                             │    │     │
│  └─────────────────────────────────────────────────────────────┘    │     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### Workflow Chronologique Complet

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ ÉTAPE 1 : UPLOAD DU DAO (DOCUMENT DU MAÎTRE D'OUVRAGE)                    │
│                                                                             │
│ 1️⃣ Jean Dupont (tenant.slug="vinci", tenant_id=UUID) upload un PDF "DAO_Gare_Nantes.pdf"       │
│    → FastAPI reçoit le fichier                                             │
│    → Calcule SHA-256 de l'empreinte                                        │
│    → Vérifie que le fichier n'existe pas déjà                             │
│    → Table documents : ligne créée                                         │
│        - id: doc-123                                                       │
│        - tenant_id: <UUID tenants.id>                                                │
│        - doc_role: "dao_courant"  ⚠️ Document du Maître d'Ouvrage         │
│        - is_dao: true                                                      │
│        - status: "pending"                                                 │
│    → MinIO : fichier sauvegardé                                            │
│    → Redis/ARQ : job d'ingestion en file d'attente                        │
│    → Réponse HTTP : { document_id: "doc-123", status: "pending" }         │
│                                                                             │
│ 2️⃣ Worker ARQ (ingestion)                                                 │
│    → Télécharge depuis MinIO                                               │
│    → Détecte si c'est un scan ou un PDF numérique                          │
│    → Si scan : PaddleOCR PP-Structure (OCR + layout)                      │
│    → Si numérique : Docling (extraction structurée)                       │
│    → Extrait le texte, les titres, les tableaux                           │
│    → Table chunks : 150 lignes créées (articles, alinéas)                 │
│        - Chaque chunk a un ID unique (chunk-001 à chunk-150)              │
│    → Qdrant : vecteurs indexés (BGE-M3 dense + sparse)                    │
│    → documents.status = "ready"                                            │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ ÉTAPE 2 : CRÉATION DE LA CONVERSATION                                     │
│                                                                             │
│ 3️⃣ Jean crée une conversation sur ce DAO                                  │
│    → Table conversations : ligne créée                                     │
│        - id: conv-001                                                      │
│        - tenant_id: <UUID tenants.id>                                                │
│        - user_id: <UUID users.id>  (username jean.dupont)                                            │
│        - dossier_id: NULL (pas encore créé)                               │
│    → Jean envoie son premier message :                                    │
│        "Je veux répondre à l'appel d'offres de la gare de Nantes"         │
│    → Table messages : ligne créée                                         │
│        - id: msg-001                                                       │
│        - conversation_id: conv-001                                         │
│        - role: "user"                                                      │
│        - content: "Je veux répondre à l'appel d'offres..."                │
│                                                                             │
│ 4️⃣ Le système crée le dossier associé                                     │
│    → Table dossiers : ligne créée                                          │
│        - id: dossier-789                                                   │
│        - tenant_id: <UUID tenants.id>                                                │
│        - dao_document_id: doc-123  ⚠️ Lié au DAO                         │
│        - client_name: "SNCF"                                               │
│        - project_name: "Gare de Nantes"                                   │
│        - status: "draft"                                                   │
│    → Mise à jour de la conversation :                                    │
│        - conversations.dossier_id = dossier-789                           │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ ÉTAPE 3 : ANALYSE DU DAO ET EXTRACTION DES EXIGENCES                      │
│                                                                             │
│ 5️⃣ Système analyse le DAO (déclenché automatiquement ou par l'utilisateur)│
│    → Vérifie que le document est bien un DAO (is_dao = true)              │
│    → LLM lit le DAO (via les chunks ou le texte complet)                  │
│    → Extrait les exigences au format JSON                                 │
│    → Table exigences : 15 lignes créées                                   │
│        - ex-001: "Certification ISO 9001 obligatoire" (technique, true)   │
│        - ex-002: "5 ans d'expérience ferroviaire" (technique, true)      │
│        - ex-003: "Chiffre d'affaires > 10M€" (financier, true)            │
│        - ex-004: "Délai de réalisation < 18 mois" (delai, true)           │
│        - ex-005: "Références similaires" (reference, true)                │
│        - ... (10 autres)                                                  │
│                                                                             │
│ 6️⃣ Système génère le plan du dossier                                      │
│    → Extrait les sections demandées par le DAO (ou utilise le template)   │
│    → Table outline_items : 8 sections définies                            │
│        - out-001: key="presentation", title="1. Présentation", ordre=1   │
│        - out-002: key="comprehension", title="2. Compréhension", ordre=2 │
│        - out-003: key="moyens_humains", title="3. Moyens humains", ordre=3│
│        - out-004: key="moyens_materiels", title="4. Moyens matériels", o=4│
│        - out-005: key="references", title="5. Références", ordre=5        │
│        - out-006: key="methodologie", title="6. Méthodologie", ordre=6    │
│        - out-007: key="qse", title="7. QSE", ordre=7                      │
│        - out-008: key="planning", title="8. Planning", ordre=8            │
│    → dossiers.status = "generating"                                        │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ ÉTAPE 4 : GÉNÉRATION D'UNE SECTION                                         │
│                                                                             │
│ 7️⃣ Jean demande : "Génère la section Références"                          │
│    → Table messages : msg-002 (user)                                       │
│                                                                             │
│ 8️⃣ Système génère la section "Références"                                 │
│    → Récupère le dossier (dossier-789)                                    │
│    → Récupère la rubrique (out-005, key="references")                     │
│    → Construit la requête de recherche :                                   │
│        "Trouve les projets similaires à la construction de gares"          │
│    → ⚠️ Filtres appliqués :                                                │
│        tenant_id = "vinci"                                                 │
│        doc_role IN ('patrimoine', 'dao_archive')  ⚠️ PAS de dao_courant   │
│        (on exclut les DAO des autres dossiers pour éviter la pollution)   │
│    → Recherche hybride dans Qdrant (BGE-M3 dense + sparse + rerank)       │
│    → Trouve 5 chunks pertinents                                            │
│    → Table generations : gen-001 (version 1)                              │
│        - content: { blocs: [{type: "paragraphe", texte: "..."}] }         │
│        - citations: ["chunk-045", "chunk-078", "chunk-123"]               │
│        - context_snapshot: {...}  ⚠️ Pour audit                           │
│        - version: 1                                                        │
│    → Table messages : msg-003 (assistant)                                 │
│        - content: "Voici la section Références..."                         │
│        - generation_id: gen-001  ⚠️ Lien message → génération             │
│    → outline_items.status = "generated"                                    │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ ÉTAPE 5 : REVUE HUMAINE (HITL)                                            │
│                                                                             │
│ 9️⃣ Jean révise la section générée                                          │
│    → Il voit le contenu + les sources                                      │
│    → Il trouve que les grues de 50 tonnes ne sont pas mentionnées          │
│    → Il demande : "Régénère en ajoutant les grues de 50 tonnes"           │
│    → Table reviews : rev-001                                               │
│        - generation_id: gen-001                                            │
│        - user_id: <UUID users.id>  (username jean.dupont)                                            │
│        - action: "regen"  ⚠️ Demande de régénération                      │
│        - comment: "Ajouter les grues de 50 tonnes"                        │
│        - regen_instruction: "Insister sur les grues de 50 tonnes"         │
│                                                                             │
│ 🔄 Le système régénère la section avec la nouvelle consigne               │
│    → Table generations : gen-002 (version 2)                              │
│        - content: {...} (nouveau contenu avec les grues)                  │
│        - version: 2                                                        │
│                                                                             │
│ 1️⃣0️⃣ Jean approuve la nouvelle version                                    │
│    → Table reviews : rev-002                                               │
│        - generation_id: gen-002                                            │
│        - user_id: <UUID users.id>  (username jean.dupont)                                            │
│        - action: "approve"                                                 │
│    → outline_items.status = "approved"                                     │
│    → dossiers.status = "ready_export" (si toutes les sections sont faites)│
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ ÉTAPE 6 : EXPORT DU DOSSIER FINAL                                          │
│                                                                             │
│ 1️⃣1️⃣ Jean demande l'export du dossier complet                             │
│    → Système assemble toutes les sections approuvées (dans l'ordre)        │
│    → Génère le DOCX (via python-docx)                                      │
│    → Génère le PDF (via weasyprint)                                        │
│    → Table exports : ligne créée                                           │
│        - id: exp-001                                                       │
│        - dossier_id: dossier-789                                           │
│        - version: 1                                                        │
│        - format: "docx"                                                    │
│        - object_key: "vinci/exports/dossier-789/v1.docx"                   │
│        - sections_included: ["gen-001", "gen-003", "gen-004", ...]        │
│        - exported_by: <UUID users.id>                                        │
│    → MinIO : fichier sauvegardé                                            │
│    → dossiers.status = "exported"                                          │
│    → dossiers.current_version = 1                                          │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ ÉTAPE 7 : HISTORIQUE COMPLET DISPONIBLE                                    │
│                                                                             │
│ 1️⃣2️⃣ Jean peut à tout moment :                                            │
│    → Voir l'historique complet de la conversation                          │
│        SELECT * FROM messages WHERE conversation_id = 'conv-001'           │
│    → Voir toutes les versions d'une section                                │
│        SELECT * FROM generations WHERE dossier_id='dossier-789'            │
│        AND section_key='references' ORDER BY version                       │
│    → Voir toutes les décisions humaines                                    │
│        SELECT * FROM reviews WHERE generation_id IN (...)                 │
│    → Voir tous les exports                                                 │
│        SELECT * FROM exports WHERE dossier_id='dossier-789'                │
│    → Comparer les versions                                                 │
│    → Revenir à une version antérieure                                      │
│    → Audit complet de la création du dossier                               │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Authentification : flux V1 et permissions

Routes publiques : `/health`, `/auth/login`, `/docs`, `/openapi.json`.  
Le reste exige `Authorization: Bearer <access_token>`.

### 4.1 Inscription / seed

1. Créer `tenants` (`slug`, `name`, `email`, `status=active`).
2. Créer `users` admin (`role=admin`, mot de passe hashé).
3. Login → `sessions` + `refresh_tokens` + JWT.

Ajout d’un collaborateur V1 : l’admin crée le user (email, rôle, mot de passe temporaire). Pas d’invitation par lien.

### 4.2 Connexion

`POST /auth/login` `{ email, password }` :

1. User existe, `status=active`, tenant `status=active`.
2. Vérifier le hash du mot de passe.
3. Créer session (`token_hash`, `expires_at`) et refresh token.
4. Réponse : `access_token`, `refresh_token`, `{ user_id, tenant_id, role }`.
5. `audit_logs` : `action_type=login`.

### 4.3 Requête authentifiée

Le middleware : hash du Bearer → `sessions` non révoquée et non expirée → decode JWT (`sub`, `tenant_id`, `role`) → user et tenant actifs → `request.state.user_id` / `tenant_id` / `role`.

**Toute requête métier filtre `tenant_id = request.state.tenant_id`.** Un UUID d’un autre tenant → 404/403, jamais de fuite cross-tenant.

### 4.4 Rôles V1

| Action | Rôle mini |
|--------|-----------|
| Lire documents / dossiers | `consultant` |
| Upload, générer, approuver | `redacteur` |
| Supprimer document | `manager` (+ `can_delete` si présent) |
| Export | `redacteur` (+ `can_export` si présent) |
| Gérer users / voir audit | `admin` |

### 4.5 Vérification d’accès document

1. Document existe.
2. `doc.tenant_id == current_user.tenant_id`.
3. Rôle dans `admin|manager|redacteur|consultant`.

---

## 5. Contraintes et règles de validation

### 5.1. Règle : Filtrage des documents pour la recherche

```python
def recherche_pour_generation(dossier_id, query, section_key=None):
    """
    Recherche les documents pertinents pour générer une section.
    
    ⚠️ RÈGLES DE FILTRAGE :
    1. Seulement les documents du même tenant
    2. Exclure les dao_courant (sauf exceptions)
    3. Inclure les patrimoine et dao_archive
    4. Exclure les documents en erreur (status != 'ready')
    """
    
    # 1. Récupérer le dossier
    dossier = get_dossier(dossier_id)
    if not dossier:
        raise ValueError(f"Dossier {dossier_id} introuvable")
    
    # 2. Récupérer le DAO de ce dossier (pour référence)
    dao_id = dossier.dao_document_id
    
    # 3. Construire les filtres
    filtres = {
        "tenant_id": dossier.tenant_id,
        "status": "ready",  # ⚠️ Seulement les documents prêts
        # ⚠️ On autorise les patrimoine ET le dao_archive
        # MAIS on n'inclut PAS les dao_courant des autres dossiers
        "doc_role": ["patrimoine", "dao_archive"],
    }
    
    # 4. ⚠️ Exception : on peut inclure le DAO courant pour référence
    # Mais seulement pour certaines sections (ex: analyse des exigences)
    if section_key in ["comprehension", "methodologie"]:
        # Pour ces sections, on peut aussi chercher dans le DAO courant
        filtres["doc_role"].append("dao_courant")
        # ⚠️ On limite au DAO de CE dossier
        filtres["document_id"] = dao_id
    
    # 5. ⚠️ Exclusion stricte : on n'utilise JAMAIS les DAO des autres dossiers
    # Cela se fait via le tenant_id + doc_role = "dao_courant"
    # On va chercher les autres DAO du même tenant, mais avec doc_role='dao_archive'
    # Les dao_courant des autres dossiers ne sont JAMAIS retournés
    
    # 6. Recherche
    resultats = hybrid_search(query, filtres)
    return resultats
```

### 5.2. Règle : Extraction des exigences

```python
def extraction_exigences(dao_document_id):
    """
    Extrait les exigences d'un DAO.
    
    ⚠️ RÈGLES :
    1. Vérifier que le document est un DAO
    2. Vérifier que le document est prêt (status = 'ready')
    3. Utiliser le texte du document (pas les chunks)
    4. Ne PAS utiliser d'autres documents pour l'extraction
    5. Sortie structurée JSON
    """
    
    # 1. Récupérer le document
    doc = get_document(dao_document_id)
    if not doc:
        raise ValueError(f"Document {dao_document_id} introuvable")
    
    # 2. ⚠️ Vérifier que c'est bien un DAO
    if not doc.is_dao:
        raise ValueError(f"Le document {dao_document_id} n'est pas un DAO")
    
    # 3. ⚠️ Vérifier que le document est prêt
    if doc.status != 'ready':
        raise ValueError(f"Le document {dao_document_id} n'est pas encore prêt (status: {doc.status})")
    
    # 4. ⚠️ Récupérer le texte COMPLET du DAO (pas les chunks)
    # On utilise les chunks parents (les articles) ou le texte original
    full_text = get_full_document_text(dao_document_id)
    
    # 5. ⚠️ Extraire les exigences AVEC le LLM
    # On utilise un prompt spécifique : "Extrait les exigences obligatoires de ce DAO"
    exigences = llm_extract_exigences(full_text)
    
    # 6. ⚠️ Ne PAS utiliser d'autres documents pour l'extraction
    # Pas de recherche RAG, pas d'autres sources
    
    return exigences
```

### 5.3. Règle : Archivage des DAO

```python
def archiver_dao(dao_document_id, dossier_id):
    """
    Archive un DAO après soumission.
    
    ⚠️ RÈGLES :
    1. Le DAO devient 'dao_archive'
    2. On garde la traçabilité (dossier_origine_id)
    3. Il reste indexé en RAG pour référence future
    4. Il n'est PLUS utilisé pour l'extraction d'exigences
    """
    
    doc = get_document(dao_document_id)
    
    # ⚠️ Vérifier que c'est un DAO courant
    if doc.doc_role != 'dao_courant':
        raise ValueError(f"Le document {dao_document_id} n'est pas un dao_courant")
    
    # ⚠️ Mise à jour
    doc.doc_role = 'dao_archive'
    doc.dossier_origine_id = dossier_id
    doc.archived_at = datetime.now()
    
    # ⚠️ On garde is_dao = true (pour traçabilité)
    # doc.is_dao reste True
    
    save_document(doc)
    
    # ⚠️ Note : Le document reste indexé en Qdrant
    # Mais il ne sera plus utilisé pour l'extraction d'exigences
```

### 5.4. Règle : Les documents uploadés pendant la conversation

```python
def upload_document_pendant_conversation(conversation_id, file):
    """
    Upload d'un document pendant une conversation.
    
    ⚠️ RÈGLES :
    1. Le document devient 'patrimoine' (pas dao_courant)
    2. Il enrichit la base de connaissances
    3. Il est disponible pour TOUS les dossiers du tenant
    4. Le message de l'utilisateur y fait référence
    """
    
    # 1. Upload du document
    doc = upload_document(
        file=file,
        tenant_id=get_tenant(conversation_id),
        doc_role='patrimoine',  # ⚠️ Toujours patrimoine
        is_dao=False,  # ⚠️ Ce n'est pas un DAO
        doc_type='reference'
    )
    
    # 2. Créer un message pour référence
    message = create_message(
        conversation_id=conversation_id,
        role='user',
        content=f"J'ai uploadé un document de référence : {file.filename}"
    )
    
    # 3. Le document est indexé en RAG
    # Il sera disponible pour toutes les futures recherches
    
    return doc
```

### 5.5. Règle : Génération d'une section (avec le contexte)

```python
def generer_section(dossier_id, section_key, consigne_utilisateur=None):
    """
    Génère une section du dossier.
    
    ⚠️ RÈGLES :
    1. La section doit exister dans outline_items
    2. Le contexte de recherche est filtré (voir recherche_pour_generation)
    3. Le LLM n'invente PAS de titres
    4. Les citations sont OBLIGATOIRES pour les faits chiffrés
    5. Si une exigence obligatoire n'est pas couverte → le validateur bloque
    6. La génération est traçable (context_snapshot)
    """
    
    # 1. Vérifier que la section existe
    outline = get_outline_item(dossier_id, section_key)
    if not outline:
        raise ValueError(f"Section {section_key} introuvable")
    
    # 2. Récupérer les exigences liées à cette section
    exigences = get_exigences_par_section(dossier_id, section_key)
    
    # 3. Construire la requête de recherche
    query = f"Rédige la section {outline.title} du dossier d'appel d'offres"
    if consigne_utilisateur:
        query += f". Consigne : {consigne_utilisateur}"
    
    # 4. ⚠️ Recherche avec filtres (voir fonction ci-dessus)
    extraits = recherche_pour_generation(dossier_id, query, section_key)
    
    # 5. ⚠️ Vérifier les exigences obligatoires
    exigences_obligatoires = [e for e in exigences if e.obligatoire]
    exigences_couvertes = []
    for exigence in exigences_obligatoires:
        # Vérifier si l'exigence est couverte par les extraits trouvés
        if is_exigence_couverte(exigence, extraits):
            exigences_couvertes.append(exigence.id)
    
    # 6. ⚠️ Si des exigences obligatoires ne sont pas couvertes
    # → On ne génère PAS la section, on alerte l'utilisateur
    exigences_non_couvertes = [e for e in exigences_obligatoires if e.id not in exigences_couvertes]
    if exigences_non_couvertes:
        raise ValidationError(
            f"Exigences obligatoires non couvertes : {[e.libelle for e in exigences_non_couvertes]}"
        )
    
    # 7. ⚠️ Construction du contexte AVEC les extraits
    contexte = build_context(
        titre=outline.title,
        exigences=exigences,
        extraits=extraits,
        consigne=consigne_utilisateur
    )
    
    # 8. ⚠️ Génération par le LLM (sortie JSON contrainte)
    contenu = llm_generate_section(contexte)
    
    # 9. ⚠️ Validation du contenu
    # - Pas de titres H1/H2 dans le contenu (les titres sont dans outline_items)
    # - Les citations sont valides
    # - Le JSON est bien formé
    valider_contenu_section(contenu, extraits)
    
    # 10. ⚠️ Sauvegarde
    generation = save_generation(
        dossier_id=dossier_id,
        section_key=section_key,
        content=contenu,
        citations=[e.id for e in extraits],
        context_snapshot=contexte,
        exigences_couvertes=exigences_couvertes
    )
    
    return generation
```

### 5.6. Règle : Validation des citations

```python
def valider_contenu_section(contenu, extraits):
    """
    Valide que le contenu généré est valide.
    
    ⚠️ RÈGLES :
    1. Les citations référencées doivent exister dans extraits
    2. Pas de titres H1/H2 dans le contenu
    3. Les faits chiffrés doivent avoir une citation
    4. Le JSON doit être bien formé
    """
    
    # 1. ⚠️ Vérifier que les citations existent
    citations_dans_contenu = extraire_citations(contenu)
    for citation in citations_dans_contenu:
        if citation not in [e.id for e in extraits]:
            raise ValidationError(f"Citation {citation} non trouvée dans le contexte")
    
    # 2. ⚠️ Vérifier qu'il n'y a pas de titres H1/H2
    # Les titres sont définis dans outline_items, pas dans le contenu
    if has_heading_h1_h2(contenu):
        raise ValidationError("Le contenu contient des titres H1/H2 interdits")
    
    # 3. ⚠️ Vérifier que les faits chiffrés ont des citations
    faits_chiffres = extraire_faits_chiffres(contenu)
    for fait in faits_chiffres:
        if not has_citation(fait):
            raise ValidationError(f"Fait chiffré sans citation : {fait}")
    
    return True
```

---

## 6. Résumé des contraintes de filtrage RAG

| Contexte | Documents autorisés | Documents exclus | Raison |
|----------|---------------------|------------------|--------|
| **Recherche pour génération** | `patrimoine`, `dao_archive` | `dao_courant` (sauf exceptions) | Éviter la pollution par d'autres DAO |
| **Extraction exigences** | Le DAO spécifié (un seul) | Tous les autres documents | Les exigences viennent UNIQUEMENT du DAO |
| **Recherche pour référence** | `patrimoine`, `dao_archive` | `dao_courant` | Références historiques uniquement |
| **Archive après soumission** | Le DAO devient `dao_archive` | N/A | On garde la traçabilité sans pollution |
| **Upload en conversation** | `patrimoine` | `dao_courant` | Les documents uploadés sont des références |

---

## 7. Graphe de connaissances (phase 1.5)

Le RAG hybride (index vectoriel + texte en base relationnelle) répond à : *« quels extraits parlent de X ? »*  
Le graphe répond à : *« quels **liens** existent entre les entités ? »*

Exemples : projets réalisés avec telle certification ; personnes ayant travaillé sur des projets similaires ; historique d’un client.

**Écriture du graphe = horloge A** (job après parse), **lecture = horloge B** (requête). On n’extrait pas le graphe à chaque question.

### 7.1 Nœuds

```text
ENTREPRISE (id, siret, nom, secteur)
PROJET     (id, nom, année, montant)
CLIENT     (id, nom, type public/privé)
EXIGENCE   (id, libellé, type, réf. DAO)
CERTIFICATION (id, nom, validité)
EQUIPEMENT (id, nom, capacité)
PERSONNE   (id, nom, rôle)
APPEL_OFFRES (id, réf. DAO, échéance)
CHUNK      (id = chunks.id Postgres — ancre de citation)
```

### 7.2 Relations

```text
ENTREPRISE  ─[A_REALISE]────────► PROJET          (année, rôle, montant)
ENTREPRISE  ─[DETIENT]──────────► CERTIFICATION   (date, validité)
ENTREPRISE  ─[EMPLOIE]──────────► PERSONNE
PROJET      ─[POUR]─────────────► CLIENT
PROJET      ─[UTILISE]──────────► EQUIPEMENT
APPEL_OFFRES─[CONTIENT]─────────► EXIGENCE
EXIGENCE    ─[SATISFAITE_PAR]───► PROJET | CERTIFICATION | EQUIPEMENT
PERSONNE    ─[A_TRAVAILLE_SUR]──► PROJET
CHUNK       ─[SOURCE]───────────► PROJET | EXIGENCE | …
PROJET      ─[SIMILAIRE_A]──────► PROJET          (score, raison)
```

Chaque nœud et chaque arête portent `source_chunk_id` → `chunks.id` (citation page / article).

### 7.3 Chronologie

```text
PHASE 1 — ingestion document (déjà le socle)
  fichier → parse → chunks → index vectoriel + texte relationnel
  graphe encore vide ; documents.graph_extracted = false
  documents.status = ready  → le RAG peut déjà servir

PHASE 1.5 — job extract_graph (après ready, async)
  pour chaque chunk PARENT (article / section, parent_id IS NULL) :
    LLM JSON borné → entités + relations
    MERGE dans le graphe (réutiliser un Projet déjà vu)
    source_chunk_id = chunk.id
  documents.graph_extracted = true

PHASE 1.5b — job create_similarities (périodique, ex. nuit)
  uniquement les PROJET nouveaux / pas encore scorés
  (pas un produit cartésien de tout le graphe à chaque nuit)
  score métier (même client, secteur, montant ±20 %, année ±3)
  si score > seuil → SIMILAIRE_A

PHASE 2 — horloge B
  routeur : question relationnelle → requête graphe
          : question textuelle     → RAG hybride
  le LLM met en forme ; il ne ré-extrait pas les liens
```

### 7.4 Job `extract_graph`

1. Charger le document (`status = ready`).
2. Sélectionner les chunks parents.
3. Pour chacun : prompt d’extraction JSON (types fermés, pas d’entité libre).
4. `MERGE` nœuds par clé métier (nom normalisé + type), puis `MERGE` relations — requêtes **paramétrées** (jamais interpoler un libellé dans Cypher). Détail index / résolution d’entités / batch : **§7.8**.
5. En cas de JSON invalide : retry une fois, sinon marquer le chunk `graph_extract_failed` sans bloquer le RAG.
6. `UPDATE documents SET graph_extracted = true`.

Prompt (contrat) : liste fermée d’entités et de relations ci-dessus ; sortie uniquement JSON.

### 7.5 Similarité entre projets

Pas une similarité de texte brute. Score métier, par exemple :

| Critère | Points indicatifs |
|---------|-------------------|
| Même client | +30 |
| Même secteur | +20 |
| Montant ±20 % | +25 |
| Année ±3 | +15 |
| Certifications communes | +10 |

Si total > 50 → arête `SIMILAIRE_A {score, raison}`.

Le job nuit ne compare **pas** tous les projets entre eux à chaque fois : seulement les nœuds `PROJET` sans score de similarité à jour (nouveaux ou `similarity_computed = false`). Voir §7.8.

### 7.6 Requêtes (lecture, horloge B)

- Projets similaires à un projet de référence : suivre `SIMILAIRE_A`, trier par score.
- Certifications qui couvrent les exigences d’un AO : `CONTIENT` puis `SATISFAITE_PAR`.
- Personnes sur des projets voisins : `SIMILAIRE_A` puis `A_TRAVAILLE_SUR` (multi-sauts).

Le texte cité vient toujours de Postgres via `source_chunk_id`.

### 7.7 Jobs async

| Job | Quand | Rôle |
|-----|--------|------|
| `ingest_document` | Upload | Parse, chunks, index vectoriel + Postgres |
| `extract_graph` | Après `ready` | Entités / relations → graphe |
| `create_similarities` | Périodique | `SIMILAIRE_A` **des nouveaux projets seulement** |

V1 peut livrer sans `extract_graph`. Le patrimoine n’est pas perdu : il est déjà dans les chunks. Le graphe **enrichit** les questions relationnelles.

### 7.8 Mise à jour incrémentale (pas de goulot d’étranglement)

Le risque : pour chaque nouveau chunk, **comparer à tout le graphe** (O(n) ou O(n²)). Ce n’est **pas** la stratégie retenue.

```text
NAÏF (interdit)                         RETENU
charger 1 M de nœuds                    index UNIQUE + MERGE
comparer le nom à chacun                résolution d’entités bornée (bloc)
relancer tout le graphe la nuit         enrichir : nœuds/arêtes nouveaux seulement
bloquer l’utilisateur pendant l’OCR     ingest ready d’abord ; extract_graph en ARQ
```

#### 7.8.1 Index et `MERGE` (trouver un nœud existant)

La recherche d’un nœud déjà connu passe par un **index**, pas par un parcours.

Contraintes (une fois, au bootstrap graphe), exemples :

- `ENTREPRISE.siret` UNIQUE (quand le SIRET est connu)
- `PROJET.id` UNIQUE (id métier stable)
- `CLIENT.name_normalized` UNIQUE (clé de repli, voir résolution)

`MERGE` utilise l’index : quelques millisecondes même à grande échelle. Les requêtes Cypher sont **paramétrées** (jamais interpoler un type/libellé dans la chaîne).

#### 7.8.2 Résolution d’entités (le vrai problème)

Le goulot n’est pas « trouver un id indexé », c’est **savoir si deux libellés désignent la même chose** :

```text
« Vinci »  vs  « Vinci Construction »  vs  « VINCI SA »
« projet RATP »  vs  « chantier RATP 2023 »
```

| Méthode | Rôle | Limite |
|---------|------|--------|
| Identifiant unique (SIRET, id interne) | Match exact, O(log n) | Souvent absent dans un PDF |
| Normalisation | minuscules, retirer SAS/SA/Construction | Rate les vrais synonymes |
| **Blocking** | ne comparer que le bloc (ex. 1ʳᵉ lettre / hash) | Peut rater un match hors bloc |
| Fuzzy (Levenshtein / ratio) | **dans le bloc seulement** | Interdit en O(n) sur tout le graphe |
| Embedding | synonymes sémantiques | Plus tard, si le fuzzy ne suffit pas |

**Pipeline `get_or_create` (ordre strict) :**

1. SIRET / id métier → index exact → nœud existant.
2. `name_normalized` (minuscules, formes juridiques ôtées) → index exact.
3. Sinon candidats du **même bloc** uniquement, fuzzy, seuil ~0,85.
4. Sinon **créer** le nœud (`id`, `name`, `name_normalized`, `block`, `siret`, `source_chunk_id`).

On ne charge jamais « tous les `ENTREPRISE` ».

#### 7.8.3 Batch et asynchrone

- Extraire **par document** (chunks parents concaténés, un ou quelques appels LLM), pas 1 LLM × 1 alinéa.
- Écritures graphe en parallèle bornée (`asyncio`, file ARQ).
- `extract_graph` **après** `status = ready` : l’utilisateur RAG n’attend pas le graphe.
- `graph_extracted` évite de relancer le job.

#### 7.8.4 Incrémental, jamais de reconstruction totale

À l’arrivée d’un document :

- extraire **ses** entités / relations ;
- `MERGE` vers l’existant (enrichir `updated_at` / `source_chunk_id`, pas recréer) ;
- **ne pas** recréer les anciennes arêtes du patrimoine.

Similarité : marquer les nouveaux `PROJET` ; le job nuit ne les compare qu’à un **voisinage filtré** (même client, même secteur, montant proche) — pas N×N.

#### 7.8.5 Synthèse

| Risque | Contre-mesure |
|--------|----------------|
| Trouver un nœud | Index UNIQUE + `MERGE` |
| Doublons de noms | SIRET → normalisé → blocking + fuzzy |
| Volume de chunks | Batch LLM par document |
| Bloquer l’UI | Worker ARQ ; RAG dès `ready` |
| Nuit trop longue | Similarité **des nouveaux** seulement |

```text
upload → ingest (ready, RAG OK)
              → enqueue extract_graph   (non bloquant)
user travaille au RAG
              → MERGE indexé + résolution bornée
              → graph_extracted = true
nuit          → SIMILAIRE_A sur projets nouveaux
horloge B     → lecture graphe si question relationnelle
```

---

## 8. Prochaine étape

Schéma V1 figé : métier + auth simplifiée (`tenants` / `users` / `sessions` / `refresh_tokens` / `audit_logs`).

Ensuite, dans le code :

1. Aligner `scripts/init_db.sql` et `app/models/sql.py` sur ce document.
2. Seed tenant `default` + admin.
3. Middleware JWT + filtre `tenant_id` sur toutes les routes métier.
4. Pas d’Alembic tant que le volume Docker n’a pas encore de données (recréer le volume au besoin).