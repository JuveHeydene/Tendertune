# Compréhension globale du projet BTP_RAG / backend_ao

Ce document explique **de manière textuelle et pédagogique** ce que fait la plateforme, quelles technologies elle utilise, comment elles s'articulent entre elles, et comment fonctionnent en détail les deux processus centraux : **l'ingestion documentaire** et **la génération** (réponses de chat + rédaction de sections de mémoire technique + revue humaine + export).

Il est fait pour être lu par quelqu'un qui **reprend le projet** et n'a jamais vu le code : après lecture, vous devez pouvoir situer chaque fichier, comprendre pourquoi il existe, et savoir dans quel diagramme retrouver son comportement exact.

Deux diagrammes de séquence PlantUML accompagnent ce document, dans le même dossier :

- [`01_diagramme_sequence_ingestion.puml`](01_diagramme_sequence_ingestion.puml) (rendu [`.png`](01_diagramme_sequence_ingestion.png) / [`.pdf`](01_diagramme_sequence_ingestion.pdf)) — tout le cycle de vie d'un document, du dépôt à l'extraction du graphe de connaissances, jusqu'à chaque condition et chaque branchement d'erreur.
- [`02_diagramme_sequence_generation.puml`](02_diagramme_sequence_generation.puml) (rendu [`.png`](02_diagramme_sequence_generation.png) / [`.pdf`](02_diagramme_sequence_generation.pdf)) — tout le cycle de vie d'une réponse de chat ou d'une section de mémoire technique, du message utilisateur jusqu'à l'export final, en passant par la revue humaine.
- Vue d'architecture générale (composants + infrastructure, pas un déroulé temporel) en trois formats : [`03_architecture_generale_ascii.txt`](03_architecture_generale_ascii.txt), [`03_architecture_generale.puml`](03_architecture_generale.puml) (rendu [`.png`](03_architecture_generale.png)), et [`03_architecture_generale.drawio`](03_architecture_generale.drawio) (éditable dans diagrams.net).
- [`04_architecture_api_detaillee.puml`](04_architecture_api_detaillee.puml) (rendu [`.png`](04_architecture_api_detaillee.png)) — la même architecture, mais avec la couche API décortiquée : chaque contrôleur REST/SSE réel (`app/api/*.py`) et les services internes (`app/services/`, `app/workflow/`) auxquels il délègue, pour bien voir que les contrôleurs ne parlent jamais directement à l'infrastructure.

Ces diagrammes sont **descriptifs du code réel** (pas un schéma d'intention) : ils ont été construits en lisant chaque fichier source concerné, ligne par ligne, dans `backend_ao/app/`.

---

## 1. Le projet en une phrase

`backend_ao` est une plateforme de **RAG (Retrieval-Augmented Generation)** spécialisée dans les **appels d'offres du BTP** (bâtiment/travaux publics). Elle permet à une entreprise du secteur de :

1. **Capitaliser** ses documents (chantiers passés, certifications, CV, mémoires techniques déjà rédigés — appelés "patrimoine") et le dossier de consultation d'un appel d'offres en cours (le "DAO" : RC, CCTP, CCAP, DPGF/BPU...).
2. **Interroger** cette base documentaire en langage naturel, avec des réponses sourcées (citations vers les documents).
3. **Générer automatiquement** les sections d'un mémoire technique de réponse à l'appel d'offres, en s'appuyant sur son patrimoine documentaire et sur les exigences détectées dans le DAO.
4. **Faire relire un humain** (rédacteur) chaque section générée avant de l'exporter dans le document final (Word/PDF/Markdown/texte).

Le terme "tenant" revient partout dans le code : la plateforme est **multi-entreprise** (multi-tenant), chaque entreprise ne voit que ses propres documents et dossiers.

---

## 2. Architecture globale

```
Frontend (React/Vite, SSE)
        │
        ▼
API FastAPI  ──────────────►  Postgres (pgvector) : vérité métier
   │      │                    (documents, chunks, dossiers, exigences,
   │      │                     outline_items, generations, reviews, users...)
   │      ▼
   │   Redis (file ARQ) ───► Worker Ingestion / Worker Graphe / Worker Structure
   │                              │            │                │
   │                          MinIO        Ollama (LLM)      Ollama (LLM)
   │                       (fichier brut)      │                │
   │                                        Qdrant           Neo4j
   ▼
Ollama (LLM + embeddings, local)  ◄──── utilisé aussi en direct par l'API
   │
Qdrant (vecteurs) · Neo4j (graphe) · Postgres FTS (recherche texte)
```

Tout tourne en conteneurs Docker Compose (`docker-compose.yml` à la racine), sauf le **LLM Ollama** qui tourne **sur la machine hôte** (`host.docker.internal:11434`) — c'est un choix volontaire pour profiter du GPU de la machine sans le dupliquer dans un conteneur.

### 2.1 Les services (voir `docker-compose.yml`)

| Service | Image | Rôle |
|---|---|---|
| `postgres` | `pgvector/pgvector:pg17` | Base relationnelle. L'extension `pgvector` est présente mais **la recherche dense se fait en réalité via Qdrant**, pas via pgvector — Postgres sert pour les données métier et pour la **recherche sparse** (full-text search / `text_fts`). |
| `qdrant` | `qdrant/qdrant:latest` | Base vectorielle dédiée : une seule collection `ao_chunks`, distance cosinus, dimension 768. |
| `neo4j` | `neo4j:5` (+plugin APOC) | Graphe de connaissances : entités (entreprises, projets, clients, certifications, personnes...) et leurs relations, extraites automatiquement des documents. |
| `redis` | `redis:7-alpine` | Broker de la file de tâches asynchrones, utilisée par **ARQ** (équivalent léger de Celery, en asyncio). |
| `minio` | `minio/minio:latest` | Stockage objet compatible S3 : fichiers originaux déposés (`bucket ao-raw`) et exports générés (`bucket ao-exports`). |
| `api` | build local (`backend_ao/Dockerfile`) | Le serveur FastAPI, tout ce qui répond aux requêtes HTTP/SSE synchrones. |
| `worker` | build local (`backend_ao/Dockerfile.worker`, image séparée avec l'extra OCR) | Exécute les jobs asynchrones ARQ (ingestion, extraction de graphe, analyse de structure de dossier). Séparé de l'image API car il embarque PaddleOCR/PaddlePaddle (poids lourds, dépendances CUDA spécifiques). |
| `frontend` | `node:22-alpine`, lance `npm run dev` (Vite) | Interface web React. |
| **Ollama** (hors Compose) | — | Tourne sur l'hôte, sert à la fois le **LLM de génération** (`llama3` par défaut) et le **modèle d'embeddings** (`nomic-embed-text`, 768 dimensions). |

La configuration complète (URLs, identifiants, noms de modèles, feature flags) est centralisée dans un unique fichier : `backend_ao/app/config.py`, chargé depuis `.env`. Il n'y a **pas** de bascule vers un LLM cloud (OpenAI, etc.) implémentée dans le code actuel : `llm_provider="ollama"` est la seule valeur réellement branchée.

### 2.2 Stack technique détaillée

**Backend** (`backend_ao/`, Python ≥3.12, géré par `uv`, voir `pyproject.toml`) :

- **FastAPI** — API HTTP + endpoints SSE (`text/event-stream`) pour le streaming du chat.
- **SQLAlchemy 2.0 (async) + asyncpg** — accès à Postgres, un seul driver, tout en asynchrone.
- **ARQ + Redis** — file de tâches de fond (voir `app/worker_settings.py` pour la liste des jobs enregistrés).
- **Qdrant client** — recherche vectorielle dense.
- **Neo4j driver** — graphe de connaissances (requêtes Cypher **fixes**, jamais générées librement par un LLM — choix de sécurité/fiabilité explicite dans `app/graph/cypher.py`).
- **MinIO SDK** — stockage objet (fichiers bruts + exports).
- **rapidfuzz** — correspondance floue de chaînes (déduplication d'entités et d'exigences).
- **python-docx / openpyxl / pypdf / Docling / PaddleOCR / PyMuPDF (fitz)** — extraction de contenu selon le format du fichier déposé (voir §4).
- **reportlab / python-docx / markdown** — génération des exports (PDF/DOCX/MD/TXT).
- **LangGraph / LangChain** — présents dans les dépendances et utilisés par le **flux de chat historique V1** (`app/workflow/graph.py`) ; le **pipeline agentique V2**, qui est le chemin réellement utilisé aujourd'hui par l'interface (streaming), **n'utilise pas LangGraph** : c'est de la composition de fonctions asynchrones classiques (`app/workflow/agentic_pipeline.py`).
- **PyJWT + bcrypt** — authentification par JWT, mots de passe hashés.
- **Pydantic v2** — validation de toutes les structures de données échangées avec le LLM (schémas JSON contraints) et les API.

**Frontend** (`frontend_ao/`) :

- **React 19 + Vite 8 + TypeScript** — SPA.
- **react-router-dom 7** — routage.
- **react-markdown + remark-gfm** — rendu des réponses/sections générées (qui sont en Markdown).
- Connexion au backend via `fetch` classique pour le CRUD, et via **EventSource/SSE** pour le streaming du chat.

**LLM / IA** :

- **Ollama**, en local, sert un seul modèle de génération (`llama3` par défaut, configurable) pour **absolument tous** les usages : réécriture de question, routage/supervision, extraction d'entités du graphe, jugement CRAG, génération de section JSON, extraction d'outline/exigences/pièces administratives.
- **`nomic-embed-text`** pour tous les embeddings (chunks documentaires, résolution d'entités par similarité).
- Le "reranker" configuré (`BAAI/bge-reranker-v2-m3`) est **déclaré mais non utilisé tel quel** : à cause d'un conflit de dépendances (cuDNN), `app/rag/rerank.py` implémente en réalité un score hybride **lexical (overlap de tokens) + RRF**, pas un vrai cross-encoder. C'est un point important à connaître si vous voulez améliorer la qualité du retrieval.

---

## 3. Les grandes entités de données (Postgres)

Comprendre ces objets permet de comprendre les deux diagrammes :

- **`Document`** : un fichier déposé. Champs clés : `status` (`pending → processing → ready` ou `failed`), `doc_role` (`patrimoine` / `dao_courant` / `dao_archive` / `annexe`), `doc_type` (`rc`, `cctp`, `ccap`, `dpgf`, `bpu`, `memoire`, `reference`, `administratif`, `autre`), `graph_extracted` (bool), `ingest_error`.
- **`ChunkRow`** : un fragment de texte issu du découpage d'un document, avec une hiérarchie **parent** (jusqu'à 8000 caractères) / **enfant** (fenêtres de 1100 caractères, chevauchement 120), un `section_type` (deviné par heuristique ou LLM), et un lien vers son document.
- **`Dossier`** : un appel d'offres en cours de réponse pour un tenant. `status` : `draft → analyzing → generating → exported`. Lié à un `Document` DAO (`dao_document_id`).
- **`OutlineItem`** : une section du plan du mémoire technique à produire (ex. "Présentation de l'entreprise", "Moyens humains"...). `status` : `todo → generated → approved` (ou `rejected`, transitoire pendant une régénération).
- **`ExigenceRow`** : une exigence extraite du DAO (`type` : `eliminatoire`/`technique`/`administrative`/`financiere`/`delai`/`reference`), `statut` : `a_couvrir → en_cours → couverte`/`non_couverte`.
- **`DossierPiece`** : une pièce administrative attendue (KBIS, assurance décennale...), `statut` `manquant`/`trouve_patrimoine`/`fourni`.
- **`Generation`** : une version du contenu généré pour une `OutlineItem` (versionnée : chaque approbation/édition/régénération crée potentiellement une nouvelle version).
- **`Review`** : la décision humaine (`approve`/`edit`/`regen`) prise sur une génération.
- **`RetrievalTrace`** : trace de chaque tentative de recherche faite par un "expert" (utile pour le débogage et l'évaluation de la qualité du RAG).
- **`Export`** : un fichier final généré (DOCX/PDF/MD/TXT), stocké dans MinIO.

Les entités du **graphe de connaissances** (Neo4j) sont volontairement minimalistes : un seul label `Entity {key, name, type, tenant_id}` et un seul type de relation `REL {type, source_chunk_id}` — le "type" sémantique (ex. `A_TRAVAILLE_SUR`, `PORTE`, `SATISFAITE_PAR`...) est une **propriété** de la relation, pas un type Neo4j distinct. Cela simplifie énormément les requêtes Cypher (toujours les mêmes gabarits, jamais générées par un LLM).

---

## 4. Le processus d'ingestion — vue textuelle

*(diagramme complet : [`01_diagramme_sequence_ingestion.puml`](01_diagramme_sequence_ingestion.puml))*

### 4.1 Dépôt (synchrone, rapide)

Un utilisateur dépose un fichier via `POST /documents` (`app/api/documents.py`). L'API valide immédiatement : rôle du document cohérent, type cohérent, droits de l'utilisateur (un `consultant` ne peut pas déposer), présence d'un `dossier_id` si le document est une "annexe". Le fichier est ensuite confié à `app/services/document_upload.py::store_document`, qui :

1. Calcule un **SHA-256** du contenu : si un document identique existe déjà pour ce tenant, on **ne fait rien de plus** (pas de nouvel upload, pas de nouveau job) — c'est la déduplication.
2. Sinon, envoie le fichier brut dans **MinIO**, crée la ligne `Document` (`status="pending"`) dans Postgres, puis **enfile un job ARQ** `ingest_document`.

La réponse HTTP part tout de suite (l'utilisateur n'attend pas le traitement) : c'est le principe de **l'horloge asynchrone**.

### 4.2 Traitement du fichier (asynchrone, worker ARQ)

Le job `ingest_document` (`app/workers/ingest.py`) télécharge le fichier depuis MinIO puis appelle `app/ingest/parse.py::parse_file`, qui **choisit sa stratégie selon le format** :

- **XLSX/XLSM** → `openpyxl`, une page par feuille.
- **DOCX** → `python-docx`, découpage aux styles `Heading*`.
- **TXT/MD** → lecture brute.
- **PDF** → c'est le cas le plus riche : on mesure d'abord la **densité de texte natif** avec `pypdf`.
  - Si elle est suffisante (≥ 40 caractères/page) → PDF **numérique** : on préfère **Docling** (extraction structurée, tableaux inclus) si disponible, sinon on garde le texte `pypdf` brut.
  - Si elle est trop faible → PDF **scanné** : on tente l'**OCR avec PaddleOCR** (français), avec bascule GPU→CPU automatique en cas d'erreur CUDA/cuDNN ; si PaddleOCR n'est pas installé, on retombe sur Docling, puis sur le texte `pypdf` (même pauvre), et en dernier recours on lève une erreur explicite invitant à installer les extras `ingest`/`ocr`.
- **Image seule** (JPEG/PNG/TIFF...) → OCR ; si le texte extrait est trop court, le fichier est traité comme un **"actif visuel"** (0 chunk, ce n'est pas une erreur — utile pour un plan/logo/photo de chantier joint en annexe).

Toute erreur de parsing fait basculer le document en `status="failed"` avec le message d'erreur tronqué à 4000 caractères dans `ingest_error`.

### 4.3 Découpage en chunks

`app/ingest/chunk.py` applique une règle simple et volontairement déterministe : des segments **parents** de 8000 caractères, subdivisés en fenêtres **enfants** de 1100 caractères avec 120 caractères de chevauchement. Les petits blocs (qui tiennent en une seule fenêtre) sont simplifiés pour ne garder qu'une ligne "parent", évitant des doublons inutiles. Il n'y a **pas de détection de titre au moment du découpage** : la structure hiérarchique (`heading_path`) vient uniquement de ce que le parseur a détecté en amont (styles Word, nom de feuille Excel, structure Docling).

### 4.4 Classification du type de section

Pour chaque chunk parent (sauf les annexes, jamais classifiées), `app/ingest/classify_section.py` tente d'abord une **heuristique par expression régulière** sur le titre/début de texte (repérer "règlement de consultation", "CCTP", "bordereau de prix"...). Si ça échoue, un **appel LLM** est tenté — mais **plafonné à 40 appels par document** pour éviter qu'un DAO de plusieurs centaines de pages ne bloque le worker pendant des heures (un cas réel à 739 chunks parents a motivé ce plafond).

### 4.5 Indexation vectorielle

Chaque chunk "embeddable" (enfant, ou parent si le bloc a été simplifié) est envoyé à **Ollama** pour obtenir son vecteur d'embedding (`nomic-embed-text`), puis **upserté dans Qdrant** avec toutes les métadonnées utiles au filtrage ultérieur (tenant, rôle du document, type de section, page, dossier...). C'est un **upsert séquentiel** (pas de traitement par lots) — un point d'optimisation possible si la volumétrie augmente. C'est seulement **après** cette étape que le document passe en `status="ready"` : c'est le signal que le RAG textuel est utilisable.

### 4.6 Extraction du graphe (job séparé, non bloquant)

Dès qu'un document est `ready`, un **second job** `extract_graph` est systématiquement enfilé (`app/graph/extract.py`). Il relit tous les chunks parents et demande à Ollama, pour chacun, d'en extraire des **entités** (types fermés : `ENTREPRISE`, `PROJET`, `CLIENT`, `CERTIFICATION`, `PERSONNE`, `EXIGENCE`, `LOT`, `SITE`) et des **relations** (`A_TRAVAILLE_SUR`, `PORTE`, `CONCERNE`, `SITUE_A`, `SATISFAITE_PAR`, `CONTIENT`). Chaque entité passe par une **cascade de résolution** (`app/graph/entity_match.py`) pour éviter les doublons entre documents :

1. correspondance exacte (nom normalisé),
2. distance de Levenshtein ≥ 85,
3. similarité "token-set" ≥ 80,
4. similarité cosinus d'embeddings ≥ 0,82,
5. sinon, création d'une nouvelle entité.

Ce processus est **résilient chunk par chunk** : l'échec d'un appel LLM sur un chunk ne fait pas échouer tout le document, il est simplement ignoré (log + passage au suivant). C'est pour cela que le graphe est qualifié de "phase non bloquante" — le RAG textuel fonctionne très bien sans lui.

### 4.7 Analyse de structure du dossier (à la demande, pas automatique)

Une fois un DAO `ready`, l'utilisateur peut déclencher `POST /dossiers/{id}/analyser`, qui lance le job `extract_dossier_structure` (`app/workflow/extract_structure.py`). Ce job produit trois choses, dans cet ordre, en repartant toujours de zéro (les anciennes exigences/plan sont supprimés avant régénération, pour éviter une duplication constatée en pratique) :

1. **Le plan (outline)** : extrait du texte du règlement de consultation (RC) si des mots-clés de structure y sont trouvés, sinon un **plan par défaut** à 5 sections (présentation, moyens humains, références, méthodologie, planning) est utilisé.
2. **Les exigences** : tous les chunks du DAO (sauf le BPU, purement chiffré) sont regroupés par lots de 14 000 caractères pour limiter le nombre d'appels LLM, puis dédupliqués par la même logique floue que les entités du graphe.
3. **La checklist administrative** : une liste standard de 6 pièces (KBIS, assurance décennale...) éventuellement enrichie/remplacée par ce que demande explicitement le RC, avec tentative de rapprochement automatique vers un document "patrimoine" déjà déposé.

### 4.8 Suppression

`DELETE /documents/{id}` déclenche une purge en cascade : Qdrant (par filtre `document_id`) → Neo4j (relations du document, puis nettoyage des entités du **tenant** devenues orphelines) → MinIO → Postgres. Ce n'est **pas transactionnel de bout en bout** : une panne à mi-parcours peut laisser un état partiellement nettoyé (point de vigilance identifié, pas corrigé à ce stade).

---

## 5. Le processus de génération — vue textuelle

*(diagramme complet : [`02_diagramme_sequence_generation.puml`](02_diagramme_sequence_generation.puml))*

Il existe en réalité **deux implémentations distinctes** du chat, héritées de deux versions du projet :

- **V1 (historique)** : `app/workflow/graph.py`, un vrai graphe **LangGraph**, mais très simple — un routage par **mots-clés** (pas de LLM), une seule recherche hybride, un seul appel LLM produisant du Markdown libre, sans validation. Utilisé par l'endpoint non-streamant `POST /conversations/{id}/messages`.
- **V2 (actuelle, agentique)** : `app/workflow/agentic_pipeline.py` + `app/services/chat_pipeline.py::stream_message`. C'est **le chemin réellement emprunté par l'interface** (endpoint streaming SSE). Ce n'est **pas** un graphe LangGraph : de simples fonctions asynchrones composées entre elles. C'est celui détaillé ci-dessous.

### 5.1 Réception et réécriture

Chaque message utilisateur est d'abord persisté (avec un `commit()`, pas un simple `flush()`, car les étapes suivantes écrivent des traces liées par clé étrangère depuis d'autres sessions DB). La question est ensuite **réécrite** par un appel LLM pour résoudre les références implicites ("et pour ce projet-là ?" → remplacé par le nom réel), avec un repli silencieux sur la question brute en cas d'échec.

### 5.2 Le Superviseur (routage + décomposition)

Un unique appel LLM (`app/workflow/nodes/superviseur.py`) doit renvoyer un JSON strict indiquant :

- une **intention** (`smalltalk`, `export`, `clarification_needed`, `hybrid_rag`, `run_section`),
- une liste de **sous-questions**, chacune associée à un ou plusieurs **experts** (`juridique`, `technique`, `financier`, `graphe`, `patrimoine`) et à un niveau de **complexité** (`simple`/`complexe`).

Le code **ne fait jamais confiance aveuglément** à cette sortie LLM : une série de garde-fous déterministes la corrige systématiquement après coup (limite à 4 sous-questions, cohérence entre intention et présence de sous-questions, injection d'une sous-question de secours si nécessaire, recalcul de l'indicateur "question composée"...). En cas d'échec total de l'appel LLM, un **repli** vers l'ancien routage par mots-clés (V1) est utilisé.

Si l'intention n'implique pas de recherche (`smalltalk`, `export`, `clarification_needed`), on s'arrête là : **aucune recherche documentaire n'est lancée**, ce qui évite de gaspiller du temps/calcul.

### 5.3 Recherche documentaire par "experts" (CRAG)

Pour chaque sous-question, chaque expert nommé est interrogé **en parallèle** (`asyncio.gather`). Deux stratégies selon la complexité :

- **Simple** : une seule passe hybride (Qdrant dense + Postgres full-text, fusionnées par **RRF**, puis "rerankées" — en réalité un score lexical), top-8, sans jugement de qualité.
- **Complexe** : une **boucle CRAG** (Corrective RAG) bornée à 3 itérations. Chaque itération récupère top-50, fusionne, puis **note la pertinence** (`app/rag/grading.py`) : un score au-dessus de 0,7 est jugé "correct" directement, en-dessous de 0,3 "incorrect" directement, et dans la zone grise, un **LLM-juge** tranche. Selon le verdict : on s'arrête (correct), on **élargit le périmètre de recherche** en retirant un filtre (ambigu), ou on **reformule la question** via un appel LLM (incorrect). Si les 3 tentatives échouent, l'expert **s'abstient explicitement** plutôt que d'halluciner une réponse.

L'**expert graphe** est un cas particulier : il fait extraire par le LLM les entités présentes dans la question, les résout dans Neo4j via la même cascade floue que l'ingestion, puis choisit parmi des **requêtes Cypher fixes** (jamais générées librement) selon le nombre d'entités résolues.

### 5.4 Agrégation

Tous les résultats des experts sont fusionnés en un seul **contexte** : blocs de texte numérotés avec leur source, liste de citations valides, traçabilité de "quel expert a fourni quelle citation", et liste des abstentions éventuelles (affichées à l'utilisateur pour rester honnête sur les limites de la réponse).

### 5.5 Branchement final selon l'intention

- **`smalltalk`** / **`clarification_needed`** : réponse canée ou question de clarification, pas de LLM supplémentaire.
- **`export`** : détecte le format demandé dans le texte, vérifie les droits d'écriture et la présence d'un dossier associé, déclenche le rendu (voir §5.8).
- **`hybrid_rag`** : c'est le seul cas avec un **vrai streaming token par token** — le prompt final inclut le contexte agrégé et la consigne explicite de citer les sources `[1]`, `[2]`... ou de dire que les extraits ne suffisent pas.
- **`run_section`** : génération d'une ou plusieurs sections de mémoire technique. Chaque section relance **sa propre recherche** (sauf la première, qui réutilise le contexte déjà calculé) — volontaire, pour éviter qu'une section n'hérite du contexte d'une autre. Comme la sortie doit être un **JSON strictement validé** avant d'être affichée, ce n'est pas un vrai streaming : le texte est envoyé par paquets une fois entièrement généré et validé.

### 5.6 Génération contrainte d'une section (`generate_section`)

C'est le cœur qualité du système (`app/workflow/nodes/generate_section.py`). Boucle bornée à **2 tentatives** :

1. Appel LLM en mode JSON avec un guide de rédaction selon l'"archétype" de la section (institutionnelle, factuelle, narrative, conformité).
2. Validation du **schéma Pydantic** (`SectionGeneree`).
3. Validation **métier déterministe** : chaque citation utilisée doit exister réellement dans le contexte fourni, aucun sous-titre au-delà du niveau 3, aucun "H1" littéral dans le texte, aucune image référençant un document inconnu.

Si une erreur est détectée à n'importe quelle étape, elle est **réinjectée dans le prompt** pour la tentative suivante. Si les 2 tentatives échouent, le système ne plante pas : il retourne une section **de repli minimaliste** signalant l'échec, avec une abstention explicite — un choix "échouer proprement" plutôt que de renvoyer une erreur technique brute à l'utilisateur.

### 5.7 Le cycle dossier + revue humaine (HITL)

Indépendamment du chat, une section peut être générée directement depuis la fiche du dossier (`POST /dossiers/{id}/sections/{key}/generate`, historique de conversation toujours vide — génération "pure dossier"). Le rédacteur revoit ensuite chaque section via `POST /dossiers/{id}/sections/{key}/review` avec trois actions possibles :

- **`approve`** : la section passe à `approved`, un court résumé est généré (pour être réutilisé comme contexte compact dans d'autres sections plus tard) — non bloquant si cet appel échoue.
- **`edit`** : le texte modifié par l'humain crée une **nouvelle version** de génération, directement marquée `approved`.
- **`regen`** : relance tout le cycle recherche + génération, en **injectant le commentaire de l'utilisateur** comme consigne complémentaire dans le prompt.

C'est le mécanisme central de contrôle qualité de la plateforme : **rien n'est jamais exporté sans qu'un humain ait explicitement validé le contenu**.

### 5.8 Export

L'export (DOCX/PDF/Markdown/texte) est un **pur rendu** : il relit la dernière version de génération de chaque section du plan et les assemble, sans jamais rappeler le LLM. Le fichier est déposé dans MinIO, une ligne `Export` est créée, et le dossier passe en `status="exported"`.

---

## 6. Points d'attention pour qui reprend le projet

Ces éléments ont été identifiés en traçant le code et méritent d'être connus avant d'intervenir :

- **Le reranker n'est pas un vrai cross-encoder** malgré la configuration (`rerank_model`) : c'est un score lexical + RRF (`app/rag/rerank.py`), à cause d'un conflit de dépendances cuDNN. Une vraie amélioration de qualité de retrieval passerait probablement par la résolution de ce conflit.
- **`app/workflow/nodes/validate.py` est du code mort** : jamais branché dans le graphe LangGraph V1, et le V2 ne l'utilise pas non plus (il a sa propre validation inline dans `generate_section.py`).
- **`app/services/chat_pipeline.py::_route_retrieve`** est également du code mort (jamais appelé).
- **Le flux V1** (LangGraph, endpoint non-streamant) reste dans le code et est potentiellement encore accessible, mais n'a ni CRAG, ni validation de citations, ni reranking réel — une divergence de qualité existe entre les deux endpoints de chat qu'il faut garder en tête.
- **Ré-ingestion d'un document déjà `ready`** : le code ne supprime pas explicitement les anciens points Qdrant avant d'upserter les nouveaux (seule la purge complète du document le fait) — un re-traitement pourrait laisser des vecteurs orphelins.
- **Échec de `extract_dossier_structure`** : `Dossier.status` n'a pas de valeur `"failed"` et aucun champ ne stocke l'erreur — un dossier bloqué en `"analyzing"` après un échec silencieux est difficile à diagnostiquer depuis l'interface seule (il faut regarder les logs du worker).
- **Purge de document** : les étapes (Qdrant → Neo4j → MinIO → Postgres) ne sont pas couvertes par une transaction globale ; une panne à mi-chemin laisse un état partiellement nettoyé.
- **Un seul modèle Ollama pour tout** : routage, extraction, jugement de pertinence, génération. C'est simple à opérer mais concentre tout le risque de latence/qualité sur un seul modèle — un axe d'évolution possible serait de spécialiser certains appels sur des modèles plus petits/rapides (classification, jugement) et de réserver un modèle plus capable à la génération finale.

---

## 7. Pour aller plus loin dans le code

- Point d'entrée API : `backend_ao/app/main.py`.
- Définition des jobs de fond : `backend_ao/app/worker_settings.py`.
- Toute la configuration (URLs, modèles, feature flags) : `backend_ao/app/config.py` (chargé depuis `.env`).
- Schéma des tables : `backend_ao/app/models/sql.py`.
- Schémas de validation LLM (JSON contraints) : `backend_ao/app/models/pydantic.py`.
- Lancement local : `docker compose up -d` (infra seule) ou `docker compose --profile dev up -d` (infra + API + worker + frontend), avec Ollama démarré séparément sur l'hôte (`ollama serve`, puis `ollama pull llama3` et `ollama pull nomic-embed-text`).



EXTRA :

Bonne question, et la réponse est plus simple que ce qu'on pourrait croire : Qdrant n'intervient jamais dans l'extraction du graphe. Tout part de Postgres, dans les deux sens (écriture ET lecture).

Écriture du graphe (à l'ingestion)
graph/extract.py::extract_graph lit le texte brut depuis Postgres, pas depuis Qdrant :


parents = await session.execute(
    select(ChunkRow).where(
        ChunkRow.document_id == doc.id,
        ChunkRow.parent_id.is_(None),   # uniquement les chunks "parent"
    )
)
Pour chaque chunk parent, le texte (tronqué à 3500 caractères, graph/extract.py:54) est envoyé tel quel à Ollama dans un prompt JSON contraint pour en extraire entités + relations. Le résultat est ensuite écrit dans Neo4j via MERGE, avec la relation taguée source_chunk_id = str(chunk.id) (graph/extract.py:236) — c'est-à-dire l'identifiant Postgres du chunk, stocké comme simple propriété texte côté Neo4j (les deux bases ne partagent pas de vraie clé étrangère, c'est juste une référence applicative).

Lecture du graphe (à une question de l'utilisateur)
Quand l'expert graphe (rag/graph_expert.py) répond à une question "relationnelle", il interroge Neo4j (requêtes Cypher fixes) et récupère des relations qui portent ce source_chunk_id. Pour donner une citation textuelle à l'utilisateur (pas juste "il existe un lien"), il refait un aller-retour vers Postgres :


await session.execute(select(ChunkRow).where(ChunkRow.id.in_(list(chunk_ids)[:25])))
C'est-à-dire qu'il va rechercher le texte original du (ou des) chunk(s) qui ont servi de preuve à cette relation — encore une fois, directement dans Postgres.

Et Qdrant dans tout ça ?
Qdrant ne stocke que les vecteurs d'embeddings des chunks (calculés à l'indexation, ingest/index_qdrant.py) pour la recherche sémantique dense — utilisée uniquement par les experts RAG "classiques" (rag/experts.py, recherche hybride dense+sparse) quand ils répondent à une question documentaire normale. Le pipeline de graphe ne l'interroge jamais, ni en écriture ni en lecture.

Il y a un seul autre endroit où un embedding intervient dans le graphe, mais ça n'a rien à voir avec Qdrant : dans graph/entity_match.py, le 4ᵉ étage de résolution floue calcule (via Ollama, à la volée) l'embedding du nom d'une entité (ex. "Dupont Constructions") pour le comparer aux noms d'entités déjà connues du tenant — c'est un usage ponctuel en mémoire, pour dédupliquer des entités, complètement indépendant des vecteurs de chunks stockés dans Qdrant.

En résumé : Postgres = la seule source de vérité textuelle, utilisée à la fois pour nourrir l'extraction du graphe et pour sourcer ses réponses. Qdrant = un index parallèle et indépendant, dédié uniquement à la recherche sémantique classique.


Excellente question — la réponse est plus nuancée que "oui/non", et il y a une vraie subtilité dans le code actuel.

Un seul worker (max_jobs=2) : concurrence, pas vraiment du parallélisme
ARQ tourne sur asyncio, dans un seul processus, un seul thread Python (donc un seul GIL). max_jobs=2 veut dire : 2 jobs peuvent être "en cours" en même temps, mais ils ne progressent réellement en même temps que pendant les points où le code fait un vrai await non-bloquant (ex. une requête asyncpg async). En dehors de ces points, un seul job exécute du code Python à un instant donné — l'autre est simplement en pause.

Et là, j'ai vérifié le code réel, et c'est révélateur :

workers/ingest.py appelle parse_file(), chunk_document(), embed_texts(), upsert_chunks() en appels synchrones directs, sans asyncio.to_thread (ingest.py:71,83,176,190). Donc pendant tout le parsing PDF, l'OCR PaddleOCR, ou l'appel HTTP bloquant vers Ollama pour les embeddings, la boucle événement du processus est totalement bloquée — le 2ᵉ "slot" ne sert à rien, l'autre job ne peut pas avancer d'un pouce.
graph/extract.py::extract_graph appelle _ollama_json(chunk.text) de la même façon, en synchrone direct, sans to_thread (extract.py:184) — alors que chaque appel peut durer jusqu'à 180 s (timeout configuré).
Seuls deux endroits font les choses correctement avec await asyncio.to_thread(...) : la classification de section dans ingest.py:129, et tous les appels LLM de workflow/extract_structure.py (outline/exigences/pièces).
Conclusion pour un seul worker : max_jobs=2 vous donne une concurrence réelle seulement pendant les I/O DB async et les quelques appels bien encapsulés en to_thread. Pendant les phases lourdes (OCR, parsing PDF, embeddings, extraction de graphe), c'est effectivement séquentiel malgré les "2 slots" configurés.

--scale worker=2 : ça, c'est du vrai parallélisme
Scaler le service lance un second processus OS complet (2ᵉ conteneur = 2ᵉ interpréteur Python, 2ᵉ GIL, 2ᵉ boucle asyncio, ses propres connexions à Postgres/Redis/Qdrant/Neo4j/MinIO/Ollama). Les deux processus peuvent tourner sur des cœurs CPU différents, en même temps, sans se bloquer l'un l'autre. ARQ garantit qu'un job pris dans la file Redis n'est traité que par un seul worker à la fois (pas de double traitement) — donc les deux processus se répartissent naturellement les jobs en attente.

Différence concrète : si le worker #1 est en train de bloquer son event loop sur de l'OCR (30 secondes, disons), avec max_jobs=2 seul, le job en attente dans le même processus ne bouge pas pendant ces 30 s. Avec --scale worker=2, le worker #2 (processus séparé) continue de traiter d'autres jobs sans aucun ralentissement pendant ce temps.

Le point de vigilance si vous scalez
Chaque worker ouvre son propre pool de connexions Postgres/Redis/Qdrant/Neo4j/MinIO — ça multiplie la charge sur ces services.
Si vous utilisez l'image OCR-GPU, deux workers se partageraient le même GPU de la machine hôte : risque de contention/saturation mémoire VRAM (PaddlePaddle GPU) si les deux font de l'OCR en même temps — un point à tester avant de scaler en prod avec GPU.
Le vrai levier le plus simple à court terme serait plutôt de corriger les appels synchrones manquants en asyncio.to_thread (ingest.py et graph/extract.py) : ça rendrait max_jobs=2 réellement utile avant même de scaler le nombre de conteneurs.

