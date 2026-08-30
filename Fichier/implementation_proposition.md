# Proposition d'implémentation V1 — Dossiers d'appels d'offres

> Décision : **Advanced RAG hybride (BM25 + dense + rerank)** comme moteur de recherche.
> GraphRAG est **prévu dans la même architecture**, construit **après** que l'ingestion et l'hybride marchent — pas le premier jour.
> Pas d'agents autonomes. Workflow déterministe (analyse DAO → recherche → contexte → génération section → validation → humain → export).

---

## 1. La décision en une page

| Couche | Choix | Pourquoi |
|--------|-------|----------|
| Parse PDF/DOCX **numériques** | **Docling** | Mise en page, titres, tableaux → Markdown. Un AO n'est pas une image. |
| OCR + structure des **scans** | **PaddleOCR PP-StructureV3** | Détection + reco + layout + tables. Mieux que Tesseract sur pages complexes. |
| Routage | Densité de texte du PDF | Si le PDF a déjà du texte : **pas d'OCR**. OCR seulement si scan. |
| Chunking | **Structure métier** (articles / titres) + **parent-child** | Un article de CCAP = unité de sens. Chercher petit, lire grand. |
| Embedding | **BGE-M3** (self-host) | FR+EN, dense **et** sparse dans le même modèle. |
| Reranker | **BGE-reranker-v2-m3** | Cross-encoder multilingual. Top-50 → Top-8. |
| Métier + versions + ACL | **PostgreSQL** | AO, exigences, utilisateurs, décisions humaines. |
| Recherche hybride | **Qdrant** (dense + sparse natif) | Un store, filtres riches, RRF intégré. |
| Graphe (phase 1.5) | **Neo4j** + extraction LLM | Entités AO / entreprise / projet / exigence. |
| Orchestration | **LangGraph** | États, retries bornés, HITL. |
| Schémas | **Pydantic** | `Exigence`, `ExtraitCite`, `SectionGeneree`. |
| API | **FastAPI** | Dépôt fichiers, suivi job, revue, export. |
| Jobs d'ingestion | **ARQ + Redis** | Un DAO de 200 pages ne se parse pas dans la requête HTTP. |
| Fichiers bruts | Disque ou **MinIO** | PDF originaux + empreinte. |
| LLM rédaction | API (Claude / GPT) **ou** Qwen2.5-72B local | Sortie JSON contrainte. Interchangeable. |

**On ne prend pas :** Tesseract comme OCR principal, Chroma (trop jouet), CrewAI, GraphRAG Microsoft officiel dès J1 (trop cher à l'index), embeddings OpenAI seuls (tu perds le sparse natif de BGE-M3 et le français self-host).

---

## 2. Pourquoi cet ordre (et pas « tout en même temps »)

Tu veux hybride **et** graphe. Les deux boivent **la même ingestion**. Si tu lances GraphRAG avant d'avoir un texte propre + de bons chunks, tu paieras un LLM pour extraire des entités depuis de l'OCR pourri.

```text
  SEMAINE 1–2     Ingestion : Docling + Paddle (scans) + stockage fichiers
  SEMAINE 3       Chunking structure + BGE-M3 + Qdrant + Postgres
  SEMAINE 4       Hybride + rerank + citations + 20 questions d'or
  SEMAINE 5       Workflow LangGraph (8 étapes) + génération de section
  SEMAINE 6+      Extraction graphe → Neo4j (même corpus, déjà propre)
```

Le graphe **n'est pas un autre RAG de remplacement**. C'est un **deuxième index** pour : « qui est lié à qui », conformité (exigence → certification / projet), questions transverses. Le quotidien (clause, référence, paragraphe de méthodologie) reste **hybride + rerank**.

---

## 3. Ingestion : PaddleOCR n'est pas le point d'entrée

Un appel d'offres réel = **mélange**.

| Fichier | Cas | Outil |
|---------|-----|-------|
| CCTP / CCAP PDF « Save as PDF » | Texte extractible | **Docling uniquement** |
| Mémoire technique DOCX | Natif | **Docling** |
| DPGF / BPU XLSX | Tableur | **openpyxl** → lignes structurées en Postgres, **pas** un chunk prose |
| Scan de pièce admin, tampon, fax | Image | **PaddleOCR PP-StructureV3** (layout + table) |
| Plan / photo | Peu de texte | OCR optionnel + légende ; souvent hors RAG texte |

### 3.1 Routage (obligatoire)

```text
PDF
 ├─ nb_caractères_extraits / nb_pages  >  seuil  →  Docling (digital)
 └─ sinon                                →  rendu page (300 dpi) → PaddleOCR
```

Paddle sur un PDF digital **casse** souvent les tableaux déjà parfaits et coûte du GPU pour rien.

### 3.2 Pourquoi Paddle et pas Tesseract

Tesseract lit une ligne propre. Un DAO a des **colonnes, en-têtes, tableaux de critères, tampons**. PP-Structure sort : blocs, rôles (title / table / text), cellules. C'est du **document understanding**, pas de l'OCR isolé.

### 3.3 Sortie unique d'ingestion (contrat)

Quel que soit l'outil, tout fichier devient :

```text
{
  file_id, hash, doc_type,         # RC | CCTP | CCAP | memoire | reference | scan
  pages: [
    { page, markdown, blocks[], tables[] }
  ],
  heading_tree: [...],             # titres détectés
  ocr_used: true|false,
  ocr_confidence_avg: 0.0-1.0
}
```

Markdown + tableaux en Markdown / HTML. C'est **ça** qu'on chunk, pas le PDF binaire.

Seuil : page OCR < 0.7 de confiance → flag `needs_review`, on n'indexe pas en silence.

---

## 4. Chunking (avant tout embedding)

### 4.1 Méthode retenue : structure d'abord, fenêtre ensuite

**1. Découper sur la structure** que Docling / Paddle a déjà vue :

- `#` / `##` / `Article 12` / `12.1` / `Article 12.2`
- une **table** = **un chunk** (plus éventuellement 1 chunk « légende + en-têtes »)
- une **fiche de référence chantier** = un chunk (unité métier)

**2. Si un article dépasse ~800 tokens :** recursive split (`\n\n` → `\n` → `. `) avec **overlap 15 %**.

**3. Parent-child :**

```text
  PARENT  = section / article entier (jusqu'à ~1500 tokens)  → envoyé au LLM
  CHILD   = alinéa / sous-article (~250–400 tokens)          → embeddé / cherché
```

Tu cherches « pénalité collectivités » sur le child précis ; le LLM lit l'article **avec l'exception**.

**4. Préfixe obligatoire dans le texte embeddé** (pas seulement en metadata) :

```text
[Pièce: CCAP] [Article 8 — Pénalités] [Page 14]
Exception : les collectivités publiques relèvent du taux directeur BCE.
```

Sans ça, le vecteur ignore le titre.

### 4.2 Ce qu'on ne fait pas en V1

| Méthode | Verdict V1 |
|---------|------------|
| Fenêtre fixe 500 caractères | Non (casse les articles) |
| Semantic chunking (coupe au cosine) | Non (instable sur listes / tableaux juridiques) |
| Contextual Retrieval (LLM par chunk) | V1.5 si recall faible sur chunks orphelins |
| Late chunking | Plus tard (besoin d'un encodeur long-context) |
| 1 vecteur pour tout le PDF | Jamais |

### 4.3 Metadata sur chaque child

`tender_id`, `source_file`, `doc_type`, `heading_path`, `page`, `article_id`, `parent_id`, `year`, `lot`, `acl`, `ocr_used`, `hash`.

Filtres **avant** le Top-K : « seulement CCAP 2024+ de ce tenant ».

---

## 5. Embeddings et recherche hybride

### 5.1 Pourquoi BGE-M3

- Entraîné **multilingue** (français des DAO OK).
- Sort **dense + sparse** (lexical appris) + option late-interaction.
- Un seul modèle pour l'index et la requête (mêmes prefixes `query` / `passage` si la carte le demande).
- Self-host : pas de re-embed payant à chaque essai.

Alternative API si tu refuses de servir un modèle : `voyage-multilingual-2` ou `text-embedding-3-large` **plus** un vrai BM25 (Qdrant / Tantivy). Moins élégant.

**Règle :** changer de modèle = **re-embedder tout**. On fige BGE-M3.

### 5.2 Reranker

`BAAI/bge-reranker-v2-m3` : question + chunk **ensemble** → score 0–1.  
Retriever : Top-50. Rerank : Top-8. Puis parent-child : remplacer les children par leurs parents (dédupliqués), plafond ~3–4 k tokens de contexte.

### 5.3 Chaîne de recherche (chaque exigence / question)

```text
q
 → (option) rewrite LLM si deixis (« ça », « le dernier »)
 → en parallèle :
      Qdrant dense (BGE-M3)
      Qdrant sparse / BM25
      Postgres SQL si type=certification|montant|effectif
 → filtres metadata
 → RRF
 → rerank
 → parents + numéros [1]..[k]
 → prompt d'ancrage
 → LLM
```

C'est **l'Advanced RAG** que tu as étudié. C'est le standard de prod. Pas de graphe ici.

---

## 6. GraphRAG : comment on l'ajoute sans tout casser

### 6.1 Quand

Dès que 50+ dossiers sont **correctement** indexés en hybride et que tu as un golden set. Pas avant.

### 6.2 Quoi extraire (schéma fermé, pas un graphe Wikipedia)

Nœuds : `AppelOffres`, `Lot`, `Exigence`, `Entreprise`, `Projet`, `Certification`, `Equipement`, `Personne`, `Client`, `Piece`.

Arêtes typées seulement :

```text
AO -CONTIENT-> Exigence
Exigence -SATISFAITE_PAR-> Projet | Certification | Equipement | Personne
Entreprise -A_REALISE-> Projet
Entreprise -DETIENT-> Certification
Projet -POUR-> Client
```

Un LLM (sortie JSON Pydantic) lit **chaque parent** (pas chaque micro-child) et remplit ce schéma. Entity resolution : même `SIRET`, même nom normalisé → un nœud.

### 6.3 Requête

- **Locale** : « qui héberge / quelle certif couvre l'exigence X » → Cypher 1–2 hops + extraits source.
- **Globale** : plus tard (Leiden + résumés). Pas obligatoire pour rédiger une section d'offre.

### 6.4 On n'utilise pas Microsoft GraphRAG « officiel » en V1

Trop d'appels LLM, communautés génériques. **LightRAG** ou **extraction contrainte + Neo4j** suffit. Même idée, 10× moins cher.

---

## 7. Architecture complète (à coder)

```text
                         [UI : dépôt DAO + revue section + export]
                                          |
                                     FastAPI
                                          |
                    ┌─────────────────────┼─────────────────────┐
                    │                     │                     │
              POST /ingest          POST /run-ao           GET /trace
                    │                     │                     │
                  Redis/ARQ          LangGraph                  │
                    │                     │                     │
         ┌──────────┴──────────┐          │                     │
         v                     v          v                     v
      Docling            PaddleOCR    Analyse exigences     Logs
         │                     │      Recherche hybride
         └──────────┬──────────┘      Contexte + LLM
                    v                 Validateur schéma
         chunks + markdown            HITL
                    │
     ┌──────────────┼──────────────┐
     v              v              v
  PostgreSQL     Qdrant         Neo4j
  (métier,       (dense+        (phase 1.5
   ACL,           sparse)        entités)
   versions)
     │
     fichiers bruts (MinIO / disque)
```

### Contrats Pydantic (minimum)

- `DocumentIngested`
- `Chunk` / `ParentChunk`
- `Exigence` (id, libellé, type, obligatoire, page_source, statut)
- `ExtraitCite` (chunk_id, score, page, texte)
- `SectionGeneree` (titre, markdown, citations[], exigences_couvertes[])
- `DecisionHumaine` (approuve | edit | regen)

Le LLM **n'écrit pas** un pavé libre : il remplit `SectionGeneree`.

---

## 8. Workflow LangGraph (rappel V1, 8 nœuds)

1. Réception DAO (ingest async, attendre fin)
2. Extraction d'exigences (LLM + schéma, fenêtre longue **sur le DAO courant seulement**)
3. Pour chaque exigence : hybride (+ SQL si fiche) ; plus tard + Cypher
4. Assembleur de contexte (plafond tokens, parents, consignes anti-hallucination)
5. Génération **une section à la fois**
6. Validateur déterministe (schéma, citations existantes, obligatoires sans preuve → échec)
7. Revue humaine (interrupt LangGraph)
8. Export DOCX/PDF + version

Retour borné : validateur → génération (max 2 essais). Pas de boucle agent.

---

## 9. Stack packagée (versions d'esprit)

```text
Python 3.12
docling
paddleocr / paddlepaddle-gpu     # uniquement workers OCR
qdrant-client
pgvector / psycopg               # SQLAlchemy
neo4j                            # à partir de la phase graphe
langgraph + langchain-core
pydantic v2
fastapi + uvicorn
arq + redis
sentence-transformers            # BGE-M3 + reranker
python-docx / weasyprint         # export
```

GPU : **utile** pour Paddle + BGE-M3 + rerank en local. Sans GPU : embeddings/rerank sur CPU (plus lent) ou API d'embeddings ; Paddle CPU possible mais pénible sur 200 pages scannées.

---

## 10. Protocole pour ne pas coder à l'aveugle

Dès 10 dossiers réels :

1. 30 exigences / questions d'or avec `source_page`.
2. Mesurer **Recall@20** : dense seul vs BM25 seul vs hybride vs hybride+rerank.
3. Mesurer fidélité des sections (phrase ↔ extrait).
4. Seulement **après** : ouvrir Contextual Retrieval ou le graphe, **un levier à la fois**.

Si Recall@20 hybride < 0.7 : le problème est l'**ingestion / chunking**, pas le LLM.

---

## 11. Réponses directes à tes questions

**On va vers du RAG hybride Advanced ?**  
Oui. C'est le cœur. BM25 (ou sparse BGE-M3) + dense + RRF + rerank + citations.

**Et GraphRAG ?**  
Oui dans **la même plateforme**, deuxième index, **après** un corpus propre. Neo4j + extraction contrainte. Pas Microsoft GraphRAG jour 1.

**PaddleOCR ?**  
Oui **pour les scans**, dans PP-Structure (layout + tables). **Non** comme pipeline unique. Docling d'abord sur tout ce qui est déjà du texte.

**Comment chunker ?**  
Articles / titres / une table = un chunk ; parent-child 250–400 / jusqu'à 1500 ; overlap 15 % ; préfixer le heading dans le texte embeddé.

**Quel embed ?**  
BGE-M3 figé. Reranker BGE-v2-m3.

**Techno complète ?**  
Docling + Paddle → Postgres + Qdrant (+ Neo4j) → LangGraph + Pydantic + FastAPI + ARQ → LLM contraint → humain → DOCX/PDF.

**Pourquoi cette stack et pas « tout LangChain + Chroma » ?**  
Parce que le métier a des **fiches** (SQL), des **identifiants** (BM25), du **sens** (dense), des **scans structurés** (Paddle), et plus tard des **liens** (graphe). Un seul vecteur store + un chatbot ne porte pas un dossier d'offre.
