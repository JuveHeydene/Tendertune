# Pipeline technique détaillé — qui fait quoi, quand, où c'est stocké

Ce document répond aux questions d'implémentation : LlamaIndex, LangGraph,
FastAPI, conversation, routage hybride/graphe, appels LLM, MinIO, historique.

---

## 1. Ce que sont (et ne sont pas) ces outils

Ce ne sont **pas** des bases de données. Ce sont des **bibliothèques Python**
(frameworks) que **ton** code importe.

| Nom | Nature | Question à laquelle il répond | Il ne fait PAS |
|-----|--------|-------------------------------|----------------|
| **LlamaIndex** | Bibliothèque RAG | Comment charger, chunker, embedder, chercher (hybride, graphe) ? | Il n'écoute pas le HTTP. Il n'orchestre pas un dossier d'offre sur 8 étapes. |
| **LangGraph** | Bibliothèque d'orchestration | Dans quel **ordre** exécuter les nœuds, avec quel **état**, quels retours, quel arrêt humain ? | Il ne parse pas un PDF. Il ne stocke pas les vecteurs. |
| **FastAPI** | Bibliothèque serveur HTTP | Comment le navigateur / le front **parle** au système (upload, question, statut, export) ? | Il ne fait ni RAG ni OCR. Il **délègue**. |
| **MinIO** | Serveur de fichiers (S3) | Où vivre les **PDF/DOCX bruts** ? | Il ne lit pas le contenu. Il sert des octets. |
| **PostgreSQL** | Base relationnelle | Métier, ACL, **textes de chunks**, **historique** chat/générations | Ce n'est pas un moteur vectoriel (sauf extension). |
| **Qdrant** | Base vectorielle | Chercher les voisins dense + sparse | Elle n'a pas l'historique utilisateur. |
| **Neo4j** | Base graphe | Entités et relations | Elle ne stocke pas le PDF. |
| **Redis** | File d'attente | « Ingest ce `file_id` » | Éphémère. |

```text
  L'utilisateur ne parle JAMAIS à LlamaIndex ni à LangGraph ni à MinIO.

  Navigateur  →  FastAPI  →  (soit un job Redis, soit LangGraph)
                                │
                    LlamaIndex = boîte à outils RAG à l'intérieur
                    des nœuds « ingest » et « retrieve »
```

**Analogie :** FastAPI = standardiste. LangGraph = chef de chantier (ordre des
tâches). LlamaIndex = les ouvriers spécialisés « documents / recherche ».
MinIO = l'entrepôt des cartons. Postgres = le registre (qui a dit quoi,
quelles exigences). Qdrant = le catalogue sémantique.

Tu **peux** faire du RAG sans LlamaIndex (Qdrant + sentence-transformers à la
main). LlamaIndex **accélère** : `VectorStoreIndex`, retrievers hybrides,
nœuds parent-child, connecteur Qdrant/Neo4j. LangGraph reste l'orchestrateur
du **processus métier** (pas LlamaIndex QueryEngine tout seul, trop « une
question → une réponse »).

---

## 2. Deux horloges (la confusion n°1)

Il y a **deux pipelines distincts**. Ils ne tournent pas au même moment.

```text
  HORLOGE A — INGESTION (avant / pendant l'upload, PAS au moment de la question)
  ---------------------------------------------------------------------------
  User clique « Envoyer le PDF »
    → FastAPI reçoit le fichier
    → FastAPI POUSSE le binaire dans MinIO
    → FastAPI insère une ligne Postgres documents(status=pending)
    → FastAPI pousse un job Redis : ingest(document_id)
    → FastAPI répond tout de suite : { document_id, status: "en_cours" }

  Un WORKER (processus à part, ARQ) prend le job :
    → télécharge depuis MinIO
    → Docling ou Paddle
    → chunk
    → embed (BGE-M3)
    → écrit Qdrant + Postgres (texte des chunks)
    → (plus tard) extraction graphe → Neo4j
    → status=ready

  Tant que status != ready, le chat refuse « génère la section Références ».


  HORLOGE B — QUESTION / GÉNÉRATION (l'utilisateur tape)
  ------------------------------------------------------
  On NE relit PAS le PDF dans MinIO.
  On NE ré-embedde PAS.
  On cherche dans Qdrant / Neo4j / Postgres (déjà prêts).
  On appelle le LLM seulement pour : router (option), extraire, rédiger.
```

**Les embeddings sont faits à l'ingestion, une fois.** La génération
réutilise l'index. Relire MinIO à chaque question = lent, cher, absurde.

Exception : un **nouveau** DAO que l'utilisateur vient d'uploader pour
**cette** consultation. Il passe d'abord par l'horloge A (quelques minutes),
puis l'horloge B peut extraire les exigences.

---

## 3. Où est stocké quoi

| Quoi | Où | Pourquoi |
|------|-----|----------|
| PDF / DOCX / XLSX **originaux** | **MinIO** (`bucket/tenant/doc_id/fichier.pdf`) | Gros binaires, versionnables, pas dans Postgres |
| Texte extrait, markdown, chunks **texte** | **PostgreSQL** table `chunks` | Citations, audit, réafficher la source sans Qdrant |
| Vecteurs dense + sparse | **Qdrant** (payload = `chunk_id`) | Recherche rapide |
| Entités / relations | **Neo4j** (`source_chunk_id`) | Liens métier |
| Fiches (certifs, montants, projets) | **PostgreSQL** | Requête exacte |
| Historique conversation (messages user/assistant) | **PostgreSQL** `messages` | Relire le fil, rewrite de « ça » |
| Historique de **génération** (chaque section, contexte envoyé, citations, version) | **PostgreSQL** `generations` | Audit, « pourquoi cette phrase », régénérer |
| Décisions humaines (approuvé / corrigé) | **PostgreSQL** `reviews` | HITL |
| État du workflow en cours (quelle étape, brouillons) | **PostgreSQL** + checkpoint LangGraph | Reprendre après crash / après revue |
| Job « en train d'ingérer » | **Redis** | Queue |

Le **texte écrit par le LLM** n'est **pas** dans MinIO et **pas** dans Qdrant.
Il va dans `generations.content` (et éventuellement un export DOCX aussi
poussé dans MinIO : `exports/dossier_v3.docx`).

Qdrant ne garde le texte que comme **payload optionnel** ; la **source de
vérité** du texte de chunk = Postgres. Comme ça, une citation `[3]` = `SELECT
text, page FROM chunks WHERE id=…`.

---

## 4. FastAPI : la porte d'entrée

Le front n'importe ni LangGraph ni LlamaIndex. Il fait des HTTP.

```text
POST   /documents                 upload multipart → MinIO + job ingest
GET    /documents/{id}            status : pending | processing | ready | failed
POST   /conversations             crée un fil (conversation_id)
POST   /conversations/{id}/messages
                                  body: { "text": "…" }
                                  → LangGraph (ou un nœud router)
GET    /conversations/{id}        historique messages
POST   /dossiers/{id}/run         lance le workflow « constituer l'offre »
POST   /dossiers/{id}/sections/{sid}/review
                                  { action: approve|edit|regen, text? }
GET    /dossiers/{id}/export      DOCX/PDF (lu depuis MinIO après génération)
```

Chaque handler FastAPI :

1. authentifie (JWT) → `tenant_id`, `user_id` ;
2. valide le body (Pydantic) ;
3. **soit** enqueue un job (upload) ;
4. **soit** `graph.ainvoke({...})` / `graph.astream(...)` (question, run dossier) ;
5. renvoie du JSON. Le streaming de tokens = SSE / WebSocket si tu veux
   voir la section s'écrire.

FastAPI **n'appelle pas** Docling dans la requête HTTP (timeout). Il
**déclenche** le worker.

---

## 5. Horloge A — Upload et ingestion (le plus détaillé)

### Étape A0 — L'utilisateur choisit des fichiers

Front : « Ajouter au patrimoine » (anciens dossiers) **ou** « DAO de cette
consultation ». Le `doc_role` change : `patrimoine` vs `dao_courant`.

### Étape A1 — FastAPI reçoit

```python
# pseudo
file = request.file
sha = sha256(file)
if exists_in_postgres(sha, tenant):
    return deja_indexe  # pas de doublon

object_key = f"{tenant_id}/{doc_id}/{filename}"
minio.put("ao-raw", object_key, file)          # octets bruts

db.documents.insert(
    id=doc_id, tenant_id, object_key, sha,
    doc_role, doc_type_hint, status="pending"
)

redis.enqueue("ingest", document_id=doc_id)    # ARQ
return {document_id, status: "pending"}
```

**Personne ne parse encore.** L'utilisateur peut uploader 15 PDF d'affilée.

### Étape A2 — Worker ARQ : `ingest(document_id)`

Processus **séparé** (`arq worker`). Plusieurs workers = plusieurs PDF en
parallèle.

```python
async def ingest(ctx, document_id):
    doc = db.documents.get(document_id)
    doc.status = "processing"

    # 1. Récupérer depuis MinIO
    raw = minio.get("ao-raw", doc.object_key)   # bytes
    tmp = write_temp(raw)

    # 2. Router digital vs scan
    if is_spreadsheet(tmp):
        rows = openpyxl_load(tmp)
        db.upsert_structured(rows)              # pas Qdrant prose
        doc.status = "ready"
        return

    if pdf_text_density(tmp) >= SEUIL:
        parsed = docling.convert(tmp)           # markdown + tables + headings
        ocr_used = False
    else:
        parsed = paddle_pp_structure(tmp)       # pages images
        ocr_used = True

    # 3. Contrat unique
    ingested = to_document_ingested(parsed, ocr_used)

    # 4. LlamaIndex : découpe en nœuds (chunks)
    nodes = structure_splitter(ingested)        # voir A3

    # 5. Embed BGE-M3 (batch GPU)
    embeddings = embed_model.get_text_embedding_batch(
        [n.get_content() for n in nodes]
    )

    # 6. Persister
    for n, vec in zip(nodes, embeddings):
        db.chunks.insert(id=n.id, document_id, text=n.text,
                         parent_id, page, heading_path, …)
        qdrant.upsert(id=n.id, vector_dense=vec.dense,
                      vector_sparse=vec.sparse,
                      payload={chunk_id, tenant_id, doc_type, page})

    # 7. Graphe (phase 1.5, job séparé si trop long)
    # extract_entities_llm(parents) → neo4j.merge(...)

    doc.status = "ready"
```

**C'est ici** que « on récupère depuis MinIO avant de traiter ». Pas au chat.

### Étape A3 — Chunking côté LlamaIndex (implémentation)

LlamaIndex appelle ça des **Nodes**, pas des chunks. Même chose.

```python
# 1) un Markdown NodeParser qui respecte # / ## / Article X
# 2) HierarchicalNodeParser : child 256-400 tokens, parent = section
# 3) metadata : tenant_id, doc_role, heading_path, page
# 4) texte embeddé = f"[{doc_type}] [{heading_path}] [p.{page}]\n{body}"
```

Index LlamaIndex branché sur Qdrant :

```python
vector_store = QdrantVectorStore(client, collection="ao_chunks",
                                 enable_hybrid=True)
index = VectorStoreIndex.from_vector_store(vector_store, embed_model=bge_m3)
```

À l'ingestion on fait `index.insert_nodes(nodes)`. À la question on ne
réinsère rien : `index.as_retriever(...)`.

### Étape A4 — L'utilisateur voit « Prêt »

`GET /documents/{id}` → `ready`. Le patrimoine a **grossi**. Aucune
génération n'a encore eu lieu.

---

## 6. Horloge B — Conversation : que faire de la question ?

### 6.1 Ce que le user tape n'est pas toujours « un RAG »

Exemples :

| Message | Décision |
|---------|----------|
| « Bonjour » | Pas de retrieval. Réponse courte. |
| « Quelle est la pénalité Dupont ? » | **RAG hybride** (fait local, texte) |
| « Quelles certifs couvrent l'exigence 4.2 ? » | **Graphe** (+ éventuellement hybride pour la preuve textuelle) |
| « Génère la section Moyens matériels » | **Workflow** complet (nœuds 3–7), pas un chat one-shot |
| « Compare nos 3 dernières écoles en zone urbaine » | Hybride d'abord ; graphe si les liens projet–lieu–montant sont dans Neo4j |

### 6.2 Qui décide : pas un agent libre (V1)

Un **nœud Router** LangGraph, déterministe + petit LLM borné.

```text
  POST /messages { text }
       → FastAPI charge conversation + 10 derniers messages (Postgres)
       → graph.invoke({
             messages, user_id, tenant_id, dossier_id?
         })
```

Nœud `route` :

1. Règles rapides (regex / intentions) : `génère|rédige section` →
   `WORKFLOW_SECTION` ; `bonjour` → `CHAT_VIDE`.
2. Sinon un **appel LLM court** (classification JSON) :

```json
{ "intent": "hybrid_rag" | "graph_rag" | "hybrid_and_graph" | "smalltalk" | "run_section",
  "need_rewrite": true }
```

3. Arete LangGraph vers le nœud correspondant.

Ce LLM de route **ne récupère aucun document**. Il choisit un chemin.
1 appel, schéma Pydantic, température 0.

### 6.3 Nœud `rewrite` (si deixis)

LLM : historique + message → `query` propre.
« et la pénalité ? » + contexte Dupont → « clause de pénalité contrat Dupont ».
Stocké dans `messages.meta.query_rewrite`.

### 6.4 Nœud `retrieve_hybrid` (LlamaIndex)

```python
retriever = index.as_retriever(
    similarity_top_k=50,
    vector_store_query_mode="hybrid",   # dense + sparse, RRF côté Qdrant
    filters=MetadataFilters(tenant_id, acl, …),
)
nodes = retriever.retrieve(query)
reranked = bge_reranker.postprocess(query, nodes, top_n=8)
parents = fetch_parents(reranked)       # Postgres parent_id
```

**Toujours pas de rédaction.** On a une liste d'`ExtraitCite`.

### 6.5 Nœud `retrieve_graph` (si le router l'a choisi)

```python
entities = llm_extract_entities(query)   # petit appel, ou simple matching
records = neo4j.run("""
  MATCH (e:Exigence)-[:SATISFAITE_PAR]->(p)
  WHERE e.id IN $ids
  RETURN p, e
""")
# + textes des chunks source (Postgres)
```

### 6.6 Nœud `build_context`

Concatène extraits numérotés `[1]…`, tuples SQL, sous-graphe. Plafond tokens.
Consigne : « uniquement le contexte, cite, abstention sinon ».

### 6.7 Nœud `generate` — **c'est ICI qu'on appelle le LLM rédacteur**

**Un seul gros appel** (ou un par section si workflow dossier) :

```text
Entrée : consigne + contexte [1]..[k] + question/canevas de section
Sortie : SectionGeneree JSON (texte + citations + exigences couvertes)
```

Le LLM **ne va pas** chercher tout seul dans MinIO. Il ne voit **que** le
contexte que tu as collé. « Récupérer pour générer » = **tes nœuds retrieve**,
pas le LLM.

### 6.8 Persistance après génération

```python
db.messages.insert(conversation_id, role="assistant", content=section.text)
db.generations.insert(
    dossier_id, section_key, content, citations, context_snapshot,
    model, tokens_in, tokens_out, created_at
)
```

`context_snapshot` = les extraits réellement envoyés (audit).  
L'historique de **chat** = `messages`.  
L'historique de **production de dossier** = `generations` + `reviews`.

### 6.9 Validation + HITL

Validateur déterministe (schéma, citations existantes).  
Si section d'offre : LangGraph `interrupt` → l'humain `POST …/review`.  
Approve → état suivant. Regen → retour `build_context` / `generate`.

---

## 7. Séquence complète « upload puis question »

```text
t=0   User upload 8 anciens dossiers + 1 DAO
      FastAPI → 9 objets MinIO, 9 jobs Redis, HTTP 200 immédiat

t=0–3 min  Workers :
      GET MinIO → Docling/Paddle → chunks Postgres → vecteurs Qdrant
      (DAO courant taggé dao_courant)

t=3   GET /documents → tous ready
      User : « Quelles sont les exigences éliminatoires ? »

t=3+  FastAPI POST /messages
      LangGraph route → hybrid (et/ou extraction exigences sur dao_courant)
      LlamaIndex retrieve Qdrant
      LLM génère une liste structurée
      INSERT messages + generations

t=4   User : « Génère la section Références »
      Router → WORKFLOW_SECTION
      retrieve hybrid (+ graph projets) → context → LLM section
      interrupt revue humaine
      approve → generations.status=approved

t=5   Export : moteur documentaire assemble les sections approved
      écrit DOCX → MinIO ao-exports/… → URL signée
```

MinIO n'est **rouvert** à t=5 que pour **écrire** l'export, pas pour
ré-OCR le patrimoine.

---

## 8. Schéma des tables (minimum)

```text
documents(id, tenant_id, object_key, sha, doc_role, status, ocr_used)
chunks(id, document_id, parent_id, text, heading_path, page, token_count)
conversations(id, tenant_id, user_id, dossier_id?)
messages(id, conversation_id, role, content, query_rewrite, created_at)
dossiers(id, tenant_id, dao_document_id, status)
exigences(id, dossier_id, libelle, type, obligatoire, page_source, statut)
generations(id, dossier_id, section_key, content, citations jsonb,
            context_snapshot jsonb, model, version)
reviews(id, generation_id, user_id, action, comment)
```

Qdrant point.id = `chunks.id`.  
Neo4j nœud propriété `chunk_id`.

---

## 9. Qui appelle le LLM, combien de fois (V1)

| Moment | Appel LLM | But |
|--------|-----------|-----|
| Ingestion (option 1.5) | 1 × par **parent** | Extraire entités → Neo4j |
| Ingestion (pas V1) | Contextual Retrieval | Préfixer un chunk |
| Chat | 0 ou 1 | Router (classification) |
| Chat | 0 ou 1 | Rewrite |
| Chat / section | **1** | Rédiger avec le contexte déjà récupéré |
| DAO | 1 × N fenêtres | Extraire exigences (schéma) |
| Jamais | LLM « va chercher dans MinIO » | N'existe pas |

Retrieval = **code** (LlamaIndex + Qdrant/Neo4j). Génération = **LLM**.

---

## 10. Fichiers projet (découpage concret)

```text
app/
  api/                 # FastAPI routers
  workers/ingest.py    # ARQ : MinIO → parse → LlamaIndex insert
  rag/
    llama_index_setup.py
    hybrid_retriever.py
    rerank.py
  graph/
    extract.py
    cypher.py
  workflow/
    graph.py           # LangGraph StateGraph
    nodes/route.py
    nodes/retrieve.py
    nodes/generate.py
    nodes/validate.py
  models/              # Pydantic + SQLAlchemy
  services/minio_client.py
```

LlamaIndex **vit** dans `rag/` et `workers/ingest.py`.  
LangGraph **vit** dans `workflow/`.  
FastAPI **importe** les deux, ne les remplace pas.

---

## 11. Réponses courtes

**LlamaIndex = RAG, LangGraph = orchestration ?**  
Oui. Deux bibliothèques Python complémentaires, pas concurrentes.

**FastAPI ?**  
Le serveur HTTP. Upload, questions, statuts, revue, export. Il déclenche
workers et `graph.invoke`.

**Qui décide hybride vs graphe ?**  
Nœud `route` (règles + petit LLM classifieur). Pas un agent qui improvise.

**Quand le LLM « récupère tout » pour générer ?**  
Jamais. Tes retrievers récupèrent. Le LLM **rédige** ensuite sur le
contexte collé.

**Où sont les textes générés / l'historique ?**  
Postgres : `messages` (chat), `generations` (sections + snapshot du
contexte), `reviews`. Export final aussi copié dans MinIO.

**MinIO : qui tire les PDF, avant ou pendant la question ?**  
Le **worker d'ingestion**, **après l'upload**, **avant** les questions.
Le chat ne touche plus à MinIO (sauf télécharger un export).

**Upload pour « voluminer » la génération ?**  
Oui : chaque fichier prêt **augmente** Qdrant/Postgres/Neo4j. La prochaine
section d'offre puise dans un patrimoine plus riche, sans ré-uploader.

---

## 12. Génération du dossier **structuré par titres**

Le LLM **ne rédige pas** un roman de 40 pages en un appel. Tu **imposes**
le plan (titres), il **remplit** une case à la fois. Le DOCX final est
assemblé **par ton code** (`python-docx`), pas par le modèle qui « invente
du Word ».

### 12.1 Trois objets distincts

| Objet | Qui le crée | Rôle |
|-------|-------------|------|
| **Canevas** (`outline`) | Code + extraction du RC/DAO, ou modèle type BTP | Liste **figée** de titres (H1, H2, H3) |
| **Section générée** | LLM, **un titre à la fois** | Paragraphes + listes **sous** ce titre |
| **Document Word/PDF** | Moteur documentaire | Concatène les sections **approuvées**, applique les styles Titre 1 / Titre 2 |

Le titre **n'est pas une suggestion**. C'est une clé : `moyens_materiels`.
Le LLM n'a pas le droit de le renommer en « Nos engins superbes ».

### 12.2 D'où vient le plan (canevas)

**Ordre de priorité :**

1. Le **règlement de consultation / CCAP** dit souvent « le mémoire
   technique comprendra : … » → nœud *extraction d'exigences* produit
   aussi une `outline` (titres demandés).
2. Sinon un **canevas métier par défaut** (paramétrable), typique BTP :

```text
1. Présentation de l'entreprise          (H1)
2. Compréhension de la mission           (H1)
3. Moyens humains                        (H1)
   3.1 Organigramme du chantier          (H2)
   3.2 CV des clés                       (H2)
4. Moyens matériels                      (H1)
5. Références                            (H1)
6. Méthodologie d'exécution              (H1)
   6.1 Installation de chantier          (H2)
   6.2 Phasage                           (H2)
7. Qualité, hygiène, sécurité, environnement (H1)
8. Planning et délais                    (H1)
```

Stocké en Postgres `outline_items(dossier_id, key, heading_level, title,
sort_order, status)`.

`status` : `todo` → `generated` → `approved` | `rejected`.

### 12.3 Schéma Pydantic (le LLM remplit ÇA, rien d'autre)

```python
class Bloc(BaseModel):
    type: Literal["paragraphe", "liste", "tableau_md", "sous_titre"]
    heading_level: int | None = None   # seulement si type=sous_titre (H3 max)
    texte: str                         # markdown simple, pas de H1 inventé

class SectionGeneree(BaseModel):
    section_key: str                   # copie de l'item, ex. "moyens_materiels"
    titre: str                         # COPIE du canevas, pas inventé
    blocs: list[Bloc]
    citations: list[str]               # ids [1], [2]
    exigences_couvertes: list[str]
    abstentions: list[str]             # « pas de référence > 20 M€ dans le patrimoine »
```

**Contrainte dans le prompt :**

```text
Le titre de cette section est FIXE : « 4. Moyens matériels ».
Tu n'écris PAS de Titre 1 ni de Titre 2.
Tu n'écris QUE le corps (paragraphes, listes, éventuellement un H3
« Parc de grues » si utile).
Chaque fait chiffré porte une citation [n] présente dans CONTEXTE.
Si une info manque : remplis abstentions, n'invente pas.
```

Sortie **JSON forcé** (`with_structured_output(SectionGeneree)`). Si le
modèle sort un `# Titre` en trop, le validateur **le refuse** (regex
`^# ` dans les blocs) → retry borné ou HITL.

### 12.4 Boucle LangGraph (une section = un tour)

```text
  outline = [item1, item2, …]          # déjà en base

  pour chaque item où status=todo :
      1. query = titre + exigences liées à cette rubrique
      2. retrieve hybride (+ graphe si références / certifs)
      3. build_context
      4. LLM → SectionGeneree JSON
      5. validateur (schéma, pas de H1 pirate, citations existantes)
      6. interrupt HITL  → humain voit titre + corps + sources
      7. approve → status=approved, INSERT generations
         edit    → on stocke le texte humain, status=approved
         regen   → retour 2. avec consigne extra
  fin

  assemble_docx(items approved dans sort_order)
  → MinIO exports/
```

L'utilisateur peut aussi ne lancer **qu'une** case : « Génère la section
Références » → un seul item, pas tout le plan.

### 12.5 Du JSON au Word (titres réels)

Le LLM a produit du **contenu**. Les titres Word sont **posés par le code** :

```python
from docx import Document
from docx.enum.style import WD_STYLE_TYPE

doc = Document(template_entreprise)          # logo, marges, styles ENSPY/BTP
for item in outline.order:
    gen = db.generations.latest_approved(item.key)
    # Titre = celui du CANEVAS, style Word officiel
    if item.heading_level == 1:
        doc.add_heading(item.title, level=1)   # "4. Moyens matériels"
    elif item.heading_level == 2:
        doc.add_heading(item.title, level=2)
    for bloc in gen.blocs:
        if bloc.type == "sous_titre":
            doc.add_heading(bloc.texte, level=3)
        elif bloc.type == "paragraphe":
            doc.add_paragraph(bloc.texte)
        elif bloc.type == "liste":
            for ligne in bloc.texte.split("\n"):
                doc.add_paragraph(ligne, style="List Bullet")
doc.save(...)
minio.put("ao-exports", key, ...)
```

Résultat : le plan est **stable**, les styles Titre 1/2 viennent du
**modèle Word** de l'entreprise, pas d'un Markdown plus ou moins propre.

### 12.6 Ce qu'on ne fait pas

- Un prompt « rédige tout le mémoire » → titres incohérents, lost in the
  middle, impossible à relire.
- Laisser le LLM choisir la numérotation (`4.` vs `IV.`) → le canevas
  décide.
- Coller le RAG dans le Word sans titres : ce n'est pas un dossier
  d'offre, c'est un chat exporté.


Excellente question ! Je vais t'expliquer en détail le processus de chunking parent/enfant et le flux de données.

---

## 1. Flux global des données avant le chunking

```
Fichier (MinIO) 
    ↓
parse_file() → ParsedDocument (pages avec texte)
    ↓
chunk_document() → liste de ChunkDraft
    ↓
Stockage Postgres + Qdrant
```

**Avant le chunking :**
- Le fichier est téléchargé depuis MinIO dans un fichier temporaire
- `parse_file()` extrait le texte et retourne un `ParsedDocument` qui contient :
  - Une liste de `ParsedPage` (chaque page avec son texte, son numéro, et son titre)
  - Des métadonnées (OCR utilisé, confiance, etc.)

**Le chunking commence APRÈS le parsing**, quand on a tout le texte structuré par pages.

---

## 2. Structure du chunking : Parent/Enfant

La logique est dans `chunk_document()` et `_chunk_block()`.

### Pour chaque page/bloc de texte :

```python
def _chunk_block(block: ParsedPage) -> list[ChunkDraft]:
    text = (block.text or "").strip()
    if not text:
        return []
    
    # 1. CRÉATION DU PARENT
    parent_id = uuid.uuid4()
    parent = ChunkDraft(
        id=parent_id,
        parent_id=None,           # ← C'est un parent
        text=text[:8000],         # Texte complet de la section (limité à 8000 caractères)
        heading_path=block.heading_path,
        page=block.page,
        token_count=max(1, len(text) // 4),
        extra={"kind": "parent"},
    )
    
    # 2. DÉCOUPAGE EN ENFANTS (fenêtres)
    pieces = _windows(text)
    
    # 3. SI LE TEXTE EST PETIT → retourne juste le parent
    if len(pieces) == 1 and len(text) <= CHILD_SIZE:
        return [parent]
    
    # 4. SINON → crée des enfants
    children = []
    for piece in pieces:
        children.append(
            ChunkDraft(
                id=uuid.uuid4(),
                parent_id=parent_id,    # ← Référence au parent
                text=piece,
                heading_path=block.heading_path,
                page=block.page,
                token_count=max(1, len(piece) // 4),
                extra={"kind": "child"},
            )
        )
    
    # 5. RETOURNE PARENT + ENFANTS
    return [parent, *children]
```

### Résultat : Une structure hiérarchique

```
Document
  ├── Page 1 (ou section)
  │   ├── Parent chunk (texte complet de la page, 8000 caractères max)
  │   │   ├── Enfant 1 (fenêtre 1 : 0-1100 caractères)
  │   │   ├── Enfant 2 (fenêtre 2 : 980-2080 caractères)  ← chevauchement
  │   │   └── Enfant 3 (fenêtre 3 : 1960-...)
  │   └── ...
  ├── Page 2
  │   └── Parent + enfants
  └── ...
```

---

## 3. Le découpage en fenêtres (`_windows`)

```python
CHILD_SIZE = 1100      # Taille d'une fenêtre enfant
CHILD_OVERLAP = 120    # Chevauchement entre fenêtres

def _windows(text: str) -> list[str]:
    if len(text) <= CHILD_SIZE:
        return [text]
    
    parts = []
    start = 0
    while start < len(text):
        end = min(len(text), start + CHILD_SIZE)
        parts.append(text[start:end])
        if end == len(text):
            break
        start = end - CHILD_OVERLAP   # ← On recule de 120 caractères
    return parts
```

### Exemple avec un texte de 3000 caractères :

```
Fenêtre 1 : caractères 0 à 1100
Fenêtre 2 : caractères 980 à 2080   (chevauchement : 980-1100)
Fenêtre 3 : caractères 1960 à 3000  (chevauchement : 1960-2080)
```

**Pourquoi un chevauchement ?**
- Éviter de couper des phrases ou des concepts importants à la frontière
- Assurer que si une question porte sur un sujet à cheval entre deux fenêtres, au moins une fenêtre contient l'information complète
- Améliorer la qualité de la récupération (retrieval)

---

## 4. Pourquoi cette structure Parent/Enfant ?

| Type | Rôle | Utilisation |
|------|------|-------------|
| **Parent** | Contient le texte complet d'une page/section (jusqu'à 8000 caractères) | Utilisé pour le contexte global, la synthèse, ou quand on a besoin de voir l'ensemble |
| **Enfant** | Fenêtre de 1100 caractères avec chevauchement | Utilisé pour la recherche sémantique (Qdrant) car les embeddings sont plus précis sur des textes courts et cohérents |

### Dans l'indexation Qdrant :

```python
# Seuls les enfants (ou tous les chunks si pas d'enfants) sont vectorisés
embeddable = [d for d in drafts if d.parent_id is not None] or drafts
vectors = embed_texts([_embed_text(d, doc.doc_type) for d in embeddable])
```

- **Les enfants** sont indexés dans Qdrant pour la recherche
- **Le parent** n'est pas vectorisé (ou seulement si pas d'enfants)
- Quand un enfant est retrouvé par similarité, on peut remonter au parent pour avoir le contexte complet

---

## 5. Cas particuliers

### Texte très court (< 1100 caractères) :
```python
if len(pieces) == 1 and len(text) <= CHILD_SIZE:
    return [parent]  # ← Seulement le parent, pas d'enfants
```
**Raison** : Inutile de dupliquer un petit texte.

### Texte de 1500 caractères :
- 1 parent (1500 caractères)
- 1 enfant (fenêtre 0-1100)
- 1 enfant (fenêtre 980-1500) → 2 enfants avec chevauchement

### Texte de 5000 caractères :
- 1 parent (5000 caractères)
- 5 enfants (0-1100, 980-2080, 1960-3060, 2940-4040, 3920-5000)

---

## 6. Stockage final

### Dans Postgres (`ChunkRow`) :
- Tous les chunks (parents ET enfants) sont stockés
- La colonne `parent_id` permet de reconstruire la hiérarchie
- On peut requêter tous les enfants d'un parent donné

### Dans Qdrant (vector store) :
- Seulement les **enfants** sont vectorisés
- Chaque point Qdrant a un `document_id`, un `parent_id`, et le texte
- La recherche trouve l'enfant le plus pertinent, puis on peut aller chercher le parent en base

---

## 7. Résumé du flux

```
1. parse_file() 
   → ParsedDocument (pages structurées)

2. chunk_document()
   → Pour chaque page :
      a. Créer un parent (texte complet, 8000 max)
      b. Découper en fenêtres de 1100 caractères avec chevauchement de 120
      c. Créer un enfant par fenêtre
      d. Retourner [parent, enfant1, enfant2, ...]

3. Stockage Postgres :
   → Tous les chunks (parents + enfants)

4. Embeddings + Qdrant :
   → Seulement les enfants (ou tous si pas d'enfants)
   → Pour la recherche sémantique

5. Enqueue extract_graph :
   → Job Neo4j pour construire le graphe de connaissances
```

---

# 

Super question ! Je vais t'expliquer en détail l'implémentation du graphe Neo4j, analyser sa qualité, et te parler du fuzzy matching.

---

## 1. Architecture globale du job `extract_graph`

```
Postgres (chunks parents)
    ↓
Ollama (extraction entités/relations)
    ↓
Neo4j (MERGE des entités et relations)
    ↓
Document marqué graph_extracted = True
```

---

## 2. Déroulement détaillé

### Étape 1 : Récupération des parents depuis Postgres

```python
parents = (
    await session.execute(
        select(ChunkRow).where(
            ChunkRow.document_id == doc.id,
            ChunkRow.parent_id.is_(None),  # ← Seulement les parents
        )
    )
).scalars().all()

to_do = parents[:12]  # ← Limite à 12 chunks maximum
```

**Pourquoi seulement les parents ?**
- Les parents contiennent le texte complet des sections (jusqu'à 8000 caractères)
- Les enfants sont des fragments pour la recherche sémantique
- Pour l'extraction de graphe, on veut le **contexte global**, pas des fragments

**Pourquoi limite à 12 ?**
- Éviter de surcharger Ollama (temps d'exécution, coût)
- Un document de 100 pages pourrait avoir 100 parents → on ne traite que les 12 premiers
- ⚠️ **Limitation** : Les dernières sections ne seront pas dans le graphe

---

### Étape 2 : Appel à Ollama pour l'extraction

```python
def _ollama_json(text: str) -> dict:
    prompt = (
        PROMPT.format(types=", ".join(ENTITY_TYPES), rels=", ".join(REL_TYPES))
        + text[:3500]  # ← Troncature à 3500 caractères
    )
    payload = json.dumps({
        "model": s.llm_model,
        "prompt": prompt,
        "stream": False,
        "format": "json"  # ← Force Ollama à répondre en JSON
    }).encode()
    # ... requête HTTP à Ollama
    return json.loads(raw.get("response") or "{}")
```

**Le prompt :**
```
Tu extraies des entités BTP depuis le texte.
Types d'entités autorisés uniquement : ENTREPRISE, PROJET, CLIENT, ...
Types de relations autorisés uniquement : A_TRAVAILLE_SUR, PORTE, CONCERNE, ...
Réponds UNIQUEMENT en JSON :
{"entities":[{"type":"PROJET","name":"..."}],"relations":[{"type":"CONCERNE","from":"...","to":"..."}]}
Pas d'entité si rien de clair. Texte : [contenu du chunk]
```

**Format de réponse attendu :**
```json
{
  "entities": [
    {"type": "ENTREPRISE", "name": "BTP Construction"},
    {"type": "PROJET", "name": "Tour Eiffel"}
  ],
  "relations": [
    {"type": "A_TRAVAILLE_SUR", "from": "BTP Construction", "to": "Tour Eiffel"}
  ]
}
```

---

### Étape 3 : Normalisation des noms (clé unique)

```python
def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())
```

**Exemple :**
- "BTP   Construction" → "btp construction"
- "Tour Eiffel" → "tour eiffel"

**Pourquoi normaliser ?**
- Éviter les doublons : "BTP Construction" et "btp construction" sont considérés comme identiques
- Permet de faire des MERGE correctement

---

### Étape 4 : Création de la clé unique pour Neo4j

```python
key = f"{doc.tenant_id}:{etype}:{_norm(name)}"
```

**Exemple :**
- `tenant_id = "tenant_123"`
- `etype = "ENTREPRISE"`
- `name = "BTP Construction"`
- → `key = "tenant_123:ENTREPRISE:btp construction"`

**Pourquoi cette clé ?**
- Unicité : Une entreprise peut apparaître dans plusieurs documents du même tenant
- Isolation : Les entités d'un tenant ne polluent pas celles d'un autre
- Normalisation : Les variations de casse/espaces sont résolues

---

### Étape 5 : MERGE dans Neo4j

**Création des entités :**
```cypher
MERGE (e:Entity {key: $key})
SET e.name = $name, e.type = $type, e.tenant_id = $tenant_id
```

**Création des relations :**
```cypher
MATCH (a:Entity {key: $src}), (b:Entity {key: $dst})
MERGE (a)-[r:REL {type: $type}]->(b)
SET r.source_chunk_id = $chunk_id
```

---

## 3. Le problème du "fuzzy match" (correspondance approximative)

**Le code actuel n'utilise PAS de fuzzy matching !** Il utilise une correspondance **exacte** après normalisation.

### Comment ça marche (actuel) :

```python
# Étape 1 : Extrait les entités et relations d'Ollama
entities = [
    {"type": "ENTREPRISE", "name": "BTP Construction"},
    {"type": "PROJET", "name": "Tour Eiffel"}
]
relations = [
    {"type": "A_TRAVAILLE_SUR", "from": "BTP Construction", "to": "Tour Eiffel"}
]

# Étape 2 : Crée un dictionnaire de correspondance nom → key
keys = {}
for ent in entities:
    key = f"{tenant_id}:{etype}:{_norm(name)}"
    keys[name] = key           # "BTP Construction" → key
    keys[_norm(name)] = key    # "btp construction" → key

# Étape 3 : Pour chaque relation, cherche la clé
src = keys.get(rel.get("from"))  # Cherche "BTP Construction"
dst = keys.get(rel.get("to"))    # Cherche "Tour Eiffel"
```

### Problème : Pas de fuzzy matching

Si Ollama renvoie :
- Entité : `"BTP Construction"`
- Relation : `"BTP Constructions"` (pluriel)

→ La relation échoue car `keys` ne contient pas exactement `"BTP Constructions"`

---

## 4. Fuzzy matching : qu'est-ce que c'est ?

Le **fuzzy matching** (ou correspondance approximative) permet de trouver des correspondances même avec des **variations** :

| Technique | Exemple | Match |
|-----------|---------|-------|
| **Levenshtein** | "BTP Construction" vs "BTP Constructions" | Distance = 1 → match ✅ |
| **Soundex** | "Katherine" vs "Catherine" | Même son → match ✅ |
| **Jaccard** | "Jean Dupont" vs "Dupont Jean" | Mêmes mots → match ✅ |
| **N-gram** | "BTP Construction" vs "Constructions BTP" | N-grammes communs → match ✅ |

---

## 5. Comment implémenter du fuzzy matching ?

### Option 1 : Utiliser la distance de Levenshtein

```python
from rapidfuzz import fuzz

def fuzzy_find(keys: dict, name: str, threshold: int = 85) -> str | None:
    """Trouve la clé la plus proche avec un seuil de similarité."""
    name_norm = _norm(name)
    
    # D'abord, recherche exacte
    if name_norm in keys:
        return keys[name_norm]
    
    # Sinon, recherche floue
    best_score = 0
    best_key = None
    for key_name, key_value in keys.items():
        score = fuzz.ratio(name_norm, key_name)
        if score > best_score and score >= threshold:
            best_score = score
            best_key = key_value
    
    return best_key
```

### Option 2 : Utiliser un index vectoriel (embedding)

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('all-MiniLM-L6-v2')

def fuzzy_find_embedding(keys: dict, name: str, threshold: float = 0.8):
    """Trouve la clé par similarité sémantique."""
    # Embedding du nom à chercher
    query_emb = model.encode(name)
    
    # Comparer avec tous les noms existants
    best_score = 0
    best_key = None
    for key_name, key_value in keys.items():
        key_emb = model.encode(key_name)
        score = cosine_similarity(query_emb, key_emb)
        if score > best_score and score >= threshold:
            best_score = score
            best_key = key_value
    
    return best_key
```

### Option 3 : Regex + patterns

```python
import re

def fuzzy_find_pattern(keys: dict, name: str) -> str | None:
    """Trouve la clé par pattern matching."""
    patterns = [
        r"btp\s+construction",  # "BTP Construction"
        r"construction\s+btp",  # "Construction BTP"
        r"btp.*constructions",  # "BTP Constructions"
    ]
    # ...
```

---

## 6. Analyse critique de l'implémentation actuelle

### ✅ Points forts

1. **Isolation par tenant** : Clé avec `tenant_id` → pas de contamination entre clients
2. **Normalisation** : Gère les espaces et la casse
3. **MERGE au lieu de CREATE** : Évite les doublons
4. **Contrôle des types** : Vérifie que les entités/relations sont dans les listes autorisées
5. **Limite de chunks** : Évite la surcharge
6. **Gestion d'erreurs** : Continue même si un chunk échoue
7. **Trace des échecs** : `extra["graph_extract_failed"]`

### ❌ Points faibles

1. **Pas de fuzzy matching** : Les variations cassent les relations
2. **Limite à 12 chunks** : Les sections tardives sont ignorées
3. **Troncature à 3500 caractères** : Perte d'information pour les longs chunks
4. **Normalisation trop agressive** : "Tour Eiffel" et "La Tour Eiffel" ne matchent pas
5. **Pas de pondération** : Toutes les relations ont le même poids
6. **Pas de mise à jour des relations** : `source_chunk_id` est écrasé à chaque fois
7. **Pas de vérification de cohérence** : On ne vérifie pas si la relation est logique

### 🐛 Bugs potentiels

1. **Relations avec des entités non extraites** :
   ```json
   {"from": "BTP Construction", "to": "Entreprise Inconnue"}
   ```
   Si "Entreprise Inconnue" n'est pas dans les entités, la relation échoue silencieusement.

2. **Conflit de noms** :
   - "Projet Alpha" (projet)
   - "Alpha" (entreprise)
   - Le MERGE va créer une seule entité "Alpha" avec le dernier type rencontré

3. **Relations en double** : Deux chunks peuvent créer la même relation, mais MERGE évite les doublons

---

## 7. Suggestions d'amélioration

### Amélioration 1 : Fuzzy matching simple

```python
from rapidfuzz import fuzz

def _find_best_match(keys: dict, name: str, threshold: int = 80) -> str | None:
    """Trouve la meilleure correspondance avec fuzzy matching."""
    name = _norm(name)
    
    # Recherche exacte d'abord
    if name in keys:
        return keys[name]
    
    # Recherche floue
    best_score = 0
    best_key = None
    for key in keys:
        score = fuzz.ratio(name, key)
        if score > best_score and score >= threshold:
            best_score = score
            best_key = keys[key]
    
    return best_key
```

### Amélioration 2 : Traiter tous les parents (ou plus de 12)

```python
# Augmenter la limite
to_do = parents[:50]  # ou len(parents)

# Ou traitement par lots
for batch in chunks(parents, 12):
    # Traiter chaque batch
```

### Amélioration 3 : Validation des relations

```python
def _validate_relation(rel_type: str, from_type: str, to_type: str) -> bool:
    """Valide qu'un type de relation est cohérent."""
    valid_pairs = {
        "A_TRAVAILLE_SUR": ("ENTREPRISE", "PROJET"),
        "PORTE": ("PROJET", "CLIENT"),
        # ...
    }
    expected = valid_pairs.get(rel_type)
    return expected and from_type == expected[0] and to_type == expected[1]
```

### Amélioration 4 : Ajout de métadonnées

```python
neo.run(
    "MATCH (a:Entity {key: $src}), (b:Entity {key: $dst}) "
    "MERGE (a)-[r:REL {type: $type}]->(b) "
    "SET r.source_chunk_id = $chunk_id, "
    "    r.document_id = $document_id, "
    "    r.created_at = $created_at, "
    "    r.weight = r.weight + 1",  # ← Pondération des relations
    ...
)
```

---

## 8. Conclusion

**Est-ce que c'est bon ?** 

✅ **Fonctionnel** : Ça marche et produit un graphe utilisable
✅ **Robuste** : Gère les erreurs et continue
✅ **Isolé** : Pas de contamination entre tenants
✅ **Évolutif** : Facile à améliorer

❌ **Pas de fuzzy matching** : Les variations cassent les relations
❌ **Limité** : 12 chunks max, 3500 caractères max
❌ **Pas de validation** : Relations non vérifiées

**Note globale : 7/10** - Une base solide mais qui mérite des améliorations, notamment sur le fuzzy matching et la couverture complète du document.

Pour un système de production, je recommanderais d'ajouter au moins un fuzzy matching basique et de traiter tous les parents (ou au moins augmenter la limite).

Excellente question ! Oui, ce sont **4 techniques différentes** de fuzzy matching, chacune avec ses forces et faiblesses. Je vais te les expliquer en détail avec des exemples concrets.

---

## 1. Distance de Levenshtein (ou Edit Distance)

### Principe
Compte le **nombre minimum d'opérations** (insertion, suppression, substitution) pour transformer une chaîne en une autre.

### Exemple
```
"BTP Construction" → "BTP Constructions"
- Ajouter un 's' à la fin
→ Distance = 1
```

### Opérations possibles
| Opération | Exemple | Résultat |
|-----------|---------|----------|
| Substitution | "chat" → "chats" | Remplacer 't' par 't' (pas de changement) |
| Insertion | "chat" → "chats" | Ajouter 's' à la fin |
| Suppression | "chats" → "chat" | Supprimer 's' |

### Code Python
```python
from rapidfuzz import fuzz

# Distance de Levenshtein normalisée (0-100)
score = fuzz.ratio("BTP Construction", "BTP Constructions")
print(score)  # 96.77 (très proche)

score = fuzz.ratio("BTP Construction", "Construction BTP")
print(score)  # 77.77 (moins proche)
```

### Forces
- ✅ Bon pour les **fautes de frappe** : "construcion" → "construction"
- ✅ Bon pour les **variations de suffixe** : "constructeur" → "constructeurs"
- ✅ Simple à comprendre

### Faiblesses
- ❌ **Sensible à l'ordre** : "Jean Dupont" vs "Dupont Jean" → faible score
- ❌ **Coûteux** pour les longs textes (O(n*m))
- ❌ **Pas sémantique** : "chien" et "chat" ont une faible distance mais sont liés sémantiquement

---

## 2. Soundex

### Principe
Code les mots en fonction de **leur prononciation**, pas de leur orthographe.

### Algorithme
1. Garder la première lettre
2. Convertir les consonnes en chiffres
3. Supprimer les doublons

### Code Soundex
```
Règle :
- B, F, P, V → 1
- C, G, J, K, Q, S, X, Z → 2
- D, T → 3
- L → 4
- M, N → 5
- R → 6
- Les voyelles (A, E, I, O, U, Y) sont ignorées
```

### Exemples
```
"Katherine"  → K + 3 (T) + 6 (R) + 5 (N) = K365
"Catherine"  → C + 3 (T) + 6 (R) + 5 (N) = C365
```
→ Même code ! Donc Soundex les considère comme identiques.

### Code Python
```python
from rapidfuzz import fuzz

# Soundex n'est pas dans rapidfuzz, mais on peut l'implémenter
def soundex(name):
    # Implémentation simplifiée
    codes = {
        'B': '1', 'F': '1', 'P': '1', 'V': '1',
        'C': '2', 'G': '2', 'J': '2', 'K': '2', 'Q': '2', 'S': '2', 'X': '2', 'Z': '2',
        'D': '3', 'T': '3',
        'L': '4',
        'M': '5', 'N': '5',
        'R': '6'
    }
    # ...
    return code

print(soundex("Katherine"))  # K365
print(soundex("Catherine"))  # C365
```

### Forces
- ✅ Gère les **homophones** : "Katherine" et "Catherine"
- ✅ Gère les **différences d'orthographe** : "color" et "colour"
- ✅ Bon pour les **noms propres**

### Faiblesses
- ❌ **Anglo-centré** : Pas adapté au français (caractères accentués)
- ❌ **Perte d'information** : "Jean" et "Jeanne" ont le même code (J500)
- ❌ **Pas pour les phrases** : Fonctionne surtout pour des mots isolés

---

## 3. Similarité de Jaccard

### Principe
Compare les **ensembles de mots** ou de caractères. Le score est le ratio entre l'intersection et l'union.

### Formule
```
Jaccard(A, B) = |A ∩ B| / |A ∪ B|
```

### Exemple avec mots
```
A = {"Jean", "Dupont"}
B = {"Dupont", "Jean"}

Intersection = {"Jean", "Dupont"} → taille = 2
Union = {"Jean", "Dupont"} → taille = 2
Jaccard = 2/2 = 1.0 → Match parfait ✅
```

### Exemple avec caractères (N-gram)
```
"BTP Construction" → {BT, TP, P , " C", "Co", "on", "ns", "st", "tr", "ru", "uc", "ct", "ti", "io", "on"}
"Constructions BTP" → {Co, "on", "ns", "st", "tr", "ru", "uc", "ct", "ti", "io", "on", "ns", "s ", " B", "BT", "TP"}
Intersection = {"BT", "TP", "on", "ns", "st", "tr", "ru", "uc", "ct", "ti", "io"} → 11
Union = {"BT", "TP", "P ", " C", "Co", "on", "ns", "st", "tr", "ru", "uc", "ct", "ti", "io", "s ", " B"} → 16
Jaccard = 11/16 = 0.6875 → Match bon ✅
```

### Code Python
```python
from rapidfuzz import fuzz

# Jaccard sur les mots
score = fuzz.token_set_ratio("Jean Dupont", "Dupont Jean")
print(score)  # 100 (match parfait)

# Jaccard sur les bigrammes (n-gram de taille 2)
score = fuzz.ratio("BTP Construction", "Constructions BTP")
print(score)  # 77.77 (moins bon que Jaccard)
```

### Forces
- ✅ **Insensible à l'ordre** des mots
- ✅ Bon pour les **phrases réorganisées**
- ✅ Gère les **mots manquants/ajoutés**

### Faiblesses
- ❌ Perd l'ordre → "chien mord homme" = "homme mord chien" (même score)
- ❌ Nécessite un bon tokenizer (découpage en mots)
- ❌ Ne gère pas les synonymes

---

## 4. N-gram (ou shingling)

### Principe
Découpe le texte en **séquences de N caractères** (ou mots) consécutifs, puis compare les ensembles.

### Exemple avec bigrammes (N=2)
```
"BTP Construction"
→ {BT, TP, P , " C", Co, on, ns, st, tr, ru, uc, ct, ti, io, on}
                              ↑ espaces comptés

"Constructions BTP"  
→ {Co, on, ns, st, tr, ru, uc, ct, ti, io, on, ns, s , " B", BT, TP}
```

### Différentes tailles de N-gram
| N | Type | Exemple pour "BTP" | Utilisation |
|---|------|-------------------|-------------|
| 1 | Unigram | B, T, P | Détection de langue |
| 2 | Bigram | BT, TP | Corrections orthographiques |
| 3 | Trigram | BTP | OCR, recherche |
| 4+ | N-gram | BTP_ | Similarité de textes |

### Code Python
```python
def ngrams(text, n=2):
    """Extrait les N-grammes d'un texte."""
    text = ' ' + text + ' '  # Ajouter des espaces pour les bords
    return [text[i:i+n] for i in range(len(text)-n+1)]

def ngram_similarity(a, b, n=2):
    """Calcule la similarité Jaccard sur les N-grammes."""
    ngrams_a = set(ngrams(a, n))
    ngrams_b = set(ngrams(b, n))
    
    intersection = len(ngrams_a & ngrams_b)
    union = len(ngrams_a | ngrams_b)
    return intersection / union if union > 0 else 0

# Exemple
sim = ngram_similarity("BTP Construction", "Constructions BTP", n=2)
print(sim)  # 0.6875 (bon match)
```

### Forces
- ✅ **Robuste aux changements d'ordre** (si N=1 ou 2)
- ✅ **Robuste aux fautes de frappe** (une faute affecte peu de N-grammes)
- ✅ **Ne dépend pas de la langue** (contrairement à Soundex)

### Faiblesses
- ❌ **Coûteux en mémoire** (nombre de N-grammes = O(text length))
- ❌ Choix de N critique : trop petit → bruit, trop grand → perte de flexibilité
- ❌ Ne capture pas la sémantique

---

## Comparaison des 4 techniques

| Technique | Ordre des mots | Fautes de frappe | Homophones | Performance | Usage typique |
|-----------|---------------|------------------|------------|-------------|---------------|
| **Levenshtein** | ❌ Sensible | ✅ Excellent | ❌ Non | Moyen | Corrections, OCR |
| **Soundex** | ❌ Sensible | ✅ Bon | ✅ Excellent | Rapide | Noms propres |
| **Jaccard** | ✅ Insensible | ⚠️ Moyen | ❌ Non | Rapide | Documents, textes |
| **N-gram** | ✅ Insensible | ✅ Bon | ❌ Non | Lent | Recherche, OCR |

---

## Cas concret avec ton projet Neo4j

### Problème actuel
```python
# Ollama retourne des variations
entities = [
    {"type": "ENTREPRISE", "name": "BTP Construction"},
    {"type": "PROJET", "name": "Tour Eiffel"}
]

relations = [
    {"from": "BTP Constructions", "to": "Tour Eiffel"}  # ← Pluriel !
]

# Le code échoue car "BTP Constructions" n'est pas dans keys
src = keys.get("BTP Constructions")  # ← None ❌
```

### Solution avec Levenshtein
```python
from rapidfuzz import fuzz

def find_best_match(keys: dict, name: str, threshold: int = 85) -> str | None:
    name = _norm(name)
    
    # 1. Recherche exacte
    if name in keys:
        return keys[name]
    
    # 2. Recherche floue (Levenshtein)
    best_score = 0
    best_key = None
    for key_name, key_value in keys.items():
        # Levenshtein normalisé (0-100)
        score = fuzz.ratio(name, key_name)
        if score > best_score and score >= threshold:
            best_score = score
            best_key = key_value
    
    return best_key

# Application
src = find_best_match(keys, "BTP Constructions")
# → Trouve "BTP Construction" avec un score de ~96% ✅
```

### Solution avec Jaccard (pour l'ordre des mots)
```python
def find_best_match_jaccard(keys: dict, name: str, threshold: int = 70) -> str | None:
    name = _norm(name)
    words = set(name.split())
    
    best_score = 0
    best_key = None
    for key_name, key_value in keys.items():
        key_words = set(key_name.split())
        # Jaccard
        score = len(words & key_words) / len(words | key_words) * 100
        if score > best_score and score >= threshold:
            best_score = score
            best_key = key_value
    
    return best_key

# Application
src = find_best_match_jaccard(keys, "Construction BTP")
# → Trouve "BTP Construction" avec un score de 100% ✅
```

### Solution hybride (le meilleur des deux)
```python
def find_best_match_hybrid(keys: dict, name: str) -> str | None:
    name = _norm(name)
    
    # 1. Levenshtein (fautes de frappe)
    lev_result = find_best_match(keys, name, threshold=85)
    if lev_result:
        return lev_result
    
    # 2. Jaccard (ordre des mots)
    jac_result = find_best_match_jaccard(keys, name, threshold=70)
    if jac_result:
        return jac_result
    
    # 3. N-gram (OCR, textes longs)
    # ...
    
    return None
```

---

## Synthèse pour ton projet

### Recommandation
1. **Utilise Levenshtein** comme premier filtre (bon pour les fautes de frappe)
2. **Ajoute Jaccard** pour les cas où les mots sont réorganisés
3. **Garde la normalisation** (minuscules, espaces) comme préfiltre

### Code final proposé
```python
from rapidfuzz import fuzz, fuzz

def _find_entity_key(keys: dict, name: str) -> str | None:
    """Trouve une entité avec fuzzy matching."""
    name_norm = _norm(name)
    
    # Recherche exacte
    if name_norm in keys:
        return keys[name_norm]
    
    # Levenshtein (fautes de frappe)
    best_score = 0
    best_key = None
    for key_name, key_value in keys.items():
        # Levenshtein ratio
        score = fuzz.ratio(name_norm, key_name)
        if score > best_score and score >= 85:  # Seuil à 85%
            best_score = score
            best_key = key_value
    
    if best_key:
        return best_key
    
    # Jaccard (ordre des mots)
    best_score = 0
    best_key = None
    name_words = set(name_norm.split())
    for key_name, key_value in keys.items():
        key_words = set(key_name.split())
        score = fuzz.token_set_ratio(name_norm, key_name)  # Jaccard en pratique
        if score > best_score and score >= 70:  # Seuil à 70%
            best_score = score
            best_key = key_value
    
    return best_key
```

**Cette approche hybride** couvre la majorité des cas :
- ✅ Fautes de frappe (Levenshtein)
- ✅ Ordre des mots (Jaccard)
- ✅ Noms avec accents (normalisation)
- ✅ Pluriels (normalisation + Levenshtein)

---

## En résumé

| Technique | À utiliser quand... |
|-----------|-------------------|
| **Levenshtein** | Fautes de frappe, variantes orthographiques |
| **Soundex** | Noms propres, homophones (peu adapté au français) |
| **Jaccard** | Mots réorganisés, mots manquants/ajoutés |
| **N-gram** | OCR, textes longs, recherche approximative |

**Dans ton cas** : Une combinaison **Levenshtein + Jaccard** avec normalisation préalable est la solution la plus robuste pour matcher les entités extraites par Ollama.



# Analyse détaillée du fonctionnement du système de conversation RAG

## Architecture générale

Ce système est une application de **chat RAG (Retrieval-Augmented Generation)** avec capacités d'export multi-format et de gestion de dossiers. Il combine :

1. **Une API REST** (FastAPI) pour gérer les conversations
2. **Un pipeline de traitement** asynchrone et synchrone
3. **Un système de workflow** (graph) pour le routage, la récupération et la génération
4. **Une persistance** des données via SQLAlchemy
5. **Des capacités d'export** vers DOCX, PDF, MD, TXT

---

## 1. Structure des données

### Modèles principaux
- **Conversation** : conteneur de messages avec un `dossier_id` optionnel
- **Message** : messages utilisateur/assistant avec `role`, `content`, `meta`
- **User** : utilisateur avec rôles (`admin`, `manager`, `redacteur`, `consultant`)
- **Dossier** : regroupement de sections de documents

### Rôles utilisateur
- **admin** : tous les droits
- **manager** : peut écrire, exporter
- **redacteur** : peut écrire, exporter
- **consultant** : lecture seule, ne peut pas déposer de documents

---

## 2. API Routes (conversations.py)

### `GET /conversations` - Lister les conversations
```python
async def list_conversations(...)
```
- Filtre par `tenant_id` (multi-tenant)
- Filtre par `user_id` sauf pour admin
- Ne retourne que les conversations avec au moins un message
- Tri par `updated_at` décroissant

### `POST /conversations` - Créer une conversation
```python
async def create_conversation(...)
```
- Crée une conversation avec titre optionnel
- Peut être liée à un `dossier_id` existant
- Titre par défaut : "Nouvelle conversation"

### `GET /conversations/{id}` - Récupérer une conversation
```python
async def get_conversation(...)
```
- Charge la conversation avec ses messages
- Génère l'aperçu (preview) depuis les sections et messages
- Vérifie les droits d'accès

### `PATCH /conversations/{id}` - Mettre à jour le titre
```python
async def update_conversation(...)
```
- Met à jour le titre (1-255 caractères)
- Met à jour `updated_at`

### `DELETE /conversations/{id}` - Supprimer une conversation
```python
async def delete_conversation(...)
```
- Appelle `purge_conversation` pour suppression complète

---

## 3. Fonctionnalités principales

### 3.1 Upload de documents (`POST /{id}/documents`)

```python
async def upload_conversation_document(...)
```

**Processus :**
1. Vérifie que l'utilisateur n'est pas consultant
2. Lit le fichier uploadé
3. Si l'utilisateur peut écrire et pas de dossier : crée un dossier avec `ensure_dossier`
4. Stocke le document via `store_document` (avec déduplication)
5. Ajoute un message système indiquant le statut
6. Met à jour la conversation

**Gestion de duplication :**
- `duplicate=True` : document déjà indexé
- `doc_status` : état du document (ready, processing, error)

### 3.2 Envoi de message synchrone (`POST /{id}/messages`)

```python
async def post_message(...)
```

**Processus :**
1. Ajoute le message utilisateur
2. Appelle `process_message_sync` (voir détail ci-dessous)
3. Ajoute la réponse assistant avec `generation_id`
4. Met à jour le titre si c'est la première conversation
5. Retourne la conversation mise à jour

### 3.3 Envoi de message stream (`POST /{id}/messages/stream`)

```python
async def post_message_stream(...)
```

**Processus :**
1. Utilise une **Server-Sent Events (SSE)** response
2. Appelle `stream_message` qui génère des événements :
   - `user` : confirmation du message utilisateur
   - `intent` : type d'intention détectée
   - `token` : tokens générés progressivement
   - `section_start/end` : pour les sections
   - `preview` : aperçu final markdown
   - `done` : fin du streaming

### 3.4 Export de conversation (`POST /{id}/export`)

```python
async def export_conversation(...)
```

**Processus :**
1. Vérifie les droits d'écriture
2. Assure l'existence du dossier
3. Récupère les 12 derniers messages
4. Appelle `export_document` avec le format demandé
5. Ajoute un message d'export dans l'historique

**Formats supportés :** docx, pdf, md, txt

---

## 4. Pipeline de chat (chat_pipeline.py)

### 4.1 Fonction `process_message_sync`

**Flux détaillé :**

```
1. Historique → _message_history(conv)
   └─ Récupère tous les messages triés chronologiquement

2. Exécution du graph → _run_graph(query, tenant_id, history)
   └─ Appelle le workflow LangGraph

3. Analyse de l'intention retournée
   ├─ "export" → export du document
   ├─ "run_section" → rédaction d'une section
   ├─ "smalltalk" → réponse conversationnelle
   └─ "hybrid_rag" → réponse RAG classique

4. Traitement selon l'intention
```

#### Cas "export" :
```python
- Détection du format dans la requête (pdf, docx, md, txt)
- ensure_dossier() pour créer le dossier si nécessaire
- export_document() avec les derniers messages
- Retourne la version du document
```

#### Cas "run_section" :
```python
- Vérification des droits d'écriture
- _persist_sections() sauvegarde la section générée
- Si generate_all=True : génère toutes les sections du plan
- Retourne un message de confirmation
```

#### Cas "smalltalk" :
```python
- Appelle le nœud chitchat
- Génère une réponse conversationnelle
- Pas de persistance en base
```

### 4.2 Fonction `stream_message`

**Flux détaillé (SSE) :**

```
1. Ajout du message utilisateur
   └─ SSE "user"

2. Routage initial → _route_retrieve()
   ├─ route_node() : détecte l'intention
   ├─ pick_section() : pour les sections
   └─ retrieve_node() : récupère les documents pertinents

3. Boucle de génération des sections
   ├─ Pour chaque section à générer :
   │  ├─ build_prompt() construit le prompt
   │  ├─ _iter_ollama_tokens() génère token par token
   │  └─ SSE "token" pour chaque token
   └─ SSE "section_start/end"

4. Génération de l'aperçu final
   └─ SSE "preview" avec le markdown complet

5. Persistance
   ├─ _persist_sections() sauvegarde en base
   └─ Ajout du message assistant

6. Fin
   └─ SSE "done"
```

---

## 5. Workflow LangGraph

### 5.1 Structure du graphe (workflow/graph.py)

```
START
  ↓
route_node()  ← Détection de l'intention
  ↓
├─ Intent: "smalltalk" → chitchat_node → END
├─ Intent: "run_section" → retrieve_node → generate_node → END
├─ Intent: "export" → export_node → END
└─ Intent: "hybrid_rag" → retrieve_node → generate_node → END
```

### 5.2 Nœuds du workflow

#### `route_node` (routing)
```python
- Analyse la requête utilisateur
- Détermine l'intention (smalltalk, run_section, export, hybrid_rag)
- Pour "run_section" : identifie la section via pick_section()
- Met à jour l'état (state)
```

#### `retrieve_node` (récupération)
```python
- Construit une requête de recherche
- Interroge la base vectorielle (FAISS/Chroma)
- Récupère les chunks pertinents avec scores
- Formate les résultats avec métadonnées
```

#### `generate_node` (génération)
```python
- Construit le prompt avec contexte et historique
- Appelle Ollama pour générer la réponse
- Retourne la réponse et les métadonnées
```

#### `chitchat_node` (dialogue)
```python
- Gère les conversations hors-sujet
- Réponses conversationnelles prédéfinies
- Pas de RAG appliqué
```

---

## 6. Gestion des sections et dossiers

### 6.1 Structure des sections

```python
DEFAULT_OUTLINE = [
    ("presentation", 1, "Présentation"),
    ("patrimoine_global", 1, "Patrimoine global"),
    ("immobilier", 1, "Immobilier"),
    ("financier", 1, "Financier"),
    ("professionnel", 1, "Professionnel"),
    ("notes_travail", 1, "Notes de travail"),
    # ... etc
]
```

### 6.2 Fonction `_persist_sections`

```python
async def _persist_sections(session, conv, user, state, section_texts=None):
    1. Vérifie les droits d'écriture
    2. ensure_dossier() : crée ou récupère le dossier
    3. Extraire les citations (chunks + pages)
    4. save_generation() pour chaque section
    5. Si generate_all : génère toutes les sections manquantes
```

### 6.3 Fonction `ensure_dossier`

```python
- Vérifie si un dossier existe pour la conversation
- Si non : crée un nouveau dossier
- Associe le dossier à la conversation
- Retourne l'ID du dossier
```

---

## 7. Gestion de l'aperçu (preview)

### 7.1 Construction du preview

```python
def _merge_preview(sections, msgs):
    # 1. Preview depuis les sections en base
    from_db = _preview_from_sections(sections)
    
    # 2. Preview depuis les messages assistant
    from_msgs = _preview_from_messages(msgs)
    
    # 3. Fusion intelligente
    # - Évite les doublons
    # - Garde la version la plus complète
    # - Vérifie l'inclusion
```

### 7.2 Format du preview
```markdown
## Titre section 1

Contenu de la section...

---

## Titre section 2

Contenu de la section...
```

---

## 8. Intégration avec Ollama

### 8.1 Génération synchrone
```python
def _run_graph(query, tenant_id, history):
    result = compiled_graph().invoke({
        "query": query,
        "tenant_id": str(tenant_id),
        "messages": [...],
        "history": history
    })
    return result
```

### 8.2 Génération en streaming
```python
async def _iter_ollama_tokens(prompt):
    # Worker thread pour Ollama
    # Queue asynchrone pour les tokens
    # SSE pour chaque token
```

### 8.3 Build prompt
```python
def build_prompt(state):
    # 1. Contexte : documents récupérés (retrieved)
    # 2. Historique : messages précédents
    # 3. Instruction : selon l'intention
    # 4. Requête : question utilisateur
    # → prompt complet avec instructions de formatage
```

---

## 9. Export multi-format

### 9.1 Fonction `export_document`

```python
async def export_document(session, dossier, user, fmt, transcript):
    # 1. Récupère les sections du dossier
    # 2. Construit le document complet
    # 3. Format spécifique :
    #    - DOCX : python-docx
    #    - PDF : weasyprint/pyppeteer
    #    - MD : markdown pur
    #    - TXT : texte brut
    # 4. Sauvegarde la version
    # 5. Retourne le document et la version
```

### 9.2 Gestion des versions
- Chaque export incrémente la version
- Stockage des métadonnées de version
- Historique des exports dans les messages

---

## 10. Gestion des erreurs et logs

### 10.1 Points de logging
- Horloge B : suivi des performances
- Logging des erreurs avec stacktrace
- Logs des intents et actions

### 10.2 Gestion des exceptions
- HTTPException pour les erreurs API
- RuntimeError pour les erreurs de traitement
- Timeout et gestion des threads

---

## 11. Flux complet d'une requête utilisateur

### Exemple : "Rédige la section immobilier"

```
1. Client → POST /conversations/{id}/messages/stream
   {
     "text": "Rédige la section immobilier"
   }

2. API → stream_message()
   ├─ Ajout message user
   └─ SSE "user"

3. _route_retrieve()
   ├─ route_node() → intent="run_section"
   ├─ pick_section() → section_key="immobilier"
   └─ retrieve_node() → chunks pertinents

4. SSE "intent": {"intent": "run_section"}

5. Pour chaque section à générer :
   ├─ build_prompt() → prompt avec contexte
   ├─ _iter_ollama_tokens() → streaming Ollama
   └─ SSE "token" x N

6. SSE "section_end": {
     "key": "immobilier",
     "title": "Immobilier",
     "markdown": "..."
   }

7. _persist_sections()
   ├─ ensure_dossier() → dossier existant ou création
   └─ save_generation() → sauvegarde en base

8. SSE "done": {
     "ok": true,
     "message": "Section « Immobilier » rédigée."
   }

9. Client → reçoit le flux complet
   └─ Affiche la réponse progressive
```

---

## 12. Points clés d'architecture

### 12.1 Multi-tenant
- Chaque utilisateur a un `tenant_id`
- Isolation des données par tenant
- Les requêtes filtrent par tenant

### 12.2 Gestion des droits
- `can_write()` : admin, manager, redacteur
- Consultation : lecture seule
- Chaque endpoint vérifie les droits

### 12.3 Streaming vs Sync
- **Sync** : réponse complète, pour les appels API classiques
- **Stream** : réponse progressive, pour l'expérience utilisateur

### 12.4 Persistance asynchrone
- SQLAlchemy AsyncSession
- Transactions pour la cohérence
- Flush/Commit explicites

### 12.5 Gestion des sections
- Génération incrémentale
- Fusion avec aperçu existant
- Déduplication des sections

---

## 13. Optimisations et bonnes pratiques

### 13.1 Déduplication
- Documents : vérification des doublons à l'upload
- Sections : évite les générations en double
- Preview : fusion intelligente

### 13.2 Performance
- Streaming pour les longues réponses
- Threading pour Ollama (non bloquant)
- Pagination des résultats

### 13.3 Robustesse
- Gestion des timeouts
- Retry sur erreur
- Validation des inputs (Pydantic)
- Logs structurés

---

## Résumé des composants

| Composant | Rôle |
|-----------|------|
| **Conversations API** | Endpoints REST pour les conversations |
| **Chat Pipeline** | Logique métier de traitement des messages |
| **Workflow Graph** | Orchestration du RAG avec LangGraph |
| **Dossier Workflow** | Gestion des dossiers et sections |
| **Ollama LLM** | Génération de texte via Ollama |
| **Base de données** | Persistance SQL avec SQLAlchemy |
| **Export Service** | Génération de documents multi-format |
| **Upload Service** | Gestion des documents uploadés |



# Analyse du choix d'intention et son utilité

## 1. Comment l'intention est choisie ?

### Le nœud `route()` - Règles de détection

```python
def route(state: dict) -> dict:
    text = (state.get("query") or "").strip()
    
    # 1. Normalisation du texte
    lowered = text.lower()
    
    # 2. Mots-clés pour chaque intention
    export_w = ("export", "exporte", "télécharge", "telecharge", "docx", "pdf du dossier")
    gen_w = ("génère", "genere", "rédige", "redige", 
             "écris la section", "ecris la section",
             "ajoute au document", "ajoute ça au document", "ajoute ca au document",
             "mémoire technique", "memoire technique")
    
    # 3. Détection par priorité (ordre important !)
    if any(w in lowered for w in export_w):
        intent = "export"
    elif any(w in lowered for w in gen_w):
        intent = "run_section"
    elif not text.strip() or lowered.strip() in {"bonjour", "hello", "salut", "coucou"}:
        intent = "smalltalk"
    else:
        intent = "hybrid_rag"  # Par défaut
    
    return {**state, "intent": intent, "query": text}
```

### Règles de priorité (ordre d'évaluation)

L'ordre des conditions est **crucial** car il détermine quelle intention est choisie en cas d'ambiguïté :

```
1️⃣ export     → Priorité la plus haute
2️⃣ run_section → Priorité moyenne
3️⃣ smalltalk   → Priorité basse
4️⃣ hybrid_rag  → Par défaut (fallback)
```

### Exemples concrets de détection

| Requête utilisateur | Intention détectée | Raison |
|---------------------|-------------------|--------|
| "Exporte le document en PDF" | **export** | Contient "exporte" |
| "Rédige la section immobilier" | **run_section** | Contient "rédige" |
| "Bonjour" | **smalltalk** | Dans la liste des salutations |
| "Quelle est la valeur de mon patrimoine ?" | **hybrid_rag** | Aucun mot-clé spécifique |
| "Exporte la section immobilier" | **export** | Priorité sur "section" |
| "Ajoute ça au document" | **run_section** | Dans gen_w |
| "PDF du dossier" | **export** | Contient "pdf" |

---

## 2. À quoi sert l'intention ?

### 2.1 Orchestration du workflow

L'intention détermine **quel chemin** va emprunter le pipeline :

```
                    ┌─────────────────┐
                    │   route()       │
                    │  Détection      │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
              ▼              ▼              ▼
         ┌────────┐    ┌──────────┐   ┌─────────┐
         │ export │    │run_section│   │smalltalk│
         └────────┘    └──────────┘   └─────────┘
              │              │              │
              ▼              ▼              ▼
         Exportation    Génération     Dialogue
         Document       Section        Simple
```

### 2.2 Impact sur le traitement

#### **Cas `export`**
```python
if intent == "export":
    # 1. Détection du format (pdf, docx, md, txt)
    # 2. Récupération du dossier
    # 3. Export du document
    # 4. Enregistrement de la version
    return msg_document_exporte
```
- **Pas de génération LLM**
- **Pas de RAG**
- Action directe : exporter le document existant

#### **Cas `run_section`**
```python
if intent == "run_section":
    # 1. Identification de la section
    key, title, all_flag = pick_section(query)
    # 2. Récupération des documents pertinents (retrieve)
    # 3. Génération de la section (LLM)
    # 4. Sauvegarde en base
    return section_generee
```
- **Génération LLM**
- **RAG** pour le contexte
- **Persistance** en base de données

#### **Cas `smalltalk`**
```python
if intent == "smalltalk":
    # 1. Pas de retrieve
    # 2. Réponse conversationnelle simple
    # 3. Pas de persistance
    return reponse_chitchat
```
- **Pas de RAG**
- **Pas de persistance**
- Réponse rapide et légère

#### **Cas `hybrid_rag`** (défaut)
```python
if intent == "hybrid_rag":
    # 1. Récupération des documents (retrieve)
    # 2. Génération avec contexte (LLM)
    # 3. Pas de persistance automatique
    return reponse_avec_citations
```
- **RAG complet**
- **Génération LLM avec contexte**
- **Citations** des sources

---

## 3. Utilité dans le contexte RAG

### 3.1 Optimisation des coûts et performance

| Intention | RAG | LLM | Persistance | Coût |
|-----------|-----|-----|-------------|------|
| export | ❌ | ❌ | ✅ | Très bas |
| smalltalk | ❌ | ✅ | ❌ | Bas |
| hybrid_rag | ✅ | ✅ | ❌ | Élevé |
| run_section | ✅ | ✅ | ✅ | Très élevé |

### 3.2 Amélioration de l'expérience utilisateur

- **Export rapide** : pas d'attente de génération
- **Conversation fluide** : les salutations sont traitées sans overhead
- **Réponses contextualisées** : RAG pour les questions patrimoniales
- **Génération structurée** : sections bien formatées pour le document final

### 3.3 Cas d'usage spécifiques

```python
# Exemple 1: Demande d'export
"Exporte le dossier en PDF" 
→ intent = "export"
→ Action directe, pas de LLM

# Exemple 2: Génération de section
"Rédige la section immobilier"
→ intent = "run_section"
→ Retrieve + LLM + Persistance

# Exemple 3: Question simple
"Bonjour, comment ça va ?"
→ intent = "smalltalk"
→ Réponse rapide sans contexte

# Exemple 4: Question patrimoniale
"Quelle est la valeur de mon appartement ?"
→ intent = "hybrid_rag"
→ Retrieve (documents pertinents) + LLM + Citations
```

---

## 4. Dans le flux `stream_message()`

### Comment l'intention est utilisée dans le streaming

```python
async def stream_message(...):
    # 1. Détection initiale
    state = _route_retrieve(query, tenant_id, history)
    intent = state.get("intent")
    
    # 2. Envoi de l'intention au client
    yield _sse("intent", {"intent": intent})
    
    # 3. Branchement selon l'intention
    
    if intent == "smalltalk":
        # Réponse rapide, pas de retrieve
        yield token_immédiat
        
    elif intent == "export":
        # Action directe, pas de streaming LLM
        yield export_ready
        
    elif intent == "run_section":
        # Streaming token par token
        for token in _iter_ollama_tokens(prompt):
            yield token
        # Persistance
            
    else:  # hybrid_rag
        # Streaming avec contexte
        for token in _iter_ollama_tokens(prompt):
            yield token
        # Citations incluses
```

---

## 5. Résumé des bénéfices

### Pour l'utilisateur
- ✅ **Réponses plus rapides** pour les actions simples
- ✅ **Expérience cohérente** : les salutations ne déclenchent pas de RAG inutile
- ✅ **Actions intentionnelles** : exporter, générer, questionner

### Pour le système
- ✅ **Optimisation des ressources** : pas de LLM pour les exports
- ✅ **Réduction des coûts** : moins d'appels LLM inutiles
- ✅ **Meilleure scalabilité** : les actions légères sont moins gourmandes

### Pour le développeur
- ✅ **Code modulaire** : chaque intention a sa propre logique
- ✅ **Débogage facilité** : traçabilité des décisions
- ✅ **Évolutivité** : facile d'ajouter de nouvelles intentions

---

## 6. Limitations et améliorations possibles

### Limitations actuelles
- ❌ Approche basée sur **mots-clés** uniquement
- ❌ Pas de classification ML pour l'intention
- ❌ Pas de contexte sémantique (ex: "je veux le document" → export ?)
- ❌ Ordre de priorité rigide

### Améliorations possibles
```python
# Version améliorée avec classification ML
def route_advanced(state):
    text = state.get("query")
    
    # 1. Règles rapides (fallback)
    if not text: return default
    
    # 2. Classification ML
    intent = classifier.predict(text)
    
    # 3. Si confiance faible, fallback sur règles
    if intent.confidence < 0.7:
        intent = rule_based_fallback(text)
    
    return intent
```

---Dans le code que tu as partagé, **les mécanismes de BM25, de recherche sémantique et de RRF ne sont pas explicitement implémentés**. Le fichier `chat_pipeline.py` que tu m'as montré fait appel à des fonctions externes (`retrieve_node` et `compiled_graph`) qui les contiennent probablement.

Voici comment ces techniques fonctionnent généralement dans un pipeline "hybrid_rag" pour améliorer la recherche d'information.

### 🎯 Le Rôle du `retrieve_node` dans "hybrid_rag"

Lorsque l'intention est `hybrid_rag`, le pipeline fait appel au nœud `retrieve_node` . C'est à ce moment précis que les techniques de recherche hybride (BM25 + sémantique) sont mises en œuvre pour trouver les documents les plus pertinents.

### 🔍 BM25 : La Recherche par Mots-Clés Exacte

BM25 est un algorithme de recherche lexicale qui excelle dans la recherche de **termes exacts** . C'est la partie "recherche par mots-clés" de l'approche hybride.

*   **Fonctionnement :** Il compare les mots de la requête utilisateur avec ceux des documents dans la base. Il est particulièrement efficace pour trouver des **identifiants précis** (comme des numéros de contrat, des noms de lois) ou des **termes rares** que la recherche sémantique pourrait "oublier" .
*   **Utilité dans ton contexte :** Si un utilisateur demande des informations sur un document spécifique, comme "le contrat `CT-2024-001`", BM25 est idéal pour le retrouver exactement, là où une recherche par "sens" pourrait échouer .

### 🧠 Recherche Sémantique (Vectorielle) : La Compréhension du Sens

La recherche sémantique utilise des **vecteurs numériques** (des *embeddings*) pour comprendre le sens et le contexte d'une requête .

*   **Fonctionnement :** Les documents et la requête sont transformés en vecteurs. La recherche consiste à trouver les vecteurs de documents les plus proches (similaires) dans l'espace vectoriel. Elle est idéale pour les questions **conceptuelles**, où l'utilisateur cherche une idée ou un thème général (ex: "Comment optimiser ma fiscalité ?") .
*   **Utilité dans ton contexte :** Si un utilisateur reformule une question de manière différente (ex: "maison" au lieu de "appartement"), la recherche sémantique comprendra le lien, là où BM25 pourrait passer à côté.

### 🔗 RRF (Reciprocal Rank Fusion) : Le "Fusionneur" des Résultats

RRF est l'élément qui combine les résultats des deux recherches précédentes .

*   **Fonctionnement :** Il prend les deux classements (le classement de la recherche BM25 et celui de la recherche sémantique) et les fusionne en un seul . Sa force est de ne pas avoir besoin de comparer les scores bruts des deux moteurs, car ils ne sont pas sur la même échelle .
    > La formule est la suivante : `Score_RRF(d) = Somme( 1 / (k + rang_i(d)) )` où `k` est une constante (souvent 60) et `rang_i(d)` est la position du document dans le classement `i` .

*   **Utilité :** Il garantit que les documents qui sont bien classés *à la fois* par BM25 et par la recherche sémantique se retrouvent en tête du classement final, offrant ainsi le meilleur des deux mondes .

### 📊 Résumé des Forces de Chaque Approche

| Approche | Force Principale | Exemple de Question |
| :--- | :--- | :--- |
| **BM25 (Lexical)** | Recherche exacte de mots-clés et d'identifiants  | "Quel est le montant de la prime pour le contrat `P-2024-0123` ?" |
| **Sémantique (Vectorielle)** | Compréhension du sens, des synonymes et du contexte  | "Explique-moi les avantages d'un PER par rapport à une assurance-vie." |
| **RRF (Fusion)** | Combine les deux pour un classement optimal et robuste  | *(N'est pas une requête, mais une méthode de classement)* |

**En conclusion**, le système d'intention est un **routage intelligent** qui permet d'optimiser les ressources tout en offrant une expérience utilisateur adaptée à chaque type de demande. C'est le "cerveau" qui décide quoi faire avec la requête utilisateur.
