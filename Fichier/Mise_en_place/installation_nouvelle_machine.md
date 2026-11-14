# Installer le projet sur une nouvelle machine

Ce fichier répond à deux questions : **quoi copier** pour donner le projet à quelqu’un, et **comment tout réinstaller** derrière, avec quelles versions.

Voir aussi : [ingestion_horloge_A.md](ingestion_horloge_A.md), [conversation_horloge_B.md](conversation_horloge_B.md) (fonctionnement), `Fichier/aaa_Commandes.md` (commandes du quotidien une fois installé).

---

## 1. Réponse courte : qu’est-ce qu’on copie ?

| Dossier / fichier | Copier ? | Pourquoi |
|---|---|---|
| Tout le code (`backend_ao/app`, `frontend_ao/src`, `*.toml`, `*.json`, `Dockerfile*`, `docker-compose*.yml`, `.env.example`) | **Oui** | C’est le projet |
| `backend_ao/uv.lock`, `frontend_ao/package-lock.json` | **Oui, impératif** | Fige les versions exactes (voir §2) — sans eux, la nouvelle machine peut installer des versions différentes |
| `backend_ao/.venv/` | **Non, jamais** | Regénéré par `uv sync` en 1 commande. Chez nous : **11 Go** (torch/paddle-gpu/transformers) contre **17 Mo** pour tout le code source utile. En plus il contient des binaires compilés (CUDA, wheels natifs) **liés à cette machine** — ça ne marche même pas forcément ailleurs |
| `frontend_ao/node_modules/` | **Non, jamais** | Regénéré par `npm install` (164 Mo ici, à partir de `package-lock.json`) |
| `.git/` | Optionnel | Utile si vous voulez l’historique / pouvoir faire des PR ; sinon un simple export de fichiers suffit |
| `.env` | **Non tel quel** | Contient des secrets/mots de passe (même si ce sont des valeurs par défaut de dev). Donnez `.env.example` et laissez la personne le compléter (§4) — ou donnez le vôtre en **changeant `JWT_SECRET` et `ADMIN_PASSWORD`** avant |
| `data/`, `tmp/`, `*.log` | **Non** | Données locales / caches, rien d’utile dedans |
| `__pycache__/`, `*.pyc`, `dist/`, `.pytest_cache/` etc. | **Non** | Régénérés automatiquement |

Tout ça est déjà dans `.gitignore` — donc si vous copiez via `git` (clone, archive, ou zip depuis GitHub/GitLab), vous n’avez **rien à filtrer manuellement**, c’est déjà propre.

### Comment copier concrètement

**Option recommandée — via git** (garde l’historique, le plus simple) :

```bash
git clone <url-du-repo> btp_rag
# ou, si le dépôt est déjà cloné ailleurs et que vous voulez juste transférer :
git bundle create btp_rag.bundle --all
# puis sur l'autre machine : git clone btp_rag.bundle btp_rag
```

**Option sans git** — copier les fichiers en excluant explicitement le lourd/inutile :

```bash
rsync -av \
  --exclude='.venv' --exclude='node_modules' --exclude='.git' \
  --exclude='__pycache__' --exclude='*.pyc' \
  --exclude='dist' --exclude='.pytest_cache' --exclude='.ruff_cache' --exclude='.mypy_cache' \
  --exclude='data' --exclude='tmp' --exclude='*.log' \
  --exclude='.env' \
  "/home/juve/Lectures_&_projects/Projets/AI_ML/Tendertune/" utilisateur@nouvelle-machine:/chemin/cible/
```

Ou une simple archive tar avec les mêmes exclusions :

```bash
tar --exclude='.venv' --exclude='node_modules' --exclude='.git' \
    --exclude='__pycache__' --exclude='data' --exclude='tmp' --exclude='.env' \
    -czf btp_rag.tar.gz .
```

Résultat : quelques dizaines de Mo (le `.pdf` du mémoire LaTeX et les diagrammes `Nouvelle_Architecture/` pèsent plus lourd que tout le code) au lieu des ~11 Go du dossier complet avec `.venv`.

---

## 2. Où sont fixées les versions des paquets

| Composant | Fichier « source de vérité » | Regénérer avec |
|---|---|---|
| Dépendances Python (API + worker) | `backend_ao/pyproject.toml` (contraintes) + `backend_ao/uv.lock` (versions exactes résolues) | `cd backend_ao && uv sync` |
| Dépendances Node (front) | `frontend_ao/package.json` + `frontend_ao/package-lock.json` | `cd frontend_ao && npm install` |
| Images Docker de base (Postgres, Qdrant, Neo4j, Redis, MinIO, Node, Python) | tags dans `docker-compose.yml` et `FROM …` dans `backend_ao/Dockerfile` / `Dockerfile.worker` | `docker compose --profile dev build` (télécharge/construit les images) |
| Modèles LLM / embeddings (Ollama) | **pas un fichier lock** — juste le nom du modèle dans `.env` (`LLM_MODEL`, `EMBED_MODEL`) | `ollama pull <nom:tag>` (voir §5) |
| Variables d’environnement / secrets | `.env` (réel, jamais commité) — `.env.example` (squelette, **actuellement incomplet**, voir §4) | copier `.env.example` → `.env` puis compléter |

**Règle générale :** tant que `uv.lock` et `package-lock.json` sont copiés avec le code, `uv sync` / `npm install` réinstallent **exactement** les mêmes versions que sur cette machine, peu importe où c’est lancé. Ce sont ces deux fichiers qui remplacent le besoin de copier `.venv`/`node_modules`.

---

## 3. Prérequis système sur la nouvelle machine

| Outil | Version utilisée ici | Obligatoire ? | Installer |
|---|---|---|---|
| Docker Engine | 29.6.2 | Oui (mode Docker) | https://docs.docker.com/engine/install/ |
| Docker Compose (plugin `compose`) | v5.3.1 | Oui (mode Docker) | inclus avec Docker Desktop / `docker-compose-plugin` |
| Python | 3.12 (`requires-python >=3.12` dans `pyproject.toml`) | Oui si mode hybride hôte | paquet système ou [pyenv](https://github.com/pyenv/pyenv) |
| **uv** (gestionnaire Python) | 0.12.3 | Oui si mode hybride hôte | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Node.js | **22** (image `node:22-alpine` utilisée par le service `frontend`) | Oui si front hors Docker | https://nodejs.org (ou `nvm install 22`) |
| Ollama | dernière version | Oui (LLM + embeddings) | https://ollama.com/download |
| NVIDIA driver + `nvidia-container-toolkit` | driver 595.84 ici | **Optionnel** — seulement pour GPU réel (OCR PaddleOCR, Ollama plus rapide) | voir `ingestion_horloge_A.md` §1 « GPU réel » |

Sans GPU/nvidia-container-toolkit : tout fonctionne quand même, juste plus lent (OCR en CPU). Ollama, lui, utilise le GPU nativement dès qu’un driver NVIDIA est présent sur l’hôte — aucune installation Docker particulière n’est nécessaire pour ça (Ollama tourne hors conteneur).

---

## 4. `.env` — compléter le squelette

`.env.example` actuel ne couvre que JWT/admin/front — **il manque Postgres/Qdrant/Neo4j/Redis/MinIO/LLM**, qui ont des valeurs par défaut dans `backend_ao/app/config.py` mais qu’il vaut mieux fixer explicitement. Base à copier dans `.env` à la racine :

```bash
# Postgres
POSTGRES_USER=ao_user
POSTGRES_PASSWORD=ao_pass
POSTGRES_DB=ao_db
POSTGRES_HOST_PORT=5432
DATABASE_URL=postgresql://ao_user:ao_pass@localhost:5432/ao_db

# Qdrant
QDRANT_URL=http://localhost:6333
QDRANT_GRPC_HOST=localhost
QDRANT_GRPC_PORT=6334
QDRANT_COLLECTION=ao_chunks

# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password123

# Ports hôte (évite les clashs avec d’autres stacks locales)
MINIO_API_HOST_PORT=9010
MINIO_CONSOLE_HOST_PORT=9011
REDIS_HOST_PORT=6380
API_HOST_PORT=8001
FRONTEND_HOST_PORT=5174

REDIS_URL=redis://localhost:6380
MINIO_ENDPOINT=localhost:9010
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET_RAW=ao-raw
MINIO_BUCKET_EXPORT=ao-exports
MINIO_USE_SSL=false

# LLM / embeddings — Ollama
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
LLM_MODEL=granite3.3:2b
EMBED_PROVIDER=ollama
EMBED_MODEL=nomic-embed-text
EMBED_DIM=768
RERANK_MODEL=BAAI/bge-reranker-v2-m3

# API
API_HOST=0.0.0.0
API_PORT=8000
USE_GPU=false                     # true seulement si driver NVIDIA présent
JWT_SECRET=change-me-en-quelque-chose-de-vraiment-aleatoire
JWT_EXPIRE_MINUTES=180
ADMIN_EMAIL=admin@btp.local
ADMIN_USERNAME=admin
ADMIN_PASSWORD=ChangeMoi2026!

# Front
VITE_API_BASE_URL=http://localhost:8000
```

**À changer obligatoirement avant toute utilisation au-delà d’un test local :** `JWT_SECRET`, `ADMIN_PASSWORD`, `POSTGRES_PASSWORD`, `NEO4J_PASSWORD`, `MINIO_ACCESS_KEY`/`MINIO_SECRET_KEY`. Les valeurs ci-dessus sont celles utilisées en dev — pratiques pour tester vite, à ne pas garder telles quelles en dehors d’une machine perso/isolée.

---

## 5. Installation pas à pas (mode Docker — recommandé)

```bash
# 1. Récupérer le code (voir §1)
git clone <url> btp_rag && cd btp_rag
# (ou décompresser l'archive rsync/tar)

# 2. Créer .env (voir §4)
cp .env.example .env
# … puis compléter avec les variables manquantes ci-dessus, ou remplacer entièrement par le bloc du §4

# 3. Construire et lancer toute la stack
docker compose --profile dev up -d --build
docker compose --profile dev ps        # attendre "healthy" sur postgres/qdrant/redis/neo4j

# 4. Modèles Ollama (sur l'hôte, PAS dans Docker — voir ingestion_horloge_A.md §1)
ollama pull granite3.3:2b
ollama pull nomic-embed-text
# Vérifier qu'Ollama écoute sur 0.0.0.0 (pas juste 127.0.0.1), sinon Docker ne le joint pas :
#   OLLAMA_HOST=0.0.0.0:11434 dans son unit systemd / variable d'environnement

# 5. Vérifier
curl -s http://localhost:8001/health
```

`http://localhost:8001/health` doit répondre avec `llm_model: "granite3.3:2b"`. Front : `http://localhost:5174` (identifiants par défaut : `admin@btp.local` / la valeur de `ADMIN_PASSWORD`).

Pour un accès GPU réel côté worker Docker (OCR PaddleOCR) : voir `ingestion_horloge_A.md` §1 (installation de `nvidia-container-toolkit` + relance avec l’overlay `docker-compose.gpu.yml`).

---

## 6. Installation pas à pas (mode hybride hôte — optionnel)

Utile pour déboguer avec `--reload`, ou pour l’OCR GPU en direct sans passer par Docker (voir `Fichier/aaa_Commandes.md` §19). Nécessite l’infra Docker déjà up (étape 3 ci-dessus) mais **pas** les conteneurs `api`/`worker`.

```bash
cd backend_ao
uv sync                                    # dépendances de base
# extras optionnels (jamais ocr + ocr-gpu ensemble, voir ingestion_horloge_A.md §1) :
uv sync --extra ingest --extra ocr-gpu     # Docling + PaddleOCR GPU

uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Frontend hors Docker :

```bash
cd frontend_ao
npm install
npm run dev -- --port 5174
```

---

## 7. Vérification finale

```bash
docker compose --profile dev ps                 # tout "healthy"/"Up"
curl -s http://localhost:8001/health             # {"status":"ok", "llm_model":"granite3.3:2b", ...}
ollama list                                      # granite3.3:2b + nomic-embed-text présents
```

Puis un test fonctionnel réel : se connecter sur le front, créer un dossier, déposer un DAO, attendre `ready`, générer une section, exporter en PDF, ouvrir le PDF.
