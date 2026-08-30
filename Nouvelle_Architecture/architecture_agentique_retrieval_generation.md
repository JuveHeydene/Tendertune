# Architecture agentique V2 — Récupération, mémoire, génération (détail d'implémentation)

> **Statut** : document de conception, à valider avant tout code. Rien ici n'est encore implémenté.
> **Portée** : ce document couvre uniquement l'horloge B (question → réponse), plus les outils partagés avec l'horloge A (fuzzy matching). L'indexation (horloge A) reste hors-sujet ici sauf pour les points communs.
> **Décisions déjà actées** (session précédente) :
> - `max_iter = 3` pour la boucle de récupération agentique.
> - Architecture cible = SMA (superviseur + agents experts), cf. `Fichier/architecture_synthese.md` pour la V1 et la discussion précédente pour le choix du pattern multi-agents.
> - Mémoire long terme façon Mem0 = **hors périmètre V2**, gardée comme perspective. Ce document explique pourquoi (§2).
> **Sources réutilisées** : `Fichier/pipeline_technique_detaille.md`, `Fichier/diagrammes_sequence_workflow.md`, `Fichier/comprehension personnele du projets.md`, et le vocabulaire des fiches personnelles `~/Lectures/IA/RAG/` (07, 08, 10) et `~/Lectures/IA/IA_Agentique/` (01, 10, 11) — cité par numéro de fiche quand pertinent.

---

## 0. Vue d'ensemble : ce qui change vs V1

```text
V1 (actuelle)                          V2 (ce document)
--------------                         ----------------
route = if/else sur mots-clés          route = superviseur LLM (adaptive)
retrieve = dense seul, 1 passe         retrieve = hybride (dense+sparse+RRF+rerank),
                                        borné, avec grading et abstention explicite
Neo4j jamais lu en horloge B           Neo4j lu via un agent "expert graphe"
query_rewrite = colonne inutilisée     rewrite = nœud actif, avant tout retrieve
1 seul retrieve pour toute la demande  1 retrieve par expert sollicité, en parallèle
pas de mémoire de dossier en génération contexte de génération enrichi (dossier + section en cours)
```

Rien de cette liste ne remplace le principe fondateur de la V1 (« pas d'agent partout, le code déterministe reste la règle par défaut ») — on **ajoute** de l'agentique uniquement là où une seule recherche peut légitimement échouer.

---

## 1. Séquence complète, message par message

Réponse directe à *« c'est à chaque fois que le user pose une question qu'on fait le retrieval ? »* — oui, exactement, et voici la séquence exacte, sans zone floue :

```text
 1. Message utilisateur arrive (SSE ou sync)
      │
 2. INSERT messages(role=user, content=texte_brut)
      │
 3. Charger le contexte de conversation (§2) :
      - historique court (≤8 tours, Postgres messages)
      - SI conversation liée à un dossier : résumé de progression du dossier (§2.3)
      │
 4. NŒUD REWRITE (1 appel LLM, cf. RAG-08 §3)
      entrée  : historique court + texte_brut
      sortie  : query_clean  (déixis résolue, identifiants préservés)
      → écrit dans messages.query_rewrite (la colonne existe déjà, enfin utilisée)
      │
 5. NŒUD SUPERVISEUR / ROUTER (1 appel LLM, JSON contraint, température 0)
      entrée  : query_clean + historique court
      sortie  : { intent, is_compound: bool,
                  sous_questions: [{texte, experts[], complexite}] ≤4,
                  message_clarification? }
      → is_compound, la décomposition ET la complexité par
        sous-question sont détectés DANS ce même appel, pas des
        nœuds LLM séparés — spécification complète du prompt : §8
      │
      ├── intent = smalltalk  → réponse fixe, FIN (déterministe, pas de retrieval)
      ├── intent = export     → export, FIN (déterministe, pas de retrieval)
      ├── intent = clarification_needed → renvoyer message_clarification
      │                                    à l'utilisateur, FIN (§8, garde-fou >4)
      └── intent = hybrid_rag | run_section
                │
                ▼
 6. Pour CHAQUE (sous-question × expert sollicité), en parallèle :
      → boucle de récupération bornée (CRAG, détail §5)
      → produit soit un contexte gradé "suffisant", soit une abstention explicite
      │
 7. AGRÉGATEUR : fusionne les contextes de TOUTES les sous-questions
      et de tous les experts + les abstentions (détail §5.5)
      │
 8. NŒUD GENERATE (1 appel LLM, JSON contraint — inchangé dans son principe)
      entrée : historique + résumé dossier + contexte agrégé + abstentions + consigne section
      │
 9. NŒUD VALIDATE (déterministe — inchangé : citations existent, pas de H1 inventé)
      │
10. HITL interrupt si section d'offre (inchangé)
      │
11. Persist (messages, generations, reviews — inchangé)
```

Point important sur **l'embedding de la requête** (réponse à *« on va analyser sa requête, on va l'embedder »*) : on embedde **une seule fois** `query_clean` (sortie du rewrite), **pas** le texte brut de l'utilisateur, et **pas** à chaque itération de la boucle — seulement quand la boucle décide de reformuler (§5, cas « Ambigu »/« Incorrect ») est-ce qu'on ré-embedde la nouvelle formulation.

### 1.1 Qui rédige : les experts, ou le générateur ?

Point à lever explicitement, car l'étape 6 pourrait laisser croire que chaque expert produit du texte. **Non** : un « expert » (§1 étape 6, détail §5) est **uniquement un agent de récupération scopé à un domaine** — il choisit ses filtres et ses outils (`section_type IN [ccap, rc]` pour le juridique, `section_type = cctp` pour le technique, `sql_lookup` sur DPGF/BPU pour le financier, `retrieve_graph` pour le graphe), exécute sa boucle CRAG, et remonte soit un contexte gradé « suffisant » (chunks + citations), soit une abstention. **Aucun expert n'écrit de prose.**

*(Note : le scope de chaque expert repose sur `chunks.extra.section_type`, un signal **auto-classifié et doux** — jamais sur le champ manuel `documents.doc_type`, ni sur un filtre bloquant. Détail complet et raison du choix : §3.1.)*

```text
  Expert Juridique  ──┐
  Expert Technique  ──┤
  Expert Financier  ──┼──► contextes bruts + abstentions ──► AGRÉGATEUR ──► GÉNÉRATEUR (1 seul appel)
  Expert Graphe     ──┤                                                     écrit le SectionGeneree JSON
  Expert Patrimoine ──┘
```

Raisons de ce choix (plutôt que « chaque expert rédige son paragraphe, un rédacteur-en-chef fusionne ») :

1. Le contrat `SectionGeneree` est **un seul objet JSON cohérent** (titre figé, `blocs[]`, `citations[]`) — le valider (schéma, citations existantes, pas de H1 inventé) suppose une sortie unique. Fusionner N rédactions parallèles demanderait un appel de fusion supplémentaire, donc une deuxième surface d'hallucination et une validation plus complexe.
2. Principe déjà posé dans `IA_Agentique/10` §1.6/§2.1 : *« tout remonte vers l'agent conversationnel, jamais directement au client — évite les réponses contradictoires entre agents »*. Les experts sont des *planners* au sens de cette fiche : ils ne parlent jamais directement à l'utilisateur ni ne produisent le livrable final.
3. Le « mixture of experts » sert ici à améliorer **où et comment on cherche**, pas **qui rédige** — cohérent avec l'esprit HITL : un humain relit **une** section au style homogène, pas un patchwork de contributions hétérogènes.

---

## 2. Mémoire de conversation : lever l'ambiguïté `messages` vs `generations`

C'est le point que tu as soulevé : *« on peut avoir plusieurs conversations, on va récupérer de la table `generations` via conversation_id pour donner au LLM le contenu de la conversation actuelle ? »*

### 2.1 Pourquoi `generations` n'a **pas** de `conversation_id`

Regarde le schéma (`champsdeBase_et_contraites_workflow.md` §2.6) : `generations` a `dossier_id` + `section_key`, **pas** `conversation_id`. C'est voulu : une section rédigée appartient au **dossier** (l'objet métier « réponse à cet AO »), pas à une conversation précise. Pourquoi c'est important : un même dossier peut être travaillé à travers **plusieurs conversations** (des sessions de chat différentes, à des jours différents), et une conversation peut aussi ne toucher à **aucun** dossier (pure question patrimoine).

```text
  conversations (1) ──dossier_id?──> dossiers (1) ──dossier_id──< generations
        │
        └──(1)──< messages ──generation_id?──> generations
```

Il y a donc **deux chemins** possibles pour retrouver des générations, et ils ne répondent pas à la même question :

| Chemin | Requête | Répond à |
|---|---|---|
| `messages.generation_id → generations` | « quelles générations **cette conversation précise** a-t-elle déclenchées » | Historique de dialogue |
| `conversations.dossier_id → dossiers → generations WHERE status='approved'` | « qu'est-ce qui est **déjà rédigé et validé** dans ce dossier, tous canaux confondus » | Cohérence inter-sections |

### 2.2 Pourquoi il faut les **deux**, pas un seul

Si on ne prend que le chemin 1 (via `messages` de la conversation courante) : le LLM ignore qu'une autre conversation, hier, a déjà fait approuver la section « Moyens matériels » qui dit « nous disposons de 3 grues de 50 t » — et il peut rédiger « Méthodologie » aujourd'hui en contredisant ce chiffre. C'est exactement le trou identifié dans l'analyse précédente (« pas de cohérence inter-sections », V1).

Si on ne prend que le chemin 2 (tout le dossier) sans les messages : le LLM perd le fil du dialogue en cours (« tu disais que tu voulais insister sur le côté ferroviaire, c'est toujours le cas ? »).

**Décision proposée** : les deux, mais pas au même format ni au même volume — sinon explosion du budget de tokens.

### 2.3 Ce qu'on injecte concrètement dans le prompt de génération

```text
┌─────────────────────────────────────────────────────────┐
│ CONTEXTE DE CONVERSATION (chemin 1)                      │
│  - derniers ~8 tours de `messages`, tronqués (~700 car/  │
│    message, règle déjà en place, chat_history.py)        │
├─────────────────────────────────────────────────────────┤
│ RÉSUMÉ DE PROGRESSION DU DOSSIER (chemin 2, si dossier)  │
│  - PAS le texte complet de chaque génération approuvée   │
│  - juste : liste des outline_items avec status +         │
│    1 phrase de synthèse par section approuvée            │
│    (ex. "Références (approuvée) : 3 chantiers ferroviaires,│
│     dont gare de Nantes, grues 50t")                     │
│  - CETTE synthèse peut être un champ précalculé (ex.      │
│    `generations.summary_short`, généré au moment de       │
│    l'approve, PAS régénéré à chaque question — 1 appel LLM│
│    court UNE fois par approve, pas par question)          │
├─────────────────────────────────────────────────────────┤
│ SI regen d'une section déjà existante :                  │
│  - texte COMPLET de la version précédente de CETTE section│
│    (nécessaire pour appliquer la consigne de régénération)│
└─────────────────────────────────────────────────────────┘
```

Le point clé à valider avec toi : le "résumé de progression du dossier" est **précalculé à l'approve**, pas recalculé à chaque question — sinon on paierait un appel LLM de résumé sur chaque tour de chat, ce qui casse la latence pour rien (même logique que l'Adaptive RAG, §5.1 : ne pas payer un coût qu'on peut amortir une fois).

Ceci répond aussi à ta question implicite : ce n'est **pas** une mémoire Mem0 (§11 de tes fiches) — pas de store vectoriel séparé, pas d'extraction LLM générique de « faits ». C'est une agrégation **structurée**, sur des tables qui existent déjà (`messages`, `generations`, `outline_items`), avec un seul champ à ajouter (`generations.summary_short`). C'est pour ça que je maintenais Mem0 hors périmètre V2 : le besoin réel ici est couvert par le schéma relationnel existant, pas par une mémoire sémantique générique.

---

## 3. Boîte à outils horloge A (ingestion) — le fuzzy oublié dans le tour précédent

Tu as raison, la liste précédente ne couvrait que l'horloge B. Voici la boîte à outils horloge A complète, y compris le fuzzy déjà codé :

| Tool | Rôle | Statut |
|---|---|---|
| `parse_file(path)` | Docling / PaddleOCR / pypdf, routage densité | Existant |
| `chunk_document(parsed)` | Découpe parent/enfant | Existant (à améliorer, cf. discussion indexation précédente) |
| `embed_texts(texts[])` | Embeddings Ollama | Existant |
| `extract_entities_relations(chunk_text)` | LLM JSON contraint → entités/relations brutes | Existant (`extract.py`, `_ollama_json`) |
| `fuzzy_resolve_entity(name, type, tenant_id)` | Cascade exact → Levenshtein(≥85) → Jaccard(≥80) → embedding(≥0.82) → clé canonique Neo4j | **Existant** (`entity_match.py`) — réutilisé tel quel en horloge B, §4.7 |
| `merge_entity_neo4j(key, name, type)` / `merge_relation_neo4j(...)` | Écriture Neo4j | Existant |

Le point important : `fuzzy_resolve_entity` n'est **pas un outil à créer**, c'est un outil **existant côté horloge A qu'on réutilise côté horloge B** (§4.7) pour résoudre les entités mentionnées dans la question de l'utilisateur contre le même index Neo4j. Un seul outil, deux appelants — pas de duplication de logique fuzzy.

*(Amélioration optionnelle, hors périmètre immédiat : un `fuzzy_dedup_document(tenant_id, doc_sample)` pour détecter les quasi-doublons de documents au-delà du SHA exact — ex. le même CCTP réenregistré avec un tampon en plus. Je le mentionne pour mémoire, pas pour ce round de conception.)*

### 3.1 Le problème du routage par expert : `doc_type` n'est pas fiable

`documents.doc_type` (`rc|cctp|ccap|memoire|reference|dpgf|bpu|autre`) est **saisi à la main** à l'upload. Rien ne garantit qu'il soit renseigné — un utilisateur qui uploade 15 fichiers d'affilée ne va pas typer chacun soigneusement. **S'appuyer sur ce champ pour router un expert serait une erreur** : le jour où il est vide (le cas courant), l'expert juridique ne trouve simplement rien, silencieusement.

**Solution : classifier automatiquement, au niveau du chunk PARENT (pas du document entier — un même fichier peut mélanger de l'admin et du technique), en deux couches.**

```text
  COUCHE 1 — heuristique, sur TOUS les parents, coût ≈ 0
  --------------------------------------------------------
  Les pièces d'un AO français ont des titres très standardisés
  (Code de la commande publique — déjà dans `test.md` §1.2.1) :

    "RÈGLEMENT DE CONSULTATION" / "RC"                    → rc
    "CAHIER DES CLAUSES ADMINISTRATIVES PARTICULIÈRES"    → ccap
    "CAHIER DES CLAUSES TECHNIQUES PARTICULIÈRES"         → cctp
    "DÉCOMPOSITION DU PRIX GLOBAL ET FORFAITAIRE"         → dpgf
    "BORDEREAU DES PRIX UNITAIRES"                        → bpu
    "MÉMOIRE TECHNIQUE" / "MÉMOIRE JUSTIFICATIF"          → memoire
    "RÉFÉRENCES CHANTIER" / "ATTESTATION DE BONNE EXÉCUTION" → reference

  Regex/mots-clés sur heading_path + les ~200 premiers caractères
  du parent (au cas où le titre soit dans le corps, ex. sur un scan
  où le heading n'a pas été détecté). Zéro appel LLM.

  COUCHE 2 — LLM, UNIQUEMENT si couche 1 muette
  --------------------------------------------------------
  Même pattern que `extract_entities_relations` (JSON contraint),
  appliqué à TOUS les parents non résolus par la couche 1 —
  PAS limité à 12 comme l'extraction de graphe (ce serait
  réintroduire le même bug ailleurs).

  Résultat stocké : chunks.extra.section_type
                     chunks.extra.section_type_confidence
                     chunks.extra.section_type_method (heuristic|llm)
                     (champ `extra` JSONB déjà existant, pas de migration)
```

**Règle de conception, non négociable : `section_type` est un signal doux, jamais un filtre dur.** Un chunk mal classé (ou non classé, confiance faible) doit rester **visible par défaut à tous les experts** — *fail open*, pas *fail closed*. Un filtre bloquant transformerait une erreur de classification en trou invisible dans le retrieval.

C'est pour ça que ce signal se branche directement sur la boucle CRAG (§5.2), comme **un levier supplémentaire** de l'étape « Ambigu → élargir », au même titre que le filtre `doc_role` :

```text
  Expert Juridique, tentative 1 :
      filters = { tenant_id, section_type IN [ccap, rc] }
      → grade = Incorrect / 0 résultat
              │
              ▼
  tentative 2 (ÉLARGIR, pas reformuler) :
      filters = { tenant_id }   ← section_type LÂCHÉ
      → cherche tout le corpus avec la MÊME requête
```

Aucun nouveau mécanisme de secours à construire : une classification ratée s'auto-corrige exactement comme une reformulation ratée — via le même `max_iter=3` déjà posé.

---

## 4. Boîte à outils horloge B — détail technique de chaque outil

### 4.1 `rewrite_query(history, raw_query) -> query_clean`

1 appel LLM, température 0, prompt court (RAG-08 §3). Ne fait que réécrire, ne répond jamais à la question.

```text
Entrée : historique(8 tours) + "et la pénalité ?"
Sortie : "Quelle est la clause de pénalité de retard du contrat Dupont ?"
```

### 4.2 `retrieve_dense(query_clean, filters, top_k=50)`

- Embedding de `query_clean` avec **le même modèle** qu'à l'indexation (règle d'or, RAG-03) — actuellement `nomic-embed-text`.
- Recherche ANN dans Qdrant, sur la collection des **enfants** (children) — inchangé par rapport à la V1.

**Pourquoi ça ne compare pas à tous les vecteurs (ta question §8)** : Qdrant utilise HNSW (*Hierarchical Navigable Small World* — déjà dans ton tableau `test.md` §1.6.2 « Approximations pour l'indexation »). HNSW construit un graphe de voisinage à plusieurs couches à l'indexation ; une recherche descend les couches (grossière → fine) et ne visite qu'un petit sous-ensemble de nœuds proches, pas les $N$ millions de vecteurs. Complexité de requête en $O(\log N)$ approximatif, pas $O(N)$. C'est une recherche **approchée** (on peut manquer le voisin exact le plus proche dans de rares cas), pas exhaustive — c'est le compromis qui rend le vectoriel utilisable à grande échelle.

### 4.3 `retrieve_sparse(query_clean, filters, top_k=50)` — le cœur de ta question BM25

**Ta question centrale** : *« comment se passe le BM25, tu ne vas pas comparer tous les mots, ça fait beaucoup à comparer dans cette énorme BD ? »*

Réponse courte : non, exactement pour la même raison structurelle que le dense (juste un mécanisme différent) — un **index inversé**, pas une comparaison brute. Ta propre fiche RAG-07 §2 le dit déjà : *« un dictionnaire mot → liste des chunks qui le contiennent, comme l'index à la fin d'un livre »*.

```text
  SANS index inversé (ce qu'on NE fait PAS)
  --------------------------------------------
  pour chaque chunk de la base (potentiellement des millions) :
      comparer chaque mot du chunk aux mots de la requête
  → scan complet, O(N × longueur_moyenne_chunk)

  AVEC index inversé (ce qu'on fait)
  --------------------------------------------
  Index construit UNE FOIS à l'indexation :
      "pénalité"   → [chunk_12, chunk_88, chunk_340, ...]
      "dupont"     → [chunk_12, chunk_500, ...]
      "9001"       → [chunk_7, chunk_12, ...]

  Requête "pénalité contrat Dupont" (3 termes après nettoyage) :
      lookup("pénalité") → liste courte (chunks qui contiennent CE mot)
      lookup("dupont")   → liste courte
      lookup("contrat")  → liste courte (mot fréquent → IDF faible, pesé moins)
      UNION/intersection des listes → score BM25 sur ce sous-ensemble SEULEMENT
```

Le nombre de chunks réellement scorés = la taille des listes de posting des 2-3 termes de la requête, pas la taille de la base. Un mot rare (« ISO 9001 », un numéro d'article) a une liste **courte** → lookup quasi instantané. Un mot très fréquent (« le », « contrat ») a une liste longue mais un poids IDF faible dans le score final — c'est justement ce que BM25 est conçu pour gérer (RAG-07 §3).

**Choix d'implémentation pour ce projet** (décision à valider) :

| Option | Avantage | Inconvénient | Verdict |
|---|---|---|---|
| **Postgres full-text search** (`tsvector` généré + index GIN sur `chunks.text`, config `french`) | Zéro nouvelle infra — Postgres est déjà la source de vérité du texte des chunks ; filtres `tenant_id`/`doc_role` dans le **même** `WHERE` SQL | Fonction de ranking `ts_rank`/`ts_rank_cd` de Postgres, pas du BM25 au sens strict (même esprit : IDF + fréquence), légèrement moins fin | **Recommandé en V2** — proportionné à l'échelle d'une PME BTP, pas du web-scale |
| `rank_bm25` (lib Python, BM25 pur) | Vrai BM25, formule exacte | Charge tout le corpus en mémoire — ne passe pas à l'échelle au-delà de quelques dizaines de milliers de chunks | Non retenu |
| Moteur dédié (Elasticsearch/OpenSearch/Tantivy/Meilisearch) | Vrai BM25, scalable, mature | Nouveau service à opérer, à synchroniser avec Postgres (double écriture) | Trop lourd pour ce stade — à envisager seulement si `retrieve_sparse` devient un goulot mesuré |
| Sparse natif Qdrant (SPLADE ou BGE-M3 sparse) | Un seul moteur pour dense+sparse, cohérent avec la cible BGE-M3 déjà documentée dans `pipeline_technique_detaille.md` | Suppose de migrer l'embedding vers BGE-M3 (chantier séparé, déjà identifié comme amélioration d'indexation) | Bonne cible **si/quand** BGE-M3 remplace nomic-embed-text — pas un préalable à la boucle agentique |

**Recommandation** : Postgres FTS maintenant (aucune dépendance nouvelle, corpus à l'échelle d'une entreprise BTP, pas du grand public), avec un chemin de migration documenté vers le sparse natif Qdrant quand BGE-M3 sera en place.

### 4.4 Granularité : réponse précise à *« ce sera appliqué aux parents, pas aux enfants ? vectoriel ou texte ? »*

**Non** — le sparse doit s'appliquer à la **même granularité que le dense : les enfants**, pas les parents. Raison structurelle, pas de préférence arbitraire : la fusion RRF (RAG-07 §4) additionne $1/(60+\text{rang})$ pour un **même identifiant** présent dans les deux listes classées. Si le dense classe des `child_id` et le sparse classe des `parent_id`, il n'y a **aucun identifiant commun** à fusionner — RRF n'a plus de sens.

```text
  CORRECT (même granularité)                INCORRECT
  ---------------------------                ---------
  dense  Top-50 : [child_12, child_88, ...]   dense  Top-50 : [child_12, ...]
  sparse Top-50 : [child_12, child_340, ...]  sparse Top-50 : [parent_3, ...]
         │                                           │
     RRF sur child_id → OK, fusion cohérente     RRF sur ??? → pas de clé commune
```

Sur « vectoriel ou texte » : le BM25 (ou son équivalent Postgres FTS) travaille sur une représentation **texte normalisée** (`tsvector` = liste de lexèmes racinisés + positions, ce n'est **pas** un embedding numérique appris) — donc « texte », pas « vectoriel » au sens du dense. Le terme « sparse vector » qu'on croise dans la littérature (SPLADE, BGE-M3 sparse) désigne un vecteur creux de la taille du vocabulaire — c'est une **autre** implémentation possible du même principe (terme exact → poids), mais ce n'est pas ce qu'on retient pour la V2 (cf. tableau 4.3).

Une fois le Top-8 obtenu après RRF+rerank sur les enfants, on fait l'**expansion enfant→parent** exactement comme aujourd'hui (`expand_hits_with_page_parents`, inchangé) pour donner au LLM le contexte complet de la section.

### 4.5 `rerank(query_clean, candidates[50]) -> top_8`

Cross-encoder (question+chunk lus ensemble) sur le pool fusionné de 50, pas sur toute la base — inchangé dans le principe, actuellement un stub (`return nodes[:top_n]`) à remplacer par un vrai modèle (BGE-reranker-v2-m3, déjà la cible documentée).

### 4.6 `extract_query_entities(query_clean) -> [{name, type_hint}]`

Réponse à *« tu vas utiliser un LLM pour extraire les entités de la requête ? »* — oui, et pour rester cohérent avec l'existant plutôt qu'inventer un nouveau mécanisme : **même pattern** que `_ollama_json` déjà utilisé en horloge A pour extraire entités/relations d'un chunk (`extract.py`), appliqué cette fois à la question de l'utilisateur au lieu d'un chunk de document. Même prompt JSON contraint, mêmes `ENTITY_TYPES` autorisés (ENTREPRISE, PROJET, CLIENT, CERTIFICATION, ÉQUIPEMENT, PERSONNE, EXIGENCE…). Un seul appel LLM, pas un NER séparé à maintenir.

```text
  Question : "Quelles certifications couvrent l'exigence ISO 9001 du projet Gare de Nantes ?"

  extract_query_entities →
    [{"name": "ISO 9001", "type_hint": "CERTIFICATION"},
     {"name": "Gare de Nantes", "type_hint": "PROJET"}]
```

### 4.7 `retrieve_graph(entities_extraites, tenant_id) -> relations + chunks source`

Procédure complète, étape par étape (réponse à *« comment et quelle procédure vas-tu adopter ? »*) :

```text
  1. extract_query_entities(query_clean)
         │
  2. POUR CHAQUE entité extraite :
         fuzzy_resolve_entity(name, type_hint, tenant_id)   ← OUTIL RÉUTILISÉ (§3)
         → clé canonique Neo4j, ou "non résolu" si aucun match ≥ seuil
         │
  3. SI AUCUNE entité ne se résout :
         → court-circuit immédiat, pas d'appel Cypher inutile
         → cet expert "graphe" remonte directement une abstention
           (grading trivial : "Incorrect", cf. §5)
         │
  4. SI AU MOINS UNE entité résolue :
         construire une requête Cypher à partir d'un TEMPLATE fixe
         (PAS de Cypher généré librement par le LLM — trop risqué,
          même principe que "un agent, une responsabilité" : le LLM
          extrait des entités, LE CODE construit la requête)

         Exemples de templates, choisis selon le type de question :

         a) 1-hop, "qui est lié à X ?" :
            MATCH (e:Entity {key:$k})-[r:REL]-(o:Entity)
            RETURN o, r LIMIT 25

         b) bornée 1-2 sauts, relation typée (conformité) :
            MATCH (e:Entity {key:$k})-[:SATISFAITE_PAR|DETIENT*1..2]-(o)
            RETURN o

         c) 2 entités données (question à 2 ancres) :
            MATCH (a:Entity {key:$k1})-[r*1..2]-(b:Entity {key:$k2})
            RETURN r
         │
  5. Pour chaque relation retournée :
         récupérer r.source_chunk_id (déjà stocké depuis l'extraction
         horloge A, cf. JOURNAL.md "Étape — Fuzzy matching")
         → SELECT text, page FROM chunks WHERE id = source_chunk_id
         → nécessaire pour la CITATION (on ne cite jamais un fait de
           graphe sans le chunk texte qui le prouve)
         │
  6. Résultat remonté à l'agrégateur : {relations[], chunks_source[]}
         → gradé comme les autres (§5) : relations trouvées et
           cohérentes avec la question = "Correct" ; rien trouvé
           malgré des entités résolues = "Ambigu" → élargir le hop
           (1→2) avant d'abandonner
```

Ce nœud est celui qui **active enfin la lecture de Neo4j en horloge B**, jamais faite en V1 (`diagrammes_sequence_workflow.md` §6 : *« GraphRAG au chat : Neo4j écrit, jamais lu »*).

### 4.8 `sql_lookup(table, filters) -> rows`

Pour les questions chiffrées exactes (DPGF/BPU déjà stockés en lignes structurées Postgres, pas en prose vectorisée — `implementation_proposition.md` §3). Requête SQL directe, pas de LLM impliqué dans la recherche elle-même — seulement, en aval, pour formuler la phrase à partir des lignes retournées.

### 4.9 `grade_context(query_clean, chunks_ou_relations) -> Correct | Ambigu | Incorrect`

Détaillé au §5 (c'est le cœur de la boucle bornée).

---

## 5. La boucle agentique bornée (CRAG) — détail complet

### 5.1 Adaptive : ne pas boucler pour rien

Avant même d'entrer dans une boucle, le superviseur (§1, étape 5) classe la complexité — reprise directe de RAG-10 §7 :

| Complexité | Exemple | Traitement |
|---|---|---|
| Triviale | « Bonjour » | Aucun retrieval, réponse fixe |
| **Contenu déjà fourni** | « Voici le texte du client pour la méthodologie : [...]. Rédige la section à partir de ça. » | **Aucun retrieval** — `experts=[]` pour cette sous-question (détail §8.2, règle R9), génération directe sur l'historique de conversation. **Distinct d'une abstention** (§5.4) : on n'a pas cherché, ce n'était pas nécessaire — ne doit jamais déclencher l'alerte ⚠️ réservée aux vraies abstentions |
| Simple | « Délai de garantie décennale ? » | **1 seule passe** hybride + rerank, PAS de boucle de grading — on accepte le Top-8 tel quel (comme la V1 aujourd'hui, juste avec l'hybride en plus) |
| Complexe / incertaine | Question multi-critères, entité rare, ou déjà un échec silencieux en V1 (ex. exigence non trouvée) | Boucle CRAG complète (§5.2) |

Le signal "complexe" peut être simple à coder au départ (ex. règle : question porte sur `run_section` OU contient plusieurs entités OU le premier essai simple a un score de rerank sous un seuil) — pas besoin d'un classifieur sophistiqué dès le premier jour.

**Adaptive vs CRAG — ce n'est pas la même décision, ne pas confondre :**

```text
              AVANT toute recherche               APRÈS chaque recherche
              ------------------------             ------------------------
              ADAPTIVE (ce paragraphe)             CRAG / grading (§5.2, §5.3)
              "cette question mérite-t-elle         "ce résultat précis est-il
               qu'on mette en place la               suffisant, ou faut-il
               boucle de correction ?"                corriger et réessayer ?"
```

Adaptive est un **triage à froid**, décidé sur la question seule, sans avoir encore rien cherché. CRAG est un **contrôle qualité**, décidé après coup, sur ce que la recherche a réellement ramené. On garde les deux : sans Adaptive, on paierait le coût du grading (potentiellement 1 appel LLM-juge, §5.3) même sur « Bonjour » ou une FAQ triviale — exactement ce que RAG-10 §9 chiffre (Naive = 1 appel, boucle agent = 4 à 10 appels) et que RAG-10 §7 vise à éviter.

### 5.2 La boucle, état par état

```text
  État initial : query_clean, tentative = 0, filters = {tenant_id, doc_role: [patrimoine, dao_archive]}

  ┌─────────────────────────────────────────────────────────────┐
  │ TENTATIVE (tentative += 1)                                   │
  │                                                               │
  │  retrieve_dense(query, filters, 50)  ┐                       │
  │  retrieve_sparse(query, filters, 50) ┴─→ RRF → rerank → Top-8│
  │                                                               │
  │  grade_context(query, top_8) → Correct | Ambigu | Incorrect  │
  └──────────────────┬────────────────────────────────────────────┘
                      │
     ┌────────────────┼─────────────────────┐
  Correct           Ambigu               Incorrect
     │                 │                     │
     ▼                 ▼                     ▼
  → generate    élargir SANS reformuler   reformuler (rewrite
  (sortie de    ex: filters.doc_role      variante, ou multi-query
   la boucle)   += dao_courant,           RAG-08 §4) PUIS relancer
                ou top_k 50→100           retrieve

                      └──────────┬──────────┘
                                 ▼
                    tentative < max_iter (3) ?
                       │                │
                      OUI              NON
                       │                │
                       ▼                ▼
                  TENTATIVE          ABSTENTION
                  (reboucle)         { found: false,
                                       reason: "...",
                                       tentatives: 3 }
                                       → remontée à l'agrégateur,
                                         PAS de génération sur du vide
```

### 5.3 `grade_context` — comment noter concrètement

Décision à trancher avec toi (déjà posée, je reformule avec plus de détail maintenant que le reste est clair) :

| Approche | Mécanisme | Coût | Finesse |
|---|---|---|---|
| **Seuil de score** | Score du reranker sur le meilleur chunk : `> 0.7` → Correct, `0.3–0.7` → Ambigu, `< 0.3` → Incorrect | Gratuit (le rerank est déjà calculé) | Grossier — un score élevé peut être un faux positif thématique (RAG-07 exemple : « duree standard 12 mois » scorait haut sans répondre à la question de résiliation) |
| **LLM juge** | 1 appel LLM court : « ce contexte permet-il de répondre à cette question ? Correct/Ambigu/Incorrect + pourquoi » | +1 appel LLM par tentative (donc jusqu'à 3 appels de plus dans le pire cas) | Plus fiable, capte les cas où le score est haut mais la réponse absente |
| **Hybride** | Seuil de score d'abord (rapide) ; si zone grise (Ambigu par score), un seul appel LLM juge pour trancher | +0 ou +1 appel selon les cas | Bon compromis coût/fiabilité |

Je recommande l'**hybride** — c'est cohérent avec le principe Adaptive (ne payer le coût LLM que quand le signal bon marché ne suffit pas). Mais c'est ta décision à valider (tu avais laissé la question ouverte).

### 5.4 Ce que l'abstention devient en aval

L'abstention d'un expert n'arrête **pas** tout le pipeline — elle est agrégée avec les résultats des autres experts (§1 étape 7), et transmise telle quelle au générateur via le champ `abstentions` du schéma `SectionGeneree` qui existe déjà. Le générateur écrit alors explicitement, par exemple : *« Aucune référence à un chantier ferroviaire de plus de 20 M€ n'a été trouvée dans le patrimoine. »* — au lieu d'inventer, ou de planter.

**À ne pas confondre avec `experts=[]` (§5.1, « contenu déjà fourni »).** L'agrégateur doit distinguer explicitement 3 sources par sous-question, pas 2 :

```text
  source = "retrieval"     → au moins 1 expert a cherché et gradé Correct
  source = "abstention"    → au moins 1 expert a cherché et échoué (3 tentatives)
  source = "conversation"  → experts=[] : AUCUNE recherche n'a été tentée
```

Seule `"abstention"` déclenche l'alerte ⚠️ côté UI (`base_de_donnees_et_interface.md` §3.5). `"conversation"` ne doit jamais afficher ce bandeau — l'absence de recherche n'est pas un échec.

### 5.5 Questions composées : décomposition planifiée

Trou comblé ici (signalé en cours de conception, absent des versions précédentes du document) : une question comme *« Compare nos 3 dernières références ferroviaires et dis-moi laquelle correspond le mieux à ce projet »* ne peut pas passer par un seul `query_clean` unique — il faut plusieurs recherches distinctes avant qu'une réponse ait un sens.

**Choix retenu : décomposition planifiée, pas agent dynamique** (RAG-08 §7 pose exactement ce choix : *« planifiée : simple à tester, idéal si questions toujours du même moule »* vs *« agent : plus souple, plus lent, idéal questions ouvertes »*). Même logique que pour CRAG : rester borné et traçable plutôt qu'ouvrir une boucle libre, cohérent avec l'exigence de traçabilité stricte du domaine AO.

**Où ça se branche — dans le Superviseur, pas un nœud à part.** Le Superviseur (§1 étape 5) fait déjà un appel LLM JSON pour classifier l'intention ; on étend simplement son schéma de sortie pour qu'il détecte *dans le même appel* si la question est composée, et produise la liste ordonnée des sous-questions — zéro appel LLM supplémentaire pour la détection elle-même.

```text
  query_clean : "Compare nos 3 dernières références ferroviaires
                 et dis-moi laquelle correspond le mieux à ce projet"

  Sortie Superviseur (schéma détaillé et exemples complets : §8) :
  {
    "intent": "hybrid_rag",
    "is_compound": true,
    "sous_questions": [
      {"texte": "Quelles sont nos 3 dernières références de chantiers ferroviaires réalisées ?",
       "experts": ["patrimoine"], "complexite": "complexe"},
      {"texte": "Quelles sont les caractéristiques techniques et le contexte du projet actuel de ce dossier ?",
       "experts": ["technique", "patrimoine"], "complexite": "simple"}
    ]
  }
```

**Garde-fou obligatoire** (même famille que `max_iter`, RAG-10 §8) : **max 4 sous-questions**. Au-delà, le Superviseur doit soit fusionner, soit renvoyer une clarification à l'utilisateur plutôt que multiplier les recherches — évite qu'une question mal posée fasse exploser le nombre d'appels (RAG-10 §9 : chaque sous-question ajoute son propre coût de boucle CRAG, potentiellement ×3 à ×8 la latence si chacune est jugée « complexe », §5.1).

**Exécution : en parallèle, pas séquentiel, dans le cas général.** Pour la grande majorité des questions composées de ce domaine (« compare A et B », « quelles exigences ET quel délai »), les sous-questions sont **indépendantes** — chercher les 3 dernières références ne dépend pas de chercher les caractéristiques du projet actuel. On lance donc les boucles CRAG des sous-questions **simultanément**, comme le fait déjà le multi-query de RAG-08 §4 (*« piège : 5 recherches l'une après l'autre = 5× la latence, il faut les lancer en même temps »*).

*Limite assumée, hors périmètre V2* : le cas d'un **vrai enchaînement dépendant** (« qui est le chef de chantier du projet qui a eu le plus gros budget » — il faut connaître le projet avant de chercher son chef de chantier) demanderait une exécution séquentielle où la sous-question 2 est construite à partir du résultat de la sous-question 1. Ce cas existe dans la littérature (RAG-08 §7, *multi-hop*) mais je le laisse en dehors du périmètre V2 — le couvrir proprement demanderait de sortir de la décomposition planifiée vers un agent dynamique (RAG-08 §7, colonne « Agent »), ce qui revient à réintroduire une boucle non bornée exactement là où on cherche à l'éviter. À réévaluer si l'usage réel du système fait remonter ce besoin.

**Agrégation finale — toujours un seul générateur.** Une fois toutes les sous-questions résolues (contexte gradé ou abstention chacune), l'agrégateur (§1 étape 7) fusionne l'ensemble en un seul contexte numéroté, et **un seul appel** au générateur (§1 étape 8) produit la réponse — y compris la comparaison/le calcul demandé (« laquelle correspond le mieux », « calcule Z ») qui n'est **pas** une recherche supplémentaire mais un raisonnement du générateur sur les faits déjà réunis. Ça préserve exactement le principe du §1.1 : les sous-questions multiplient la **récupération**, jamais la **rédaction**.

---

## 6. Pourquoi la requête n'est jamais « chunkée »

Réponse directe à *« tu vas découper en chunks la requête pour le parse ? »* — non, et c'est important de bien distinguer les deux :

```text
  CHUNKING (horloge A, ingestion)
  --------------------------------
  Objet découpé : le DOCUMENT (des dizaines/centaines de pages)
  Pourquoi      : un embedding représente MAL un texte trop long
                  et hétérogène (RAG-04 §2 : "un vecteur pour 50
                  pages est une moyenne de toutes les idées")
  Résultat      : des centaines de chunks, indexés UNE fois

  REQUÊTE UTILISATEUR (horloge B, question)
  --------------------------------
  Objet         : une phrase ou un court paragraphe
  Chunking ?    : NON — une question, même longue, reste UNE unité
                  de sens qu'on embedde telle quelle (ou reformulée
                  par le rewrite, §4.1)
  Cas particulier : une question COMPOSÉE ("compare X et Y puis
                  calcule Z") peut être DÉCOMPOSÉE en sous-questions
                  (RAG-08 §7, decomposition) — mais ce n'est PAS du
                  chunking, c'est une réécriture en plusieurs
                  requêtes complètes et autonomes, chacune ensuite
                  traitée comme une requête normale (§4.2-4.3).
                  Mécanisme d'implémentation complet : §5.5.
```

La confusion est compréhensible parce que les deux opérations "démembrent" du texte, mais elles répondent à des problèmes opposés : le chunking réduit un texte trop long **pour l'indexer** ; la décomposition étend une question composée **en plusieurs questions complètes**, chacune trop courte pour poser problème à un embedding.

---

## 7. Récapitulatif des décisions à valider

| # | Décision | Proposition de ce document | Statut |
|---|---|---|---|
| 1 | `max_iter` boucle CRAG | 3 | ✅ Validé (session précédente) |
| 2 | Mémoire long terme Mem0 | Hors périmètre V2 (§2.3 explique pourquoi le relationnel existant suffit) | ✅ Validé |
| 3 | Grading (`grade_context`) | Hybride seuil + LLM juge en zone grise | ✅ Validé |
| 4 | Sparse retrieval | Postgres full-text search (`tsvector`/GIN, config `french`) | ✅ Validé |
| 5 | Granularité du sparse | Enfants (même clé que le dense, pour permettre RRF) | Découle du point 4, cohérent |
| 6 | Génération de graphe Cypher | Templates fixes paramétrés, pas de Cypher libre par LLM | ✅ Validé |
| 7 | Résumé de progression de dossier | Précalculé à l'approve (`generations.summary_short`), pas recalculé par question | ✅ Validé |
| 8 | Routage des experts par type de pièce | Classification dynamique `section_type` (heuristique + LLM fallback, §3.1) sur `chunks.extra`, signal doux jamais un filtre dur — remplace `documents.doc_type` (manuel, non fiable) | ✅ Approche validée (session en cours) |
| 9 | Questions composées (multi-sous-questions) | Décomposition **planifiée** dans le Superviseur (pas d'appel LLM en plus), max 4 sous-questions, exécution en parallèle, 1 seul générateur final (§5.5). Enchaînement dépendant (vrai multi-hop séquentiel) explicitement hors périmètre V2 | ✅ Validé |

---

## 8. Spécification stricte du prompt système — Superviseur/Router

> **Pourquoi cette rigueur** : un routeur mal cadré sur-découpe des questions simples (coût inutile, §5.1) ou ne découpe jamais (§5.5 resterait mort-lettre). Le prompt ci-dessous n'est pas indicatif : chaque règle existe pour fermer un cas d'erreur précis, listé en regard.

### 8.1 Rôle et sortie (partie fixe du prompt système)

```text
Tu es le routeur d'un système de recherche documentaire pour des
dossiers d'appels d'offres BTP. Tu ne réponds JAMAIS à la question
de l'utilisateur. Ton seul travail : classifier son message et,
si nécessaire, le découper en sous-questions de recherche.

Tu dois répondre EXCLUSIVEMENT en JSON, selon ce schéma strict :

{
  "intent": "smalltalk" | "export" | "clarification_needed"
             | "hybrid_rag" | "run_section",
  "is_compound": boolean,
  "sous_questions": [
    {
      "texte": string,
      "experts": ["juridique" | "technique" | "financier"
                  | "graphe" | "patrimoine"],
      "complexite": "simple" | "complexe"
    }
  ],
  "message_clarification": string | null
}

Experts disponibles (tu ne peux JAMAIS utiliser un nom hors de
cette liste) :
  - "juridique"  : clauses, pénalités, délais, RC/CCAP
  - "technique"  : spécifications, méthodologie, CCTP
  - "financier"  : chiffres exacts, DPGF/BPU
  - "graphe"     : relations entre entités (qui a fait quoi,
                   quelle certif couvre quelle exigence)
  - "patrimoine" : références, projets passés, CV, certifications
```

### 8.2 Règles de décomposition (numérotées, chacune ferme un cas précis)

```text
R1. Décompose UNIQUEMENT si les parties de la question demandent
    des recherches INDÉPENDANTES (le résultat de l'une n'est pas
    nécessaire pour formuler l'autre). Si les parties viennent
    naturellement de la MÊME recherche, is_compound = false.
    → Ferme le cas "CA 2025 et son évolution vs 2024" : une seule
      recherche financière cohérente, PAS deux sous-questions.

R2. Chaque texte de sous-question doit être COMPLET et AUTONOME :
    aucun pronom ni référence implicite ("ce projet", "cette
    référence") sans le nommer explicitement à partir du contexte
    disponible. Même exigence que le nœud rewrite (§4.1), appliquée
    à chaque sous-question générée.
    → Ferme le cas d'une sous-question illisible hors contexte.

R3. Maximum 4 sous-questions. Si la question en demanderait plus,
    NE JAMAIS en générer davantage : soit regrouper les parties les
    plus proches sous une seule sous-question, soit répondre
    intent = "clarification_needed" avec un message_clarification
    qui demande à l'utilisateur de préciser son besoin.
    → Ferme le risque d'explosion du nombre d'appels (RAG-10 §9 :
      chaque sous-question porte son propre coût de boucle CRAG).

R4. Si is_compound = false, sous_questions contient EXACTEMENT
    1 élément. Si is_compound = true, sous_questions contient
    ENTRE 2 ET 4 éléments. Jamais 0, jamais 1 avec is_compound=true.

R5. Le calcul, la comparaison ou la synthèse finale demandés
    ("laquelle correspond le mieux", "calcule Z", "lequel est plus
    avantageux") n'est PAS une sous-question de recherche — ne
    crée JAMAIS une sous-question qui n'a pas sa propre recherche
    factuelle. Cette synthèse est faite plus tard par le
    générateur, sur les faits déjà réunis (§5.5).

R6. Si intent ∈ {"smalltalk", "export"} : sous_questions = [] et
    message_clarification = null, TOUJOURS.

R7. Si intent = "clarification_needed" : sous_questions = [] et
    message_clarification est OBLIGATOIRE (jamais null).

R8. "complexite" s'évalue par sous-question, pas globalement :
    une sous-question factuelle simple ("délai de garantie
    décennale ?") = "simple" ; une sous-question qui implique
    plusieurs critères, une entité rare, ou porte sur un
    run_section = "complexe" (déclenche la boucle CRAG complète,
    §5.1 — sinon 1 seule passe hybride).

R9. "experts" PEUT être vide ([]) — UNIQUEMENT si le message de
    l'utilisateur (ou l'historique immédiat) contient DÉJÀ le
    contenu FACTUEL SPÉCIFIQUE nécessaire à CETTE sous-question
    précise (ex. l'utilisateur colle le texte à utiliser, ou
    rappelle une donnée déjà établie plus haut dans la conversation).
    Dans le DOUTE, NE PAS mettre experts=[] : une recherche
    redondante coûte peu (§5.1, cas "simple" = 1 seule passe) ;
    une génération privée d'information disponible coûte plus cher
    en confiance. experts=[] N'EST JAMAIS une abstention (§5.4) —
    c'est l'absence VOLONTAIRE de recherche, pas un échec de recherche.
```

### 8.3 Exemples (few-shot, à injecter dans le prompt)

```text
EXEMPLE A — simple, non composée
Entrée : "Quel est le délai de garantie décennale ?"
Sortie :
{
  "intent": "hybrid_rag", "is_compound": false,
  "sous_questions": [
    {"texte": "Quel est le délai de garantie décennale mentionné dans le DAO ?",
     "experts": ["juridique"], "complexite": "simple"}
  ],
  "message_clarification": null
}

EXEMPLE B — composée, indépendante (cas cible de §5.5)
Entrée : "Compare nos 3 dernières références ferroviaires et dis-moi
          laquelle correspond le mieux à ce projet"
Sortie :
{
  "intent": "hybrid_rag", "is_compound": true,
  "sous_questions": [
    {"texte": "Quelles sont nos 3 dernières références de chantiers ferroviaires réalisées ?",
     "experts": ["patrimoine"], "complexite": "complexe"},
    {"texte": "Quelles sont les caractéristiques techniques et le contexte du projet actuel de ce dossier ?",
     "experts": ["technique", "patrimoine"], "complexite": "simple"}
  ],
  "message_clarification": null
}
NOTE : "laquelle correspond le mieux" N'EST PAS une 3e sous-question
(règle R5) — c'est une comparaison faite par le générateur.

EXEMPLE C — piège : ressemble à composée, doit RESTER simple (règle R1)
Entrée : "Quel est le chiffre d'affaires 2025 et son évolution vs 2024 ?"
Sortie :
{
  "intent": "hybrid_rag", "is_compound": false,
  "sous_questions": [
    {"texte": "Quel est le chiffre d'affaires de l'entreprise en 2025 et en 2024, avec le pourcentage d'évolution ?",
     "experts": ["financier"], "complexite": "simple"}
  ],
  "message_clarification": null
}

EXEMPLE D — trop de dimensions, clarification (règle R3)
Entrée : "Compare les 5 derniers dossiers gagnés sur leurs certifications,
          leurs équipes, leurs budgets et leurs clients"
Sortie :
{
  "intent": "clarification_needed", "is_compound": false,
  "sous_questions": [],
  "message_clarification": "Sur quel(s) critère(s) en particulier souhaitez-vous la comparaison (certifications, équipes, budgets, ou clients) ? Traiter les quatre à la fois dépasse ce que je peux faire en une seule recherche."
}

EXEMPLE E — contenu déjà fourni, PAS de recherche (règle R9)
Entrée : "Voici le texte que le client nous a envoyé pour la partie
          méthodologie : 'Nous exigeons une méthode BIM complète
          avec revues hebdomadaires.' Rédige la section méthodologie
          en te basant là-dessus."
Sortie :
{
  "intent": "run_section", "is_compound": false,
  "sous_questions": [
    {"texte": "Rédiger la section méthodologie à partir du texte fourni par l'utilisateur (méthode BIM complète, revues hebdomadaires)",
     "experts": [], "complexite": "simple"}
  ],
  "message_clarification": null
}
NOTE : experts=[] volontaire — le contenu factuel nécessaire est
DÉJÀ dans le message de l'utilisateur (règle R9). La génération
(§1 étape 8) utilisera l'historique de conversation directement.
Ce N'EST PAS une abstention (§5.4) : source="conversation", pas
d'alerte ⚠️.
```

### 8.4 Multi-hop séquentiel — tranché

✅ **Confirmé hors périmètre V2.** Ce schéma ne contient donc **volontairement pas** de champ `depends_on` — cohérent avec §5.5. Déclencheur de réévaluation explicite (pas une fermeture définitive) : si les traces de production (`retrieval_traces`, cf. document base de données) montrent des `clarification_needed` ou abstentions répétées correspondant à ce pattern, rouvrir le sujet avec des données réelles plutôt qu'une anticipation.

**Toutes les décisions du tableau §7 sont maintenant validées.** Le design du volet récupération/décomposition est figé ; l'implémentation peut commencer sur cette base.

---

## 9. Alimentation de `exigences` et `outline_items` — l'extraction qui manquait

Point comblé en cours de conception (absent des versions précédentes) : comment ces deux tables sont-elles réellement remplies ? Nouvel outil, mais **déterministe** (comme `extract_entities_relations`), pas agentique — la couverture des exigences, elle, réutilise l'agentique déjà conçu (§5).

```text
1. DAO ready + dossier.dao_document_id renseigné
      │
      ▼
2. ENQUEUE extract_dossier_structure(dossier_id)   ← nouveau job, style horloge A (ARQ, async)
      │
      ├── 2a. extract_outline(dossier_id)
      │       Cherche dans les chunks section_type='rc' (réutilise §3.1) un passage
      │       "le mémoire technique comprendra..." → LLM JSON contraint extrait la liste
      │       ordonnée de titres ; sinon fallback DEFAULT_OUTLINE (déjà codé,
      │       app/workflow/sections.py) → INSERT outline_items (status='todo')
      │
      └── 2b. extract_exigences(dossier_id)
              TOUS les parents du DAO (pas de limite à 12, contrairement au bug
              documenté de l'extraction de graphe — une exigence peut être n'importe
              où), traités par lots en parallèle. LLM JSON contraint par parent →
              dédup par fuzzy_resolve (RÉUTILISE la cascade Levenshtein/Jaccard/
              embedding déjà construite pour les entités, §3) → INSERT exigences
              (statut='a_couvrir')
      │
      ▼
3. dossiers.status : draft → analyzing → generating
      │
      ▼
4. Couverture (AGENTIQUE, réutilise §5 tel quel, aucune nouvelle mécanique) :
   pour chaque exigence 'a_couvrir' → query=libelle → Expert Patrimoine + CRAG
   (max_iter=3) → Correct: statut='couverte'+preuves_chunks ; abstention: 'non_couverte'
   Déclenchement : en lot après 2b, ou à la demande (bouton UI par exigence)
```

| Étape | Déterministe ou agentique | Pourquoi |
|---|---|---|
| `extract_outline` | Déterministe | Séquence fixe : chercher un passage → extraire ou fallback |
| `extract_exigences` | Déterministe | Même famille que `extract_entities_relations` |
| Déduplication | Déterministe (fuzzy) | Outil existant réutilisé |
| Couverture des exigences | **Agentique** | Variabilité réelle : où est la preuve, si elle existe — cas où `IA_Agentique/10` §3 dit de garder l'agent |

---

## 10. Spécialisation du prompt de génération par type de section — pas un nouvel agent

Question posée en cours de conception : faut-il un agent rédacteur spécialisé par type de section (mixture of experts appliquée à la génération) ? **Non** — mais un prompt adapté par section, oui. La différence : ici la donnée qui déterminerait le "bon expert" (`outline_items.key`) est **déjà connue par le code** au moment de générer, ce n'est pas une ambiguïté à trancher par un agent (`IA_Agentique/10` §3). C'est un `lookup`, pas une décision :

```python
prompt = PROMPT_TEMPLATES.get(outline_item.archetype, PROMPT_TEMPLATE_GENERIQUE)
```

**Ce qui varie** : les instructions du prompt (ton, type de blocs à privilégier). **Ce qui ne varie jamais** : le contrat `SectionGeneree` et le mécanisme (1 seul générateur, 1 seul appel — §1.1 inchangé).

**4 archétypes**, pas un prompt par section littérale (évite la duplication) :

| Archétype | Sections typiques (canevas par défaut) | Emphase du prompt |
|---|---|---|
| `institutionnelle` | Présentation entreprise | Ton commercial, chiffres clés, citation non obligatoire |
| `factuelle` | Moyens humains, Moyens matériels, Références, Planning | Listes/quantités, **chaque fait chiffré cite une source** |
| `narrative` | Compréhension de la mission, Méthodologie | Prose structurée en phases |
| `conformite` | QSE | Politique/normes, citations vers certifications |

**Mapping des 8 sections par défaut** : fixe, codé en dur. **Pour un plan extrait dynamiquement d'un RC atypique (§9)** : `archetype` classifié **une seule fois, au moment de `extract_outline`**, avec le même schéma cascade heuristique+LLM que `chunks.section_type` (§3.1) — classifier une fois, stocker, réutiliser à chaque régénération.

```sql
ALTER TABLE outline_items
    ADD COLUMN archetype VARCHAR(16)
        CHECK (archetype IN ('institutionnelle','factuelle','narrative','conformite'))
        DEFAULT 'factuelle';
```

---

## Liens

- `Fichier/architecture_synthese.md` — architecture V1 de référence
- `Fichier/pipeline_technique_detaille.md` — détail horloge A/B actuel
- `Fichier/diagrammes_sequence_workflow.md` — état réel du code (août 2026)
- `~/Lectures_&_projects/Lectures/IA/RAG/07, 08, 10` — Advanced RAG, query rewriting, Agentic RAG/CRAG
- `~/Lectures_&_projects/Lectures/IA/IA_Agentique/01, 10, 11` — agent/tool/boucle, architecture SMA, mémoire long terme
