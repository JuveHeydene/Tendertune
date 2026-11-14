Spécification complète et détaillée de l'état **actuel** (V2) : tables métier, authentification, contraintes de workflow. Ce document a servi de plan avant l'implémentation (V1) ; il est maintenant réaligné sur ce qui est réellement en base et dans le code, et les parties devenues fausses ou jamais construites ont été retirées ou marquées comme telles.

**Auth :** `tenants`, `users`, `sessions`, `refresh_tokens`, `audit_logs`. Les deux dernières tables existent dans le schéma mais **ne sont pas alimentées par le code actuel** (voir §1.4 et §1.5) — c'est noté explicitement pour ne pas laisser croire à une fonctionnalité qui n'existe pas.

`tenant_id` et `user_id` des tables métier sont des **UUID** vers `tenants` / `users`. Le slug lisible (`vinci`) est sur `tenants.slug`, pas recopié partout.

---

## 1. Authentification et isolation

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
    -- Overrides optionnels (LLM, template). En place : ollama / llama3 / nomic-embed-text
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
| `id` | PK. C'est **ce** UUID qui va dans `documents.tenant_id`, etc. |
| `slug` | Clé humaine unique. Pas d'espaces. Sert de préfixe MinIO (`vinci/...`). |
| `name` | Raison sociale affichée. |
| `email` | Contact principal du tenant (souvent l'admin). |
| `phone` / `address` | Infos légères (SIRET / APE plus tard). |
| `config` | JSON : modèle LLM, template Word par défaut, quotas. Pas de secrets en clair. |
| `status` | `active` = API OK. `suspended` → 403 même si le JWT est valide. |
| `created_at` / `updated_at` | Audit. |

Pas de `created_by` vers `users` (référence circulaire au seed). L'admin est créé juste après le tenant, au démarrage de l'API (`bootstrap_platform`).

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
| `hashed_password` | Hash. **Jamais** le mot de passe en clair. |
| `first_name` / `last_name` / `phone` | Affichage. |
| `role` | `admin` (tout le tenant), `manager` (dossiers + users), `redacteur` (créer/modifier), `consultant` (lecture). Pas de rôle `api`. |
| `permissions` | Overrides JSON, ex. `{"can_export": true, "can_delete": false}`. |
| `status` | `active` peut se connecter. `inactive` / `suspended` → login refusé. |
| `last_login_at` | Dernière connexion réussie. |
| `login_attempts` / `locked_until` | Anti brute-force (champs présents ; verrouillage automatique non branché à ce jour). |

---

### 1.3. Table `sessions` — Sessions JWT (accès)

On stocke le **hash** du access token, jamais le JWT en clair. **Il n'y a qu'un seul jeton** (voir §1.4) : `sessions.expires_at` = expiration du JWT lui-même.

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
| `id` | PK session. |
| `user_id` | Qui est connecté. |
| `token_hash` | SHA-256 du access token. Lookup à chaque requête authentifiée. |
| `user_agent` / `ip_address` | Traçabilité, révocation d'un device. |
| `expires_at` | Fin de vie du JWT — durée pilotée par `JWT_EXPIRE_MINUTES` (`.env`, **180 min** par défaut). |
| `last_activity_at` | Mis à jour à chaque requête authentifiée réussie. |
| `revoked` / `revoked_at` | Logout ou révocation admin (`POST /admin/sessions/{id}/revoke`). |

---

### 1.4. Table `refresh_tokens` — présente en base, **non utilisée par le code**

Conçue pour un schéma access + refresh token avec rotation. **Le code actuel ne l'utilise pas** : `POST /auth/login` ne crée qu'une ligne `sessions` et renvoie un seul `access_token` (pas de `refresh_token` dans la réponse), et il n'existe aucune route `/auth/refresh`. La table et le modèle ORM existent (prêts si le besoin apparaît — jetons de courte durée + renouvellement silencieux), mais aujourd'hui un utilisateur dont le JWT expire doit simplement se reconnecter.

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

---

### 1.5. Table `audit_logs` — présente en base, **non alimentée par le code**

Recommandée dès la conception (AO = traçabilité), le schéma existe toujours, mais **aucun endpoit n'écrit dans cette table à ce jour** — c'est un vrai manque, pas un choix : un journal d'audit serait particulièrement utile pour un usage professionnel (qui a approuvé quelle section, qui a exporté, qui a supprimé un document). À construire : brancher un `session.add(AuditLog(...))` sur les actions sensibles (login, export, suppression, changement de rôle).

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

---

### 1.6. Hors périmètre actuel (volontairement)

| Table / notion | Pourquoi pas encore |
|----------------|-------------------|
| `api_keys` | Accès machine (ERP). Tout est manuel aujourd'hui. |
| Rôle `api` | Sans clés API, inutile. |
| `user_invitations` | L'admin crée le compte + mot de passe temporaire, à la main. |
| Rotation `refresh_tokens` | Table prête (§1.4), jamais câblée. |
| Écriture `audit_logs` | Table prête (§1.5), jamais alimentée. |

**Seed :** un tenant `slug=default` + un user `admin` (email/mot de passe définis par `.env`, `ADMIN_EMAIL` / `ADMIN_PASSWORD`).

---

## 2. Schéma SQL métier

### 2.1. Table `documents` — Les fichiers uploadés

```sql
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Isolation : UUID du tenant. TOUTES les requêtes doivent filtrer dessus.
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    created_by UUID REFERENCES users(id) ON DELETE SET NULL,

    -- Chemin dans MinIO : ex '<tenant_id>/<uuid>/CCTP.pdf'
    object_key VARCHAR(512) NOT NULL,

    -- Empreinte SHA-256 (déduplication)
    sha VARCHAR(64) NOT NULL,

    -- Rôle du document — DÉTERMINE COMMENT IL EST UTILISÉ EN RECHERCHE
    -- 'patrimoine'  → référence générale du tenant, visible depuis TOUS les dossiers
    -- 'dao_courant' → DAO du dossier en cours d'instruction (extraction exigences/plan)
    -- 'dao_archive' → DAO d'un dossier déjà soumis, reste en RAG comme référence
    -- 'annexe'      → pièce d'appoint scopée à UN SEUL dossier (dossier_id ci-dessous),
    --                 jamais mélangée au patrimoine tant qu'elle n'est pas promue
    doc_role VARCHAR(32) NOT NULL CHECK (doc_role IN ('patrimoine', 'dao_courant', 'dao_archive', 'annexe')),

    doc_type VARCHAR(32) CHECK (doc_type IN
        ('rc', 'cctp', 'ccap', 'memoire', 'reference', 'dpgf', 'bpu', 'administratif', 'autre')),

    -- Vestige de la première maquette : renseigné en sortie API mais plus lu
    -- par aucune règle métier — c'est doc_role qui distingue dao_courant/
    -- dao_archive/patrimoine/annexe. Conservé pour compatibilité d'affichage.
    is_dao BOOLEAN DEFAULT FALSE,

    -- Provenance d'une annexe promue en patrimoine (traçabilité)
    dossier_origine_id UUID REFERENCES dossiers(id) ON DELETE SET NULL,

    -- Scope d'une annexe (doc_role='annexe' UNIQUEMENT) : le dossier auquel
    -- elle est rattachée. NULL pour tout autre doc_role.
    dossier_id UUID REFERENCES dossiers(id) ON DELETE CASCADE,

    -- État de l'ingestion (pipeline asynchrone : parse → OCR si besoin →
    -- découpage → classification → indexation vectorielle → extraction du graphe)
    -- 'pending'    → en file d'attente
    -- 'processing' → en cours
    -- 'ready'      → prêt pour la recherche (RAG)
    -- 'failed'     → échec (voir ingest_error)
    -- 'needs_review' → valeur définie mais jamais affectée par le worker à ce
    --                  jour (pas de bascule automatique sous un seuil de
    --                  confiance OCR — piste, pas construite)
    status VARCHAR(32) DEFAULT 'pending'
        CHECK (status IN ('pending', 'processing', 'ready', 'failed', 'needs_review')),

    -- Message d'erreur si status='failed' (affiché dans l'onglet Documents)
    ingest_error TEXT,

    -- Le graphe d'entités a-t-il été écrit pour CE document ?
    -- status='ready' → RAG hybride utilisable ; graph_extracted est un
    -- second signal, indépendant, mis à jour par le job extract_graph après.
    graph_extracted BOOLEAN NOT NULL DEFAULT FALSE,

    filename VARCHAR(255) NOT NULL,
    size_bytes BIGINT,
    mime_type VARCHAR(128),
    ocr_used BOOLEAN DEFAULT FALSE,
    ocr_confidence FLOAT CHECK (ocr_confidence >= 0 AND ocr_confidence <= 1),
    page_count INTEGER,
    archived_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT unique_tenant_sha UNIQUE (tenant_id, sha)
);

CREATE INDEX idx_documents_tenant_status ON documents(tenant_id, status);
CREATE INDEX idx_documents_tenant_role ON documents(tenant_id, doc_role);
CREATE INDEX idx_documents_dossier_origine ON documents(dossier_origine_id);
CREATE INDEX idx_documents_dossier ON documents(dossier_id);
```

Un PDF **scanné** suit exactement le même chemin qu'un PDF texte : le worker mesure la densité de texte extractible, et bascule automatiquement sur un moteur OCR si elle est trop faible — invisible pour l'utilisateur, seul le temps de traitement diffère (l'OCR est nettement plus lent, plusieurs minutes pour un DAO de 100+ pages).

---

### 2.2. Table `chunks` — Le texte découpé des documents

```sql
CREATE TABLE chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,

    -- Parent/enfant : NULL = ce chunk EST un parent (article / section entière)
    parent_id UUID REFERENCES chunks(id) ON DELETE CASCADE,

    text TEXT NOT NULL,
    heading_path VARCHAR(512),
    page INTEGER,
    token_count INTEGER,
    extra JSONB DEFAULT '{}'::jsonb,

    -- Classification dynamique du TYPE de section (signal doux pour router
    -- les experts de récupération — jamais un filtre bloquant : un chunk
    -- mal classé reste cherchable, la boucle CRAG élargit si besoin).
    -- Deux couches : heuristique par mots-clés (gratuite, sur tous les
    -- parents), puis appel LLM plafonné (40 appels max par document, au-delà
    -- le champ reste NULL plutôt que d'enchaîner des centaines d'appels
    -- séquentiels sur un très gros document).
    section_type VARCHAR(16) CHECK (section_type IN
        ('rc', 'ccap', 'cctp', 'dpgf', 'bpu', 'memoire', 'reference', 'autre')),

    -- Index de recherche plein texte (français), généré, jamais lu/écrit par
    -- l'ORM — requêté en SQL brut pour la recherche lexicale (sparse).
    text_fts TSVECTOR GENERATED ALWAYS AS (to_tsvector('french', text)) STORED,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT chunk_not_self_parent CHECK (id != parent_id)
);

CREATE INDEX idx_chunks_document ON chunks(document_id);
CREATE INDEX idx_chunks_parent ON chunks(parent_id);
CREATE INDEX idx_chunks_page ON chunks(document_id, page);
CREATE INDEX idx_chunks_section_type ON chunks(section_type);
CREATE INDEX idx_chunks_fts ON chunks USING GIN(text_fts);
```

Le même `id` sert d'ancre côté base vectorielle (pas de double numérotation à synchroniser).

---

### 2.3. Table `dossiers` — Les réponses aux appels d'offres

**Un dossier se crée indépendamment de tout DAO et de toute conversation.** C'est le point le plus important qui a changé depuis la première maquette : au départ, un dossier n'existait qu'en sous-produit d'une conversation, avec un plan générique inventé avant même la lecture du DAO — c'était l'inverse de ce que la logique métier impose. Aujourd'hui : `POST /dossiers` crée une ligne vide (`dao_document_id` NULL, aucun `outline_items`), le DAO est chargé et lié *ensuite*, l'analyse (§2.5/§2.4) ne peut démarrer qu'une fois ce DAO `status='ready'`, et une conversation choisit un dossier existant à sa création plutôt que d'en fabriquer un.

```sql
CREATE TABLE dossiers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    -- Peut être NULL : un dossier existe AVANT que son DAO soit chargé
    dao_document_id UUID REFERENCES documents(id) ON DELETE SET NULL,

    client_name VARCHAR(255),
    project_name VARCHAR(255),
    dao_reference VARCHAR(128),
    deadline TIMESTAMPTZ,

    -- 'draft'      → créé, DAO pas encore chargé ou pas encore analysé
    -- 'analyzing'  → extraction exigences/plan en cours (job asynchrone)
    -- 'generating' → plan disponible, rédaction en cours
    -- 'exported'   → un export a été produit au moins une fois
    -- (les valeurs 'review' / 'ready_export' / 'archived' envisagées dans une
    -- première maquette ne sont affectées par aucun code à ce jour — retirées
    -- de la contrainte pour ne pas laisser croire à un cycle de vie qui n'existe pas)
    status VARCHAR(32) DEFAULT 'draft' CHECK (status IN ('draft', 'analyzing', 'generating', 'exported')),

    current_version INTEGER DEFAULT 1,

    created_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Un DAO donné ne sert de source qu'à un seul dossier du tenant
    CONSTRAINT unique_tenant_dao UNIQUE (tenant_id, dao_document_id)
);

CREATE INDEX idx_dossiers_tenant_status ON dossiers(tenant_id, status);
CREATE INDEX idx_dossiers_dao ON dossiers(dao_document_id);
CREATE INDEX idx_dossiers_client ON dossiers(tenant_id, client_name);
```

Un deuxième garde-fou, applicatif celui-ci (pas une contrainte SQL) : `POST /dossiers/{id}/analyser` refuse (HTTP 409) de démarrer une deuxième analyse tant que `status='analyzing'` — observé en conditions réelles : un double-clic (ou une relance automatisée mal gardée) peut lancer deux jobs d'extraction concurrents sur le même dossier, l'un réussit, l'autre plante en pleine écriture, avec un risque de doublons dans `exigences`.

---

### 2.4. Table `exigences` — Les critères extraits du DAO

```sql
CREATE TABLE exigences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dossier_id UUID NOT NULL REFERENCES dossiers(id) ON DELETE CASCADE,
    libelle TEXT NOT NULL,
    type VARCHAR(32) NOT NULL CHECK (type IN
        ('eliminatoire', 'technique', 'administrative', 'financiere', 'delai', 'reference')),
    obligatoire BOOLEAN DEFAULT TRUE,
    page_source INTEGER,
    reference_dao VARCHAR(128),
    statut VARCHAR(32) DEFAULT 'a_couvrir' CHECK (statut IN
        ('a_couvrir', 'en_cours', 'couverte', 'non_couverte', 'a_revoir')),
    preuves_chunks JSONB DEFAULT '[]'::jsonb,
    couverte_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT couverte_after_created CHECK (couverte_at IS NULL OR couverte_at >= created_at)
);

CREATE INDEX idx_exigences_dossier ON exigences(dossier_id);
CREATE INDEX idx_exigences_statut ON exigences(dossier_id, statut);
CREATE INDEX idx_exigences_obligatoire ON exigences(dossier_id, obligatoire, statut);
```

`page_source` est l'ancre du **lot** de chunks d'où l'exigence a été extraite (voir §5.2) : l'extraction traite plusieurs chunks par appel LLM pour rester praticable sur un DAO de 150+ pages, donc la page rapportée est une approximation (première page du lot), pas nécessairement la ligne exacte du DAO.

---

### 2.5. Table `outline_items` — Le plan du dossier

```sql
CREATE TABLE outline_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dossier_id UUID NOT NULL REFERENCES dossiers(id) ON DELETE CASCADE,
    key VARCHAR(128) NOT NULL,
    heading_level INTEGER NOT NULL CHECK (heading_level IN (1, 2, 3)),
    title VARCHAR(512) NOT NULL,
    sort_order INTEGER NOT NULL,
    status VARCHAR(32) DEFAULT 'todo' CHECK (status IN ('todo', 'generated', 'approved', 'rejected')),

    -- Spécialisation déterministe du PROMPT de génération (§10 de
    -- Nouvelle_Architecture/architecture_agentique_retrieval_generation.md) :
    -- un simple lookup, jamais une décision d'agent.
    -- 'institutionnelle' → présentation de l'entreprise
    -- 'factuelle'        → moyens, références, planning (énumération sourcée)
    -- 'narrative'        → méthodologie, organisation (texte construit)
    -- 'conformite'       → QSE et rubriques réglementaires
    archetype VARCHAR(16) NOT NULL DEFAULT 'factuelle'
        CHECK (archetype IN ('institutionnelle', 'factuelle', 'narrative', 'conformite')),

    custom_instruction TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT unique_dossier_key UNIQUE (dossier_id, key)
);

CREATE INDEX idx_outline_dossier ON outline_items(dossier_id);
CREATE INDEX idx_outline_status ON outline_items(dossier_id, status);
CREATE INDEX idx_outline_order ON outline_items(dossier_id, sort_order);
```

Le plan par défaut (5 rubriques : présentation, moyens humains, références, méthodologie, planning) ne sert que de repli — dès qu'un DAO est analysé, le plan réel vient de l'extraction (§5.2) : titres tirés du règlement de consultation quand il en énumère, sinon ce même repli.

---

### 2.6. Table `generations` — Les versions des sections rédigées

```sql
CREATE TABLE generations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dossier_id UUID NOT NULL REFERENCES dossiers(id) ON DELETE CASCADE,
    section_key VARCHAR(128) NOT NULL,

    -- Contenu STRUCTURÉ (JSON contraint, jamais du texte libre) : blocs
    -- typés (paragraphe, liste, sous_titre, image), citations, exigences
    -- couvertes, abstentions éventuelles — le schéma exact vit côté
    -- application (SectionGeneree), pas en contrainte SQL.
    content JSONB NOT NULL,
    citations JSONB DEFAULT '[]'::jsonb,

    -- Snapshot du contexte agrégé envoyé au LLM (audit / reproductibilité)
    context_snapshot JSONB DEFAULT '{}'::jsonb,
    exigences_couvertes JSONB DEFAULT '[]'::jsonb,

    -- Résumé court de progression du dossier, précalculé à l'approbation —
    -- jamais recalculé à chaque question de la conversation.
    summary_short TEXT,

    -- Nom du modèle local utilisé (ex. 'llama3') — un seul fournisseur local
    -- à ce jour, ce champ garde la trace si le modèle change plus tard.
    model VARCHAR(128),

    version INTEGER DEFAULT 1,
    generation_time_seconds FLOAT,
    tokens_in INTEGER,
    tokens_out INTEGER,

    -- Vestige d'une hypothèse multi-fournisseur payant : toujours NULL en
    -- usage 100% local (pas de facturation au token en interne).
    cost_estimate FLOAT,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    FOREIGN KEY (dossier_id, section_key) REFERENCES outline_items(dossier_id, key) ON DELETE CASCADE
);

CREATE INDEX idx_generations_dossier ON generations(dossier_id);
CREATE INDEX idx_generations_section ON generations(dossier_id, section_key);
CREATE INDEX idx_generations_version ON generations(dossier_id, section_key, version);
```

---

### 2.7. Table `reviews` — Les décisions humaines (HITL)

```sql
CREATE TABLE reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    generation_id UUID NOT NULL REFERENCES generations(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,

    -- 'approve' → la section passe outline_items.status='approved'
    -- 'edit'    → texte modifié à la main, puis approuvé dans la foulée
    -- 'regen'   → nouvelle génération demandée (pas de valeur 'skip' : une
    --             section non prioritaire se traite juste plus tard, il n'y
    --             a pas de statut dédié pour l'ignorer explicitement)
    action VARCHAR(32) NOT NULL CHECK (action IN ('approve', 'edit', 'regen')),

    comment TEXT,
    modified_text TEXT,
    regen_instruction TEXT,
    review_time_seconds FLOAT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_reviews_generation ON reviews(generation_id);
CREATE INDEX idx_reviews_user ON reviews(user_id);
```

---

### 2.8. Table `conversations` — Les fils de discussion

```sql
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Choisi À LA CRÉATION de la conversation (ou laissé NULL pour une
    -- recherche libre sur le patrimoine, sans rédaction de dossier).
    -- Jamais déduit ou fabriqué après coup (voir §2.3).
    dossier_id UUID REFERENCES dossiers(id) ON DELETE SET NULL,

    title VARCHAR(255),
    summary TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_conversations_tenant_user ON conversations(tenant_id, user_id);
CREATE INDEX idx_conversations_dossier ON conversations(dossier_id);
```

---

### 2.9. Table `messages` — Les messages individuels

```sql
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role VARCHAR(32) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,

    -- Requête reformulée (autonome, sans dépendre de l'historique) envoyée
    -- au pipeline de récupération — trace comment la question a été comprise
    query_rewrite TEXT,

    generation_id UUID REFERENCES generations(id) ON DELETE SET NULL,
    meta JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_messages_conversation ON messages(conversation_id);
CREATE INDEX idx_messages_created ON messages(conversation_id, created_at);
CREATE INDEX idx_messages_generation ON messages(generation_id);
```

Le message utilisateur est **committé** (pas seulement flush) avant de lancer le pipeline agentique : les experts de récupération tournent en parallèle, chacun avec sa propre connexion base de données, et une ligne seulement flushée sur une connexion reste invisible depuis une autre tant qu'elle n'est pas validée — un point qui a provoqué une vraie violation de clé étrangère sur `retrieval_traces.message_id` (§2.12) avant d'être corrigé.

---

### 2.10. Table `exports` — Les fichiers générés

```sql
CREATE TABLE exports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dossier_id UUID NOT NULL REFERENCES dossiers(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,

    -- 4 formats (pas seulement docx/pdf) : le mémoire peut aussi sortir en
    -- markdown ou texte brut pour relecture rapide sans traitement de texte
    format VARCHAR(16) NOT NULL CHECK (format IN ('docx', 'pdf', 'md', 'txt')),

    object_key VARCHAR(512) NOT NULL,
    size_bytes BIGINT,
    sections_included JSONB DEFAULT '[]'::jsonb,
    exported_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT unique_dossier_version_format UNIQUE (dossier_id, version, format)
);

CREATE INDEX idx_exports_dossier ON exports(dossier_id);
CREATE INDEX idx_exports_version ON exports(dossier_id, version);
```

---

### 2.11. Table `dossier_pieces` — Checklist administrative

Absente de la première maquette. Sémantique volontairement différente d'`exigences` : ici on rattache un **document entier** (une pièce à fournir, comme un KBIS), pas une citation de chunk.

```sql
CREATE TABLE dossier_pieces (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dossier_id UUID NOT NULL REFERENCES dossiers(id) ON DELETE CASCADE,
    libelle VARCHAR(255) NOT NULL,
    obligatoire BOOLEAN DEFAULT TRUE,

    -- Document choisi pour couvrir cette pièce (annexe ou patrimoine)
    document_id UUID REFERENCES documents(id) ON DELETE SET NULL,

    -- 'manquant'          → rien de choisi
    -- 'trouve_patrimoine' → une pièce du patrimoine correspond déjà
    -- 'a_uploader'        → aucune pièce existante ne convient
    -- 'fourni'            → document_id renseigné, pièce couverte
    statut VARCHAR(32) DEFAULT 'manquant'
        CHECK (statut IN ('manquant', 'trouve_patrimoine', 'a_uploader', 'fourni')),

    -- 'rc'       → pièce citée explicitement par le règlement de consultation
    -- 'standard' → pièce de la liste type (KBIS, attestations…), le RC ne
    --              détaillait pas explicitement les pièces attendues
    source VARCHAR(16) DEFAULT 'standard' CHECK (source IN ('rc', 'standard')),

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_dossier_pieces_dossier ON dossier_pieces(dossier_id);
```

---

### 2.12. Table `retrieval_traces` — Observabilité de la boucle CRAG

Absente de la première maquette. Une ligne par tentative de récupération d'un expert — sert à l'évaluation (combien d'itérations en moyenne, taux d'abstention, quel expert échoue le plus souvent) sans avoir à rejouer les conversations.

```sql
CREATE TABLE retrieval_traces (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    message_id UUID REFERENCES messages(id) ON DELETE CASCADE,
    generation_id UUID REFERENCES generations(id) ON DELETE SET NULL,

    -- Index de la sous-question dans la décomposition du Superviseur (0 si
    -- question simple, non décomposée)
    sous_question_index INTEGER DEFAULT 0,
    sous_question_texte TEXT,

    -- Expert de récupération sollicité (spécialisation par domaine métier)
    expert VARCHAR(16) NOT NULL CHECK (expert IN
        ('juridique', 'technique', 'financier', 'graphe', 'patrimoine')),

    -- N-ième tentative dans la boucle CRAG bornée (1, 2, 3 au maximum)
    tentative INTEGER NOT NULL,
    query_utilisee TEXT NOT NULL,
    filtres JSONB DEFAULT '{}'::jsonb,

    -- Résultat de la notation CRAG pour cette tentative
    grade VARCHAR(16) CHECK (grade IN ('correct', 'ambigu', 'incorrect')),
    grade_method VARCHAR(16),

    chunks_retournes JSONB DEFAULT '[]'::jsonb,

    -- true si l'expert a explicitement renoncé (aucune preuve trouvée après
    -- épuisement des tentatives) plutôt que de risquer une réponse inventée
    abstention BOOLEAN DEFAULT FALSE,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_retrieval_traces_message ON retrieval_traces(message_id);
CREATE INDEX idx_retrieval_traces_tenant ON retrieval_traces(tenant_id, created_at);
```

---

### 2.13. ENUM / CHOICES — récapitulatif

| Table | Champ | Valeurs possibles |
|-------|-------|-------------------|
| `tenants` | `status` | `'active'`, `'suspended'` |
| `users` | `role` | `'admin'`, `'manager'`, `'redacteur'`, `'consultant'` |
| `users` | `status` | `'active'`, `'inactive'`, `'suspended'` |
| `documents` | `doc_role` | `'patrimoine'`, `'dao_courant'`, `'dao_archive'`, `'annexe'` |
| `documents` | `doc_type` | `'rc'`, `'cctp'`, `'ccap'`, `'memoire'`, `'reference'`, `'dpgf'`, `'bpu'`, `'administratif'`, `'autre'` |
| `documents` | `status` | `'pending'`, `'processing'`, `'ready'`, `'failed'`, `'needs_review'` (jamais affectée) |
| `chunks` | `section_type` | `'rc'`, `'ccap'`, `'cctp'`, `'dpgf'`, `'bpu'`, `'memoire'`, `'reference'`, `'autre'` — signal doux, peut être `NULL` |
| `dossiers` | `status` | `'draft'`, `'analyzing'`, `'generating'`, `'exported'` |
| `exigences` | `type` | `'eliminatoire'`, `'technique'`, `'administrative'`, `'financiere'`, `'delai'`, `'reference'` |
| `exigences` | `statut` | `'a_couvrir'`, `'en_cours'`, `'couverte'`, `'non_couverte'`, `'a_revoir'` |
| `outline_items` | `heading_level` | `1`, `2`, `3` |
| `outline_items` | `status` | `'todo'`, `'generated'`, `'approved'`, `'rejected'` |
| `outline_items` | `archetype` | `'institutionnelle'`, `'factuelle'`, `'narrative'`, `'conformite'` |
| `reviews` | `action` | `'approve'`, `'edit'`, `'regen'` |
| `messages` | `role` | `'user'`, `'assistant'`, `'system'` |
| `exports` | `format` | `'docx'`, `'pdf'`, `'md'`, `'txt'` |
| `dossier_pieces` | `statut` | `'manquant'`, `'trouve_patrimoine'`, `'a_uploader'`, `'fourni'` |
| `dossier_pieces` | `source` | `'rc'`, `'standard'` |
| `retrieval_traces` | `expert` | `'juridique'`, `'technique'`, `'financier'`, `'graphe'`, `'patrimoine'` |
| `retrieval_traces` | `grade` | `'correct'`, `'ambigu'`, `'incorrect'` |

---

## 3. Relations entre tables et workflow chronologique

### Diagramme des relations (auth + métier)

```text
  TENANTS 1──< USERS 1──< SESSIONS 1──< REFRESH_TOKENS (schéma prêt, non utilisé)
                 │
                 ├── documents.created_by
                 ├── dossiers.created_by
                 ├── conversations.user_id
                 ├── reviews.user_id
                 └── exports.exported_by

  TENANTS 1──< documents, dossiers, conversations, audit_logs (schéma prêt, non alimenté), retrieval_traces
                      │
                      └── chunks / exigences / outline_items / dossier_pieces / generations / messages / exports / retrieval_traces

  DOSSIERS (créés indépendamment) ──< documents (annexe, dossier_id)
           └──0..1── documents (dao_document_id — lié APRÈS la création)
```

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│  dossiers (créé en premier, sans DAO)                                       │
│      │ 0..1 dao_document_id ──► documents (doc_role='dao_courant')          │
│      │                              │ 1─N                                   │
│      │                              ▼                                       │
│      │                           chunks (parent/enfant, section_type)       │
│      │                                                                       │
│      ├──< exigences        (extraites du DAO analysé)                       │
│      ├──< outline_items    (plan, archetype)  ──< generations ──< reviews   │
│      ├──< dossier_pieces   (checklist administrative)                       │
│      ├──< documents (doc_role='annexe', dossier_id)                         │
│      ├──< conversations ──< messages ──< retrieval_traces                   │
│      └──< exports                                                           │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### Workflow chronologique complet

L'ordre ci-dessous est celui qui est réellement suivi par l'application — il diffère d'une première intuition où la conversation aurait précédé le dossier : créer le dossier fantôme au premier message d'une conversation produisait un plan générique inventé avant même la lecture du DAO, sans aucune exigence. L'ordre correct place le dossier et son analyse **avant** toute conversation.

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ ÉTAPE 1 : CRÉATION DU DOSSIER — indépendante, sans DAO ni conversation      │
│                                                                             │
│ 1️⃣ Jean (tenant "vinci") crée un dossier : POST /dossiers                  │
│    → Table dossiers : ligne créée                                          │
│        - dao_document_id: NULL                                             │
│        - client_name: "SNCF" · project_name: "Gare de Nantes"              │
│        - status: "draft"                                                   │
│    → Aucun outline_items inséré ici (pas de plan générique inventé)        │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ ÉTAPE 2 : CHARGEMENT DU DAO — lié à CE dossier                             │
│                                                                             │
│ 2️⃣ Jean charge "DAO_Gare_Nantes.pdf" dans l'onglet Documents du dossier    │
│    → POST /documents (doc_role="dao_courant", dossier_id=<id du dossier>)  │
│    → Table documents : ligne créée (status="pending")                     │
│    → dossiers.dao_document_id renseigné IMMÉDIATEMENT (pas après coup)     │
│    → File de tâches : job d'ingestion déposé                              │
│                                                                             │
│ 3️⃣ Travailleur d'ingestion (asynchrone)                                    │
│    → Télécharge depuis le stockage objet                                   │
│    → Mesure la densité de texte extractible ; scan → OCR, sinon lecture    │
│      directe (transparent pour l'utilisateur, juste plus lent si scan)     │
│    → Table chunks : parents + enfants créés, section_type classé          │
│    → Indexation vectorielle + texte intégral (recherche lexicale)         │
│    → documents.status = "ready"                                            │
│    → (job suivant, non bloquant) extraction du graphe d'entités            │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ ÉTAPE 3 : ANALYSE DU DAO — exigences, plan, pièces administratives         │
│                                                                             │
│ 4️⃣ Jean clique "Analyser le DAO" — refusé (409) tant que status="analyzing"│
│    déjà en cours ; refusé (400) tant que le DAO n'est pas "ready"          │
│    → dossiers.status = "analyzing"                                         │
│    → File de tâches : job d'analyse déposé                                │
│                                                                             │
│ 5️⃣ Travailleur d'analyse (asynchrone)                                     │
│    → Regroupe les chunks parents par lots (pas un appel LLM par chunk :    │
│      sur un DAO de 150+ pages, ça représenterait des heures et le job      │
│      dépasserait le délai maximal du système de tâches, qui le relance     │
│      indéfiniment depuis zéro sans jamais aboutir)                         │
│    → Table exigences : ~15 lignes (éliminatoire/technique/financière/…)    │
│    → Table outline_items : plan tiré du règlement de consultation, sinon   │
│      le plan par défaut ; chaque rubrique reçoit son archetype             │
│    → Table dossier_pieces : checklist administrative (KBIS, attestations…) │
│    → dossiers.status = "generating"                                        │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ ÉTAPE 4 : CONVERSATION — dédiée à CE dossier, choisi dès la création       │
│                                                                             │
│ 6️⃣ Jean démarre une conversation et choisit le dossier "Gare de Nantes"    │
│    → POST /conversations (dossier_id=<id du dossier>)                     │
│    → Table conversations : dossier_id renseigné DÈS LA CRÉATION           │
│      (ou laissé NULL pour une recherche libre sur le patrimoine)          │
│    → L'interface affiche en direct l'état du dossier (exigences X/Y,      │
│      sections Y/Z couvertes) au-dessus du fil de discussion               │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ ÉTAPE 5 : GÉNÉRATION D'UNE SECTION — pipeline agentique                    │
│                                                                             │
│ 7️⃣ Jean demande : "Rédige la section Références"                          │
│    → Table messages : msg-002 (user), COMMITTÉ avant dispatch des experts  │
│    → Superviseur : classe l'intention, décompose si nécessaire            │
│    → Experts de récupération (recherche dense + lexicale → fusion par     │
│      rang → ré-ordonnancement → notation CRAG ; boucle bornée à 3          │
│      tentatives, reformulation ou élargissement des filtres entre deux)   │
│    → Table retrieval_traces : une ligne par tentative de chaque expert    │
│    → Agrégation du contexte multi-experts                                  │
│    → Génération de la section selon son archetype (JSON contraint)        │
│    → Table generations : gen-001 (version 1), citations, exigences        │
│      couvertes, contexte snapshotté                                        │
│    → Table messages : msg-003 (assistant), generation_id = gen-001        │
│    → outline_items.status = "generated"                                    │
│    ⚠️ Si des exigences obligatoires ne trouvent aucune preuve, la section  │
│    est quand même générée : c'est une alerte visuelle pour le rédacteur,   │
│    jamais un blocage automatique — la décision finale reste humaine       │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ ÉTAPE 6 : REVUE HUMAINE (HITL)                                             │
│                                                                             │
│ 8️⃣ Jean approuve, modifie, ou demande une régénération                     │
│    → Table reviews : action ∈ {approve, edit, regen}                      │
│    → Si regen : Table generations : gen-002 (version 2), nouvelle boucle   │
│      de récupération avec la consigne complémentaire                      │
│    → Si approve/edit : outline_items.status = "approved"                  │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ ÉTAPE 7 : EXPORT                                                            │
│                                                                             │
│ 9️⃣ Jean exporte (docx, pdf, md ou txt)                                     │
│    → Assemble les sections approuvées, dans l'ordre du plan                │
│    → Table exports : ligne créée (version, format, object_key)            │
│    → dossiers.status = "exported"                                          │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ ÉTAPE 8 : HISTORIQUE                                                        │
│                                                                             │
│ Disponible à tout moment :                                                 │
│  - messages d'une conversation ; versions successives d'une generation ;   │
│    décisions reviews ; exports ; traces retrieval_traces pour audit/éval   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Authentification : flux réel et permissions

Routes publiques : `/health`, `/auth/login`, `/docs`, `/openapi.json`.
Le reste exige `Authorization: Bearer <access_token>`.

### 4.1 Inscription / seed

1. Créer `tenants` (`slug`, `name`, `email`, `status=active`).
2. Créer `users` admin (`role=admin`, mot de passe hashé) — fait au démarrage de l'API (`bootstrap_platform`).
3. Login → `sessions` + JWT.

Ajout d'un collaborateur : l'admin crée le user (email, rôle, mot de passe). Pas d'invitation par lien, pas de rotation de jeton (§1.4).

### 4.2 Connexion

`POST /auth/login` `{ email, password }` :

1. User existe, `status=active`, tenant `status=active`.
2. Vérifier le hash du mot de passe.
3. Créer une session (`token_hash`, `expires_at` = maintenant + `JWT_EXPIRE_MINUTES`).
4. Réponse : `{ access_token, token_type: "bearer", user: {...} }` — **un seul jeton**, pas de `refresh_token` dans la réponse (§1.4).
5. `audit_logs` : prévu mais pas encore écrit (§1.5).

### 4.3 Requête authentifiée

Le middleware : hash du Bearer → `sessions` non révoquée et non expirée → decode JWT (`sub`, `tenant_id`, `role`) → user et tenant actifs → utilisateur courant injecté dans la requête.

**Toute requête métier filtre `tenant_id = <tenant de l'utilisateur courant>`.** Un UUID d'un autre tenant → 404, jamais de fuite cross-tenant.

### 4.4 Rôles

| Action | Rôle mini |
|--------|-----------|
| Lire documents / dossiers | `consultant` |
| Upload, générer, approuver | `redacteur` |
| Supprimer document | `manager` |
| Export | `redacteur` |
| Gérer users / tenants / sessions | `admin` |

### 4.5 Vérification d'accès document

1. Document existe.
2. `doc.tenant_id == current_user.tenant_id`.
3. Rôle dans `admin|manager|redacteur|consultant` (le `consultant` ne dépose ni ne supprime rien).

---

## 5. Contraintes et règles de validation (état réel)

### 5.1. Filtrage des documents pour la recherche

```python
def filtres_recherche(dossier, doc_roles_demandes):
    """
    Filtres appliqués par un expert de récupération (app/rag/hybrid_retriever.py).

    - tenant_id : toujours.
    - doc_role IN ('patrimoine', 'dao_archive') par défaut — le dao_courant
      D'UN AUTRE dossier n'est jamais mélangé.
    - doc_role='annexe' : autorisé UNIQUEMENT si dossier_id correspond au
      dossier de la conversation en cours (jamais visible depuis un autre
      dossier, jamais confondu avec le patrimoine général).
    - section_type : signal DOUX (should, pas must) — un chunk mal classé ou
      non classé reste cherchable.
    """
```

Pas d'exception câblée pour inclure le `dao_courant` sur certaines rubriques (« compréhension », « méthodologie ») : une variante de cette idée avait été envisagée à la conception, elle n'a pas été retenue dans le code de récupération.

### 5.2. Extraction des exigences et du plan

```python
async def extract_exigences(session, dossier):
    """
    app/workflow/extract_structure.py — état réel, pas la première intuition
    ("lire le texte complet du DAO en un seul appel").

    1. Charger tous les chunks PARENTS du DAO, écarter ceux classés 'bpu'
       (un bordereau de prix n'énonce jamais d'exigence qualitative).
    2. Regrouper les parents en LOTS (jusqu'à ~14 000 caractères par lot,
       fenêtre de contexte du LLM fixée explicitement à 4096 tokens) —
       pas un appel par chunk : sur un DAO volumineux, le nombre d'appels
       séquentiels dépasserait le délai maximal du worker.
    3. Pour chaque lot : un appel LLM (JSON contraint), les exigences
       trouvées héritent de la page du DÉBUT du lot comme ancre approximative.
    4. Échec d'un lot (délai dépassé) → on l'ignore et on continue avec les
       suivants, jamais d'arrêt total du job pour un seul lot en échec.
    5. Déduplication floue (Levenshtein/Jaccard) avant insertion : un même
       critère répété dans le RC et le CCAP ne crée pas deux lignes.
    """
```

### 5.3. Archivage d'un DAO — non implémenté

Une bascule automatique `dao_courant` → `dao_archive` après soumission avait été envisagée. **Aucune route ni fonction ne fait cette bascule à ce jour** : `doc_role` reste `'dao_courant'` tant que personne ne le change manuellement. Piste plutôt qu'état réel.

### 5.4. Documents déposés pendant une conversation

```python
async def upload_conversation_document(conversation, file, role):
    """
    app/api/conversations.py — POST /conversations/{id}/documents.

    Le rôle n'est PLUS figé à 'patrimoine' (bug corrigé) : l'utilisateur
    choisit EXPLICITEMENT entre :
      - 'annexe'     → aide ponctuelle pour CE dossier uniquement, jamais
                       visible ailleurs, jamais mélangée au patrimoine
      - 'patrimoine' → référence réutilisable pour tous les futurs dossiers

    'annexe' n'a de sens que si la conversation est déjà liée à un dossier ;
    sans dossier (recherche libre), le choix retombe automatiquement sur
    'patrimoine' (rien à scoper).
    Une annexe peut être promue en patrimoine ensuite (dossier_origine_id
    trace sa provenance).
    """
```

### 5.5. Génération d'une section

```python
async def generate_section(section_key, archetype, aggregated_context):
    """
    app/workflow/nodes/generate_section.py.

    1. Le prompt est choisi selon l'archetype de la rubrique (§2.5) — un
       lookup déterministe, jamais une décision d'agent.
    2. Sortie JSON contrainte (blocs typés) ; en cas de JSON invalide,
       nouvelle tentative (2 essais maximum), pas d'exception qui remonte
       jusqu'à l'utilisateur pour un simple accroc de formatage.
    3. Les exigences obligatoires non couvertes ne bloquent PAS la
       génération : elles remontent comme alerte visuelle (bannière rouge
       dans l'interface) pour que le rédacteur tranche — décision humaine,
       pas un ValidationError qui interromprait le flux.
    """
```

### 5.6. Validation du contenu généré

La validation porte sur la forme (JSON bien formé, citations qui pointent vers des chunks réellement fournis dans le contexte) plutôt que sur un contrôle sémantique strict des faits chiffrés — c'est la revue humaine (§2.7) qui reste la dernière ligne de vérification, pas un automate qui bloquerait la génération.

---

## 6. Résumé des contraintes de filtrage RAG

| Contexte | Documents autorisés | Documents exclus | Raison |
|----------|---------------------|-------------------|--------|
| Recherche pour génération | `patrimoine`, `dao_archive`, `annexe` (scopée au dossier) | `dao_courant` d'un autre dossier | Éviter la pollution par d'autres AO |
| Extraction exigences/plan | Chunks du DAO du dossier uniquement, hors `bpu` | Tous les autres documents | Les exigences viennent uniquement du DAO en cours |
| Upload en conversation | Choix explicite `annexe` ou `patrimoine` | — | Plus de rôle figé (bug corrigé, §5.4) |

---

## 7. Graphe de connaissances

Le RAG hybride (index vectoriel + texte en base relationnelle) répond à : *« quels extraits parlent de X ? »*
Le graphe répond à : *« quels **liens** existent entre les entités ? »*

**Écriture du graphe = horloge A** (job après ingestion), **lecture = horloge B** (au moment de la question). On n'extrait pas le graphe à chaque question.

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
```

Chaque nœud et chaque arête portent `source_chunk_id` → `chunks.id` (citation page / article).

**`SIMILAIRE_A` entre projets et le job périodique associé, décrits dans une première maquette, ne sont pas implémentés** — aucun job de ce type n'existe dans le planificateur de tâches à ce jour. Les requêtes de lecture (§7.6) restent donc limitées aux relations directes et aux parcours à 1-2 sauts, jamais à une similarité calculée.

### 7.3 Chronologie

```text
PHASE 1 — ingestion document (le socle)
  fichier → parse (OCR si scan) → chunks → index vectoriel + texte relationnel
  graphe encore vide ; documents.graph_extracted = false
  documents.status = ready  → le RAG peut déjà servir

PHASE 1.5 — job extract_graph (après ready, asynchrone, non bloquant)
  pour chaque chunk PARENT (parent_id IS NULL) :
    LLM JSON borné → entités + relations
    MERGE dans le graphe (réutiliser un nœud déjà vu)
    source_chunk_id = chunk.id
  documents.graph_extracted = true

PHASE 2 — horloge B (au moment de la question)
  Superviseur : question relationnelle → expert graphe
              : question textuelle     → experts RAG hybride
  le LLM met en forme ; il ne ré-extrait pas les liens
```

### 7.4 Job `extract_graph`

1. Charger le document (`status = ready`).
2. Sélectionner les chunks parents — **sans plafond arbitraire** (une première version limitait à 12 chunks, retiré : rien ne justifiait ce chiffre, un DAO plus long perdait silencieusement ses dernières sections).
3. Pour chacun : prompt d'extraction JSON (types fermés, pas d'entité libre).
4. `MERGE` nœuds par clé métier (nom normalisé), puis `MERGE` relations — requêtes **paramétrées** (jamais interpoler un libellé dans Cypher, voir `app/graph/cypher.py`).
5. En cas de JSON invalide sur un chunk : on l'ignore et on continue, sans bloquer le RAG.
6. `documents.graph_extracted = true`.

### 7.5 Résolution d'entités (le vrai problème)

Le goulot n'est pas « trouver un id indexé », c'est **savoir si deux libellés désignent la même chose** : « Vinci » vs « Vinci Construction » vs « VINCI SA ». Pipeline implémenté (`app/graph/entity_match.py`, `EntityMatchIndex`), réutilisé à trois endroits (extraction du graphe, résolution d'entités côté requête, déduplication des exigences extraites) :

1. Identifiant unique (SIRET / id métier) → match exact.
2. Nom normalisé (minuscules, formes juridiques ôtées) → match exact.
3. Sinon comparaison floue (Levenshtein / Jaccard) parmi les candidats déjà rencontrés.
4. Sinon création d'une nouvelle entrée.

On ne charge jamais « toutes les entités » pour comparer : la cascade s'arrête dès qu'un niveau trouve une correspondance.

### 7.6 Requêtes (lecture, horloge B)

Templates Cypher fixes et paramétrés (`app/graph/cypher.py`), 1 à 2 sauts maximum — jamais de Cypher généré librement par le LLM. Le texte cité vient toujours de Postgres via `source_chunk_id`.

### 7.7 Jobs asynchrones réellement enregistrés

| Job | Fichier | Quand | Rôle |
|-----|---------|--------|------|
| `ingest_document` | `app/workers/ingest.py` | Upload d'un document | Parse (OCR si besoin), chunks, index vectoriel + Postgres |
| `extract_graph` | `app/graph/extract.py` | Après `status=ready` | Entités / relations → graphe |
| `extract_dossier_structure` | `app/workflow/extract_structure.py` | Sur demande (« Analyser le DAO ») | Exigences, plan, checklist administrative |

Ce sont les **trois seuls** jobs enregistrés dans le planificateur (`app/worker_settings.py`). Un éventuel job de calcul de similarité périodique, envisagé à la conception, n'en fait pas partie.

---

## 8. État actuel et pistes non retenues à ce jour

Ce document décrit le schéma réellement en place. Pour repartir dessus :

1. `scripts/init_db.sql` et `app/models/sql.py` sont la source de vérité exécutable — ce document en est la version commentée, à resynchroniser s'ils divergent.
2. Le seed (tenant `default` + admin) tourne au démarrage de l'API, pas besoin d'étape manuelle séparée.
3. Middleware JWT + filtre `tenant_id` déjà branché sur toutes les routes métier.

**Pistes documentées ci-dessus mais non construites**, à traiter comme du travail futur plutôt que comme un état déjà acquis :

- Rotation des jetons via `refresh_tokens` (§1.4).
- Écriture effective dans `audit_logs` (§1.5).
- Bascule automatique `needs_review` sous un seuil de confiance OCR (§2.1).
- Archivage explicite d'un DAO (`dao_courant` → `dao_archive`, §5.3).
- Calcul périodique de similarité entre projets (`SIMILAIRE_A`, §7.2).
- Clés API / rôle `api` / invitations par lien (§1.6).
