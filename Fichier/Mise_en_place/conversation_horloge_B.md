# Mise en place — conversation, rédaction, export (horloge B)

Ce dossier décrit **ce qui est implémenté maintenant** dans le code pour l'**horloge B** (conversation → rédaction → export). Pour l'ingestion documentaire (**horloge A**), voir **[ingestion_horloge_A.md](ingestion_horloge_A.md)**.

```text
Horloge A (async, worker ARQ)                          ← voir ingestion_horloge_A.md
  upload → MinIO → parse → chunks → Ollama embed → Qdrant → ready → Neo4j

Horloge B (synchrone + stream SSE, API / conversation)  ← détaillé ici
  question → historique conversation + LangGraph (route → retrieve → generate)
           → sections dossier → export multi-format MinIO ao-exports
           → upload document patrimoine depuis le chat
```

> **Note (05/09/2026)** — Ce fichier reprend la partie « horloge B » de l'ancien `ingestion_horloge_A.md` (état du 25/08), mise à jour ici sur ce qui a changé les 04–05/09 : export PDF passé de reportlab à **WeasyPrint** (template HTML/CSS), modèle LLM passé à **Granite 3.3 2B**, et un bug de persistance corrigé sur la génération de section. Le reste (dossiers/exigences/outline structuré, retrieval hybride `app/rag/hybrid_retriever.py`) a évolué depuis le 25/08 mais n'est **pas** ré-audité en détail dans ce fichier — se fier au code / à `Nouvelle_Architecture/` pour ces briques.

---

## 1. Mémoire conversationnelle

Chaque conversation conserve dans Postgres :

- **`conversations`** — titre, lien `dossier_id`, tenant, user
- **`messages`** — rôle user/assistant, contenu, `meta` JSON (markdown, citations, uploads…)

**Injection dans le LLM** (`app/services/chat_history.py`) :

- Avant chaque réponse, les **8 derniers tours** user/assistant sont formatés en bloc texte
- Injectés dans le prompt Ollama via `build_prompt()` (`app/workflow/nodes/generate.py`)
- Les uploads (« Document déposé : … ») et les réponses markdown précédentes enrichissent ce contexte
- Le RAG (Qdrant) reste la source factuelle ; l’historique évite de « oublier » ce qui s’est dit dans le fil

---

## 2. Upload document depuis une conversation

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

---

## 3. Streaming temps réel (SSE)

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

---

## 4. LangGraph + génération

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
      Ollama granite3.3:2b (stream ou sync — anciennement llama3)
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

**Bug corrigé le 04/09** — `POST /dossiers/{id}/sections/{key}/generate` (génération directe d’une section, hors chat) ne faisait **jamais `session.commit()`** : la réponse HTTP renvoyait bien la section générée, mais rien n’était persisté en base (rollback silencieux à la fermeture de la session SQLAlchemy). Un export lancé juste après ne voyait donc jamais cette section. Corrigé dans `app/api/dossiers.py` (`generate_section_endpoint`) — vérifié par un test bout-en-bout réel (génération → `SELECT` Postgres → export PDF avec le contenu généré).

---

## 5. Export multi-format

| Format | Bibliothèque | Bucket MinIO |
|--------|--------------|--------------|
| DOCX | **python-docx** | ao-exports |
| **PDF** | **WeasyPrint** (HTML/CSS → PDF, template Jinja2) — remplace reportlab depuis le 04/09 | ao-exports |
| MD | concat markdown maison | ao-exports |
| TXT | texte brut | ao-exports |

**PDF — détail du nouveau rendu** (`app/services/pdf_export.py` + `app/templates/memoire_export.html`) :

- Couverture (nom du projet, version, date), sommaire, en-tête/pied de page courants avec numérotation (`counter(page)`/`counter(pages)`, CSS Paged Media)
- Rendu à partir des **blocs structurés** de `SectionGeneree` (`paragraphe`, `liste`, `tableau_md`, `sous_titre`) plutôt que du texte aplati — les tableaux markdown deviennent de vrais `<table>` HTML (via la lib `markdown`, extension `tables`), les listes de vraies `<ul>`
- Encart visuel (`⚠️ Points non couverts`) pour les abstentions de section
- Nécessite les libs système `libpango`/`libcairo`/`libgdk-pixbuf` côté image Docker API (ajoutées au `Dockerfile`, absentes de l’image de base `python:3.12-slim`) — déjà en place et testées
- Testé bout-en-bout : génération réelle de 2 sections via le pipeline agentique (Granite 3.3 2B) → export → PDF téléchargé et inspecté visuellement

Listing : **`GET /exports`** — visible dans **Documents → Documents exportés** avec bouton Télécharger.

---

## 6. Intentions détectées (routeur déterministe)

| Intention | Exemples de phrases |
|-----------|---------------------|
| `smalltalk` | bonjour, salut |
| `hybrid_rag` | question libre sur le patrimoine |
| `run_section` | « rédige la présentation… », « génère les moyens humains », « rédige le mémoire complet » |
| `export` | « exporte le DOCX », « télécharge » |

---

## 7. Plan type du mémoire (V1)

| Clé | Titre |
|-----|--------|
| `presentation` | Présentation de l’entreprise |
| `moyens_humains` | Moyens humains |
| `references` | Références et projets similaires |
| `methodologie` | Méthodologie et organisation |
| `planning` | Planning et délais |

« Mémoire complet » enchaîne les 5 sections (plusieurs appels Ollama).

---

## 8. Rôles

| Action | Rôles |
|--------|-------|
| Lire documents / conversations | tous (consultant inclus) |
| Upload | admin, manager, rédacteur |
| Supprimer document | admin, manager |
| Rédiger section / exporter | admin, manager, rédacteur |
| Joindre document en conversation | admin, manager, rédacteur |

---

## 9. Fichiers code — horloge B

| Fichier | Rôle |
|---------|------|
| `app/api/conversations.py` | Messages stream SSE, upload doc, export, rename, delete |
| `app/api/exports.py` | Listing + téléchargement exports |
| `app/services/chat_history.py` | Format historique pour prompts |
| `app/services/document_upload.py` | Upload partagé tenant / conversation |
| `app/services/chat_pipeline.py` | Stream SSE + historique + sections |
| `app/api/dossiers.py` | Listing, génération de section, `GET …/export.{fmt}` |
| `app/workflow/graph.py` | LangGraph compile (route / retrieve / generate / chitchat / export) |
| `app/workflow/nodes/route.py` | Intentions |
| `app/workflow/nodes/retrieve.py` | Appelle le retriever |
| `app/workflow/nodes/generate.py` | Prompt Ollama + contexte |
| `app/workflow/sections.py` | Plan type + détection de section |
| `app/rag/hybrid_retriever.py` | Qdrant dense + filtre tenant / rôles (évolue au-delà de ce doc — voir note en tête) |
| `app/services/ollama_llm.py` | `POST /api/generate` |
| `app/services/dossier_workflow.py` | Dossier, generations, export DOCX/PDF/MD/TXT (assemblage + upload MinIO) |
| `app/services/pdf_export.py` | **Nouveau (04/09)** — rendu HTML (Jinja2) → PDF (WeasyPrint) à partir des blocs structurés |
| `app/templates/memoire_export.html` | **Nouveau (04/09)** — template du mémoire PDF (couverture, sommaire, styles) |

Front :

| Fichier | Rôle |
|---------|------|
| `frontend_ao/src/pages/ConversationsPage.tsx` | Chat SSE + joindre doc + aperçu + export |
| `frontend_ao/src/pages/DossiersPage.tsx` | Liste dossiers + téléchargement |
| `frontend_ao/src/api/client.ts` | `convApi`, `docsApi`, `exportsApi`, stream SSE |

---

## 10. Parcours utilisateur — partie conversation / rédaction / export

*(suite de [ingestion_horloge_A.md](ingestion_horloge_A.md) §6, une fois un document `ready`)*

1. **Conversations** → Nouvelle conversation → poser une question ou **joindre un PDF/DOCX** de référence.
2. Attendre `ready` sur le document joint (worker) puis poser des questions enrichies RAG.
3. « Rédige la présentation de l’entreprise » → section dans le fil **et** aperçu document à droite.
4. **Exporter** (DOCX / PDF / MD / TXT) depuis le panneau droit.
5. **Documents → Documents exportés** : retrouver et télécharger les exports passés.

---

## 11. Vérifications — conversation / export

1. Après une rédaction : `SELECT key, status FROM outline_items;`
2. `SELECT section_key, version FROM generations;`
3. MinIO bucket `ao-exports`.
4. `SELECT version, object_key, size_bytes FROM exports;`
5. Bouton PDF/DOCX sur Dossiers ou Conversations — ouvrir le PDF généré pour vérifier visuellement le rendu (couverture, sommaire, tableaux).

### Logs attendus (extraits)

```text
[btp.chat] horloge B FIN intent=hybrid_rag|run_section|export
[btp.dossier] export pdf FIN id=… version=…
[btp.dossier] export docx FIN …
```

---

## 12. Ce qui n’est pas encore dans cette étape (horloge B)

- Agents LangGraph autonomes (V1 = nœuds déterministes uniquement)
- Recherche hybride sparse + RRF + rerank BGE — en cours d'évolution dans `app/rag/hybrid_retriever.py`, non ré-audité ici (voir note en tête de fichier)

Voir **[ingestion_horloge_A.md](ingestion_horloge_A.md)** pour ce qui manque côté ingestion.
