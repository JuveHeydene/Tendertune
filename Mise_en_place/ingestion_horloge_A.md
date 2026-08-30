# Mise en place — pipeline documentaire (horloge A + horloge B)

Ce dossier décrit **ce qui est implémenté maintenant** dans le code : ingestion, index RAG, conversation, rédaction de sections, export DOCX, suppression.

```text
Horloge A (async, worker ARQ)
  upload → MinIO → parse → chunks → Ollama embed → Qdrant → ready → Neo4j

Horloge B (synchrone + stream SSE, API / conversation)
  question → historique conversation + LangGraph (route → retrieve → generate)
           → sections dossier → export multi-format MinIO ao-exports
           → upload document patrimoine depuis le chat
```

---

## 1. Docling et PaddleOCR : déjà installés ?

**Non.** Ils ne sont **pas** dans l’image Docker ni dans le `uv sync` de base.

| Outil | Dans `pyproject.toml` | Installé par défaut | Quand l’installer |
|-------|----------------------|---------------------|-------------------|
| **Docling** | extra `ingest` | Non | PDF numériques structurés (titres, tableaux) |
| **PaddleOCR** (+ PaddlePaddle) | extra `ocr` | Non | PDF **scans** (peu de texte extractible) |
| **pypdf** | dépendance **principale** | Oui après rebuild / `uv sync` | PDF texte, repli si Docling absent |
| **python-docx / openpyxl** | principale | Oui | DOCX / XLSX / export DOCX |
| **reportlab** | principale | Oui | Export PDF (pur Python, pas de WeasyPrint) |

L’image API/worker fait `uv sync --frozen --no-dev` **sans** extras. Docling et Paddle sont lourds (et Paddle a souvent des wheels manquants en Python 3.12). Ils restent **optionnels** : le worker les utilise **s’ils s’importent**, sinon pypdf / docx / xlsx.

### Installation optionnelle (machine hôte, worker hybride)

```bash
cd backend_ao
uv sync --extra ingest          # Docling
uv sync --extra ingest --extra ocr   # + Paddle CPU
```

GPU Paddle : `USE_GPU=true` + overlay `docker-compose.gpu.yml` + extra `gpu` — **pas** le chemin par défaut.

Sans Docling/Paddle : un PDF texte passe par **pypdf** ; un **scan** échoue avec un message d’install (`status=failed`).

### Ollama (obligatoire pour embed, graphe et chat)

Sur l’hôte (l’API Docker parle à `host.docker.internal:11434`) :

```bash
ollama pull nomic-embed-text
ollama pull llama3
```

**Important :** Ollama doit écouter sur `0.0.0.0:11434` (pas seulement `127.0.0.1`), sinon Docker ne joint pas l’hôte.

Sans `nomic-embed-text`, l’ingest reste `failed` après le parse. Sans `llama3`, le document peut être `ready` (RAG indexé) mais `graph_extracted=false`, et le chat / la rédaction échouent.

---

## 2. Prérequis stack

```bash
cd "/home/juve/Lectures_&_projects/Projets/BTP_RAG"

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
Worker ARQ  (processus séparé)
  ingest_document
    status=processing
    GET MinIO → fichier temporaire
    parse :
      xlsx → openpyxl
      docx → python-docx
      pdf  → densité texte
            assez de texte → Docling si dispo, sinon pypdf
            scan          → Paddle si dispo, sinon Docling, sinon échec
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
    POST Ollama /api/generate format=json (llama3)
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

## 4. Chaîne technique — horloge B (conversation → export)

### 4.1 Mémoire conversationnelle

Chaque conversation conserve dans Postgres :

- **`conversations`** — titre, lien `dossier_id`, tenant, user
- **`messages`** — rôle user/assistant, contenu, `meta` JSON (markdown, citations, uploads…)

**Injection dans le LLM** (`app/services/chat_history.py`) :

- Avant chaque réponse, les **8 derniers tours** user/assistant sont formatés en bloc texte
- Injectés dans le prompt Ollama via `build_prompt()` (`app/workflow/nodes/generate.py`)
- Les uploads (« Document déposé : … ») et les réponses markdown précédentes enrichissent ce contexte
- Le RAG (Qdrant) reste la source factuelle ; l’historique évite de « oublier » ce qui s’est dit dans le fil

### 4.2 Upload document depuis une conversation

```text
Navigateur  bouton « Joindre un document »
  POST /conversations/{id}/documents  (multipart file)
       │
       ▼
FastAPI
  doc_role=patrimoine  doc_type=reference  (forcé)
  dossier_origine_id = dossier lié à la conversation
  store_document → MinIO ao-raw → Postgres pending → ARQ ingest
  INSERT message user meta={upload, document_id, filename}
       │
       ▼
Worker (horloge A) — même pipeline ingest → Qdrant → Neo4j
  → le document rejoint le patrimoine indexé pour les prochaines questions RAG
```

Si la conversation est encore un brouillon (`/new`), le front **crée d’abord** la conversation puis envoie le fichier.

### 4.3 Streaming temps réel (SSE)

**Endpoint :** `POST /conversations/{id}/messages/stream`

```text
Navigateur                          FastAPI                         Ollama
    │                                  │                              │
    │  fetch POST (body JSON text)     │                              │
    │─────────────────────────────────►│                              │
    │                                  │  route + retrieve (Qdrant)   │
    │  event: user                     │                              │
    │◄─────────────────────────────────│                              │
    │  event: intent                   │                              │
    │◄─────────────────────────────────│                              │
    │                                  │  POST /api/generate stream   │
    │                                  │─────────────────────────────►│
    │  event: token {t:"..."}          │◄── chunks JSON ndjson ───────│
    │◄─────────────────────────────────│                              │
    │  (répété à chaque token)         │                              │
    │  event: section_start/end        │  (rédaction section)         │
    │  event: done                     │  commit Postgres messages    │
    │◄─────────────────────────────────│                              │
```

**Bibliothèques / composants :**

| Couche | Techno |
|--------|--------|
| Protocole | **SSE** (Server-Sent Events) — `text/event-stream` |
| Backend HTTP | **FastAPI** `StreamingResponse` + générateur async |
| Format SSE | `event: token\ndata: {"t":"..."}\n\n` (maison, `chat_pipeline._sse`) |
| LLM stream | **Ollama** `POST /api/generate` avec `"stream": true` |
| Client HTTP LLM | `app/services/ollama_llm.py` → `ollama_generate_stream()` (itérateur Python) |
| Pont sync→async | `threading.Thread` + `asyncio.Queue` (`_iter_ollama_tokens`) |
| Front | **`fetch` + `ReadableStream`** (`convApi.sendStream` dans `client.ts`) |
| Affichage live | **React** state `streamDraft` → bulle assistant (`react-markdown` + `remark-gfm`) |
| Rendu markdown chat | **react-markdown** 9.x, **remark-gfm** (tableaux, listes) |

Le panneau **aperçu document** (droite) **ne stream pas** : il montre la synthèse des sections **persistées** après commit.

### 4.4 LangGraph + génération

```text
FastAPI  (horloge B)
  LangGraph compiled :
    route
      smalltalk     → chitchat
      export        → flag export
      hybrid_rag | run_section → retrieve → generate
    retrieve
      embed query (nomic) → Qdrant query_points
      filtre tenant_id + doc_role ∈ {patrimoine, dao_archive}
      repli sans filtre rôle si 0 hit
    generate
      prompt = historique + question + extraits RAG
      Ollama llama3 (stream ou sync)
       │
       ▼
  Si run_section (rédacteur / manager / admin) :
    ensure dossier lié à la conversation
    plan type outline_items (présentation, moyens, références, méthodo, planning)
    INSERT generations (content JSON titre+texte, citations)
    outline_items.status = generated
       │
       ▼
  Export (bouton ou phrase « exporte le PDF ») :
    assemble sections → docx | pdf | md | txt
    PUT MinIO ao-exports  {tenant}/exports/{dossier_id}/v{N}.{ext}
    INSERT exports
    GET /exports  (listing)  ou  GET /exports/{id}/download
```

### 4.5 Export multi-format

| Format | Bibliothèque | Bucket MinIO |
|--------|--------------|--------------|
| DOCX | **python-docx** | ao-exports |
| PDF | **reportlab** (Platypus, Helvetica — pas de WeasyPrint) | ao-exports |
| MD | concat markdown maison | ao-exports |
| TXT | texte brut | ao-exports |

Listing : **`GET /exports`** — visible dans **Documents → Documents exportés** avec bouton Télécharger.

### Intentions détectées (routeur déterministe)

| Intention | Exemples de phrases |
|-----------|---------------------|
| `smalltalk` | bonjour, salut |
| `hybrid_rag` | question libre sur le patrimoine |
| `run_section` | « rédige la présentation… », « génère les moyens humains », « rédige le mémoire complet » |
| `export` | « exporte le DOCX », « télécharge » |

### Plan type du mémoire (V1)

| Clé | Titre |
|-----|--------|
| `presentation` | Présentation de l’entreprise |
| `moyens_humains` | Moyens humains |
| `references` | Références et projets similaires |
| `methodologie` | Méthodologie et organisation |
| `planning` | Planning et délais |

« Mémoire complet » enchaîne les 5 sections (plusieurs appels Ollama).

### Rôles

| Action | Rôles |
|--------|--------|
| Lire documents / conversations | tous (consultant inclus) |
| Upload | admin, manager, rédacteur |
| Supprimer document | admin, manager |
| Rédiger section / exporter | admin, manager, rédacteur |
| Joindre document en conversation | admin, manager, rédacteur |

---

## 5. Où ça vit (toutes les bases)

| Donnée | Base |
|--------|------|
| Fichier brut | MinIO `ao-raw` |
| Métadonnées + statut document | Postgres `documents` |
| Texte des chunks (citations) | Postgres `chunks` |
| Vecteurs dense 768 | Qdrant `ao_chunks` |
| Entités / relations | Neo4j `Entity` / `REL` |
| Job ingest / graphe | Redis (ARQ) |
| Conversation + messages + historique LLM | Postgres `conversations` / `messages` |
| Upload depuis chat | POST `/conversations/{id}/documents` → patrimoine |
| Export DOCX / PDF / MD / TXT | MinIO `ao-exports` + Postgres `exports` |
| Listing exports | GET `/exports` — page Documents |

Le graphe est **après** `ready` : le RAG n’attend pas Neo4j. Si Ollama LLM est down, le PDF peut quand même être `ready` ; le chat échouera.

---

## 6. Fichiers code

### Horloge A

| Fichier | Rôle |
|---------|------|
| `app/api/documents.py` | Upload MinIO + enqueue + DELETE |
| `app/services/queue.py` | Pool ARQ |
| `app/services/purge_document.py` | Purge MinIO / Qdrant / Neo4j / Postgres |
| `app/ingest/parse.py` | Routeur Docling / Paddle / pypdf / docx / xlsx |
| `app/ingest/chunk.py` | Parent section + fenêtres ~1100 car. |
| `app/ingest/index_qdrant.py` | Collection + embeddings + upsert |
| `app/workers/ingest.py` | Job `ingest_document` |
| `app/graph/extract.py` | Job `extract_graph` |
| `app/worker_settings.py` | Les deux jobs |
| `app/services/logging_setup.py` | Logs `YYYY-MM-DD HH:MM:SS` flush stdout |

### Horloge B

| Fichier | Rôle |
|---------|------|
| `app/api/conversations.py` | Messages stream SSE, upload doc, export, rename, delete |
| `app/api/exports.py` | Listing + téléchargement exports |
| `app/services/chat_history.py` | Format historique pour prompts |
| `app/services/document_upload.py` | Upload partagé tenant / conversation |
| `app/services/chat_pipeline.py` | Stream SSE + historique + sections |
| `app/api/dossiers.py` | Listing + `GET …/export.docx` |
| `app/workflow/graph.py` | LangGraph compile (route / retrieve / generate / chitchat / export) |
| `app/workflow/nodes/route.py` | Intentions |
| `app/workflow/nodes/retrieve.py` | Appelle le retriever |
| `app/workflow/nodes/generate.py` | Prompt Ollama + contexte |
| `app/workflow/sections.py` | Plan type + détection de section |
| `app/rag/hybrid_retriever.py` | Qdrant dense + filtre tenant / rôles |
| `app/services/ollama_llm.py` | `POST /api/generate` |
| `app/services/dossier_workflow.py` | Dossier, generations, export DOCX/PDF/MD/TXT |

### Front

| Fichier | Rôle |
|---------|------|
| `frontend_ao/src/pages/DocumentsPage.tsx` | Upload patrimoine, exports téléchargeables, suppression |
| `frontend_ao/src/pages/ConversationsPage.tsx` | Chat SSE + joindre doc + aperçu + export |
| `frontend_ao/src/pages/DossiersPage.tsx` | Liste dossiers + téléchargement |
| `frontend_ao/src/api/client.ts` | `convApi`, `docsApi`, `exportsApi`, stream SSE |

---

## 7. Parcours utilisateur (bout en bout)

1. Se connecter (`admin@btp.local` / mot de passe `.env`).
2. **Documents** → déposer un fichier patrimoine (PDF texte / DOCX / XLSX / TXT).
3. Suivre les logs worker jusqu’à `STATUT → ready` puis éventuellement `GRAPH FINI`.
4. **Conversations** → Nouvelle conversation → poser une question ou **joindre un PDF/DOCX** de référence.
5. Attendre `ready` sur le document joint (worker) puis poser des questions enrichies RAG.
6. « Rédige la présentation de l’entreprise » → section dans le fil **et** aperçu document à droite.
7. **Exporter** (DOCX / PDF / MD / TXT) depuis le panneau droit.
8. **Documents → Documents exportés** : retrouver et télécharger les exports passés.

---

## 8. Vérifications

### Ingest

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

### Conversation / export

1. Après une rédaction : `SELECT key, status FROM outline_items;`
2. `SELECT section_key, version FROM generations;`
3. MinIO bucket `ao-exports`.
4. `SELECT version, object_key, size_bytes FROM exports;`
5. Bouton DOCX sur Dossiers ou Conversations.

### Logs attendus (extraits)

```text
[btp.upload] [1/4] MinIO PUT FIN …
[btp.ingest] [A] MinIO GET FIN …
[btp.ingest] [E] OLLAMA EMBEDDINGS FIN …
[btp.ingest] STATUT → ready …
[btp.graph] ======== GRAPH FINI …
[btp.chat] horloge B FIN intent=hybrid_rag|run_section|export
[btp.dossier] export DOCX FIN …
```

---

## 9. Ce qui n’est pas encore dans cette étape

- Recherche hybride sparse + RRF + rerank BGE
- Extraction d’exigences DAO → table `exigences` (HITL revue section)
- Relance manuelle d’un ingest `failed`
- Export PDF (**reportlab** — inclus dans l’image Docker de base)
- Image Docker avec Docling/Paddle préinstallés
- Similarités Neo4j `SIMILAIRE_A` (job nuit)
- Agents LangGraph autonomes (V1 = nœuds déterministes uniquement)
