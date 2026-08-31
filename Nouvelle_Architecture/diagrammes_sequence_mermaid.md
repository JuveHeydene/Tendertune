# Diagrammes de séquence V2 (Mermaid) — Horloge A, Horloge B, sous-processus

> **Format** : Mermaid `sequenceDiagram`, pas PlantUML — s'affiche directement dans la plupart des visionneuses Markdown (GitHub, VS Code avec l'extension Mermaid, etc.), sans outil externe. Équivalent complet de `diagrammes_sequence_v2.txt` (PlantUML), même contenu, syntaxe différente.
> **À lire avec** : `architecture_agentique_retrieval_generation.md` et `base_de_donnees_et_interface.md` — ces diagrammes illustrent ce qui y est décrit en détail, section par section.

---

## 0. Vue d'ensemble — croquis ASCII des deux horloges

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                         NAVIGATEUR (React / Vite)                        │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │ HTTP / SSE
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    FastAPI  (backend_ao/app)                              │
└───────────────┬─────────────────────────────────────┬───────────────────┘
                │                                     │
     HORLOGE A (async, jobs)              HORLOGE B (sync / stream, agentique)
                │                                     │
                ▼                                     ▼
     Redis + worker ARQ                      Superviseur (LLM, §8)
     ingest_document                         │
     extract_graph                           ├─ intent = smalltalk/export → déterministe
     extract_dossier_structure               ├─ intent = clarification_needed → message
                │                            └─ intent = hybrid_rag | run_section
                ▼                                     │
     MinIO → parse → classify                         ▼
     → chunk (parent/enfant)              Dispatch sous-questions EN PARALLÈLE
     → Postgres + Qdrant                  → Experts (juridique/technique/
     → Neo4j (extraction graphe)             financier/graphe/patrimoine)
                │                          → Boucle CRAG bornée (max_iter=3)
                ▼                                     │
     outline_items / exigences /                      ▼
     dossier_pieces (extraction §9)        Agrégation (retrieval/abstention/
                                            conversation, §5.4)
                                                       │
                                                       ▼
                                            Génération par archétype (§10)
                                            → SectionGeneree JSON validé
                                                       │
                                                       ▼
                                            HITL (approve/edit/regen) → export
```

Table de correspondance rapide (quel diagramme répond à quelle question) :

| # | Diagramme | Répond à |
|---|---|---|
| 1 | Horloge A détaillée | Comment un fichier (PDF/DOCX/XLSX/**image**) devient des chunks cherchables + un graphe ? |
| 2 | Superviseur / routage | Comment une question est classée, décomposée, routée vers les experts ? |
| 3 | Boucle CRAG | Comment UN expert cherche, juge, corrige, ou abandonne (abstention) ? |
| 4 | Expert Graphe | Comment Neo4j est enfin lu en horloge B ? |
| 5 | Extraction exigences/outline/pièces | Comment `exigences`, `outline_items`, `dossier_pieces` sont remplis ? |
| 6 | Génération + HITL | Comment le texte final est écrit, validé, revu par un humain ? |

---

## 1. Horloge A — Ingestion détaillée (PDF / DOCX / XLSX / IMAGE)

```mermaid
sequenceDiagram
    autonumber
    actor User as Utilisateur
    participant UI as Interface Web
    participant API as API / Passerelle
    participant Queue as File d'attente (Redis/ARQ)
    participant Worker as Worker d'ingestion
    participant Parser as Compréhension docs<br/>(Docling/PaddleOCR/pypdf)
    participant Classifier as Classificateur<br/>section_type
    participant RelDB as Postgres
    participant VecDB as Qdrant + FTS
    participant GraphDB as Neo4j

    Note over User,GraphDB: Étape 1 — Téléversement synchrone
    User->>UI: Envoie un fichier (DAO, patrimoine, annexe, pièce admin)
    activate UI
    UI->>API: POST /documents (fichier + doc_role + dossier_id si annexe)
    activate API
    API->>API: Valide droits, tenant, cohérence doc_role/dossier_id
    API->>RelDB: SHA-256, vérifie doublon
    RelDB-->>API: nouveau OU document existant

    alt Doublon détecté
        API-->>UI: document existant (pas de ré-ingestion)
    else Nouveau document
        API->>RelDB: INSERT documents(status="pending")
        RelDB-->>API: document_id
        API->>Queue: enqueue ingest_document(document_id)
        Queue-->>API: accusé
    end
    API-->>UI: { document_id, status }
    deactivate API
    UI-->>User: "Document reçu, traitement en cours"
    deactivate UI

    Note over Worker,GraphDB: Étape 2 — Routage du format (asynchrone)
    activate Worker
    Worker->>Queue: consomme ingest_document
    Queue-->>Worker: document_id
    Worker->>RelDB: status = "processing"

    alt PDF numérique (densité ≥ 40 car/page)
        Worker->>Parser: Docling → markdown structuré
        Parser-->>Worker: pages structurées
    else PDF scan (densité < 40 car/page)
        Worker->>Parser: rasterise (PyMuPDF) → PaddleOCR
        Parser-->>Worker: texte OCR + confiance
    else DOCX / XLSX
        Worker->>Parser: python-docx / openpyxl
        Parser-->>Worker: contenu structuré (ou lignes SQL)
    else IMAGE (.jpg/.png/.tiff/.webp) — NOUVEAU V2
        Worker->>Parser: PaddleOCR direct (pas de rasterisation)
        Parser-->>Worker: texte OCR (peut être vide)
        Note right of Worker: Bug V1 corrigé : le moteur OCR supportait déjà<br/>l'image, seul le routage manquait (§5.1)
        alt Texte OCR ≥ 40 caractères
            Worker->>Worker: traité comme un scan normal
        else Texte OCR < 40 car. ou absent
            Worker->>Worker: marqué "actif visuel" (0 chunk, PAS un échec)
        end
    else Format non supporté
        Worker->>RelDB: status = "failed"
    end

    Note over Worker,GraphDB: Étape 3 — Découpage, classification, indexation
    Worker->>Worker: chunk_document() — parent (≤8000 car.) + enfants (1100/overlap 120)

    loop Pour chaque chunk PARENT — NOUVEAU V2
        Worker->>Classifier: classify_section_type(parent)
        activate Classifier
        Classifier->>Classifier: Couche 1 — heuristique (titres canoniques RC/CCAP/CCTP/DPGF/BPU)
        alt Mot-clé canonique trouvé
            Classifier-->>Worker: section_type (méthode="heuristic")
        else Aucun mot-clé trouvé
            Classifier->>Classifier: Couche 2 — LLM JSON contraint (TOUS les parents restants)
            Classifier-->>Worker: section_type (méthode="llm")
        end
        deactivate Classifier
    end
    Note right of Classifier: section_type = signal DOUX,<br/>jamais un filtre bloquant (§3.1)

    Worker->>RelDB: REPLACE chunks (parents + enfants + section_type)
    Worker->>VecDB: embed + upsert (dense) + index sparse (Postgres FTS)
    Worker->>RelDB: status = "ready"
    Note over Worker,RelDB: ✅ RAG hybride disponible immédiatement

    Note over Worker,GraphDB: Étape 4 — Extraction du graphe (non bloquante)
    Worker->>RelDB: charge TOUS les parents (pas de limite à 12 — bug V1 corrigé)
    RelDB-->>Worker: liste des parents

    loop Pour chaque parent
        Worker->>Worker: extraction LLM entités/relations (JSON contraint, types fermés)
        Worker->>Worker: fuzzy_resolve_entity() — exact→Levenshtein→Jaccard→embedding
        Worker->>GraphDB: MERGE Entity + REL
    end
    Worker->>RelDB: graph_extracted = true
    deactivate Worker
    Note over User,GraphDB: ✅ Horloge A terminée
```

---

## 2. Horloge B — Superviseur, décomposition, routage

```mermaid
sequenceDiagram
    autonumber
    actor User as Rédacteur
    participant UI as Interface Web
    participant API as API (SSE)
    participant Rewrite as Nœud Rewrite
    participant Sup as Superviseur<br/>(Router + Décomposition)
    participant DB as Postgres
    participant Experts as Pool d'Experts<br/>(cf. Diagramme 3)
    participant Agg as Agrégateur
    participant Gen as Générateur<br/>(cf. Diagramme 6)

    User->>UI: Tape un message
    UI->>API: POST /conversations/{id}/messages/stream
    activate API
    API->>DB: INSERT messages(role="user")
    API->>DB: charge historique court + résumé dossier (summary_short)
    Note right of DB: messages = fil de dialogue (chemin 1)<br/>generations.summary_short = progression<br/>du dossier, PRÉCALCULÉE à l'approve (chemin 2)

    API->>Rewrite: rewrite_query(historique, texte_brut)
    Rewrite-->>API: query_clean
    API->>DB: UPDATE messages.query_rewrite

    API->>Sup: 1 appel LLM JSON contraint (query_clean + historique)
    activate Sup
    Note right of Sup: intent ∈ {smalltalk, export,<br/>clarification_needed, hybrid_rag, run_section}<br/>Règles R1-R10 : voir §8

    alt is_compound = true (règles R1-R3, max 4 sous-questions)
        Sup->>Sup: découpe en sous_questions[] (chacune complète et autonome)
    else is_compound = false
        Sup->>Sup: 1 seule sous-question
    end

    loop Pour chaque sous-question
        Sup->>Sup: assigne experts[] (0 à 5) et complexite
        Note right of Sup: experts=[] est VALIDE (règle R9) :<br/>contenu déjà fourni par l'utilisateur<br/>→ source="conversation", PAS une abstention
    end
    Sup-->>API: JSON { intent, is_compound, sous_questions[] }
    deactivate Sup
    API->>DB: messages.meta = sortie du Superviseur

    alt intent = smalltalk
        API-->>UI: réponse fixe (déterministe)
    else intent = export
        API-->>UI: déclenche l'export (déterministe)
    else intent = clarification_needed
        API-->>UI: message_clarification
    else intent = hybrid_rag OU run_section
        par Chaque sous-question EN PARALLÈLE
            alt experts non vide
                API->>Experts: boucle CRAG bornée (Diagramme 3)
                Experts-->>API: contexte gradé OU abstention
            else experts = []
                API->>API: source = "conversation" (règle R9, pas d'appel)
            end
        end
        API->>Agg: fusionne tous les résultats
        activate Agg
        Agg-->>API: contexte agrégé + abstentions
        deactivate Agg
        API->>Gen: génère la section (Diagramme 6)
        Gen-->>API: SectionGeneree JSON
    end
    API-->>UI: flux SSE (tokens, preview, done)
    deactivate API
    UI-->>User: affiche la réponse / section
```

---

## 3. Boucle CRAG bornée (pour UN expert)

```mermaid
sequenceDiagram
    autonumber
    participant Orch as Superviseur/Orchestrateur
    participant Expert as Expert<br/>(juridique|technique|financier|patrimoine)
    participant VecDB as Qdrant (dense)
    participant FTS as Postgres FTS (sparse)
    participant Rerank as Reranker
    participant Grade as Évaluateur (grading)
    participant Traces as retrieval_traces

    Orch->>Expert: sous_question.texte, filtres (section_type + doc_role)
    activate Expert

    Note over Expert: Adaptive — décision AVANT toute recherche (§5.1)
    alt complexite = "simple"
        Expert->>VecDB: retrieve_dense(query, filtres, top_k=8)
        VecDB-->>Expert: Top-8
        Expert->>FTS: retrieve_sparse(query, filtres, top_k=8)
        FTS-->>Expert: Top-8
        Expert->>Rerank: fusion RRF + rerank
        Rerank-->>Expert: Top-8 ordonné
        Note right of Expert: PAS de grading ici — 1 seule passe,<br/>on fait confiance au Top-8 (§5.1)
        Expert->>Traces: INSERT trace (grade=null, méthode=null)
        Expert-->>Orch: contexte (source="retrieval")
    else complexite = "complexe"
        loop tentative = 1 à 3 (max_iter)
            par Recherche hybride en parallèle
                Expert->>VecDB: retrieve_dense(query, filtres, top_k=50)
                VecDB-->>Expert: 50 candidats
            and
                Expert->>FTS: retrieve_sparse(query, filtres, top_k=50)
                Note right of FTS: Index inversé (tsvector/GIN) —<br/>PAS un scan complet
                FTS-->>Expert: 50 candidats
            end
            Expert->>Rerank: fusion RRF (même granularité : enfants) + rerank
            Rerank-->>Expert: Top-8

            Expert->>Grade: grade_context(query, Top-8)
            activate Grade
            Grade->>Grade: seuil de score (>0.7 / 0.3-0.7 / <0.3)
            alt zone grise (0.3-0.7)
                Grade->>Grade: LLM-juge (1 appel, seulement ici)
            end
            Grade-->>Expert: Correct | Ambigu | Incorrect
            deactivate Grade

            Expert->>Traces: INSERT trace (expert, tentative, grade, chunks)

            alt grade = Correct
                Expert->>Expert: sort de la boucle (succès)
            else grade = Ambigu
                Expert->>Expert: ÉLARGIR (drop section_type, drop doc_role, top_k↑)
            else grade = Incorrect
                Expert->>Expert: REFORMULER (rewrite variante, multi-query)
            end
        end

        alt une tentative a réussi
            Expert-->>Orch: contexte gradé (source="retrieval")
        else 3 tentatives épuisées
            Expert->>Traces: INSERT trace (abstention=true)
            Note right of Expert: { found:false, reason, tentatives:3 }<br/>PAS de génération sur du vide
            Expert-->>Orch: abstention (source="abstention")
        end
    end
    deactivate Expert
```

---

## 4. Expert Graphe — résolution d'entités + Cypher

```mermaid
sequenceDiagram
    autonumber
    participant Orch as Superviseur
    participant ExpertG as Expert Graphe
    participant LLM as LLM Extracteur d'entités
    participant Fuzzy as Résolveur Fuzzy<br/>(réutilisé horloge A)
    participant GraphDB as Neo4j
    participant RelDB as Postgres

    Orch->>ExpertG: sous_question.texte
    activate ExpertG
    ExpertG->>LLM: extract_query_entities(query) — JSON contraint
    LLM-->>ExpertG: [{name, type_hint}, ...]

    loop Pour chaque entité extraite
        ExpertG->>Fuzzy: fuzzy_resolve_entity(name, type_hint, tenant_id)
        Fuzzy->>Fuzzy: exact → Levenshtein ≥85 → Jaccard ≥80 → embedding ≥0.82
        Fuzzy-->>ExpertG: clé canonique OU "non résolu"
    end

    alt Aucune entité résolue
        ExpertG->>ExpertG: court-circuit immédiat (grading trivial = Incorrect)
        ExpertG-->>Orch: abstention
    else Au moins 1 entité résolue
        ExpertG->>ExpertG: sélectionne un TEMPLATE Cypher fixe<br/>(1-hop | 1-2 sauts typés | 2 ancres)
        Note right of ExpertG: Jamais de Cypher généré librement par le LLM —<br/>le CODE construit la requête à partir de templates
        ExpertG->>GraphDB: exécute le template paramétré
        GraphDB-->>ExpertG: relations trouvées

        alt Relations trouvées
            ExpertG->>RelDB: SELECT text, page FROM chunks WHERE id = source_chunk_id
            RelDB-->>ExpertG: texte source (pour citation)
            ExpertG-->>Orch: { relations[], chunks_source[] } (source="retrieval")
        else Rien trouvé malgré entités résolues
            ExpertG->>ExpertG: élargir le hop (1→2) avant abandon
            ExpertG-->>Orch: abstention si toujours rien
        end
    end
    deactivate ExpertG
```

*Ce diagramme active la lecture de Neo4j en horloge B — écrit en horloge A (Diagramme 1, étape 4), jamais lu jusqu'ici.*

---

## 5. Alimentation exigences / outline_items / pièces administratives

```mermaid
sequenceDiagram
    autonumber
    participant Worker as Worker<br/>(extract_dossier_structure)
    participant RelDB as Postgres
    participant LLM as LLM Extracteur
    participant Fuzzy as Résolveur Fuzzy
    participant Expert as Expert Patrimoine<br/>+ Boucle CRAG (Diagramme 3)

    Note over Worker,RelDB: Déclenchement — job déterministe, style horloge A
    RelDB->>Worker: DAO status="ready" + dossiers.dao_document_id renseigné
    activate Worker
    Worker->>RelDB: dossiers.status = "analyzing"

    Note over Worker,LLM: Étape A — extract_outline (déterministe)
    Worker->>RelDB: charge chunks WHERE section_type='rc'
    RelDB-->>Worker: chunks du RC
    alt Passage structurel trouvé ("le mémoire technique comprendra...")
        Worker->>LLM: extrait la liste ordonnée de titres
        LLM-->>Worker: outline[] structuré
    else Rien trouvé
        Worker->>Worker: fallback DEFAULT_OUTLINE (canevas 8 sections)
    end
    Worker->>RelDB: INSERT outline_items(status="todo", archetype=...)

    Note over Worker,Fuzzy: Étape B — extract_exigences (déterministe)
    Worker->>RelDB: charge TOUS les parents du DAO (pas de limite à 12)
    RelDB-->>Worker: parents
    loop Pour chaque lot de parents
        Worker->>LLM: extrait exigences (JSON contraint)
        LLM-->>Worker: exigences brutes
    end
    Worker->>Fuzzy: dédup des exigences répétées (RC et CCAP se répètent souvent)
    Fuzzy-->>Worker: exigences dédupliquées
    Worker->>RelDB: INSERT exigences(statut="a_couvrir")

    Note over Worker,RelDB: Étape C — checklist administrative (§5.3)
    Worker->>RelDB: cherche pièces demandées dans le RC, sinon liste standard
    Worker->>RelDB: INSERT dossier_pieces (statut='trouve_patrimoine' si déjà en patrimoine)
    Worker->>RelDB: dossiers.status = "generating"
    deactivate Worker

    Note over RelDB,Expert: Étape D — couverture, AGENTIQUE (réutilise Diagramme 3 tel quel)
    loop Pour chaque exigence "a_couvrir"
        RelDB->>Expert: query = exigence.libelle
        activate Expert
        Expert->>Expert: Expert Patrimoine + boucle CRAG (max_iter=3)
        alt grade = Correct
            Expert->>RelDB: UPDATE exigences statut="couverte", preuves_chunks=[...]
        else Abstention après 3 tentatives
            Expert->>RelDB: UPDATE exigences statut="non_couverte"
            Note right of Expert: Si obligatoire=true → alerte visuelle<br/>prioritaire côté UI (risque d'élimination)
        end
        deactivate Expert
    end
```

---

## 6. Génération par archétype, validation, HITL

```mermaid
sequenceDiagram
    autonumber
    actor User as Rédacteur
    participant UI as Interface Web
    participant Agg as Agrégateur
    participant Gen as Générateur
    participant RelDB as Postgres
    participant Valid as Validateur<br/>(déterministe)

    Note over Agg,RelDB: Étape 1 — Préparation du prompt
    Agg->>RelDB: lit outline_items.archetype
    RelDB-->>Agg: archetype (institutionnelle|factuelle|narrative|conformite)
    Note right of Agg: Lookup DÉTERMINISTE — outline_items.key est<br/>déjà connu, aucune décision d'agent nécessaire (§10)

    Agg->>Gen: historique + résumé dossier + contexte agrégé + abstentions + prompt spécialisé
    activate Gen
    Note over Gen: Étape 2 — Génération (1 seul appel, JSON contraint)
    Gen->>Gen: construit SectionGeneree {titre, blocs[], citations[], exigences_couvertes[], abstentions[]}
    Note right of Gen: Un bloc peut être type="image" (document_id) —<br/>le générateur peut SUGGÉRER via retrieve_images(),<br/>mais ne place JAMAIS l'image seul (§5.4)
    Gen-->>Agg: SectionGeneree JSON
    deactivate Gen

    Note over Agg,Valid: Étape 3 — Validation déterministe
    Agg->>Valid: valide le JSON
    activate Valid
    Valid->>Valid: citations existent ? pas de H1 inventé ? bloc image → document_id connu ?
    alt Validation échoue
        Valid-->>Agg: échec (max 2 essais)
        Agg->>Gen: retry avec correction
    else Validation OK
        Valid-->>Agg: OK
    end
    deactivate Valid

    Agg->>RelDB: INSERT generations(version, content, citations, abstentions)
    Agg->>RelDB: outline_items.status = "generated"
    Agg-->>UI: section générée
    UI-->>User: affiche pour revue (citations attribuées par expert, abstentions explicites)
    Note right of UI: ⚠️ affiché SEULEMENT si source="abstention"<br/>— jamais si source="conversation" (§5.4)

    Note over User,RelDB: Étape 4 — Décision humaine (HITL)
    User->>UI: Approuve / Modifie / Régénère
    UI->>RelDB: INSERT reviews(action, comment, regen_instruction)

    alt action = approve
        UI->>RelDB: outline_items.status = "approved"
        UI->>RelDB: génère generations.summary_short (1 fois, précalculé)
        Note right of RelDB: Résumé PRÉCALCULÉ ici, jamais recalculé<br/>à chaque question (§2.3)
    else action = regen
        UI->>Agg: relance avec regen_instruction
        Agg->>Agg: retour à l'Étape 1 (nouvelle recherche si nécessaire)
    else action = edit
        UI->>RelDB: sauvegarde texte humain, status = "approved"
    end
```

---

## Liens

- `Nouvelle_Architecture/architecture_agentique_retrieval_generation.md` — texte complet référencé par ces diagrammes (§ citées dans les notes)
- `Nouvelle_Architecture/base_de_donnees_et_interface.md` — schéma DB et interface associés
- `Nouvelle_Architecture/diagrammes_sequence_v2.txt` — même contenu en PlantUML (couleurs, légendes détaillées), pour l'export figure du mémoire LaTeX
