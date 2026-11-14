# Mise en place — pipeline d'ingestion (horloge A)

Ce dossier décrit **ce qui est implémenté maintenant** dans le code pour l'**horloge A** (ingestion). Pour la conversation / rédaction / export (**horloge B**), voir **[conversation_horloge_B.md](conversation_horloge_B.md)**.

```text
Horloge A (async, worker ARQ)                          ← détaillé ici
  upload → MinIO → parse → chunks → Ollama embed → Qdrant → ready → Neo4j

Horloge B (synchrone + stream SSE, API / conversation)  ← voir conversation_horloge_B.md
  question → historique conversation + LangGraph (route → retrieve → generate)
           → sections dossier → export multi-format MinIO ao-exports
           → upload document patrimoine depuis le chat
```

> **Note (05/09/2026)** — Ce fichier décrit l'état du 25/08, mis à jour ici uniquement sur ce qui a changé les 04–05/09 : GPU réel pour PaddleOCR (`nvidia-container-toolkit`) et modèle Ollama (Granite 3.3 2B). Le reste (dossiers/exigences/outline structuré, retrieval hybride `app/rag/hybrid_retriever.py`) a évolué depuis le 25/08 mais n'est **pas** ré-audité dans ce fichier — se fier au code / à `Nouvelle_Architecture/` pour ces briques.

---

## 1. Docling et PaddleOCR : déjà installés ?

**Non.** Ils ne sont **pas** dans l’image Docker API ni dans le `uv sync` de base (l’image **worker**, elle, embarque `ocr-gpu` — voir plus bas).

| Outil | Dans `pyproject.toml` | Installé par défaut | Quand l’installer |
|-------|----------------------|---------------------|-------------------|
| **Docling** | extra `ingest` | Non | PDF numériques structurés (titres, tableaux) |
| **PaddleOCR** (+ PaddlePaddle) | extra `ocr` (CPU) / `ocr-gpu` (GPU) | Non (image API) — **oui** dans l’image `worker` (`ocr-gpu`) | PDF **scans** (peu de texte extractible) |
| **pypdf** | dépendance **principale** | Oui après rebuild / `uv sync` | PDF texte, repli si Docling absent |
| **python-docx / openpyxl** | principale | Oui | DOCX / XLSX / export DOCX |

L’image API fait `uv sync --frozen --no-dev` **sans** extras (Docling/Paddle sont lourds). L’image **worker** (`Dockerfile.worker`) installe `ocr-gpu` de base. Le code n’utilise ces libs que **si elles s’importent**, sinon repli pypdf / docx / xlsx.

### Installation optionnelle (machine hôte, worker hybride)

```bash
cd backend_ao
uv sync --extra ingest                  # Docling seul
uv sync --extra ingest --extra ocr      # + Paddle CPU
uv sync --extra ingest --extra ocr-gpu  # + Paddle GPU (RTX A5000 confirmé)
```

⚠️ **Piège vérifié en pratique** : ne **jamais** installer `ocr` et `ocr-gpu` dans le même venv (`uv sync --all-extras` par exemple). `paddlepaddle` (CPU) et `paddlepaddle-gpu` s’installent tous les deux dans le même module `paddle` et se corrompent mutuellement (`ImportError: cannot import name '...' from 'paddle...'` à l’usage, symptôme trompeur qui ressemble à un souci réseau). Un seul des deux extras à la fois — en cas de doute, `rm -rf backend_ao/.venv` puis `uv sync` avec le bon extra repart propre.

### GPU réel (PaddleOCR) — Docker et hôte

Statut au 05/09 : **fonctionnel et testé** des deux côtés.

- **Hôte (worker hybride)** : `uv sync --extra ingest --extra ocr-gpu` puis `.venv/bin/python -c "import paddle; print(paddle.device.is_compiled_with_cuda(), paddle.device.get_device())"` → `True gpu:0`. `PaddleOCR(use_gpu=True)` s’initialise en ~2 s.
- **Docker (`worker`)** : nécessite `nvidia-container-toolkit` (absent par défaut). Une fois installé + runtime configuré + démon Docker redémarré, lancer avec l’overlay :

  ```bash
  sudo apt-get install -y nvidia-container-toolkit
  sudo nvidia-ctk runtime configure --runtime=docker
  sudo systemctl restart docker   # redémarre tous les conteneurs (restart: unless-stopped → remontent seuls)

  docker compose -f docker-compose.yml -f docker-compose.gpu.yml --profile dev up -d worker
  ```

  Vérifié : `docker exec btp-rag-worker-1 nvidia-smi` voit le GPU, `paddle.device.get_device()` renvoie `gpu:0` **dans le conteneur**.
  Détail complet des commandes : `Fichier/aaa_Commandes.md` §3 (« Worker Docker avec GPU réel »).

  Sans cette installation, le worker Docker tourne toujours en **CPU** pour l’OCR même avec `USE_GPU=true` (repli silencieux documenté dans `Dockerfile.worker` et `_try_paddle()` de `app/ingest/parse.py`) — juste plus lent par page, pas d’échec.

Sans Docling/Paddle : un PDF texte passe par **pypdf** ; un **scan** échoue avec un message d’install (`status=failed`).

### Ollama (obligatoire pour embed, graphe et chat)

Sur l’hôte (l’API Docker parle à `host.docker.internal:11434`) :

```bash
ollama pull nomic-embed-text
ollama pull granite3.3:2b
```

**Modèle par défaut depuis le 04/09 : `granite3.3:2b`** (IBM Granite 3.3, 2B, Ollama) — remplace `llama3`. Tourne 100 % GPU sur la RTX A5000 (`ollama ps`). Utilisé partout où le code appelle Ollama sans modèle explicite : chat, rédaction de section (horloge B) **et** extraction du graphe (horloge A, ci-dessous) — un seul réglage `LLM_MODEL` dans `.env` / `config.py`.

**Important :** Ollama doit écouter sur `0.0.0.0:11434` (pas seulement `127.0.0.1`), sinon Docker ne joint pas l’hôte.

Sans `nomic-embed-text`, l’ingest reste `failed` après le parse. Sans le modèle LLM, le document peut être `ready` (RAG indexé) mais `graph_extracted=false`, et le chat / la rédaction échouent.

---

## 2. Prérequis stack

```bash
cd "/home/juve/Lectures_&_projects/Projets/AI_ML/Tendertune"

# infra + API + worker + front
docker compose --profile dev up -d

# après changement de pyproject / lock : rebuild
docker compose --profile dev build api
docker compose --profile dev up -d api worker
```

Après un changement Python dans `backend_ao/app` (bind-mount) :

```bash
docker compose --profile dev restart api worker
```

Services / ports **hôte** (`.env`) :

| Service | Port hôte | Interne Docker |
|---------|-----------|----------------|
| Postgres | 5432 | 5432 |
| Redis | 6380 | 6379 |
| MinIO API / console | 9010 / 9011 | 9000 / 9001 |
| Qdrant | 6333 | 6333 |
| Neo4j | 7474 / 7687 | idem |
| API | 8001 | 8000 |
| Front Vite | 5174 | 5173 |

Compte admin : `.env` (`ADMIN_EMAIL` / `ADMIN_PASSWORD`, défaut `admin@btp.local`).

Psql interactif :

```bash
docker exec -ti -e PAGER="less -S" btp-rag-postgres-1 psql -U ao_user -d ao_db
```

Logs datés à la seconde (API + worker) :

```bash
docker compose --profile dev logs -f api worker
```

Toutes les variantes de lancement/arrêt/logs (Docker et hybride) : `Fichier/aaa_Commandes.md` §19.

---

## 3. Chaîne technique — horloge A (ingestion)

```text
Navigateur
  POST /documents  (multipart)
       │
       ▼
FastAPI (ne parse pas le PDF)
  1. SHA-256 → doublon tenant ?
  2. MinIO bucket ao-raw  clé {tenant_id}/{uuid}/{filename}
  3. INSERT documents status=pending
  4. ARQ enqueue ingest_document(id)
  5. Réponse HTTP immédiate
       │
       ▼
Worker ARQ  (processus séparé — Docker ou hybride hôte, GPU réel des deux côtés depuis le 04/09)
  ingest_document
    status=processing
    GET MinIO → fichier temporaire
    parse :
      xlsx → openpyxl
      docx → python-docx
      pdf  → densité texte
            assez de texte → Docling si dispo, sinon pypdf
            scan          → Paddle si dispo (GPU si dispo, sinon CPU), sinon Docling, sinon échec
    chunk parent / enfant
    DELETE anciens chunks du doc
    INSERT Postgres chunks
    POST Ollama /api/embeddings (nomic-embed-text)
    UPSERT Qdrant collection ao_chunks (vecteur dense 768)
    status=ready  ocr_used / page_count
    enqueue extract_graph
       │
       ▼
  extract_graph
    chunks parents (max 12)
    POST Ollama /api/generate format=json (granite3.3:2b — anciennement llama3)
    MERGE Neo4j Entity {key} + REL {type}  (Cypher paramétré)
    documents.graph_extracted = true
```

**Statuts `documents.status` :** `pending` → `processing` → `ready` | `failed`.
`graph_extracted` est un booléen séparé (pas un statut).

### Suppression d’un document

`DELETE /documents/{id}` (rôles **admin** / **manager**) purge dans l’ordre :

1. Qdrant — points `document_id`
2. Neo4j — `REL` liés aux `source_chunk_id`, puis `Entity` orphelines du tenant
3. MinIO — objet `ao-raw`
4. Postgres — ligne `documents` (chunks en `ON DELETE CASCADE`)

UI : bouton Supprimer + modal Oui / Annuler (pas `window.confirm`).

---

## 4. Où ça vit (toutes les bases)

| Donnée | Base |
|--------|------|
| Fichier brut | MinIO `ao-raw` |
| Métadonnées + statut document | Postgres `documents` |
| Texte des chunks (citations) | Postgres `chunks` |
| Vecteurs dense 768 | Qdrant `ao_chunks` |
| Entités / relations | Neo4j `Entity` / `REL` |
| Job ingest / graphe | Redis (ARQ) |
| Conversation + messages + historique LLM | Postgres `conversations` / `messages` *(horloge B)* |
| Export DOCX / PDF / MD / TXT | MinIO `ao-exports` + Postgres `exports` *(horloge B)* |

Le graphe est **après** `ready` : le RAG n’attend pas Neo4j. Si Ollama LLM est down, le PDF peut quand même être `ready` ; le chat échouera.

---

## 5. Fichiers code — horloge A

| Fichier | Rôle |
|---------|------|
| `app/api/documents.py` | Upload MinIO + enqueue + DELETE |
| `app/services/queue.py` | Pool ARQ |
| `app/services/purge_document.py` | Purge MinIO / Qdrant / Neo4j / Postgres |
| `app/ingest/parse.py` | Routeur Docling / Paddle (GPU/CPU) / pypdf / docx / xlsx |
| `app/ingest/chunk.py` | Parent section + fenêtres ~1100 car. |
| `app/ingest/index_qdrant.py` | Collection + embeddings + upsert |
| `app/workers/ingest.py` | Job `ingest_document` |
| `app/graph/extract.py` | Job `extract_graph` |
| `app/worker_settings.py` | Les deux jobs |
| `app/services/logging_setup.py` | Logs `YYYY-MM-DD HH:MM:SS` flush stdout |

Front (ingestion) : `frontend_ao/src/pages/DocumentsPage.tsx` — upload patrimoine, statut, suppression.

---

## 6. Parcours utilisateur — partie ingestion

1. Se connecter (`admin@btp.local` / mot de passe `.env`).
2. **Documents** → déposer un fichier patrimoine (PDF texte / DOCX / XLSX / TXT).
3. Suivre les logs worker jusqu’à `STATUT → ready` puis éventuellement `GRAPH FINI`.

→ Conversation, rédaction et export : suite du parcours dans **[conversation_horloge_B.md](conversation_horloge_B.md)**.

---

## 7. Vérifications — ingest

1. MinIO console : http://localhost:9011 (`minioadmin` / `minioadmin`) — objet dans `ao-raw`.
2. Front Documents : statut `ready` (puis graphe « oui »).
3. Postgres :

```sql
SELECT id, filename, status, graph_extracted, ingest_error FROM documents ORDER BY created_at DESC LIMIT 10;
SELECT count(*) FROM chunks;
```

4. Qdrant : collection `ao_chunks`.
5. Neo4j Browser http://localhost:7474 :

```cypher
MATCH (e:Entity) RETURN e LIMIT 25
```

### Logs attendus (extraits)

```text
[btp.upload] [1/4] MinIO PUT FIN …
[btp.ingest] [A] MinIO GET FIN …
[btp.ingest] [E] OLLAMA EMBEDDINGS FIN …
[btp.ingest] STATUT → ready …
[btp.graph] ======== GRAPH FINI …
```

---

## 8. Ce qui n’est pas encore dans cette étape (horloge A)

- Relance manuelle d’un ingest `failed`
- Image Docker avec Docling/Paddle préinstallés
- Similarités Neo4j `SIMILAIRE_A` (job nuit)

Voir **[conversation_horloge_B.md](conversation_horloge_B.md)** pour ce qui manque côté conversation / rédaction / export.
