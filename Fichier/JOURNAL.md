# Journal du projet BTP RAG

Document vivant : on y consigne **ce qui a été fait**, **pourquoi**, et **les commandes à lancer**.  
Les notes d’architecture restent dans `Fichier/` (synthèse encadreur : `Fichier/architecture_synthese.md`) ; ici c’est le fil des étapes concrètes.

**Décision figée :** jobs d’ingestion = **ARQ + Redis** (pas Celery). Un essai Celery a été annulé.

**Lancement :** `docker compose up -d` = infra. `--profile dev` (ou `app`) = API + worker + **un** front Vite. Hybride : uvicorn + `npm run dev` dans `frontend_ao`.

---

---

## Étape 0 — Prérequis machine (24 août 2026)

Vérifié sur `kemayou-PC` :

| Outil | Version / état |
|--------|----------------|
| Docker | 29.6.2 |
| Docker Compose | v5.3.1 |
| Ollama | 0.16.2 |
| Python | 3.13.13 (`>= 3.12` requis) |
| uv | 0.12.3 |

Modèles Ollama déjà présents :

| Nom | Rôle dans le projet |
|-----|---------------------|
| `llama3:latest` | LLM local (`LLM_MODEL=llama3`) |
| `nomic-embed-text:latest` | embeddings (`EMBED_MODEL=nomic-embed-text`) |

Le GPU **n’est pas obligatoire**. Interrupteur unique : `USE_GPU=false` dans `.env`.  
BGE-M3 / reranker HuggingFace restent l’objectif métier plus tard ; on part d’Ollama.

**Commandes déjà exécutées :** `docker --version`, `docker compose version`, `ollama --version`, `ollama list`, `python3 --version`, `uv --version`.

---

## Étape 1 — Initialisation du socle (fichiers créés)

Objectif de cette étape : poser l’**environnement reproductible** (Docker + `uv` + config) et le **squelette applicatif**, sans encore parser de PDF ni lancer de RAG réel.

### 1.1 Décisions d’implémentation

```text
Navigateur
    → FastAPI (app/)                    porte HTTP, pas de parse
         → ARQ / Redis                  horloge A : ingestion longue
         → LangGraph                    horloge B : question / dossier
              → LlamaIndex + Ollama

Fichiers bruts     MinIO
Texte des chunks   PostgreSQL   ← source de vérité des citations
Vecteurs           Qdrant
Graphe (phase 1.5) Neo4j        ← lancé, pas encore utilisé
```

- **Docker** = infrastructure seulement (Postgres, Qdrant, Neo4j, Redis, MinIO).
- **API + worker ARQ** = lancés sur l’hôte avec `uv`, pour parler à Ollama en `localhost:11434`.
- **GPU** : overlay `docker-compose.gpu.yml` seulement si `USE_GPU=true`.

### 1.2 Fichiers créés et pourquoi

#### Racine — outillage

| Fichier | Pourquoi |
|---------|----------|
| `pyproject.toml` | Projet `uv` : dépendances cœur (FastAPI, LlamaIndex, ARQ, clients DB). Docling / Paddle / GPU = extras optionnels, pas installés au départ. |
| `.python-version` | Python 3.12+ (la machine a 3.13, compatible). |
| `.env` / `.env.example` | Une source de vérité runtime. `.env` n’est pas versionné. `USE_GPU`, URLs, modèles Ollama. |
| `.gitignore` | Ignore `.venv`, `.env`, caches. |
| `.dockerignore` | Image Docker plus légère (plus tard). |
| `Dockerfile` | Image API/worker pour un déploiement VPS ultérieur. Non utilisée tant qu’on tourne en local avec `uv`. |
| `docker-compose.yml` | 5 services infra + profil optionnel `app` (API/worker). **Pas de GPU.** |
| `docker-compose.gpu.yml` | Overlay NVIDIA. À n’appliquer que si `USE_GPU=true`. |
| `JOURNAL.md` | Ce fichier : historique des étapes. |

#### `app/` — code Python

| Fichier | Pourquoi |
|---------|----------|
| `app/config.py` | `pydantic-settings` : lit `.env`. `use_gpu` → `device` (`cpu` / `cuda`). |
| `app/main.py` | FastAPI + `/health` (affiche GPU, LLM, embed). |
| `app/worker_settings.py` | Config ARQ : Redis + fonction `ingest_document`. |
| `app/api/documents.py` | Upload / statut document (squelette). |
| `app/api/conversations.py` | Chat (squelette). |
| `app/api/dossiers.py` | Workflow dossier + revue HITL + export (squelette). |
| `app/models/pydantic.py` | Contrats : `Exigence`, `SectionGeneree`, `Chunk`, etc. Le LLM remplira ça, pas du texte libre. |
| `app/models/sql.py` | Miroir SQLAlchemy des tables Postgres. |
| `app/services/minio_client.py` | Client S3 MinIO + création des buckets. |
| `app/services/db_client.py` | Engine SQLAlchemy **async** (`postgresql+asyncpg://`). |
| `app/rag/llama_index_setup.py` | Branche LlamaIndex sur Ollama + Qdrant. |
| `app/rag/hybrid_retriever.py` | Placeholder recherche hybride. |
| `app/rag/rerank.py` | Placeholder rerank (respectera `USE_GPU`). |
| `app/workflow/graph.py` | LangGraph V1 : route → retrieve → generate. |
| `app/workflow/nodes/route.py` | Intent déterministe (règles). |
| `app/workflow/nodes/retrieve.py` | Retrieve (vide pour l’instant). |
| `app/workflow/nodes/generate.py` | Génération (vide pour l’instant). |
| `app/workflow/nodes/validate.py` | Validateur schéma / citations (vide). |
| `app/workers/ingest.py` | Job ARQ : log seulement. Parse / embed à brancher. |
| `app/graph/extract.py` | Phase 1.5 graphe — volontairement vide. |
| `app/graph/cypher.py` | Requêtes Neo4j — volontairement vide. |

#### `scripts/` et `tests/`

| Fichier | Pourquoi |
|---------|----------|
| `scripts/init_db.sql` | Schéma Postgres. Exécuté **automatiquement** au premier start Docker (volume vide). |
| `scripts/create_buckets.py` | Crée `ao-raw` (PDF originaux) et `ao-exports` (DOCX générés). |
| `tests/test_config.py` | Vérifie `USE_GPU=false` → `cpu`, `true` → `cuda`. |

### 1.3 Ce qui n’est **pas** encore fait

- Pas de parse Docling / Paddle.
- Pas d’upload réel ni de `enqueue` ARQ depuis l’API.
- Pas d’indexation Qdrant.
- Routes HTTP = `not_implemented`.

### 1.4 Commandes encore à lancer (dans l’ordre)

Depuis la racine du projet :

```bash
# 1. Lock + venv (Python 3.13 OK)
uv lock
uv sync --all-groups

# 2. Vérifier que .env est bien lu
uv run python -c "from app.config import get_settings; s=get_settings(); print(s.use_gpu, s.device, s.llm_model, s.embed_model)"
# Attendu : False cpu llama3 nomic-embed-text

# 3. Toute la stack (Postgres, Qdrant, Neo4j, Redis, MinIO, API, worker ARQ)
# Les buckets MinIO et le worker partent tout seuls.
docker compose up -d --build
docker compose ps

# 4. Health
curl -s http://localhost:8000/health
```

Consoles : MinIO http://localhost:9001 (`minioadmin`/`minioadmin`) · Qdrant http://localhost:6333/dashboard · Neo4j http://localhost:7474 (`neo4j`/`password123`) · API http://localhost:8000/docs

---

## Schéma PostgreSQL — à quoi sert chaque table

Postgres n’est **pas** le moteur vectoriel. Il est le **registre métier** :

- qui a uploadé quoi ;
- le **texte** des chunks (pour citer une page sans dépendre de Qdrant) ;
- l’historique chat ;
- le dossier d’offre (exigences, plan, générations, décisions humaines).

Qdrant pointe vers `chunks.id`. Neo4j (plus tard) pointera aussi vers `chunks.id`.  
Le PDF binaire n’est **jamais** dans Postgres : il est dans MinIO, référencé par `documents.object_key`.

```text
documents 1 ──< chunks
                 │
dossiers  1 ──< exigences
     │ 1 ──< outline_items          (plan du mémoire : titres figés)
     │ 1 ──< generations            (JSON d’une section rédigée)
     │         └── 1 ──< reviews    (HITL : approve / edit / regen)
     │
conversations 1 ──< messages        (fil de chat, distinct des générations)
     └── dossier_id ?               (chat éventuellement lié à un dossier)
```

### `documents`

**Rôle :** une ligne par fichier uploadé (DAO courant ou patrimoine). C’est la fiche d’identité du binaire MinIO.

Sans cette table on ne saurait pas si un PDF est déjà indexé, s’il est un scan, ni où il vit dans MinIO.

| Attribut | Type | Rôle |
|----------|------|------|
| `id` | UUID PK | Identifiant unique du document. C’est lui qu’on passe au job ARQ `ingest(document_id)`. |
| `tenant_id` | VARCHAR(64) | Isolation multi-entreprises / multi-entités. V1 = `"default"`. Toutes les recherches filtreront dessus (ACL). |
| `object_key` | VARCHAR(512) | Chemin MinIO du fichier brut, ex. `default/<id>/CCTP.pdf`. Postgres ne stocke pas les octets. |
| `sha` | VARCHAR(64) | Empreinte SHA-256 du fichier. Avec `tenant_id`, contrainte `UNIQUE` : on refuse d’ingérer deux fois le même PDF. |
| `doc_role` | VARCHAR(32) | `patrimoine` (anciens dossiers, mémoire) vs `dao_courant` (consultation en cours). Change le filtrage RAG : on n’extrait les exigences que sur le DAO courant. |
| `doc_type` | VARCHAR(32) | Nature métier : `rc`, `cctp`, `ccap`, `memoire`, `reference`, `scan`, `dpgf`, `bpu`, `autre`. Sert de filtre metadata (ex. « seulement les CCAP »). |
| `status` | VARCHAR(32) | Cycle d’ingestion : `pending` → `processing` → `ready` \| `failed` \| `needs_review`. Le chat refuse de générer une section tant que le DAO n’est pas `ready`. |
| `ocr_used` | BOOLEAN | `true` si Paddle a été utilisé (scan). Utile pour audit qualité et pour ne pas indexer en silence une page OCR < 0,7. |
| `filename` | VARCHAR(255) | Nom d’origine affiché à l’utilisateur. |
| `created_at` | TIMESTAMPTZ | Date d’upload. |

### `chunks`

**Rôle :** **source de vérité du texte** découpé (articles, tableaux, alinéas). Qdrant ne garde que les vecteurs + `chunk_id` ; une citation `[3]` = `SELECT text, page FROM chunks WHERE id = …`.

Le découpage est **parent / child** : on cherche sur le child (petit), le LLM lit le parent (article entier).

| Attribut | Type | Rôle |
|----------|------|------|
| `id` | UUID PK | Identifiant du chunk. **Identique** au point Qdrant. C’est l’id mis dans les citations. |
| `document_id` | UUID FK → `documents` | Relie le passage à son PDF. `ON DELETE CASCADE` : supprimer le document enlève ses chunks. |
| `parent_id` | UUID nullable | Si renseigné : ce chunk est un **child**. Le parent est la section / l’article (~jusqu’à 1500 tokens) envoyé au LLM. `NULL` = ce chunk est lui-même un parent. |
| `text` | TEXT | Texte indexé / cité. Inclut un préfixe métier du type `[Pièce: CCAP] [Article 8] [Page 14]` pour que l’embedding « voie » le titre. |
| `heading_path` | VARCHAR(512) | Fil d’Ariane structurel, ex. `CCAP > Article 8 > Pénalités`. Filtre et affichage. |
| `page` | INTEGER | Page source dans le PDF. Obligatoire pour la traçabilité AO. |
| `token_count` | INTEGER | Taille en tokens. Sert à plafonner le contexte collé au LLM. |
| `extra` | JSONB | Métadonnées souples : `ocr_confidence`, `lot`, `year`, `article_id`, `acl`, etc. sans migrer le schéma à chaque champ. |

### `conversations`

**Rôle :** un **fil de chat** (pas un dossier d’offre). Permet de relire l’historique et de réécrire « et la pénalité ? » grâce aux messages précédents.

| Attribut | Type | Rôle |
|----------|------|------|
| `id` | UUID PK | Identifiant du fil. Correspond à `POST /conversations/{id}/messages`. |
| `tenant_id` | VARCHAR(64) | Même isolation ACL que les documents. |
| `user_id` | VARCHAR(64) | Qui parle. Auth JWT plus tard. |
| `dossier_id` | UUID nullable | Si le chat est lié à un dossier d’offre en cours. `NULL` = chat patrimoine / Q&A libre. |
| `created_at` | TIMESTAMPTZ | Création du fil. |

### `messages`

**Rôle :** historique **conversationnel** (user / assistant). Distinct de `generations`, qui archive une **section de dossier** + le contexte RAG envoyé.

| Attribut | Type | Rôle |
|----------|------|------|
| `id` | UUID PK | Identifiant du message. |
| `conversation_id` | UUID FK → `conversations` | Fil parent. Cascade à la suppression du fil. |
| `role` | VARCHAR(32) | `user` ou `assistant` (éventuellement `system`). |
| `content` | TEXT | Texte affiché dans le chat. |
| `query_rewrite` | TEXT | Version « nettoyée » de la question après nœud rewrite LangGraph (deixis : « ça » → « clause de pénalité Dupont »). Audit + debug retrieval. |
| `created_at` | TIMESTAMPTZ | Ordre chronologique du fil. |

### `dossiers`

**Rôle :** une **consultation / offre en cours de constitution**. C’est l’objet métier du workflow LangGraph (pas un PDF).

| Attribut | Type | Rôle |
|----------|------|------|
| `id` | UUID PK | Identifiant du dossier. Routes `/dossiers/{id}/run`, export, revue. |
| `tenant_id` | VARCHAR(64) | Isolation. |
| `dao_document_id` | UUID FK → `documents` | Le DAO **de cette** consultation (celui dont on extrait les exigences). Le patrimoine est ailleurs, via `doc_role`. |
| `status` | VARCHAR(32) | Cycle dossier : `draft` → génération sections → `ready_export`, etc. |
| `created_at` | TIMESTAMPTZ | Création. |

### `exigences`

**Rôle :** critères extraits du DAO (obligatoires, techniques, admin…). Une section générée devra lister `exigences_couvertes`. Sans ça, on ne peut pas vérifier la conformité.

| Attribut | Type | Rôle |
|----------|------|------|
| `id` | UUID PK | Identifiant d’exigence (référencé dans `SectionGeneree.exigences_couvertes`). |
| `dossier_id` | UUID FK → `dossiers` | Appartient à un dossier. Cascade si on supprime le dossier. |
| `libelle` | TEXT | Énoncé, ex. « ISO 9001 obligatoire ». C’est ce qu’on envoie au retriever. |
| `type` | VARCHAR(64) | Famille : éliminatoire, technique, admin, financier, délai… Oriente hybride vs SQL vs graphe. |
| `obligatoire` | BOOLEAN | Si `true` et aucune preuve en citation → le validateur **échoue** (on n’invente pas). |
| `page_source` | INTEGER | Page du DAO d’où vient l’exigence. Traçabilité. |
| `statut` | VARCHAR(32) | `todo` / couverte / non couverte / à revoir. |

### `outline_items`

**Rôle :** **canevas figé** du mémoire (titres H1/H2). Le LLM n’a pas le droit d’inventer la numérotation. Le Word pose ces titres via `python-docx`, pas le modèle.

| Attribut | Type | Rôle |
|----------|------|------|
| `id` | UUID PK | Identifiant de la rubrique. |
| `dossier_id` | UUID FK → `dossiers` | Plan propre à ce dossier (un RC peut imposer un plan différent). |
| `key` | VARCHAR(128) | Clé stable, ex. `moyens_materiels`. Unique par dossier. C’est `section_key` côté LLM. |
| `heading_level` | INTEGER | 1 = Titre 1 Word, 2 = Titre 2. Jamais choisi par le LLM. |
| `title` | VARCHAR(512) | Libellé affiché, ex. `4. Moyens matériels`. Copié tel quel dans `SectionGeneree.titre`. |
| `sort_order` | INTEGER | Ordre d’assemblage du DOCX. |
| `status` | VARCHAR(32) | `todo` → `generated` → `approved` \| `rejected`. On ne lance le LLM que sur `todo` (ou regen). |

Contrainte `UNIQUE (dossier_id, key)` : une seule case « Moyens matériels » par dossier.

### `generations`

**Rôle :** archive de **production** : chaque essai de rédaction d’une section, avec le JSON structuré, les citations, et le **snapshot du contexte** réellement envoyé au LLM (audit « pourquoi cette phrase »).

Ce n’est pas MinIO, ce n’est pas Qdrant.

| Attribut | Type | Rôle |
|----------|------|------|
| `id` | UUID PK | Identifiant de la génération. Cible des `reviews`. |
| `dossier_id` | UUID FK → `dossiers` | Dossier concerné. |
| `section_key` | VARCHAR(128) | Correspond à `outline_items.key`. Plusieurs versions possibles pour la même clé. |
| `content` | JSONB | Objet `SectionGeneree` (blocs paragraphe/liste, pas un pavé Markdown libre). |
| `citations` | JSONB | Liste d’ids de chunks `[1]…[k]` réellement utilisés. Le validateur vérifie qu’ils existent. |
| `context_snapshot` | JSONB | Extraite collée au LLM (textes + scores). Permet de rejouer / déboguer sans relancer Qdrant. |
| `model` | VARCHAR(128) | Modèle utilisé, ex. `llama3`. Traçabilité. |
| `version` | INTEGER | 1, 2, 3… après chaque `regen`. On conserve l’historique, on n’écrase pas. |
| `created_at` | TIMESTAMPTZ | Horodatage de l’essai. |

### `reviews`

**Rôle :** **human-in-the-loop**. LangGraph s’interrompt ; l’humain `approve` / `edit` / `regen`. Sans cette table, pas d’audit des décisions.

| Attribut | Type | Rôle |
|----------|------|------|
| `id` | UUID PK | Identifiant de la décision. |
| `generation_id` | UUID FK → `generations` | Quelle version de section a été jugée. |
| `user_id` | VARCHAR(64) | Qui a tranché. |
| `action` | VARCHAR(32) | `approve` (on avance), `edit` (texte humain stocké, status approved), `regen` (retour retrieve/generate). |
| `comment` | TEXT | Motif, consigne pour un regen (« insiste sur les grues 50 t »). |
| `created_at` | TIMESTAMPTZ | Quand la revue a eu lieu. |

---

## Ce qui n’est **pas** dans Postgres (volontairement)

| Donnée | Où | Pourquoi |
|--------|-----|----------|
| PDF / DOCX / XLSX originaux | MinIO `ao-raw` | Gros binaires, versionnables. |
| Vecteurs dense (et plus tard sparse) | Qdrant, payload `chunk_id` | Recherche k-NN. |
| Entités / relations (phase 1.5) | Neo4j | « qui satisfait quelle exigence ». |
| Job « en train d’ingérer » | Redis / ARQ | File éphémère. |
| Export Word final | MinIO `ao-exports` | Fichier livrable, en plus de `generations`. |

L’extension `vector` (pgvector) est **installée** dans l’image Postgres pour rester compatible, mais V1 cherche dans **Qdrant**, pas dans pgvector.

---

## Mode hybride (dev quotidien)

Les conteneurs `api` / `worker` sont derrière le profil Compose `app`. Un rebuild n’est **pas** nécessaire pour voir une modification Python : tu lances uvicorn **sur l’hôte**.

Si `api` et `worker` tournent encore (ancien `up` sans profil) :

```bash
docker compose stop api worker
```

Infra seule (après le changement de profil, `up -d` ne relance plus api/worker) :

```bash
docker compose up -d
docker compose ps
```

Buckets une fois (si l’API Docker ne l’a pas déjà fait) :

```bash
cd backend_ao
uv run python scripts/create_buckets.py
```

Backend avec rechargement à chaque sauvegarde — **port 8000**, pas 8001 :

```bash
cd backend_ao
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Worker ARQ (autre terminal, seulement quand tu testes l’ingestion) :

```bash
cd backend_ao
uv run arq app.worker_settings.WorkerSettings
```

`curl http://localhost:8000/health` — `.env` pointe déjà vers `localhost` (Redis 6380, MinIO 9010).

Stack « comme en prod » (image, **sans** `--reload`) :

```bash
docker compose --profile app up -d
# health : http://localhost:8001/health
```

Rebuild **uniquement** si tu changes `Dockerfile`, `pyproject.toml` ou `uv.lock` :

```bash
docker compose --profile app up -d --build
```

---

## Étape 2 — Docling + PaddleOCR (worker hybride GPU) — 26 août 2026

Objectif : faire passer **les PDF scannés** (OCR) et **les PDF numériques structurés** (Docling), sans alourdir l’image Docker API/worker. Le worker d’ingestion tourne **sur l’hôte** avec les extras Python ; l’infra reste en Docker.

### 2.1 Contexte machine (`kemayou-PC`)

| Élément | Valeur |
|---------|--------|
| GPU | NVIDIA RTX A5000 Laptop (16 Go VRAM) |
| Driver | 595.84 — CUDA 13.2 |
| Python worker | **3.12.3** dans `backend_ao/.venv` (pas 3.13 hôte) |
| Ollama | `llama3` + `nomic-embed-text` sur l’hôte (`localhost:11434`) |

### 2.2 Architecture retenue (hybride)

```text
Docker (--profile dev)
  postgres, redis, minio, qdrant, neo4j, api, frontend
  └── worker Docker : ARRÊTÉ (stop) — pas Docling/Paddle dans l’image

Hôte (backend_ao/.venv)
  Worker ARQ hybride
    → parse : pypdf | Docling | PaddleOCR (PDF rasterisé via PyMuPDF)
    → chunk → Postgres → Ollama embed → Qdrant → Neo4j
```

**Pourquoi hybride ?** L’image Docker fait `uv sync --frozen --no-dev` **sans** extras (`ingest`, `ocr-gpu`). Docling + Paddle + PyTorch pèsent > 2 Go et compliquent le build. Le worker hôte voit Ollama et le GPU directement.

### 2.3 Paquets Python installés

Commande exécutée (depuis `backend_ao/`) :

```bash
cd "/home/juve/Lectures_&_projects/Projets/AI_ML/Tendertune/backend_ao"
uv lock
uv sync --extra ingest --extra ocr-gpu
```

| Extra | Paquets clés | Rôle |
|-------|--------------|------|
| `ingest` | `docling>=2.0` | PDF numériques → Markdown structuré |
| `ocr-gpu` | `paddleocr>=2.8,<3`, `paddlepaddle-gpu>=2.6`, `pymupdf>=1.24`, `nvidia-cudnn-cu12==8.9.7.29`, `nvidia-cublas-cu12` | OCR scans (GPU si cuDNN OK, sinon repli CPU) |

**Important — ne jamais faire :**

```bash
# INTERDIT : conflit libpaddle (CPU + GPU)
uv sync --extra ingest --extra ocr --extra gpu
```

Utiliser **`ocr-gpu`** seul (pas `ocr` + `gpu`).

**Versions figées dans `pyproject.toml` :**

- PaddleOCR **2.10** (pas 3.x — incompatible avec Paddle 2.6 GPU sans refonte API)
- `paddlepaddle-gpu` **2.6.2**
- `nvidia-cudnn-cu12` **8.9.7.29** (cuDNN 8 — requis par Paddle 2.6)

### 2.4 Dépendances système

```bash
# Déjà présent sur kemayou-PC :
# libgomp1 (OpenMP) — nécessaire à Paddle

# Optionnel si apt disponible :
sudo apt install -y libgomp1 libglib2.0-0
```

Pas de `sudo` exécuté automatiquement (mot de passe requis) ; `libgomp1` était déjà installé.

### 2.5 Configuration `.env`

```bash
USE_GPU=true   # était false — activé pour tenter Paddle GPU
```

Le worker lit `.env` à la racine du projet (`REDIS_URL=redis://localhost:6380`, etc.).

### 2.6 Script worker hybride

Fichier créé : `backend_ao/scripts/run_worker_hybrid.sh`

- Charge `.env`
- Configure `LD_LIBRARY_PATH` vers les libs NVIDIA du venv (`nvidia/cudnn/lib`, etc.)
- Lance : `.venv/bin/python -m arq app.worker_settings.WorkerSettings`

**Note chemin avec `&` :** `uv run arq` et le shebang `.venv/bin/arq` peuvent échouer à cause du `&` dans `Lectures_&_projects`. Utiliser **`python -m arq`** (corrigé dans le script).

**Démarrage :**

```bash
cd "/home/juve/Lectures_&_projects/Projets/AI_ML/Tendertune"

# 1. Infra + API + front Docker
docker compose --profile dev up -d

# 2. Couper le worker Docker (sinon double consommation Redis)
docker compose --profile dev stop worker

# 3. Worker hybride (terminal dédié ou nohup)
./backend_ao/scripts/run_worker_hybrid.sh

# Alternative avec log fichier :
nohup ./backend_ao/scripts/run_worker_hybrid.sh > /tmp/btp-worker-hybrid.log 2>&1 &
```

**Arrêt worker hybride :**

```bash
pkill -f "python -m arq app.worker_settings"
# ou retrouver le PID : pgrep -af "arq app.worker_settings"
```

### 2.7 Modifications code (`app/ingest/parse.py`)

| Changement | Détail |
|------------|--------|
| Rasterisation PDF | PyMuPDF (`fitz`) — pages PNG 200 dpi avant PaddleOCR |
| Paddle GPU → CPU | Si cuDNN/CUDA indisponible, repli automatique `paddleocr-cpu` |
| Docling tolérant | Exception capturée → repli pypdf / Paddle au lieu de `failed` |
| Parser tracé | `pypdf`, `docling`, `paddleocr-gpu`, `paddleocr-cpu` |

### 2.8 GPU — état réel sur cette machine

| Composant | GPU | Remarque |
|-----------|-----|----------|
| PaddleOCR 2.6 GPU | **Échec cuDNN** | `libcudnn.so.8` installé via pip, mais Paddle ne charge pas cuDNN → **repli CPU** (fonctionne) |
| Docling (torch layout) | **Échec cuDNN 9** | torch 2.13 veut `libcudnn.so.9` — conflit avec cuDNN 8 de Paddle |
| pypdf | N/A | OK — PDF « Cameroun_Accès Ouest Douala.pdf » : 167 car/page → texte digital |
| Ollama embeddings | Hôte | OK — indépendant du worker Python |

**Conséquence pratique :** les PDF **avec texte extractible** passent via **pypdf** ; les **vrais scans** passent via **PaddleOCR CPU** (plus lent qu’un GPU, mais opérationnel). Pour activer Docling + torch GPU plus tard : installer cuDNN 9 système (`libcudnn9`) **ou** séparer les environnements.

### 2.9 Vérification effectuée (26 août 2026)

1. Worker hybride : log `worker ARQ prêt — jobs ingest_document + extract_graph`
2. Document `Cameroun_Accès Ouest Douala.pdf` (ex-`failed` sous worker Docker) :
   - Re-enqueue manuel → **`status=ready`**, 38 pages, 38 chunks, Qdrant OK
   - Parser final : **`pypdf`** (Docling skip cuDNN, pas OCR car texte digital)
3. Test unitaire OCR : image PNG « Test pipeline OCR » → **`paddleocr-cpu`** après échec GPU

**Relancer un ingest `failed` :**

```sql
UPDATE documents SET status='pending', ingest_error=NULL WHERE id='…';
```

```bash
cd backend_ao
source ../.env
.venv/bin/python -c "
import asyncio
from app.services.queue import enqueue_ingest
asyncio.run(enqueue_ingest('UUID-DOCUMENT'))
"
```

### 2.10 Procédure pour une autre machine (checklist)

1. **Prérequis** : Docker, uv, Python 3.12, NVIDIA driver + `nvidia-smi` OK, Ollama avec `nomic-embed-text` + `llama3`
2. **Cloner** le projet, copier `.env.example` → `.env`, ajuster ports
3. **Infra** : `docker compose --profile dev up -d`
4. **Extras Python** :
   ```bash
   cd backend_ao
   uv sync --extra ingest --extra ocr-gpu
   ```
   - Machine **sans GPU** : `uv sync --extra ingest --extra ocr` et `USE_GPU=false`
5. **Stop worker Docker** : `docker compose --profile dev stop worker`
6. **Lancer worker** : `./backend_ao/scripts/run_worker_hybrid.sh`
7. **Test** : upload PDF dans Documents → logs `STATUT → ready`
8. **Logs** : `tail -f /tmp/btp-worker-hybrid.log` ou terminal du script

**Pièges connus :**

- Ne pas lancer **deux workers** (Docker + hôte) en parallèle
- Ne pas mélanger `ocr` (CPU paddle) et `ocr-gpu`
- Chemin avec caractères spéciaux (`&`) → `python -m arq`, pas `uv run arq`
- Premier lancement PaddleOCR : télécharge ~15 Mo de modèles dans `~/.paddleocr/`
- Premier lancement Docling : télécharge modèles layout dans cache HuggingFace / docling

### 2.11 Fichiers modifiés (cette étape)

| Fichier | Modification |
|---------|--------------|
| `backend_ao/pyproject.toml` | extras `ocr-gpu`, `pymupdf`, pin PaddleOCR `<3`, cuDNN pip |
| `backend_ao/uv.lock` | lock mis à jour (~260 paquets) |
| `backend_ao/app/ingest/parse.py` | OCR PDF, replis GPU/CPU, Docling tolérant |
| `backend_ao/scripts/run_worker_hybrid.sh` | **nouveau** — lance worker hôte |
| `.env` | `USE_GPU=true` |
| `docker-compose` worker | **stopped** (`docker compose --profile dev stop worker`) |

---



## IMPLEMENTATION DU STREAMING 

Voici comment le streaming est branché dans **BTP_RAG**, de bout en bout.

## Idée générale

Ce n’est **pas** WebSocket. C’est du **SSE (Server-Sent Events)** sur une réponse HTTP longue :

1. Le navigateur envoie la question en `POST`
2. Le serveur garde la connexion ouverte
3. Il envoie des **événements** au fur et à mesure (`token`, `done`, …)
4. Le front affiche chaque token dès qu’il arrive

```text
UI ──POST──► FastAPI ──SSE──► UI (tokens)
                 │
                 ▼
            Ollama /api/generate (stream=true)
```

---

## 1. Couche Ollama (vrai flux LLM)

Fichier : `backend_ao/app/services/ollama_llm.py`

- Appel `POST {OLLAMA_BASE_URL}/api/generate` avec `"stream": true`
- Ollama renvoie **une ligne JSON par morceau**
- On lit chaque ligne, on extrait `response`, on `yield` le texte

C’est le générateur synchrone `ollama_generate_stream()`.

---

## 2. Pont async (thread → asyncio)

Fichier : `chat_pipeline.py` → `_iter_ollama_tokens`

Ollama est synchrone (`urllib`). FastAPI est async. Donc :

- un **thread** lit Ollama et pousse les tokens dans une `asyncio.Queue`
- la coroutine async consomme la queue et `yield` les tokens sans bloquer l’event loop

---

## 3. Pipeline métier en SSE

Fichier : `stream_message()` dans `chat_pipeline.py`

Helper SSE :

```python
def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"
```

Séquence typique :

| Event | Quand |
|--------|--------|
| `user` | message utilisateur enregistré |
| `intent` | après route (`hybrid_rag`, `run_section`, `export`, `smalltalk`) |
| `section_start` | début d’une génération |
| `token` | **chaque morceau** de texte (`{"t": "..."}`) |
| `section_end` | section terminée |
| `preview` | markdown complet (aperçu) |
| `export_ready` | export prêt (téléchargement) |
| `done` | fin + commit en base |
| `error` | échec |

Pour une question RAG / section :

1. Route + retrieve (hors stream LLM)
2. Construction du prompt
3. Boucle : chaque token Ollama → `yield _sse("token", …)`
4. Persist message + éventuellement sections dossier
5. `done`

---

## 4. Endpoint FastAPI

```380:401:backend_ao/app/api/conversations.py
@router.post("/{conversation_id}/messages/stream")
async def post_message_stream(...):
    async def event_gen():
        async for chunk in stream_message(...):
            yield chunk
    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
```

`StreamingResponse` = la réponse HTTP n’attend pas la fin : elle **pousse** les chunks SSE.

---

## 5. Front : lecture du flux

Fichier : `frontend_ao/src/api/client.ts` → `convApi.sendStream`

On n’utilise **pas** `EventSource` (limité au GET). On fait :

1. `fetch(.../messages/stream)` en POST
2. `res.body.getReader()` (ReadableStream)
3. Décodage UTF-8, découpage sur `\n\n` (blocs SSE)
4. Parse `event:` + `data:`
5. Callbacks : `onToken`, `onPreview`, `onExportReady`

---

## 6. Affichage dans le chat

Fichier : `ConversationsPage.tsx`

Avant le stream :

- message user + bulle assistant vide (optimiste)
- `streaming = true`, `streamDraft = ''`

Pendant :

```ts
onToken: (t) => setStreamDraft((prev) => prev + t)
```

La bulle assistant affiche `streamDraft` en live (`MarkdownPreview` variant chat).

Après `done` :

- `GET` conversation fraîche (messages + preview persistés)
- reset `streamDraft` / `streaming`

L’aperçu document à droite n’est **plus** mis à jour via `onPreview` pendant le stream (pour éviter le glitch) : seulement après le reload.

---

## Schéma mental

```text
Utilisateur tape → onSend()
  → create conversation si brouillon
  → POST /conversations/{id}/messages/stream
       → stream_message()
            → route/retrieve
            → pour chaque token Ollama :
                 SSE "token" { "t": "..." }
            → commit DB
            → SSE "done"
  → reader lit les tokens → streamDraft++
  → rechargement conversation complète
```

---

## Points importants

- **Deux streams imbriqués** : Ollama → API → navigateur
- Format **SSE** (`event` / `data`), pas JSON unique en fin de requête
- Le message court en chat (`"Section rédigée"`) est séparé du **markdown** stocké dans `meta.markdown`
- Il existe aussi un endpoint sync `POST .../messages` (sans stream) ; l’UI utilise le stream

Si tu veux, on peut ensuite détailler uniquement la partie **parse SSE côté front** ou uniquement **route → prompt → Ollama**.

---

## Étape — Fuzzy matching entités Neo4j (27 août 2026)

### Problème

Ollama extrait parfois des **variantes de noms** :
- entité : `BTP Construction`
- relation : `from: "BTP Constructions"` ou `"Construction BTP"`

Avant : lookup **exact** seulement → relation **droppée**.  
Aussi : deux docs du même tenant créaient deux nœuds pour la même entreprise si l’orthographe variait.

### Solution intégrée

Fichier : `backend_ao/app/graph/entity_match.py`  
Branché dans : `backend_ao/app/graph/extract.py`  
Dépendance : `rapidfuzz` (dans `pyproject.toml`)

Pipeline de résolution d’un nom vers une clé Neo4j :

```text
1. Exact (brut ou normalisé lower/espaces)
2. Levenshtein (rapidfuzz.ratio)        seuil ≥ 85   → fautes / pluriels
3. Jaccard tokens (token_set_ratio)     seuil ≥ 80   → ordre des mots
4. Embedding Ollama (nomic-embed-text)  cosinus ≥ 0.82 → sémantique
   (uniquement si 1–3 échouent ; réutilise embed_texts déjà en place)
```

Deux usages dans `extract_graph` :

| Moment | Effet |
|--------|--------|
| Création d’entité | `_canonical_key` : fuzzy vs entités **déjà en Neo4j pour le tenant** → réutilise la même `key` si type compatible (`:ENTREPRISE:` dans la clé) |
| Relation `from` / `to` | `resolve_entity_key` sur un index = patrimoine tenant + entités du chunk courant |

Contrainte de type : on ne fusionne `BTP Construction` vers une clé existante que si la clé contient `:{TYPE}:` attendu (évite de coller une ENTREPRISE sur un PROJET).

`MERGE` Neo4j : `SET e.name = coalesce(e.name, $name)` pour ne pas écraser le nom canonique déjà stocké.

### Tests

```bash
cd backend_ao
uv sync   # tire rapidfuzz
.venv/bin/python -m pytest tests/test_entity_match.py -q
```

### Ce que ce n’est pas

- Pas de GraphRAG au chat (horloge B ne lit toujours pas Neo4j)
- Pas d’alias table manuelle ; le fuzzy est automatique
- Soundex non utilisé (peu adapté au français)

### Schéma

```text
Ollama JSON {entities, relations}
        │
        ├─ pour chaque entity :
        │     fuzzy vs Neo4j tenant → key canonique
        │     MERGE Entity
        │
        └─ pour chaque relation :
              fuzzy(from) + fuzzy(to) → clés
              si OK : MERGE REL
              sinon : log + drop
```

---

## Prochaine étape

- Bouton UI **relancer ingest** pour les documents `failed`
- Résoudre conflit cuDNN 8 (Paddle) vs 9 (torch/Docling) pour activer Docling GPU
- Vrai PDF **100 % scan** (densité < 40 car/page) → valider `paddleocr-cpu` ou `-gpu`
- Option prod : image Docker worker `ocr-gpu` dédiée (sans API)
- Brancher Neo4j en lecture côté chat (GraphRAG) si besoin métier
