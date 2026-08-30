# Commandes BTP_RAG

Aide-mémoire pour lancer, arrêter et lire les logs — **Docker** ou **hybride (hôte)** — sans rien casser.

Racine du projet (à adapter si besoin) :

```bash
cd "/home/juve/Lectures_&_projects/Projets/BTP_RAG"
```

Ports **hôte** (`.env`) : Postgres `5432` · Qdrant `6333` · Neo4j `7474`/`7687` · Redis `6380` · MinIO `9010`/`9011` · API Docker `8001` · Front `5174`.

Dans Docker, l’API parle à `postgres:5432`, `redis:6379`, `minio:9000` (réseau interne).

---

## Table des matières

1. [Choix rapide : Docker vs hybride](#1-choix-rapide--docker-vs-hybride)
2. [Infra seule](#2-infra-seule--redis-qdrant-minio-postgres-neo4j)
3. [Stack Docker complète](#3-stack-docker-complète---profile-dev)
4. [Worker hybride (Docling / Paddle sur l’hôte)](#4-worker-hybride-docling--paddle-sur-lhôte)
5. [Basculer Docker ↔ hybride](#5-basculer-docker--hybride)
6. [Logs (live / nohup / conteneurs)](#6-logs-live--nohup--conteneurs)
7. [Démarrer / arrêter un service précis](#7-démarrer--arrêter-un-service-précis)
8. [Backend + worker sans Docker (API aussi sur l’hôte)](#8-backend--worker-sans-docker-api-aussi-sur-lhôte)
9. [Front sans Docker](#9-front-sans-docker)
10. [Identifiants / login](#10-identifiants--login)
11. [Ollama](#11-ollama-hôte)
12. [MinIO](#12-minio)
13. [Postgres](#13-postgres--connexion-et-lecture)
14. [Qdrant](#14-qdrant)
15. [Redis](#15-redis-port-hôte-6380)
16. [Neo4j](#16-neo4j)
17. [Docker — listing & rebuild](#17-docker--listing--rebuild)
18. [Extras uv (Docling / Paddle)](#18-extras-uv-docling--paddle)

---

## 1. Choix rapide : Docker vs hybride

| Mode | Qui parse les PDF | Docling / Paddle | Quand l’utiliser |
|------|-------------------|------------------|------------------|
| **Docker complet** | Conteneur `worker` | Non (image légère) | PDF texte / DOCX / XLSX, setup simple |
| **Hybride** | Process ARQ sur l’hôte (`run_worker_hybrid.sh`) | Oui (`backend_ao/.venv`) | Scans OCR, Docling, GPU/CPU |

**Règle d’or :** ne jamais faire tourner **deux workers** en même temps (Docker + hybride) — ils se disputent la même file Redis.

---

## 2. Infra seule — Redis, Qdrant, MinIO, Postgres, Neo4j

Pas d’API, pas de worker, pas de front.

```bash
docker compose up -d postgres qdrant neo4j redis minio
docker compose ps
```

Attendre `healthy` (sauf MinIO : `Up` suffit).

Arrêter uniquement l’infra :

```bash
docker compose stop postgres qdrant neo4j redis minio
```

Relancer un service d’infra :

```bash
docker compose start redis
docker compose up -d postgres
```

---

## 3. Stack Docker complète (`--profile dev`)

Infra + API + worker + un front Vite.

```bash
docker compose --profile dev up -d
docker compose --profile dev ps
```

Équivalent ciblé (si l’infra est déjà là) :

```bash
docker compose --profile dev up -d api worker frontend
```

UI : http://localhost:5174 · API : http://localhost:8001/health

Après **modif Python** (`backend_ao/app/`) — uvicorn/ARQ sans reload :

```bash
docker compose --profile dev restart api worker
```

Après **modif front** : souvent rien (HMR). Sinon :

```bash
docker compose --profile dev restart frontend
```

Après **pyproject.toml / uv.lock / Dockerfile** :

```bash
cd backend_ao && uv lock && cd ..
docker compose --profile dev build api
docker compose --profile dev up -d api worker
```

Tout couper (profile, **volumes conservés**) :

```bash
docker compose --profile dev down
```

`down -v` **efface les volumes** (base, MinIO, Qdrant, Neo4j) — destructif.

### Worker Docker — lancer / arrêter

```bash
# Lancer
docker compose --profile dev up -d worker

# Arrêter
docker compose --profile dev stop worker

# Redémarrer
docker compose --profile dev restart worker

# État
docker compose --profile dev ps worker
```

---

## 4. Worker hybride (Docling / Paddle sur l’hôte)

Prérequis : infra + API (+ front) Docker up ; **worker Docker stoppé** ; extras installés dans `backend_ao/.venv` (voir [§18](#18-extras-uv-docling--paddle)).

### Lancer (logs dans le terminal)

```bash
cd "/home/juve/Lectures_&_projects/Projets/BTP_RAG"
docker compose --profile dev stop worker
./backend_ao/scripts/run_worker_hybrid.sh
```

Les logs s’affichent **dans ce terminal**. Fermer le terminal = arrêter le worker.

### Lancer en arrière-plan (`nohup`)

`nohup` = le process **continue** si tu fermes le terminal. Les logs partent dans un fichier.

```bash
cd "/home/juve/Lectures_&_projects/Projets/BTP_RAG"
docker compose --profile dev stop worker
nohup ./backend_ao/scripts/run_worker_hybrid.sh > /tmp/btp-worker-hybrid.log 2>&1 &
```

| Morceau | Rôle |
|---------|------|
| `nohup` | Survit à la fermeture du terminal |
| `> /tmp/btp-worker-hybrid.log` | Sortie normale → fichier |
| `2>&1` | Erreurs → même fichier |
| `&` | Arrière-plan (terminal libre) |

### Savoir s’il tourne

```bash
# Filtre propre (évite le bruit Cursor / sandbox)
pgrep -af "[.]venv/bin/python -m arq app.worker_settings"
```

- Une ligne du type `.venv/bin/python -m arq app.worker_settings.WorkerSettings` → **tourne**
- Rien → **arrêté**

Variantes :

```bash
ps aux | grep "arq app.worker_settings" | grep -v grep
ps -p <PID> -o pid,etime,cmd
```

### L’arrêter

```bash
# Arrêt propre (recommandé)
pkill -f "[.]venv/bin/python -m arq app.worker_settings"

# Si ça résiste
pkill -9 -f "[.]venv/bin/python -m arq app.worker_settings"
```

Ou avec le PID vu dans `pgrep` :

```bash
kill <PID>
kill -9 <PID>
```

Vérifier :

```bash
pgrep -af "[.]venv/bin/python -m arq app.worker_settings"
# (aucune sortie = arrêté)
```

---

## 5. Basculer Docker ↔ hybride

### Passer en **hybride** (OCR / Docling)

```bash
docker compose --profile dev stop worker
./backend_ao/scripts/run_worker_hybrid.sh
# ou nohup … > /tmp/btp-worker-hybrid.log 2>&1 &
```

### Revenir en **worker Docker**

```bash
pkill -f "[.]venv/bin/python -m arq app.worker_settings"
docker compose --profile dev up -d worker
docker compose --profile dev logs -f worker
```

---

## 6. Logs (live / nohup / conteneurs)

### Worker hybride

```bash
# Terminal dédié : logs déjà à l’écran
./backend_ao/scripts/run_worker_hybrid.sh

# Si lancé avec nohup : suivre le fichier en live
tail -f /tmp/btp-worker-hybrid.log
```

`tail -f` = affiche la fin du fichier et **suit** les nouvelles lignes. Sans `nohup`, tu n’as en général pas besoin de `tail -f`.

### Worker / API Docker

```bash
# Worker seul
docker compose --profile dev logs -f worker
docker logs -f --tail 100 btp-rag-worker-1

# API seule
docker compose --profile dev logs -f api
docker logs -f --tail 100 btp-rag-api-1

# API + worker
docker compose --profile dev logs -f api worker

# Front
docker compose --profile dev logs -f frontend

# Dernières N lignes puis sortir (sans -f)
docker compose --profile dev logs --tail 200 worker
```

**Note :** si le worker Docker est **stoppé** (mode hybride), `logs -f worker` ne montre que l’historique — les nouveaux jobs passent par le hybride (`/tmp/btp-worker-hybrid.log` ou le terminal).

### Autres services

```bash
docker compose logs -f postgres
docker compose logs -f redis
docker compose logs -f minio
docker compose logs -f qdrant
docker compose logs -f neo4j
```

---

## 7. Démarrer / arrêter un service précis

Noms Compose courants : `postgres` · `qdrant` · `neo4j` · `redis` · `minio` · `api` · `worker` · `frontend`.

```bash
# État
docker compose --profile dev ps
docker ps --format "table {{.ID}}\t{{.Names}}\t{{.Status}}\t{{.Ports}}"

# Arrêter un conteneur
docker compose --profile dev stop api
docker compose --profile dev stop worker
docker compose --profile dev stop frontend
docker stop btp-rag-api-1

# Arrêter plusieurs
docker compose --profile dev stop api worker frontend
docker stop btp-rag-api-1 btp-rag-worker-1

# Relancer (sans rebuild)
docker compose --profile dev start api
docker compose --profile dev up -d worker
docker compose --profile dev restart frontend

# Lancer un service (démarre aussi ses depends si besoin)
docker compose --profile dev up -d api
docker compose up -d redis
```

Health API Docker :

```bash
curl -s http://localhost:8001/health
```

---

## 8. Backend + worker **sans** Docker (API aussi sur l’hôte)

Infra Docker déjà up. Ollama **sur l’hôte**.

```bash
cd backend_ao
uv sync
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Autre terminal — worker ARQ (sans script hybride ; préférer le script si OCR) :

```bash
cd backend_ao
# Chemin avec & : préférer python -m arq plutôt que uv run arq
.venv/bin/python -m arq app.worker_settings.WorkerSettings
```

Ou le script (recommandé pour Docling/Paddle) :

```bash
./backend_ao/scripts/run_worker_hybrid.sh
```

Health : http://localhost:8000/health  
`.env` : `REDIS_URL=redis://localhost:6380`, `MINIO_ENDPOINT=localhost:9010`, `DATABASE_URL=…localhost:5432…`

---

## 9. Front **sans** Docker

API hybride sur **8000** (proxy Vite par défaut) :

```bash
cd frontend_ao
npm install
npm run dev -- --port 5174
```

UI : http://localhost:5174

Si l’API est celle de Docker (`8001`) :

```bash
cd frontend_ao
VITE_DEV_PROXY_TARGET=http://localhost:8001 npm run dev -- --port 5174
```

---

## 10. Identifiants / login

- URL : http://localhost:5174  
- Email : `admin@btp.local`  
- Mot de passe : `ADMIN_PASSWORD` dans `.env` (défaut `AdminChantier2026!`)

---

## 11. Ollama (hôte)

```bash
ollama --version
ollama list
ollama pull llama3
ollama pull nomic-embed-text
ollama serve
```

Depuis un container : `OLLAMA_BASE_URL=http://host.docker.internal:11434`.

---

## 12. MinIO

- Console : http://localhost:9011  
- User / pass : `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` (défaut `minioadmin` / `minioadmin`)  
- API S3 hôte : `localhost:9010`  
- Buckets : `ao-raw` (uploads), `ao-exports`

CLI (si `mc` installé) :

```bash
mc alias set local http://localhost:9010 minioadmin minioadmin
mc ls local/ao-raw
```

---

## 13. Postgres — connexion et lecture

```bash
docker exec -it btp-rag-postgres-1 psql -U ao_user -d ao_db
ou
docker exec -ti -e PAGER="less -S" btp-rag-postgres-1 psql -U ao_user -d ao_db
```

Ou depuis l’hôte :

```bash
psql postgresql://ao_user:ao_pass@localhost:5432/ao_db
```

Dans `psql` :

```sql
\dt
SELECT id, email, role, status FROM users;
SELECT id, filename, status, ocr_used, graph_extracted, left(ingest_error, 80)
  FROM documents ORDER BY created_at DESC;
SELECT count(*) FROM chunks;
SELECT id, title FROM conversations;
\q
```

Relancer un ingest `failed` (après worker hybride up) :

```sql
UPDATE documents SET status='pending', ingest_error=NULL WHERE id='UUID-DOCUMENT';
```

```bash
cd backend_ao
set -a && source ../.env && set +a
.venv/bin/python -c "
import asyncio
from app.services.queue import enqueue_ingest
asyncio.run(enqueue_ingest('UUID-DOCUMENT'))
"
```

---

## 14. Qdrant

- API : http://localhost:6333  
- Dashboard : http://localhost:6333/dashboard  

```bash
curl -s http://localhost:6333/readyz
curl -s http://localhost:6333/collections
```

---

## 15. Redis (port hôte 6380)

```bash
docker exec -it btp-rag-redis-1 redis-cli
```

Depuis l’hôte :

```bash
redis-cli -p 6380
```

Dans le CLI :

```text
PING
KEYS *
LLEN arq:queue
INFO clients
MONITOR
```

`Ctrl+C` pour quitter MONITOR, `QUIT` pour sortir.

---

## 16. Neo4j

- Browser : http://localhost:7474  
- Bolt : `bolt://localhost:7687`  
- User / pass : `neo4j` / `NEO4J_PASSWORD` (défaut `password123`)

```cypher
MATCH (e:Entity) RETURN e LIMIT 25;
MATCH (a)-[r:REL]->(b) RETURN a, r, b LIMIT 25;
```

---

## 17. Docker — listing & rebuild

```bash
docker ps
docker compose ps
docker compose --profile dev ps
docker ps --format "table {{.ID}}\t{{.Names}}\t{{.Status}}\t{{.Ports}}"
```

Rebuild image API/worker (même Dockerfile) :

```bash
docker compose --profile dev build api
docker compose --profile dev up -d api worker
```

---

## 18. Extras uv (Docling / Paddle)

Installés **sur l’hôte** dans `backend_ao/.venv` — **pas** dans l’image Docker actuelle.

```bash
cd backend_ao

# Docling seul
uv sync --extra ingest

# Docling + Paddle CPU
uv sync --extra ingest --extra ocr

# Docling + Paddle GPU (ne pas combiner avec --extra ocr)
uv sync --extra ingest --extra ocr-gpu
```

| Extra | Contenu |
|-------|---------|
| `ingest` | Docling |
| `ocr` | PaddleOCR + paddle **CPU** + pymupdf |
| `ocr-gpu` | PaddleOCR + paddle **GPU** + pymupdf + cuDNN |

`.env` : `USE_GPU=true` tente le GPU (repli CPU si cuDNN KO) ; `USE_GPU=false` force le CPU.

Vérifier ce qui est installé :

```bash
cd backend_ao
.venv/bin/python -c "
from importlib.metadata import version, PackageNotFoundError
for n in ['docling','paddleocr','paddlepaddle','paddlepaddle-gpu','pymupdf']:
  try: print(f'{n}={version(n)}')
  except PackageNotFoundError: print(f'{n}=ABSENT')
"
```
