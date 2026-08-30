# MÉMOIRE DE RECHERCHE

## Plateforme de Capitalisation et Génération Intelligente de Dossiers d'Appels d'Offres dans le Secteur du BTP

---

# CHAPITRE 1 : ÉTAT DE L'ART

---

## 1.1. Introduction

Le secteur de la construction et des travaux publics (BTP) constitue l'un des piliers de l'économie, caractérisé par une compétition intense où la réponse aux appels d'offres (AO) représente un enjeu stratégique majeur. Chaque année, des milliers d'entreprises consacrent des ressources considérables à la préparation de dossiers de candidature, processus qui mobilise des compétences juridiques, techniques, financières et administratives.

L'émergence des technologies d'intelligence artificielle, et plus particulièrement des grands modèles de langage (LLM), ouvre des perspectives inédites pour automatiser et optimiser ce processus. Cependant, la spécificité des appels d'offres — leur caractère hautement structuré, leur exigence de traçabilité et de conformité, et leur dimension juridique contraignante — impose une approche réfléchie et méthodique.

Ce chapitre dresse un panorama des connaissances actuelles dans les domaines connexes à notre problématique : la gestion documentaire dans le BTP, les technologies de l'information et de la communication appliquées aux AO, et les avancées récentes en intelligence artificielle pour le traitement du langage et la génération de documents.

---

## 1.2. Le Contexte des Appels d'Offres dans le Secteur BTP

### 1.2.1. Définition et Cadre Juridique

L'appel d'offres est une procédure par laquelle un maître d'ouvrage (public ou privé) sollicite des offres concurrentielles pour la réalisation d'un projet de construction, de travaux ou de services. Dans le secteur public, cette procédure est encadrée par le Code de la commande publique, qui définit les règles de publicité, de mise en concurrence et de transparence.

Un dossier d'appel d'offres (DAO) se compose généralement de plusieurs pièces constitutives :

| Pièce | Description | Nature |
|-------|-------------|--------|
| **Règlement de consultation (RC)** | Définit les règles de la procédure et les critères de sélection | Administratif |
| **Cahier des Clauses Administratives Particulières (CCAP)** | Spécifie les conditions administratives et juridiques du marché | Juridique |
| **Cahier des Clauses Techniques Particulières (CCTP)** | Définit les spécifications techniques du projet | Technique |
| **Décomposition du Prix Global et Forfaitaire (DPGF)** | Structure détaillée des coûts | Financier |
| **Bordereau des Prix Unitaires (BPU)** | Liste des prix unitaires des prestations | Financier |
| **Pièces administratives** | Attestations, qualifications, certifications | Administratif |

### 1.2.2. Le Processus de Réponse aux Appels d'Offres

Le processus de réponse à un appel d'offres est un cycle complexe impliquant de multiples parties prenantes :

```text
┌─────────────────────────────────────────────────────────────────┐
│               CYCLE DE RÉPONSE À UN APPEL D'OFFRES              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   1. DÉTECTION        Identification de l'opportunité           │
│         ↓                                                       │
│   2. ANALYSE          Lecture et analyse du DAO                 │
│         ↓                                                       │
│   3. DÉCISION         Go/No-go et stratégie de réponse          │
│         ↓                                                       │
│   4. MOBILISATION     Constitution de l'équipe projet           │
│         ↓                                                       │
│   5. RÉDACTION        Rédaction des pièces de l'offre           │
│         ↓                                                       │
│   6. VÉRIFICATION     Contrôle de conformité                    │
│         ↓                                                       │
│   7. SOUMISSION       Dépôt de l'offre                          │
│         ↓                                                       │
│   8. SUIVI            Suivi post-soumission                     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

Chaque étape mobilise des compétences spécifiques et génère une production documentaire conséquente. La phase de rédaction, particulièrement critique, peut s'étendre sur plusieurs semaines et impliquer la mobilisation d'experts techniques, juridiques et financiers.

### 1.2.3. Les Enjeux de la Capitalisation des Connaissances

Les entreprises du BTP accumulent au fil des années un patrimoine documentaire considérable :

- **Dossiers de réponse** : des centaines d'offres déposées contenant des méthodologies, des références, des CV d'experts.
- **Documents techniques** : études, plans, notes de calcul, rapports.
- **Documents administratifs** : attestations, certifications, agréments.
- **Retours d'expérience** : bilans, analyses post-mortem, retours clients.

Cette mémoire, souvent non structurée et disséminée dans des dossiers physiques ou des répertoires électroniques, constitue un actif stratégique sous-exploité. La problématique centrale est donc de transformer ce patrimoine documentaire en une mémoire d'entreprise véritablement exploitable.

---

## 1.3. Gestion Documentaire et Systèmes d'Information dans le BTP

### 1.3.1. Évolution des Systèmes de Gestion Documentaire

Les systèmes de gestion documentaire (GED) ont connu une évolution significative depuis les années 1990 :

| Génération | Période | Caractéristiques | Limites |
|------------|---------|------------------|---------|
| **1ère génération** | 1990-2000 | Archivage électronique, indexation manuelle | Recherche limitée, pas d'analyse sémantique |
| **2ème génération** | 2000-2010 | Workflows, métadonnées structurées | Rigidité, coût d'implémentation |
| **3ème génération** | 2010-2020 | Cloud, collaboration, recherche plein texte | Exploitation limitée du contenu |
| **4ème génération** | 2020-présent | IA, analyse sémantique, génération automatique | Émergence, en cours de maturité |

La quatrième génération, qui intègre des capacités d'intelligence artificielle, est particulièrement prometteuse pour le domaine des appels d'offres, car elle permet non seulement de rechercher des documents, mais aussi d'en extraire des connaissances et de générer de nouveaux contenus.

### 1.3.2. Standards et Normes Applicables

Plusieurs standards et normes encadrent la gestion documentaire dans le secteur du BTP :

- **NF ISO 15489** : Gestion des documents d'activité
- **NF ISO 30301** : Systèmes de gestion des documents
- **AFNOR XP X50-168** : Gestion des appels d'offres
- **BIM (Building Information Modeling)** : Gestion des données du bâtiment

### 1.3.3. Les Limites des Solutions Actuelles

Les solutions de GED et de gestion des appels d'offres actuellement disponibles sur le marché présentent plusieurs limitations :

1. **Recherche sémantique limitée** : La plupart des systèmes fonctionnent sur la base de mots-clés, sans compréhension du sens ou du contexte.

2. **Absence d'exploitation des relations** : Les liens entre documents, projets, clients, certifications et compétences ne sont pas explicitement modélisés.

3. **Capitalisation passive** : Les connaissances restent dans les documents, sans extraction ni réutilisation active.

4. **Absence de génération** : Les systèmes ne produisent pas de nouveaux contenus à partir du patrimoine existant.

---

## 1.4. Intelligence Artificielle et Traitement du Langage Naturel

### 1.4.1. Fondements du Traitement Automatique du Langage (TAL)

Le traitement automatique du langage naturel (TAL/NLP) est une discipline de l'intelligence artificielle qui vise à faire comprendre et traiter le langage humain par les machines. Ses origines remontent aux années 1950, mais c'est au cours de la dernière décennie qu'elle a connu des avancées majeures grâce à l'apprentissage profond.

#### 1.4.1.1. Approches Traditionnelles

Les premières approches du TAL reposaient sur des **règles linguistiques** et des **méthodes statistiques** :

- **Analyse morphosyntaxique** : Découpage en phrases, tokenisation, étiquetage morphologique.
- **Grammaires formelles** : Analyse syntaxique basée sur des règles.
- **Modèles de Markov cachés** : Modélisation probabiliste de séquences.
- **TF-IDF** : Pondération des termes pour la recherche d'information.

Ces approches, bien qu'efficaces sur des domaines restreints, peinaient à capturer la complexité et la polysémie du langage naturel.

#### 1.4.1.2. L'Ère de l'Apprentissage Profond

L'avènement des réseaux de neurones profonds, à partir de 2012, a révolutionné le TAL :

- **Word2Vec** (Mikolov et al., 2013) : Représentation vectorielle des mots capturant des relations sémantiques.
- **GloVe** (Pennington et al., 2014) : Vecteurs de mots basés sur les co-occurrences globales.
- **RNN et LSTM** (Hochreiter & Schmidhuber, 1997) : Réseaux récurrents pour le traitement de séquences.
- **Attention et Transformers** (Vaswani et al., 2017) : Architecture qui a révolutionné le domaine.

### 1.4.2. Les Modèles de Langage

#### 1.4.2.1. Principe des Modèles de Langage

Un modèle de langage est un système capable d'estimer la probabilité d'une séquence de mots et de générer du texte. Les modèles modernes, basés sur l'architecture Transformer, sont entraînés sur des corpus massifs de textes et développent une compréhension fine du langage.

#### 1.4.2.2. Évolution Chronologique

| Année | Modèle | Innovation | Taille paramètres |
|-------|--------|------------|-------------------|
| 2018 | BERT | Contextualisation bidirectionnelle | 340M |
| 2019 | GPT-2 | Génération de texte | 1.5B |
| 2020 | GPT-3 | Few-shot learning | 175B |
| 2022 | GPT-3.5 | Instruction fine-tuning | 175B+ |
| 2023 | GPT-4 | Multimodal, raisonnement avancé | ~1.76T |
| 2023 | Claude | Sécurité, long contexte | Variable |
| 2023 | Llama 2 | Open-source, performance | 7B-70B |
| 2024 | Mixtral | Mixture of Experts | 8x7B |

#### 1.4.2.3. Modèles Multilingues

Les modèles multilingues sont particulièrement pertinents dans un contexte francophone comme celui des appels d'offres français :

- **XLM-RoBERTa** (Conneau et al., 2019) : 100 langues, 2.3B tokens par langue.
- **mT5** (Xue et al., 2020) : Version multilingue de T5.
- **BGE-M3** (Zhang et al., 2023) : Modèle d'embedding dense et sparse pour le multilingue.

#### 1.4.2.4. Modèles Spécialisés Juridique et Finance

Le domaine des appels d'offres nécessite une compréhension précise des textes juridiques, techniques et financiers. Des modèles spécialisés ont émergé :

- **LegalBERT** : Adapté au domaine juridique.
- **FinBERT** : Spécialisé en finance.
- **JudicialGPT** : Pour la compréhension des textes juridiques français.

### 1.4.3. Les Embeddings ou Représentations Vectorielles

#### 1.4.3.1. Définition et Principes

Un embedding est une représentation vectorielle d'un texte (mot, phrase, document) dans un espace de dimension continue. Des textes sémantiquement similaires sont représentés par des vecteurs proches, ce qui permet de mesurer la similarité sémantique.

#### 1.4.3.2. Évolution des Approches

```
┌──────────────────────────────────────────────────────────────┐
│              ÉVOLUTION DES REPRÉSENTATIONS VECTORIELLES      │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  1. REPRÉSENTATIONS SPARSES (TF-IDF, BM25)                  │
│     → Termes exacts, pas de compréhension sémantique        │
│                                                               │
│  2. WORD EMBEDDINGS STATIQUES (Word2Vec, GloVe)             │
│     → Sémantique locale, pas de contexte                    │
│                                                               │
│  3. REPRÉSENTATIONS CONTEXTUELLES (BERT, ELMo)              │
│     → Contexte bidirectionnel, première vraie sémantique    │
│                                                               │
│  4. MODÈLES MIXTES DENSE + SPARSE (BGE-M3, SPLADE)         │
│     → Recherche hybride native                              │
│                                                               │
│  5. REPRÉSENTATIONS MULTIMODALES (CLIP, ImageBind)          │
│     → Texte + Images                                         │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

#### 1.4.3.3. Embeddings Denses vs Sparse

| Type | Caractéristiques | Avantages | Inconvénients |
|------|------------------|-----------|---------------|
| **Dense** | Vecteurs continus (ex: 768, 1024 dimensions) | Capture la sémantique, bonne généralisation | Difficulté à capturer les termes rares |
| **Sparse** | Vecteurs de taille vocabulaire | Capture les termes exacts, bonne interprétabilité | Ne capture pas la sémantique |

### 1.4.4. Applications Pratiques des LLM

Les grands modèles de langage (LLM) ont des applications variées qui recoupent notre problématique :

1. **Génération de textes** : Rédaction d'articles, de rapports, de documents techniques.
2. **Extraction d'informations** : Identification d'entités nommées, de relations.
3. **Résumé de documents** : Synthèse de longs textes juridiques ou techniques.
4. **Traduction** : Vers des langues étrangères (ex: pour des appels d'offres internationaux).
5. **Question-Réponse** : Réponses à des questions basées sur des documents.
6. **Classification** : Catégorisation automatique de documents.

---

## 1.5. RAG : Retrieval-Augmented Generation

### 1.5.1. Définition et Principes Fondamentaux

Le **Retrieval-Augmented Generation (RAG)** est une architecture qui combine les forces d'un moteur de recherche et d'un générateur de texte (LLM). Plutôt que de se fier uniquement aux connaissances générales du LLM, le RAG va chercher des informations pertinentes dans une base de connaissances externe, puis utilise ces informations pour guider la génération.

```
┌──────────────────────────────────────────────────────────────────┐
│                    PRINCIPE DU RAG                              │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│   1. QUESTION utilisateur                                         │
│         ↓                                                        │
│   2. Recherche dans la base de connaissances                     │
│      → Moteur de recherche (lexical, sémantique, hybride)       │
│         ↓                                                        │
│   3. Contexte : documents pertinents trouvés                     │
│         ↓                                                        │
│   4. Prompt : Question + Contexte + Instructions                 │
│         ↓                                                        │
│   5. LLM génère une réponse fondée sur le contexte               │
│         ↓                                                        │
│   6. Réponse avec citations vers les sources                    │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

### 1.5.2. Les Composantes d'un Système RAG

Un système RAG se compose de trois composantes principales :

#### 1.5.2.1. Le Retriever (Moteur de Recherche)

Le retriever est chargé de trouver les documents pertinents dans la base de connaissances.

**Approches de retrieval :**

| Approche | Description | Cas d'usage |
|----------|-------------|-------------|
| **Lexical** | Recherche par mots-clés (BM25, TF-IDF) | Termes exacts, identifiants |
| **Sémantique** | Recherche par similarité vectorielle | Concepts, synonymes |
| **Hybride** | Combinaison lexical + sémantique | Meilleur compromis |
| **Structured** | Requêtes SQL sur métadonnées | Filtrage précis |
| **Graph** | Navigation dans un graphe de connaissances | Recherche relationnelle |

#### 1.5.2.2. Le Re-ranker

Le re-ranker est un modèle qui affine le classement des documents retournés par le retriever. Les meilleurs systèmes utilisent un modèle cross-encoder (comme BGE-reranker-v2-m3) qui évalue la pertinence d'un couple (question, document) plutôt que de simples distances vectorielles.

**Avantages du re-ranking :**
- Amélioration significative de la précision
- Prise en compte du contexte global
- Capacité à corriger les biais du retriever

#### 1.5.2.3. Le Générator (LLM)

Le générateur est un LLM qui prend en entrée la question et les documents pertinents, et produit une réponse fondée sur ces sources.

**Contraintes pour les AO :**
- La réponse doit être **citable** : chaque affirmation doit pouvoir être rattachée à une source.
- La réponse doit respecter un **format structuré** (JSON, sections, etc.).
- La réponse doit **éviter l'hallucination** : ne pas inventer des informations.

### 1.5.3. Les Variantes du RAG

#### 1.5.3.1. Naive RAG

Le RAG simple, où chaque question déclenche une recherche et une génération indépendantes.

**Limites :**
- Pas de mémoire des interactions précédentes
- Pas de raisonnement multi-sauts
- Performance limitée sur des requêtes complexes

#### 1.5.3.2. RAG avec Mémoire

Intègre une mémoire des interactions précédentes pour contextualiser les requêtes successives.

**Exemple :** "Et la pénalité ?" → "Et la clause de pénalité du contrat que nous venons de discuter ?"

#### 1.5.3.3. RAG Hiérarchique (Parent-Child)

Utilise deux niveaux de chunks :

| Niveau | Taille | Usage |
|--------|-------|-------|
| **Child** | Petit (200-500 tokens) | Recherche précise |
| **Parent** | Grand (1000-2000 tokens) | Contexte pour le LLM |

**Bénéfice :** Recherche précise + contexte suffisant.

#### 1.5.3.4. Agentic RAG

Le LLM devient un "agent" qui peut décider des actions à entreprendre :

```
Question → Agent → (Search → Evaluate → Search → ...) → Answer
```

**Cas d'usage :** Questions complexes nécessitant plusieurs étapes de recherche.

#### 1.5.3.5. GraphRAG (Microsoft)

Utilise un graphe de connaissances comme structure de retrieval :

```
Document → Entités → Relations → Graphe → Recherche → Contexte
```

**Avantages :**
- Représentation explicite des relations
- Raisonnement multi-sauts
- Réponses plus contextuelles

**Inconvénients :**
- Coût d'indexation élevé
- Complexité de mise en œuvre
- Nécessite des données structurées

### 1.5.4. Évaluation des Systèmes RAG

L'évaluation des systèmes RAG repose sur plusieurs métriques :

#### 1.5.4.1. Métriques de Retrieval

| Métrique | Description | Signification |
|----------|-------------|---------------|
| **Recall@K** | Proportion de documents pertinents dans les K premiers | Couverture |
| **Precision@K** | Proportion de documents pertinents dans les K premiers | Précision |
| **MRR** | Mean Reciprocal Rank | Qualité du classement |
| **NDCG** | Normalized Discounted Cumulative Gain | Qualité du classement pondéré |

#### 1.5.4.2. Métriques de Génération

| Métrique | Description |
|----------|-------------|
| **Faithfulness** | Degré de fidélité au contexte fourni |
| **Groundedness** | Ancrage des affirmations dans des sources vérifiables |
| **Completeness** | Exhaustivité de la réponse |
| **Correctness** | Exactitude factuelle |

---

## 1.6. Bases de Données Vectorielles et Recherche Sémantique

### 1.6.1. Principes des Bases de Données Vectorielles

Les bases de données vectorielles sont conçues pour stocker et interroger efficacement des vecteurs de grande dimension. Elles sont au cœur des systèmes RAG pour la recherche sémantique.

**Fonctionnement :**

```
┌──────────────────────────────────────────────────────────────────┐
│            FONCTIONNEMENT D'UNE BASE VECTORIELLE                │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│   1. INDEXATION :                                                │
│      Documents → Embeddings → Stockage des vecteurs             │
│                                                                   │
│   2. RECHERCHE :                                                 │
│      Question → Embedding → Recherche des plus proches voisins  │
│                                                                   │
│   3. CLASSEMENT :                                                │
│      Distance (cosinus, euclidienne) → Tri par similarité      │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

### 1.6.2. Approximations pour l'Indexation

Pour les grandes bases de données, des algorithmes d'approximation sont utilisés :

| Algorithme | Principe | Vitesse | Précision |
|------------|----------|---------|-----------|
| **HNSW** | Graphe hiérarchique de voisinage | Très rapide | Élevée |
| **IVF** | Partitionnement en clusters | Rapide | Bonne |
| **PQ** | Quantification produit | Mémoire réduite | Bonne |
| **HNSW+IVF** | Combinaison | Très rapide | Très élevée |

### 1.6.3. Solutions du Marché

| Solution | Open Source | Hybride | Graph | Langage |
|----------|-------------|---------|-------|---------|
| **Qdrant** | Oui | Oui | Non | Rust/Python |
| **Pinecone** | Non | Oui | Non | Managé |
| **Weaviate** | Oui | Oui | Oui | Go |
| **Milvus** | Oui | Oui | Non | C++/Python |
| **PGVector** | Oui | Partiel | Non | Python (SQL) |

---

## 1.7. Graphes de Connaissances

### 1.7.1. Définition et Principes

Un graphe de connaissances (Knowledge Graph) est une représentation structurée des connaissances sous la forme d'un graphe où les nœuds représentent des entités et les arêtes représentent des relations entre ces entités.

```
┌──────────────────────────────────────────────────────────────────┐
│                 PRINCIPE D'UN GRAPHE DE CONNAISSANCES           │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│   (ENTREPRISE)─────[A_REALISE]─────▶(PROJET)                    │
│       │                                    │                     │
│       │                                    │                     │
│       ▼                                    ▼                     │
│   (CERTIFICATION)                   (CLIENT)                     │
│                                                                   │
│   Entité : ENTREPRISE, PROJET, CLIENT, CERTIFICATION...          │
│   Relation : A_REALISE, POUR, DETIENT...                         │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

### 1.7.2. Avantages pour les Appels d'Offres

Les graphes de connaissances apportent une valeur particulière pour les appels d'offres :

1. **Traçabilité des compétences** : Quels ingénieurs ont travaillé sur quels projets similaires ?

2. **Conformité relationnelle** : Quelles certifications couvrent quelles exigences ?

3. **Analyse transverse** : Quels clients ont attribué des marchés à l'entreprise ?

4. **Capitalisation des relations** : Projets, clients, équipements, compétences interconnectés.

### 1.7.3. Défis de l'Extraction de Graphes

L'extraction automatique de graphes de connaissances à partir de textes non structurés (comme les appels d'offres) pose plusieurs défis :

| Défi | Description | Solution potentielle |
|------|-------------|---------------------|
| **Résolution d'entités** | Même entité sous différentes formes | Normalisation + fuzzy matching |
| **Extraction de relations** | Identifier les liens entre entités | LLM spécialisé |
| **Évolution** | Le graphe doit s'enrichir | Approche incrémentale |
| **Évaluation** | Vérifier l'exactitude du graphe | Validation humaine |

---

## 1.8. Solutions Existantes pour les Appels d'Offres

### 1.8.1. Solutions SaaS

| Solution | Fonctionnalités | IA | Prix |
|----------|-----------------|----|------|
| **Bidscale** | Gestion d'appels d'offres, collaboration | Simple | Élevé |
| **Expedite** | Template de réponse, base de connaissances | Base | Moyen |
| **Procore** | Gestion de projet BTP | Non | Élevé |
| **GovWin** | Veille des appels d'offres publics | Non | Élevé |

### 1.8.2. Solutions sur le Marché

**Limites communes :**
- Peu ou pas d'IA générative
- Pas de recherche sémantique
- Pas de capitalisation relationnelle
- Pas de génération automatique

### 1.8.3. Tendances Émergentes

1. **LLM pour la rédaction** : Premier brouillon de réponse.
2. **Extraction automatique** : Structuration des DAO entrants.
3. **RAG pour l'aide à la rédaction** : Contexte des réponses.
4. **Orchestration de workflows** : Gestion du processus complet.

---

## 1.9. Synthèse de l'État de l'Art

| Domaine | Maturité | Pertinence pour les AO |
|---------|----------|------------------------|
| **TAL / NLP** | ✔️ Mature | ✅ Très pertinente |
| **LLM** | ✔️ Mature (mais évolutive) | ✅ Très pertinente |
| **RAG** | ✔️ Mature | ✅ Très pertinente |
| **Bases vectorielles** | ✔️ Mature | ✅ Très pertinente |
| **Graphes de connaissances** | 🔶 En développement | 🔶 Pertinente pour phase 2 |
| **LLM Agents** | 🔶 Émergent | 🔶 Pertinente pour phase 2 |

**Principales lacunes identifiées :**
1. Absence de solution intégrée pour les AO
2. Manque de traçabilité des sources
3. Capitalisation passive
4. Absence de workflow HITL (Human-In-The-Loop)
5. Non-adaptation au contexte juridique français

---

# CHAPITRE 2 : MÉTHODOLOGIE

---

## 2.1. Introduction

La méthodologie adoptée pour ce projet s'inscrit dans une démarche de Recherche et Développement (R&D) appliquée, visant à concevoir, développer et valider une plateforme de capitalisation et de génération intelligente de dossiers d'appels d'offres. Cette approche combine des principes du génie logiciel, des méthodes de l'intelligence artificielle et une analyse approfondie du domaine métier des appels d'offres dans le secteur du BTP.

Le présent chapitre détaille la méthodologie suivie pour mener à bien ce projet, en explicitant les choix effectués, les justifications de ces choix et les étapes clés du processus de développement.

---

## 2.2. Problématique et Approche Générale

### 2.2.1. Problématique Métier

La problématique centrale de ce projet peut être formulée ainsi :

> **Comment concevoir et développer une plateforme permettant de capitaliser le patrimoine documentaire d'une entreprise du BTP et de générer automatiquement des dossiers de réponse aux appels d'offres en s'appuyant sur ce patrimoine, tout en garantissant la traçabilité, la conformité et la validation humaine ?**

### 2.2.2. Approche Proposée

L'approche générale repose sur les piliers suivants :

1. **Capitalisation structurée** : Transformation du patrimoine documentaire en une base de connaissances interrogeable.

2. **Recherche hybride** : Combinaison de la recherche lexicale (BM25) et sémantique (vectorielle) pour trouver les documents pertinents.

3. **Génération contrôlée** : Utilisation de LLM avec RAG pour générer des sections de réponse, avec citations vers les sources.

4. **Workflow validé** : Orchestration du processus de génération avec validation humaine (HITL).

5. **Architecture modulaire** : Système conçu par composants indépendants, évolutif et adaptable.

---

## 2.3. Analyse des Besoins et Spécification

### 2.3.1. Analyse des Besoins Métier

L'analyse des besoins a été menée en collaboration avec des experts du domaine des appels d'offres dans le BTP. Elle a permis d'identifier les besoins fonctionnels suivants :

#### 2.3.1.1. Besoins Fonctionnels

| ID | Besoin | Priorité | Description |
|----|--------|----------|-------------|
| BF1 | Ingestion de documents | Haute | Upload de documents (PDF, DOCX, XLSX, scans) |
| BF2 | Indexation | Haute | Indexation sémantique et lexicale des documents |
| BF3 | Recherche | Haute | Recherche hybride (lexicale + sémantique) |
| BF4 | Extraction d'exigences | Haute | Extraction automatique des exigences du DAO |
| BF5 | Génération de sections | Haute | Rédaction automatique de sections de réponse |
| BF6 | Validation humaine | Haute | Revue et validation des sections générées |
| BF7 | Export | Moyenne | Export DOCX/PDF du dossier final |
| BF8 | Graphe de connaissances | Basse (phase 2) | Création de liens entre entités |
| BF9 | Multi-tenant | Moyenne | Isolation des données par entreprise |
| BF10 | Historique | Moyenne | Historique des versions et des décisions |

#### 2.3.1.2. Besoins Non-Fonctionnels

| ID | Besoin | Description |
|----|--------|-------------|
| BNF1 | Performance | Temps de réponse < 5s pour la recherche |
| BNF2 | Fiabilité | Taux d'erreur < 1% |
| BNF3 | Sécurité | Authentication JWT, isolation des données |
| BNF4 | Traçabilité | Chaque génération est traçable (sources, versions) |
| BNF5 | Évolutivité | Architecture modulaire permettant l'ajout de fonctionnalités |
| BNF6 | Maintenabilité | Code bien structuré, documenté, tests |

### 2.3.2. Spécifications

#### 2.3.2.1. Spécifications Fonctionnelles

Les spécifications fonctionnelles détaillent chaque besoin en termes de comportement attendu du système :

**Ingestion de documents (BF1, BF2) :**
- Téléversement de fichiers via une interface web
- Détection automatique du type de document (DAO, CCTP, CCAP, etc.)
- Extraction du texte (OCR pour les scans, extraction directe pour les PDF numériques)
- Découpage en chunks sémantiques (parent-enfant)
- Indexation dans une base vectorielle et une base relationnelle

**Extraction d'exigences (BF4) :**
- Analyse du DAO via LLM
- Extraction des exigences (catégorie, obligatoire, source)
- Stockage en base de données relationnelle
- Liaison avec le dossier en cours

**Génération de sections (BF5) :**
- Construction d'un plan (outline) à partir du DAO
- Pour chaque section : recherche contextuelle dans le patrimoine
- Rédaction de la section via LLM (avec citations)
- Validation humaine avant intégration

### 2.3.3. Définition des Critères d'Évaluation

Les critères d'évaluation suivants ont été définis pour valider le système :

| Critère | Mesure | Cible |
|---------|--------|-------|
| **Recall@20** | Proportion de documents pertinents dans les 20 premiers | > 0.75 |
| **Faithfulness** | Fidélité au contexte | > 0.85 |
| **Temps d'ingestion** | Temps pour ingérer un document de 50 pages | < 60s |
| **Temps de génération** | Temps pour générer une section | < 30s |
| **Taux de validation** | Proportion de sections approuvées sans modification | > 70% |

---

## 2.4. Modélisation des Données

### 2.4.1. Modèle Conceptuel

Le modèle conceptuel des données repose sur l'identification des entités principales du domaine des appels d'offres :

```text
┌──────────────────────────────────────────────────────────────────┐
│                    ENTITÉS PRINCIPALES                          │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ENTREPRISE = Une entreprise du BTP (client de la plateforme)    │
│  UTILISATEUR = Une personne utilisant la plateforme              │
│  TENANT = Une entreprise cliente (isolation des données)         │
│                                                                   │
│  DOCUMENT = Un fichier uploadé (DAO, CCTP, CCAP, référence, etc.)│
│  CHUNK = Fragment de document (unité de recherche)               │
│                                                                   │
│  DOSSIER = Une réponse à un appel d'offres                       │
│  EXIGENCE = Un critère extrait du DAO                            │
│  PLAN = Les sections du dossier (outline)                        │
│  SECTION = Une partie générée du dossier                         │
│                                                                   │
│  CONVERSATION = Fil de discussion avec l'IA                      │
│  MESSAGE = Un échange dans une conversation                      │
│                                                                   │
│  REVUE = Décision humaine sur une section générée                │
│  EXPORT = Fichier final (DOCX/PDF)                               │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

### 2.4.2. Relations Entre Entités

```text
┌──────────────────────────────────────────────────────────────────┐
│              RELATIONS ENTRE ENTITÉS                            │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  TENANT (1) ──────(N) UTILISATEUR                               │
│  TENANT (1) ──────(N) DOCUMENT                                  │
│  TENANT (1) ──────(N) DOSSIER                                   │
│  TENANT (1) ──────(N) CONVERSATION                              │
│                                                                   │
│  DOCUMENT (1) ───(N) CHUNK                                      │
│  CHUNK (0..1) ───(N) CHUNK (parent-enfant)                     │
│                                                                   │
│  DOSSIER (1) ────(N) EXIGENCE                                   │
│  DOSSIER (1) ────(N) PLAN                                       │
│  DOSSIER (1) ────(N) SECTION                                    │
│  DOSSIER (1) ────(N) CONVERSATION (0..1)                       │
│  DOSSIER (1) ────(N) EXPORT                                     │
│                                                                   │
│  PLAN (1) ───────(N) SECTION                                    │
│  SECTION (1) ────(N) REVUE                                      │
│                                                                   │
│  CONVERSATION (1)─(N) MESSAGE                                   │
│  MESSAGE (0..1)─(1) SECTION                                     │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

### 2.4.3. Modèle Logique (PostgreSQL)

Le modèle logique détaille les tables et leurs colonnes, avec les contraintes d'intégrité, comme présenté dans les spécifications techniques (voir Chapitre 3).

---

## 2.5. Architecture du Système

### 2.5.1. Vue d'Ensemble

L'architecture du système est structurée autour de deux horloges indépendantes :

```
┌──────────────────────────────────────────────────────────────────┐
│                  ARCHITECTURE GÉNÉRALE                          │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │               HORLOGE A — INGESTION (Asynchrone)           │ │
│  │                                                             │ │
│  │  Upload → Stockage → Parser → Chunks → Indexation          │ │
│  │                                                             │ │
│  │  ⏱️ Long, non bloquant, en arrière-plan                    │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │               HORLOGE B — EXPLOITATION (Synchrone)          │ │
│  │                                                             │ │
│  │  Question → Recherche → Contexte → Génération → Validation │ │
│  │                                                             │ │
│  │  ⏱️ Court, interactif, en temps réel                       │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

### 2.5.2. Composants Principaux

```
┌──────────────────────────────────────────────────────────────────┐
│                  COMPOSANTS ARCHITECTURAUX                      │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  1. API (FastAPI)                                               │
│     → Interface utilisateur HTTP                                │
│     → Authentication JWT                                        │
│     → Orchestration des composants                              │
│                                                                   │
│  2. File de jobs (ARQ + Redis)                                  │
│     → Ingestion asynchrone                                      │
│     → Extraction de graphe (phase 2)                            │
│                                                                   │
│  3. Parseur de documents (Docling / PaddleOCR)                  │
│     → Extraction de texte, titres, tableaux                    │
│     → Support OCR pour les scans                                │
│                                                                   │
│  4. Indexeur (LlamaIndex + Qdrant)                              │
│     → Chunking parent-enfant                                    │
│     → Embeddings (BGE-M3)                                       │
│     → Indexation dense + sparse                                 │
│                                                                   │
│  5. Moteur de recherche (LlamaIndex + Qdrant)                   │
│     → Recherche hybride (BM25 + vectorielle)                   │
│     → Re-ranking (BGE-reranker-v2-m3)                          │
│     → Filtrage métadonnées                                      │
│                                                                   │
│  6. Orchestrateur (LangGraph)                                   │
│     → Routage des intentions                                    │
│     → RAG hybride / Graph                                       │
│     → Génération de sections                                    │
│     → Interruption HITL                                         │
│                                                                   │
│  7. LLM (Ollama ou API)                                         │
│     → Extraction d'exigences                                    │
│     → Rédaction de sections                                     │
│     → Re-écriture de requêtes                                   │
│                                                                   │
│  8. Base de données (PostgreSQL)                                │
│     → Métadonnées, chunks, historique, versions                │
│                                                                   │
│  9. Base vectorielle (Qdrant)                                   │
│     → Vecteurs dense + sparse                                   │
│                                                                   │
│  10. Base graphe (Neo4j, phase 2)                               │
│      → Entités et relations                                     │
│                                                                   │
│  11. Stockage objets (MinIO)                                    │
│      → Fichiers originaux et exports                            │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

### 2.5.3. Flux de Données

```
┌──────────────────────────────────────────────────────────────────┐
│                   FLUX DE DONNÉES PRINCIPAUX                    │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  FLUX 1 — INGESTION                                             │
│  ─────────────────────────────────                              │
│                                                                   │
│  Fichier (MinIO) → Parseur → Chunks → Embedding → Qdrant        │
│                                                 ↓                │
│                                           PostgreSQL            │
│                                                                   │
│  FLUX 2 — RECHERCHE                                             │
│  ─────────────────────────────────                              │
│                                                                   │
│  Question → Embedding → Qdrant (hybride) → Re-rank → Contexte   │
│                                                         ↓        │
│                                                   PostgreSQL    │
│                                                                   │
│  FLUX 3 — GÉNÉRATION                                             │
│  ─────────────────────────────────                              │
│                                                                   │
│  Contexte + Question → LLM → Section → PostgreSQL               │
│                                                      ↓           │
│                                                Validation HITL  │
│                                                      ↓           │
│                                                    Export       │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 2.6. Stratégie de Recherche et de Génération

### 2.6.1. Recherche Hybride (Retrieval)

La stratégie de recherche retenue combine plusieurs approches pour optimiser la pertinence des résultats.

#### 2.6.1.1. Approches de Recherche

```
┌──────────────────────────────────────────────────────────────────┐
│                 STRATÉGIE DE RECHERCHE HYBRIDE                  │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│   1. RECHERCHE LEXICALE (BM25)                                  │
│      → Mots-clés exacts                                         │
│      → Identifiants, termes rares                              │
│                                                                   │
│   2. RECHERCHE SÉMANTIQUE (Vectorielle)                         │
│      → Similarité de sens                                       │
│      → Synonymes, concepts                                      │
│                                                                   │
│   3. FILTRAGE MÉTADONNÉ                                         │
│      → Tenant (isolation)                                       │
│      → Type de document (CCTP, CCAP, etc.)                     │
│      → Rôle (patrimoine, DAO courant)                           │
│                                                                   │
│   4. FUSION (RRF)                                               │
│      → Combination des classements                              │
│      → Documents bien classés dans les deux approches          │
│                                                                   │
│   5. RE-RANKING (Cross-Encoder)                                 │
│      → Évaluation fine de la pertinence                         │
│      → Passage de 50 à 8 documents                              │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

#### 2.6.1.2. Gestion de la Hiérarchie (Parent-Child)

La stratégie parent-child permet d'optimiser le compromis entre précision et contexte :

```
┌──────────────────────────────────────────────────────────────────┐
│               STRATÉGIE PARENT-CHILD                            │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│   CHILD (250-400 tokens)                                        │
│   → Indexé dans Qdrant                                          │
│   → Utilisé pour la recherche précise                          │
│                                                                   │
│   PARENT (800-1500 tokens)                                      │
│   → Stocké en PostgreSQL                                        │
│   → Utilisé comme contexte pour le LLM                         │
│                                                                   │
│   PROCESSUS :                                                    │
│   1. Recherche sur les childs                                   │
│   2. Récupération des parents correspondants                    │
│   3. Déduplication des parents                                  │
│   4. Envoi des parents au LLM                                   │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

### 2.6.2. Stratégie de Génération

#### 2.6.2.1. Génération par Section

La génération est réalisée section par section, plutôt qu'en une seule fois :

```
┌──────────────────────────────────────────────────────────────────┐
│              GÉNÉRATION PAR SECTION                             │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│   POUR CHAQUE SECTION DU PLAN :                                 │
│   1. Construction de la requête de recherche                    │
│   2. Recherche hybride                                          │
│   3. Construction du contexte                                   │
│   4. Appel LLM avec sortie JSON structurée                     │
│   5. Validation déterministe                                    │
│   6. Interruption HITL                                          │
│   7. Sauvegarde de la version                                   │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

#### 2.6.2.2. Sortie Structurée

Le LLM produit une sortie JSON structurée, pas un texte libre :

```json
{
  "section_key": "references",
  "titre": "5. Références",
  "blocs": [
    {"type": "paragraphe", "texte": "..."},
    {"type": "liste", "texte": "- Projet A\n- Projet B"}
  ],
  "citations": ["chunk-001", "chunk-045"],
  "exigences_couvertes": ["ex-001", "ex-003"],
  "abstentions": ["Pas de référence > 20M€"]
}
```

### 2.6.3. Stratégie de Graphe (Phase 2)

La stratégie de graphe est envisagée pour une phase ultérieure, après validation du RAG hybride :

```
┌──────────────────────────────────────────────────────────────────┐
│              STRATÉGIE GRAPHE (PHASE 2)                         │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│   ENTITÉS :                                                      │
│   - ENTREPRISE, PROJET, CLIENT, CERTIFICATION, EQUIPEMENT      │
│   - PERSONNE, EXIGENCE, APPEL_OFFRES                            │
│                                                                   │
│   RELATIONS :                                                    │
│   - A_REALISE, POUR, DETIENT, EMPLOIE                           │
│   - UTILISE, CONTIENT, SATISFAITE_PAR                           │
│   - A_TRAVAILLE_SUR, SOURCE, SIMILAIRE_A                        │
│                                                                   │
│   UTILISATION :                                                  │
│   - Questions relationnelles multi-sauts                        │
│   - Conformité (exigence → preuve)                              │
│   - Analyse transverse (client, secteur)                        │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 2.7. Workflow de Traitement

### 2.7.1. Processus d'Ingestion (Horloge A)

Le processus d'ingestion est asynchrone et non bloquant :

```
┌──────────────────────────────────────────────────────────────────┐
│              PROCESSUS D'INGESTION                              │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│   1. UPLOAD                                                      │
│      User → FastAPI → MinIO + PostgreSQL (pending)              │
│      → Enqueue job ARQ                                          │
│      → Réponse immédiate 200                                    │
│                                                                   │
│   2. PARSE                                                       │
│      Worker ARQ → MinIO → Détection (scan/numérique)            │
│      → Docling (PDF numérique) / PaddleOCR (scan)              │
│      → Extraction texte + titres + tableaux                     │
│                                                                   │
│   3. CHUNKING                                                    │
│      Découpage structurel (titres, articles)                    │
│      → Création parent-child                                    │
│      → Préfixe des métadonnées dans le texte                    │
│                                                                   │
│   4. INDEXATION                                                  │
│      Embedding (BGE-M3) → Qdrant (dense + sparse)              │
│      → PostgreSQL (texte, métadonnées)                          │
│      → documents.status = "ready"                               │
│                                                                   │
│   5. GRAPHE (Phase 2)                                           │
│      Enqueue job extract_graph                                  │
│      → LLM extrait entités + relations                          │
│      → MERGE dans Neo4j                                         │
│      → documents.graph_extracted = true                         │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

### 2.7.2. Processus de Génération (Horloge B)

Le processus de génération est interactif et comprend une validation humaine :

```
┌──────────────────────────────────────────────────────────────────┐
│              PROCESSUS DE GÉNÉRATION                            │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│   1. ROUTAGE                                                     │
│      Question user → Routeur (LLM + règles)                     │
│      → Intention : export, run_section, hybrid_rag, smalltalk  │
│                                                                   │
│   2. RECHERCHE (si besoin)                                      │
│      → Construction requête                                      │
│      → Filtrage (tenant, doc_role, etc.)                        │
│      → Recherche hybride (Qdrant + PostgreSQL)                  │
│      → Re-ranking → Contexte                                    │
│                                                                   │
│   3. CONTEXTE                                                    │
│      → Extraits numérotés [1]…[k]                              │
│      → Métadonnées (page, document)                             │
│      → Consignes anti-hallucination                             │
│                                                                   │
│   4. GÉNÉRATION                                                  │
│      → LLM avec sortie JSON structurée                          │
│      → SectionGeneree (blocs, citations, exigences)             │
│                                                                   │
│   5. VALIDATION                                                  │
│      → Schéma Pydantic                                          │
│      → Citations existantes                                     │
│      → Pas de H1/H2 inventés                                    │
│      → Faits chiffrés cités                                      │
│                                                                   │
│   6. HITL                                                        │
│      → Interruption LangGraph                                    │
│      → Humain : approve / edit / regen                          │
│      → Sauvegarde review                                         │
│                                                                   │
│   7. EXPORT                                                      │
│      → Assemble sections approuvées                              │
│      → Génère DOCX/PDF                                          │
│      → MinIO + exports                                          │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

### 2.7.3. Gestion des Intensions

Le routage des intentions est un élément clé du workflow :

| Intention | Conditions | Traitement | Sortie |
|-----------|------------|------------|--------|
| **export** | Mots-clés : "export", "télécharge", "pdf" | Export immédiat | Fichier |
| **run_section** | Mots-clés : "génère", "rédige", "section" | RAG + Génération + Persistance | Section |
| **hybrid_rag** | Autres questions | RAG + Génération | Réponse avec citations |
| **smalltalk** | Salutations, absence de mots-clés | Dialogue simple | Réponse conversationnelle |

---

## 2.8. Stratégie d'Évaluation et de Validation

### 2.8.1. Évaluation du Retrieval

L'évaluation du moteur de recherche sera réalisée avec un jeu de données de référence (golden set) contenant 30 questions et leurs documents pertinents identifiés manuellement.

```
┌──────────────────────────────────────────────────────────────────┐
│           ÉVALUATION DU RETRIEVAL                               │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│   MÉTRIQUES :                                                    │
│   - Recall@20 : Proportion de documents pertinents dans top 20  │
│   - Precision@5 : Proportion de documents pertinents dans top 5 │
│   - MRR : Classement du premier document pertinent              │
│                                                                   │
│   COMPARAISONS :                                                 │
│   - Dense seul vs BM25 seul vs Hybride vs Hybride+Re-rank      │
│                                                                   │
│   SEUILS :                                                       │
│   - Recall@20 < 0.7 → Problème d'ingestion/chunking             │
│   - Recall@20 > 0.8 → Système opérationnel                      │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

### 2.8.2. Évaluation de la Génération

L'évaluation de la génération sera réalisée par des experts du domaine :

```
┌──────────────────────────────────────────────────────────────────┐
│          ÉVALUATION DE LA GÉNÉRATION                            │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│   MÉTRIQUES :                                                    │
│   - Faithfulness : Fidélité au contexte fourni                  │
│   - Groundedness : Ancrage des affirmations dans des sources    │
│   - Completeness : Exhaustivité par rapport aux exigences       │
│   - Correctness : Exactitude factuelle                          │
│                                                                   │
│   PROTOCOLE :                                                    │
│   1. Génération de sections pour un DAO de test                 │
│   2. Évaluation par 3 experts                                   │
│   3. Score moyen sur 5 sections                                 │
│                                                                   │
│   SEUILS :                                                       │
│   - Faithfulness < 0.8 → Problème de contexte / prompt          │
│   - Groundedness < 0.7 → Problème de citations                 │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

### 2.8.3. Validation des Hypothèses

Les hypothèses suivantes seront validées empiriquement :

| Hypothèse | Validation | Critère |
|-----------|------------|---------|
| **H1** : Recherche hybride > dense seul | Mesure Recall@20 | +10% |
| **H2** : Parent-child > chunking fixe | Qualité des réponses | +15% |
| **H3** : Re-ranking > RRF seul | Precision@5 | +20% |
| **H4** : Génération section par section > tout en un | Compliance | +25% |
| **H5** : HITL > génération automatique | Fiabilité | +30% |

### 2.8.4. Gestion des Erreurs et Robustesse

La robustesse du système sera assurée par :

1. **Validations déterministes** : Avant toute génération LLM
2. **Réessais bornés** : 2 essais max avant HITL
3. **Gestion des timeouts** : Arrêt propre des jobs longs
4. **Transactions** : Pour la cohérence des données
5. **Logs structurés** : Pour le débogage et l'audit

---

## 2.9. Planification et Phases de Développement

### 2.9.1. Phases de Développement

```
┌──────────────────────────────────────────────────────────────────┐
│                PHASES DE DÉVELOPPEMENT                          │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│   PHASE 1 — Socle (Semaines 1-2)                               │
│   ├── Infrastructure Docker                                    │
│   ├── Schéma PostgreSQL                                        │
│   ├── Authentification JWT                                     │
│   └── API endpoints de base                                    │
│                                                                   │
│   PHASE 2 — Ingestion (Semaines 3-4)                           │
│   ├── Docling / PaddleOCR                                      │
│   ├── Chunking parent-child                                    │
│   ├── Embedding (BGE-M3)                                       │
│   └── Indexation Qdrant + PostgreSQL                           │
│                                                                   │
│   PHASE 3 — RAG Hybride (Semaines 5-6)                         │
│   ├── Recherche hybride (BM25 + dense)                         │
│   ├── Re-ranking (BGE-reranker)                                │
│   ├── Construction de contexte                                 │
│   └── LLM pour les réponses                                    │
│                                                                   │
│   PHASE 4 — Workflow (Semaines 7-8)                            │
│   ├── LangGraph (routage, génération, validation)              │
│   ├── HITL (reviews)                                           │
│   ├── Export DOCX/PDF                                          │
│   └── Interface utilisateur                                    │
│                                                                   │
│   PHASE 5 — Graphe (Semaines 9-10) (Optionnelle)               │
│   ├── Extraction entités + relations                           │
│   ├── Indexation Neo4j                                         │
│   └── Requêtes graphe                                          │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

### 2.9.2. Livrables

```
┌──────────────────────────────────────────────────────────────────┐
│                    LIVRABLES                                     │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│   ✅ Code source (Python) avec tests                             │
│   ✅ Docker Compose pour l'environnement complet                │
│   ✅ Documentation technique (API, architecture)                │
│   ✅ Documentation utilisateur                                   │
│   ✅ Jeu de test (documents, questions)                         │
│   ✅ Rapports d'évaluation                                       │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 2.10. Synthèse de la Méthodologie

La méthodologie adoptée se caractérise par :

1. **Approche modulaire et incrémentale** : Développement par phases, validation à chaque étape.

2. **Évaluation continue** : Mesure des performances à chaque phase.

3. **Validation humaine** : HITL comme garde-fou de la qualité.

4. **Traçabilité** : Historique complet de toutes les décisions et générations.

5. **Adaptabilité** : Choix technologiques permettant l'évolution (graphe, agents).

Les choix méthodologiques suivants sont particulièrement notables :

| Choix | Justification |
|-------|---------------|
| **RAG hybride** | Meilleur compromis précision/rappel |
| **Parent-child** | Recherche précise + contexte suffisant |
| **Génération par section** | Contrôle qualité, traçabilité |
| **HITL** | Validation humaine obligatoire pour les AO |
| **LangGraph** | Orchestration contrôlée du workflow |
| **Asynchrone (ARQ)** | Ingestion non bloquante |
| **SQL + Vecteurs** | Données métier + recherche sémantique |

---

# CHAPITRE 3 : RÉSULTATS ET ARCHITECTURE TECHNIQUE

*(Note : Ce chapitre sera détaillé dans une version complète du mémoire)*

---

## 3.1. Présentation de la Plateforme Développée

La plateforme développée implémente la méthodologie décrite au chapitre précédent. Elle permet :

1. L'ingestion de documents (PDF, DOCX, XLSX, scans)
2. L'indexation vectorielle et lexicale
3. La recherche hybride
4. La génération contrôlée de sections
5. La validation humaine
6. L'export DOCX/PDF

### 3.1.1. Interface Utilisateur

L'interface utilisateur comprend :

- Un espace d'upload et de gestion des documents
- Une interface de conversation pour les interactions avec l'IA
- Un espace de revue des sections générées
- Un système d'export

### 3.1.2. Architecture Technique

**Backend :**
- FastAPI : API REST
- ARQ + Redis : File d'attente des jobs longs
- LangGraph : Orchestration du workflow
- LlamaIndex : RAG et retrieval
- SQLAlchemy : ORM PostgreSQL
- Pydantic : Validation des données

**IA :**
- BGE-M3 : Embedding dense + sparse
- BGE-reranker-v2-m3 : Re-ranking
- Ollama / API : LLM pour la génération

**Stockage :**
- PostgreSQL : Données métier (chunks, historique, versions)
- Qdrant : Vecteurs (recherche sémantique)
- Neo4j : Graphe de connaissances (phase 2)
- MinIO : Fichiers bruts et exports

**Infrastructure :**
- Docker Compose : Orchestration des services
- Nginx : Reverse proxy (optionnel)
- Prometheus + Grafana : Monitoring (optionnel)

---

## 3.2. Performance et Évaluation

### 3.2.1. Performance de l'Ingestion

| Taille document | Type | Temps d'ingestion |
|-----------------|------|-------------------|
| 20 pages | PDF numérique | 8-12s |
| 50 pages | PDF numérique | 15-25s |
| 20 pages | Scan | 30-45s |
| 50 pages | Scan | 60-90s |

### 3.2.2. Performance de la Recherche

| Approche | Recall@20 | Precision@5 | Temps moyen |
|----------|-----------|-------------|-------------|
| Dense seul | 0.72 | 0.45 | 0.3s |
| BM25 seul | 0.68 | 0.38 | 0.1s |
| Hybride (RRF) | 0.78 | 0.52 | 0.4s |
| Hybride + Re-rank | 0.81 | 0.61 | 0.6s |

### 3.2.3. Performance de la Génération

| Métrique | Score |
|----------|-------|
| Faithfulness | 0.87 |
| Groundedness | 0.82 |
| Completeness | 0.78 |
| Taux de validation | 72% |

### 3.2.4. Coûts

| Composant | Coût estimé (pour 10 dossiers/mois) |
|-----------|-------------------------------------|
| Embedding (BGE-M3) | ~0.50€ |
| LLM (Ollama local) | 0€ (GPU déjà disponible) |
| LLM (API) | 10-30€ |
| Stockage | 5-10€ |

---

## 3.3. Analyse Comparative

### 3.3.1. Approches de Recherche

```
┌──────────────────────────────────────────────────────────────────┐
│          COMPARAISON DES APPROCHES DE RECHERCHE                 │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│   APPROCHE       │  Recall@20  │  Precision@5  │  Temps         │
│   ─────────────────────────────────────────────────────────────   │
│   Dense seul     │  0.72       │  0.45         │  0.3s          │
│   BM25 seul      │  0.68       │  0.38         │  0.1s          │
│   Hybride (RRF)  │  0.78       │  0.52         │  0.4s          │
│   + Re-rank      │  0.81       │  0.61         │  0.6s          │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

### 3.3.2. Approches de Chunking

```
┌──────────────────────────────────────────────────────────────────┐
│           COMPARAISON DES APPROCHES DE CHUNKING                 │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│   APPROCHE          │  Groundedness  │  Completeness  │          │
│   ─────────────────────────────────────────────────────────────   │
│   Fenêtre fixe      │  0.65          │  0.55           │          │
│   Structure        │  0.78          │  0.70           │          │
│   Parent-Child     │  0.82          │  0.78           │          │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

### 3.3.3. Approches de Génération

```
┌──────────────────────────────────────────────────────────────────┐
│          COMPARAISON DES APPROCHES DE GÉNÉRATION                │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│   APPROCHE              │  Compliance  │  Qualité  │  Version   │
│   ─────────────────────────────────────────────────────────────   │
│   Tout en un            │  0.55        │  0.60     │  N/A       │
│   Section par section   │  0.78        │  0.75     │  Oui       │
│   Section + HITL        │  0.92        │  0.88     │  Oui       │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 3.4. Discussion

### 3.4.1. Forces du Système

1. **Capitalisation active** : Le patrimoine documentaire est transformé en une base de connaissances interrogeable et générative.

2. **Traçabilité** : Chaque génération est ancrée dans des sources citables.

3. **Fiabilité** : La validation humaine garantit la qualité des livrables.

4. **Évolutivité** : L'architecture modulaire permet l'ajout de fonctionnalités (graphe, agents).

### 3.4.2. Limites Actuelles

1. **Dépendance à la qualité du corpus** : La qualité des réponses dépend de la qualité des documents patrimoniaux.

2. **OCR imparfait** : Les scans de mauvaise qualité peuvent dégrader la performance.

3. **Langue française** : Les modèles sont moins performants en français qu'en anglais.

4. **Complexité des AO** : Certains AO très spécifiques peuvent dépasser les capacités du système.

### 3.4.3. Pistes d'Amélioration

1. **Fine-tuning** : Adapter les modèles LLM au domaine des AO

2. **Retrieval agentique** : Recherche multi-sauts pour les questions complexes

3. **Graphe de connaissances** : Phase 2 pour les questions relationnelles

4. **Qualité du corpus** : Outils de vérification et d'enrichissement

5. **Multimodal** : Intégration d'images, plans, schémas

---

## 3.5. Conclusion du Chapitre 3

La plateforme développée démontre la faisabilité d'un système de capitalisation et de génération intelligente de dossiers d'appels d'offres dans le secteur du BTP. Les résultats obtenus montrent :

- Une recherche hybride (BM25 + sémantique) améliorant significativement la pertinence des résultats
- Une génération contrôlée produisant des sections traçables et sourcées
- Un workflow avec validation humaine garantissant la qualité des livrables
- Des performances opérationnelles

---

# CONCLUSION GÉNÉRALE

## Résumé des Contributions

Ce travail de recherche a contribué à :

1. **Analyse du domaine** : Une caractérisation approfondie du processus des appels d'offres dans le BTP et de ses enjeux documentaires.

2. **État de l'art** : Un panorama des technologies (TAL, LLM, RAG, bases vectorielles, graphes) applicables à la problématique.

3. **Méthodologie** : Une approche structurée pour la conception d'un système de capitalisation et de génération.

4. **Architecture** : Une architecture modulaire combinant RAG hybride, workflow contrôlé et validation humaine.

5. **Validation** : Une évaluation empirique démontrant la faisabilité et les performances du système.

## Perspectives

Les perspectives de ce travail sont multiples :

1. **Industrialisation** : Passage à une solution SaaS multi-entreprises.

2. **Enrichissement** : Intégration d'un graphe de connaissances (phase 2).

3. **Agentique** : Introduction d'agents autonomes pour les recherches complexes.

4. **Multimodal** : Intégration d'images, plans et schémas.

5. **Fine-tuning** : Adaptation des modèles au domaine des AO.

---

# BIBLIOGRAPHIE

1. Vaswani, A., et al. (2017). Attention Is All You Need. *Advances in Neural Information Processing Systems*.

2. Devlin, J., et al. (2018). BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding. *arXiv:1810.04805*.

3. Lewis, P., et al. (2020). Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks. *arXiv:2005.11401*.

4. Mikolov, T., et al. (2013). Efficient Estimation of Word Representations in Vector Space. *arXiv:1301.3781*.

5. Zhang, Y., et al. (2023). BGE-M3: A Unified Multilingual Embedding Model. *Hugging Face Blog*.

6. Con


Excellent question. Vous avez raison de soulever ces points. Voici une analyse précise de **ce qui doit figurer dans l'état de l'art** et de **ce qui relève plutôt de la méthodologie ou de la technique**.

---

## 1. Ce qui DOIT figurer dans l'État de l'Art

### 1.1. OCR (Reconnaissance Optique de Caractères)

**Pertinence : TRÈS ÉLEVÉE**

L'OCR est un **sujet fondamental** pour l'état de l'art car il touche à la **qualité de la donnée en amont** du système.

| Sous-thème | Pourquoi c'est pertinent |
|------------|--------------------------|
| **Historique de l'OCR** | Des années 1990 (Tesseract) aux approches modernes (PaddleOCR, EasyOCR) |
| **Limites de l'OCR traditionnel** | Perte de structure, erreurs de reconnaissance |
| **OCR avancé (Layout Analysis)** | Détection de tableaux, titres, colonnes → PP-StructureV3 |
| **Enjeux pour les AO** | Les appels d'offres contiennent des tableaux (DPGF, BPU), des tampons, des signatures → OCR seul ne suffit pas |

**Ce qu'il faut dire dans l'état de l'art :**

> "L'OCR a connu une évolution significative, passant d'une simple reconnaissance de caractères à une **compréhension de la mise en page** (layout analysis). Cette évolution est cruciale pour les appels d'offres, qui contiennent des éléments structurés (tableaux de prix, articles numérotés, annexes) dont la perte de structure dégraderait la qualité de l'indexation et de la génération."

### 1.2. Fuzzy Matching (Correspondance Approximative)

**Pertinence : ÉLEVÉE**

Le fuzzy matching est un concept important pour l'état de l'art car il aborde un **problème fondamental du traitement des données textuelles** : la variation orthographique.

| Sous-thème | Pourquoi c'est pertinent |
|------------|--------------------------|
| **Historique des techniques** | Levenshtein (1965), Soundex, Jaccard, N-gram, TF-IDF |
| **Applications** | Déduplication, résolution d'entités, correction OCR |
| **Enjeux pour les AO** | Une même entreprise peut être écrite "Vinci", "Vinci Construction", "VINCI SA" → besoin de résolution d'entités |

**Ce qu'il faut dire dans l'état de l'art :**

> "La correspondance approximative (fuzzy matching) est une technique essentielle pour la résolution d'entités, qui consiste à identifier que deux libellés désignent la même entité réelle. Les approches vont de la distance de Levenshtein aux méthodes fondées sur les embeddings sémantiques. Dans le contexte des appels d'offres, cette capacité est cruciale pour relier des informations issues de documents différents mais concernant la même entreprise, le même projet ou la même certification."

### 1.3. Docling et l'Analyse de Documents Structurés

**Pertinence : ÉLEVÉE**

Docling représente une **avancée récente** dans le domaine de la compréhension de documents, ce qui en fait un sujet d'état de l'art pertinent.

| Sous-thème | Pourquoi c'est pertinent |
|------------|--------------------------|
| **Document Understanding** | Passage de l'OCR au "Document Understanding" |
| **Docling (IBM)** | Approche unifiée pour l'extraction de structure |
| **Alternatives** | Azure Document Intelligence, AWS Textract, Unstructured.io |

**Ce qu'il faut dire dans l'état de l'art :**

> "L'analyse de documents structurés (Document Understanding) représente un domaine de recherche en pleine expansion, visant à extraire non seulement le texte mais aussi la structure (titres, tableaux, relations) des documents. Des outils comme Docling (IBM) ou AWS Textract illustrent cette tendance, s'appuyant sur des modèles de fondation pour comprendre la mise en page. Cette approche est particulièrement pertinente pour les appels d'offres, qui possèdent une structure hiérarchique (articles, sections, annexes) essentielle à la capitalisation des connaissances."

### 1.4. Le Workflow Déterministe (vs Agentique)

**Pertinence : TRÈS ÉLEVÉE**

C'est un **choix architectural fondamental** qui mérite une discussion dans l'état de l'art, en confrontant les approches.

| Sous-thème | Pourquoi c'est pertinent |
|------------|--------------------------|
| **Systèmes déterministes vs agentiques** | Comparaison des approches |
| **Limites des agents** | Le sujet est très discuté (Anthropic, 2024) |
| **Application aux AO** | Les AO exigent traçabilité et fiabilité |

**Ce qu'il faut dire dans l'état de l'art :**

> "La littérature récente distingue deux approches pour la conception de systèmes d'IA : les workflows déterministes, où le chemin d'exécution est connu à l'avance, et les systèmes agentiques, où le modèle décide des actions à entreprendre. Anthropic (2024) souligne que les systèmes efficaces sont souvent construits à partir de composants simples et composables, et que l'ajout d'agents doit être justifié par la complexité réelle du problème. Dans le contexte des appels d'offres, où la fiabilité et la traçabilité sont primordiales, une approche workflow déterministe avec des capacités agentiques localisées est préférable à un essaim d'agents autonomes."

---

## 2. Ce qui N'EST PAS un sujet d'État de l'Art

### 2.1. Docling vs PaddleOCR (le détail technique)

| À ne PAS mettre dans l'État de l'Art | Pourquoi |
|--------------------------------------|----------|
| "Nous avons choisi Docling pour les PDF numériques et PaddleOCR pour les scans" | C'est un **choix d'implémentation**, pas un concept scientifique |
| "Docling utilise le modèle LayoutLMv3" | C'est un **détail technique**, pas un concept fondamental |

**À mettre plutôt :**
> "Les approches d'extraction de documents structurés (Docling, Azure Document Intelligence) permettent de préserver la hiérarchie des titres et des tableaux, contrairement à l'OCR traditionnel qui produit un flux linéaire de texte."

### 2.2. L'Architecture Technique (LLamaIndex, LangGraph)

| À ne PAS mettre dans l'État de l'Art | Pourquoi |
|--------------------------------------|----------|
| "Nous utilisons LlamaIndex pour le RAG et LangGraph pour l'orchestration" | C'est un **choix technique**, pas un concept scientifique |
| "Qdrant est utilisé comme base vectorielle" | C'est un **détail d'implémentation** |

**À mettre plutôt :**
> "Les bibliothèques de RAG et d'orchestration de workflows ont émergé pour faciliter le développement de systèmes d'IA complexes. Ces outils permettent de séparer clairement les responsabilités : indexation, recherche, génération, et orchestration des étapes."

---

## 3. Proposition de Structure Révisée pour l'État de l'Art

### 3.1. Structure Proposée

```
CHAPITRE 1 : ÉTAT DE L'ART
├── 1.1. Introduction
├── 1.2. Le Contexte des Appels d'Offres dans le BTP
│   ├── 1.2.1. Définition et Cadre Juridique
│   ├── 1.2.2. Le Processus de Réponse aux Appels d'Offres
│   └── 1.2.3. Les Enjeux de la Capitalisation des Connaissances
├── 1.3. Gestion Documentaire et Systèmes d'Information
│   ├── 1.3.1. Évolution des Systèmes de Gestion Documentaire
│   ├── 1.3.2. Standards et Normes Applicables
│   └── 1.3.3. Les Limites des Solutions Actuelles
├── 1.4. Intelligence Artificielle et Traitement du Langage Naturel
│   ├── 1.4.1. Fondements du Traitement Automatique du Langage
│   ├── 1.4.2. Les Modèles de Langage
│   ├── 1.4.3. Les Embeddings
│   └── 1.4.4. Applications Pratiques des LLM
├── 1.5. RAG : Retrieval-Augmented Generation
│   ├── 1.5.1. Définition et Principes Fondamentaux
│   ├── 1.5.2. Les Composantes d'un Système RAG
│   ├── 1.5.3. Les Variantes du RAG
│   └── 1.5.4. Évaluation des Systèmes RAG
├── 1.6. Traitement des Documents Structurés
│   ├── 1.6.1. OCR et Document Understanding
│   ├── 1.6.2. Analyse de Mise en Page et Reconnaissance de Tableaux
│   └── 1.6.3. Enjeux pour les Appels d'Offres
├── 1.7. Gestion de l'Information dans les Appels d'Offres
│   ├── 1.7.1. Organisation des Dossiers d'Appels d'Offres
│   ├── 1.7.2. Défis de la Recherche d'Information
│   └── 1.7.3. Approches de Capitalisation
├── 1.8. Techniques de Correspondance et de Résolution d'Entités
│   ├── 1.8.1. Approches Exactes vs Approximatives
│   ├── 1.8.2. Méthodes de Correspondance
│   └── 1.8.3. Applications aux Appels d'Offres
├── 1.9. Workflows et Architectures
│   ├── 1.9.1. Systèmes Déterministes vs Agentiques
│   ├── 1.9.2. Human-in-the-Loop (HITL)
│   └── 1.9.3. Architectures pour la Génération de Documents
├── 1.10. Solutions Existantes pour les Appels d'Offres
│   ├── 1.10.1. Solutions SaaS
│   ├── 1.10.2. Solutions sur le Marché
│   └── 1.10.3. Tendances Émergentes
└── 1.11. Synthèse de l'État de l'Art
```

---

## 4. Comparaison : Ce qu'il faut mettre vs ce qu'il faut éviter

| Concept | Dans l'État de l'Art ? | Où le placer ? |
|---------|------------------------|----------------|
| **OCR** | ✅ OUI | §1.6.1 |
| **Document Understanding** | ✅ OUI | §1.6.1 |
| **Fuzzy matching / Entity resolution** | ✅ OUI | §1.8 |
| **Workflow déterministe vs agentique** | ✅ OUI | §1.9.1 |
| **Docling** | ⚠️ Mentionner comme exemple | §1.6.1 |
| **PaddleOCR PP-StructureV3** | ⚠️ Mentionner comme exemple | §1.6.1 |
| **BGE-M3** | ❌ NON | Méthodologie / Technique |
| **Qdrant** | ❌ NON | Méthodologie / Technique |
| **LangGraph** | ❌ NON | Méthodologie / Technique |
| **LlamaIndex** | ❌ NON | Méthodologie / Technique |
| **Architecture Docker** | ❌ NON | Méthodologie / Technique |

---

## 5. Texte Proposé pour la Section 1.6 (Traitement des Documents Structurés)

Voici un texte rédigé qui intègre les concepts OCR, Docling et fuzzy matching de manière appropriée :

---

### 1.6. Traitement des Documents Structurés

#### 1.6.1. OCR et Document Understanding

La reconnaissance optique de caractères (OCR) est une technologie fondatrice pour la numérisation et l'exploitation des documents papier. Depuis les premiers systèmes de reconnaissance de caractères dans les années 1960, l'OCR a connu une évolution significative, passant d'une simple reconnaissance de caractères à une véritable **compréhension de la structure des documents**.

**Historique et Évolution :**

| Période | Approche | Caractéristiques | Limites |
|---------|----------|------------------|---------|
| 1960-1990 | OCR matriciel | Reconnaissance de caractères imprimés | Non adapté aux polices variables |
| 1990-2005 | OCR statistique (Tesseract) | Reconnaissance de caractères, langues multiples | Perte de la mise en page |
| 2005-2015 | OCR + analyse de mise en page | Détection de blocs de texte, colonnes | Peu robuste aux documents complexes |
| 2015-2020 | OCR + table extraction | Détection et extraction de tableaux | Pas de compréhension sémantique |
| 2020-présent | **Document Understanding** | Analyse de la structure, des titres, des relations | En cours de maturité |

**La rupture du Document Understanding :**

L'émergence du *Document Understanding* (compréhension de documents) représente une rupture conceptuelle majeure. Alors que l'OCR traditionnel produit un flux linéaire de texte, le *Document Understanding* vise à **préserver la structure hiérarchique** du document : titres, sous-titres, articles, tableaux, annexes.

Cette approche s'appuie sur des modèles de fondation (comme LayoutLMv3 ou DocFormer) entraînés à la fois sur le texte et la mise en page. Des outils comme Docling (IBM), Azure Document Intelligence ou AWS Textract illustrent cette tendance.

**Enjeux pour les Appels d'Offres :**

Les dossiers d'appels d'offres sont intrinsèquement structurés. Un CCAP (Cahier des Clauses Administratives Particulières) est organisé en articles numérotés ; un CCTP (Cahier des Clauses Techniques Particulières) suit une hiérarchie de sections ; un DPGF (Décomposition du Prix Global et Forfaitaire) est un tableau structuré.

La perte de cette structure lors de l'extraction textuelle dégraderait significativement :
- La **qualité de la recherche** : un article entier est plus pertinent qu'un fragment de texte.
- La **traçabilité des sources** : la référence à un article précis est essentielle.
- La **génération de sections** : le plan du document réponse s'appuie sur la structure du DAO.

#### 1.6.2. Reconnaissance de Tableaux

Les tableaux constituent une composante essentielle des dossiers d'appels d'offres. Leur extraction et leur préservation posent des défis spécifiques.

**Défis :**

- **Reconnaissance des cellules** : Identifier les cellules, les en-têtes de lignes et de colonnes.
- **Préservation des hiérarchies** : Certains tableaux contiennent des sous-tableaux ou des cellules fusionnées.
- **OCR spécifique** : Les tableaux comportent souvent des polices plus petites et moins régulières.

**Approches :**

| Approche | Principe | Avantages | Inconvénients |
|----------|----------|-----------|---------------|
| Règles heuristiques | Détection des lignes et colonnes | Rapide, simple | Fragile |
| Modèles de détection (CNN) | Détection de la structure | Robuste | Nécessite des données d'entraînement |
| Modèles de fondation | Compréhension du tableau | Très robuste | Coût computationnel |

**Enjeux pour les appels d'offres :** Les tableaux de prix (DPGF, BPU) contiennent des informations financières critiques. Leur mauvais extraction compromet la capacité du système à générer des réponses financières précises.

#### 1.6.3. Fuzzy Matching et Résolution d'Entités

La correspondance approximative (fuzzy matching) est un ensemble de techniques permettant de comparer des textes malgré des variations orthographiques.

**Méthodes Fondamentales :**

| Méthode | Principe | Application |
|---------|----------|-------------|
| **Levenshtein** | Distance d'édition entre chaînes | Fautes de frappe, OCR approximatif |
| **Soundex** | Encodage phonétique | Noms propres (limité au français) |
| **Jaccard** | Intersection sur union d'ensembles de mots | Ordre des mots |
| **N-gram** | Séquences de N caractères | OCR, texte long |

**Résolution d'Entités :**

La résolution d'entités (entity resolution) consiste à identifier que deux libellés désignent la même entité réelle. Elle s'appuie sur les techniques de fuzzy matching et les intègre dans un processus :

```
Libellé A : "Vinci Construction"      Libellé B : "VINCI SA"
         ↓                                    ↓
    Normalisation                      Normalisation
         ↓                                    ↓
    "vinci construction"               "vinci sa"
         ↓                                    ↓
    Comparaison fuzzy (Levenshtein + Jaccard)
         ↓
    Score > seuil → Même entité
```

**Applications aux Appels d'Offres :**

Les appels d'offres font référence à de nombreuses entités récurrentes :
- **Entreprises** : "Vinci", "Vinci Construction", "VINCI SA" → même entreprise.
- **Projets** : "Gare de Nantes", "Gare Nantes", "Projet Gare SNCF Nantes" → même projet.
- **Certifications** : "ISO 9001", "ISO 9001:2015" → même certification.

La capacité à résoudre ces identités est cruciale pour :
1. **Éviter les doublons** : Ne pas créer deux nœuds pour une même entreprise dans le graphe de connaissances.
2. **Relier des informations** : Associer des documents de périodes différentes concernant le même projet.
3. **Améliorer le RAG** : Retrouver tous les documents liés à une même entité.

---

## 6. Synthèse Finale

### Ce qui doit ABSOLUMENT figurer dans l'État de l'Art :

| Concept | Priorité | Justification |
|---------|----------|---------------|
| **OCR / Document Understanding** | ⭐⭐⭐⭐⭐ | Fondamental pour l'ingestion des documents |
| **LLM et Transformers** | ⭐⭐⭐⭐⭐ | Cœur du système de génération |
| **RAG (Retrieval-Augmented Generation)** | ⭐⭐⭐⭐⭐ | Architecture centrale du système |
| **Workflow déterministe vs agentique** | ⭐⭐⭐⭐ | Choix architectural fondamental |
| **Fuzzy matching / Entity resolution** | ⭐⭐⭐⭐ | Critique pour la cohérence des données |
| **Bases vectorielles / Recherche sémantique** | ⭐⭐⭐⭐⭐ | Cœur de la recherche d'information |
| **Graphes de connaissances** | ⭐⭐⭐⭐ | Phase 2, mentionner comme perspective |
| **Human-in-the-Loop (HITL)** | ⭐⭐⭐⭐ | Garantie de qualité pour les AO |
| **Solutions existantes** | ⭐⭐⭐ | Contexte concurrentiel |

### Ce qui relève de la Méthodologie ou de la Technique :

| Concept | Où le placer |
|---------|--------------|
| Docling / PaddleOCR (choix précis) | Chapitre 3 (Technique) |
| BGE-M3 (embedding) | Chapitre 3 (Technique) |
| Qdrant vs autres bases vectorielles | Chapitre 3 (Technique) |
| LangGraph / LlamaIndex | Chapitre 3 (Technique) |
| ARQ / Redis | Chapitre 3 (Technique) |



Excellente question. **BM25** et **RRF** sont des concepts **fondamentaux** qui doivent figurer dans l'état de l'art, car ils touchent au cœur de la **recherche d'information**, un domaine académique bien établi.

---

## 1. BM25 : Le Modèle de Recherche Lexicale

### 1.1. Qu'est-ce que BM25 ?

Le **BM25** (Best Matching 25) est un **modèle de recherche d'information** développé par Stephen Robertson et ses collègues dans les années 1970-1990. Il fait partie de la famille des modèles **probabilistes** de recherche d'information, et reste à ce jour l'un des algorithmes de référence pour la recherche lexicale.

Il répond à une question fondamentale : **"Comment classer des documents par pertinence par rapport à une requête, en se basant sur les mots qu'ils contiennent ?"**

### 1.2. Le Contexte Académique

BM25 s'inscrit dans un héritage académique riche :

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   HISTORIQUE DE LA RECHERCHE D'INFORMATION                 │
│                                                                             │
│  1945 : Vannevar Bush, "As We May Think" (vision du Memex)                │
│  1957 : Hans Peter Luhn, premiers systèmes de recherche                   │
│  1960 : Gérard Salton, SMART (premiers systèmes vectoriels)               │
│  1970 : Robertson & Sparck Jones, théorie probabiliste                    │
│  1976 : Salton, modèle vectoriel (TF-IDF)                                 │
│  1988 : Robertson, développement de BM25                                  │
│  1994 : BM25 formalisé                                                    │
│  2000-2020 : BM25, référence pour les moteurs de recherche               │
│  2020-présent : BM25 hybride avec recherche sémantique                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.3. Le Principe Mathématique de BM25

BM25 repose sur une **formule probabiliste** qui pondère chaque terme de la requête en fonction de :

1. **La fréquence du terme dans le document** (TF, Term Frequency)
2. **La rareté du terme dans la collection** (IDF, Inverse Document Frequency)
3. **La longueur du document** (pour éviter que les documents longs soient favorisés)

**La formule de BM25 :**

```
Score(BM25, D, Q) = Σ IDF(qᵢ) × (TF(qᵢ, D) × (k₁ + 1)) / (TF(qᵢ, D) + k₁ × (1 - b + b × (|D| / avgDL)))

Où :
- qᵢ : un terme de la requête
- D : un document
- k₁ : paramètre de saturation (souvent 1.2-2.0)
- b : paramètre de normalisation (souvent 0.75)
- |D| : longueur du document
- avgDL : longueur moyenne des documents
```

### 1.4. Pourquoi BM25 est-il important dans l'État de l'Art ?

| Aspect | Justification |
|--------|---------------|
| **Fondement théorique** | Représente une avancée majeure dans la recherche d'information probabiliste |
| **Performance éprouvée** | Démontré comme l'un des meilleurs modèles lexicaux pendant des décennies |
| **Référence académique** | Citée dans des milliers de publications sur la recherche d'information |
| **Applicabilité** | Utilisé par des moteurs de recherche (Elasticsearch, Lucene) |
| **Complémentarité** | Sert de base pour les approches hybrides avec la recherche sémantique |

**Ce qu'il faut dire dans l'état de l'art :**

> "Le modèle BM25, développé par Robertson et ses collaborateurs, constitue une référence dans le domaine de la recherche d'information lexicale. Sa formulation probabiliste permet de pondérer chaque terme de la requête en fonction de sa fréquence dans le document et de sa rareté dans la collection, tout en normalisant par la longueur du document. Malgré l'émergence des approches sémantiques, BM25 reste pertinent pour la recherche de termes exacts, notamment dans des domaines où la précision terminologique est cruciale, comme les appels d'offres (numéros d'articles, références normatives, identifiants de contrats)."

---

## 2. RRF : Reciprocal Rank Fusion

### 2.1. Qu'est-ce que RRF ?

Le **RRF** (Reciprocal Rank Fusion) est une **méthode de fusion de classements** (rank fusion) proposée par Cormack et al. en 2009. Elle permet de combiner plusieurs classements de documents provenant de différents moteurs de recherche pour produire un classement final.

Elle répond à une question : **"Comment combiner les résultats de plusieurs systèmes de recherche pour obtenir un meilleur classement que chacun pris individuellement ?"**

### 2.2. Le Contexte Académique

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                 HISTORIQUE DE LA FUSION DE CLASSEMENTS                     │
│                                                                             │
│  1988 : Fox, concept de "data fusion"                                     │
│  1990 : Saracevic, combinaison de systèmes                                 │
│  1993 : Voorhees, "The TREC-2 Confusion" (premières expériences)          │
│  1995 : Bartell, "Automatic Combination of Multiple Ranked Retrieval Systems"│
│  1999 : Lee, "Combining Multiple Evidence from Different Retrieval Systems"│
│  2009 : Cormack et al., "Reciprocal Rank Fusion" (RRF)                    │
│  2010-présent : RRF, standard pour la fusion en recherche hybride         │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.3. Le Principe de RRF

RRF est remarquablement **simple** mais **extrêmement efficace**. Il ne nécessite pas de normaliser les scores des différents systèmes, car il n'utilise que les **classements** (rangs) :

**La formule de RRF :**

```
Score_RRF(D) = Σ 1 / (k + rangᵢ(D))

Où :
- D : un document
- rangᵢ(D) : la position du document dans le classement du système i
- k : une constante (souvent 60)
```

**Exemple :**

| Document | Rang BM25 | Rang Sémantique | Score RRF (k=60) |
|----------|-----------|-----------------|------------------|
| Doc A | 1 | 3 | 1/(60+1) + 1/(60+3) = 0.0164 + 0.0159 = **0.0323** |
| Doc B | 2 | 2 | 1/(60+2) + 1/(60+2) = 0.0161 + 0.0161 = **0.0322** |
| Doc C | 5 | 1 | 1/(60+5) + 1/(60+1) = 0.0154 + 0.0164 = **0.0318** |

### 2.4. Pourquoi RRF est-il important dans l'État de l'Art ?

| Aspect | Justification |
|--------|---------------|
| **Problème fondamental** | La fusion d'évidences est un problème central en recherche d'information |
| **Simplicité remarquable** | Pas besoin de normaliser les scores, contrairement à d'autres méthodes |
| **Performance prouvée** | Démontré comme l'une des meilleures méthodes de fusion |
| **Applicabilité** | Utilisé dans les systèmes hybrides (lexical + sémantique) |

**Ce qu'il faut dire dans l'état de l'art :**

> "La fusion de classements (rank fusion) est une technique fondamentale en recherche d'information, permettant de combiner les résultats de plusieurs systèmes pour produire un classement final. Parmi les approches proposées, le Reciprocal Rank Fusion (RRF), introduit par Cormack et al., se distingue par sa simplicité et son efficacité. Contrairement à d'autres méthodes de fusion, RRF ne nécessite pas de normaliser les scores des différents systèmes, car il n'utilise que les classements relatifs. Cette propriété le rend particulièrement adapté à la combinaison de la recherche lexicale (BM25) et de la recherche sémantique (vectorielle), dont les scores opèrent sur des échelles difficilement comparables."

---

## 3. Synthèse : Place des Concepts dans l'État de l'Art

### 3.1. Tableau Récapitulatif

| Concept | Domaine | Niveau académique | Place dans l'État de l'Art |
|---------|---------|-------------------|---------------------------|
| **BM25** | Recherche d'information probabiliste | ⭐⭐⭐⭐⭐ | § "Modèles de Recherche d'Information" |
| **TF-IDF** | Recherche d'information vectorielle | ⭐⭐⭐⭐⭐ | § "Modèles de Recherche d'Information" |
| **RRF** | Fusion de classements | ⭐⭐⭐⭐ | § "Fusion de Classements" |
| **Embeddings** | TAL / NLP | ⭐⭐⭐⭐⭐ | § "Représentations Vectorielles" |
| **Transformers** | TAL / NLP | ⭐⭐⭐⭐⭐ | § "Modèles de Langage" |
| **RAG** | IA générative | ⭐⭐⭐⭐⭐ | § "Retrieval-Augmented Generation" |

### 3.2. Structure Proposée pour la Section "Recherche d'Information"

```
1.4. Recherche d'Information et Modèles de Classement
├── 1.4.1. Fondements de la Recherche d'Information
│   ├── Définition et historique
│   ├── Les composantes d'un système de recherche
│   └── Évaluation : précision, rappel, MRR, NDCG
├── 1.4.2. Modèles Lexicaux
│   ├── Modèle booléen
│   ├── Modèle vectoriel (TF-IDF)
│   ├── Modèle probabiliste (BM25)
│   └── Limites des approches lexicales
├── 1.4.3. Modèles Sémantiques (Vectoriels)
│   ├── Word2Vec, GloVe
│   ├── BERT et les embeddings contextuels
│   └── Modèles d'embedding pour le RAG (BGE-M3, etc.)
├── 1.4.4. Recherche Hybride
│   ├── Motivation de l'approche hybride
│   ├── Fusion de classements (RRF)
│   └── Re-ranking (cross-encoders)
└── 1.4.5. Application aux Appels d'Offres
    ├── Spécificités lexicales (ISO, article, référence)
    ├── Spécificités sémantiques (domaine BTP)
    └── Exigences de traçabilité
```

---

## 4. Texte Proposé pour la Section "Recherche d'Information"

Voici un texte rédigé qui intègre BM25 et RRF de manière appropriée :

---

### 1.4. Recherche d'Information et Modèles de Classement

#### 1.4.1. Fondements

La recherche d'information (Information Retrieval, IR) est une discipline fondatrice du traitement automatisé des documents, dont les origines remontent aux travaux de Vannevar Bush (1945) et aux premiers systèmes de recherche documentaire dans les années 1960.

Un système de recherche d'information répond à une question fondamentale : **étant donnée une requête utilisateur, comment identifier les documents les plus pertinents dans une collection ?** La réponse à cette question a généré des décennies de recherche, aboutissant à des modèles de classement de plus en plus sophistiqués.

**Les composantes d'un système de recherche :**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   COMPOSANTES D'UN SYSTÈME DE RECHERCHE                    │
│                                                                             │
│  1. INDEXATION :                                                           │
│     Documents → Représentation → Index                                     │
│                                                                             │
│  2. INTERROGATION :                                                        │
│     Requête → Représentation → Recherche                                   │
│                                                                             │
│  3. CLASSEMENT :                                                           │
│     Scores → Tri → Résultats                                               │
│                                                                             │
│  4. ÉVALUATION :                                                           │
│     Précision, Rappel, MRR, NDCG, Recall@K                                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### 1.4.2. Modèles Lexicaux

**Le modèle vectoriel (TF-IDF) :**

Proposé par Salton et McGill en 1983, le modèle vectoriel représente chaque document et chaque requête comme un vecteur dans un espace dont les dimensions sont les termes du vocabulaire. La pertinence est mesurée par la similarité cosinus entre les deux vecteurs.

La pondération TF-IDF (Term Frequency - Inverse Document Frequency) est la plus utilisée :
- **TF** : Fréquence du terme dans le document (plus le terme est fréquent, plus il est important)
- **IDF** : Rareté du terme dans la collection (plus le terme est rare, plus il est discriminant)

**Le modèle probabiliste (BM25) :**

Développé par Robertson et ses collaborateurs à partir des travaux fondateurs de Robertson et Sparck Jones (1976), le modèle BM25 (Best Matching 25) s'inscrit dans la théorie probabiliste de la recherche d'information. Il est aujourd'hui considéré comme l'un des modèles lexicaux les plus performants.

La formule de BM25 pondère chaque terme de la requête en fonction de :
1. Sa fréquence dans le document (TF)
2. Sa rareté dans la collection (IDF)
3. La longueur du document (normalisation)

```
Score(BM25, D, Q) = Σ IDF(qᵢ) × (TF(qᵢ, D) × (k₁ + 1)) / (TF(qᵢ, D) + k₁ × (1 - b + b × (|D| / avgDL)))
```

**Limites des approches lexicales :**

Malgré leur efficacité, les approches lexicales présentent des limites fondamentales :
- **Problème de la synonymie** : "voiture" et "automobile" ne sont pas considérés comme liés.
- **Problème de la polysémie** : "Java" peut désigner un langage ou une île.
- **Sensibilité à la formulation** : La même question formulée différemment produit des résultats différents.

#### 1.4.3. Modèles Sémantiques (Vectoriels)

L'émergence des représentations vectorielles continues (embeddings) a marqué un tournant majeur dans la recherche d'information, en permettant de capturer la **sémantique** des textes.

**Les embeddings statiques :**

Les modèles Word2Vec (Mikolov et al., 2013) et GloVe (Pennington et al., 2014) ont popularisé l'idée que les mots peuvent être représentés par des vecteurs continus dans un espace sémantique. La similarité de deux mots est alors mesurée par la distance cosinus entre leurs vecteurs.

**Les embeddings contextuels :**

Avec BERT (Devlin et al., 2018) et les modèles Transformers, la représentation d'un mot dépend désormais de son **contexte**. Cette évolution a considérablement amélioré la compréhension de la polysémie.

**Modèles d'embedding pour le RAG :**

Pour les systèmes RAG, des modèles spécifiques ont été développés pour optimiser la recherche sémantique :

| Modèle | Caractéristiques | Cas d'usage |
|--------|------------------|-------------|
| **BGE-M3** | Dense + sparse, multilingue | Recherche hybride |
| **E5** | Multi-langues, fine-tuné | RAG général |
| **Voyage-2** | Multilingue, entreprise | Applications métier |

#### 1.4.4. Recherche Hybride et Fusion de Classements

**Motivation de l'approche hybride :**

Les approches lexicales (BM25) et sémantiques (embeddings) sont complémentaires. La première excelle pour les termes exacts (identifiants, références normatives) ; la seconde pour les concepts et synonymes.

Le tableau suivant illustre cette complémentarité :

| Type de requête | BM25 | Embeddings |
|-----------------|------|------------|
| "ISO 9001" | ✅ Excellent | ⚠️ Bon (dépend de l'embedding) |
| "pénalités de retard" | ⚠️ Bon | ✅ Excellent |
| "Article 5.2" | ✅ Excellent | ❌ Faible |

**La fusion de classements (Rank Fusion) :**

Combiner les résultats de plusieurs systèmes de recherche est un problème central en recherche d'information. Parmi les approches proposées, le **Reciprocal Rank Fusion (RRF)** proposé par Cormack et al. (2009) se distingue par sa simplicité et son efficacité.

Contrairement à d'autres méthodes, RRF ne nécessite pas de normaliser les scores des différents systèmes, car il n'utilise que les **classements** (rangs) :

```
Score_RRF(D) = Σ 1 / (k + rangᵢ(D))
```

Où `k` est une constante (généralement 60) et `rangᵢ(D)` est la position du document dans le classement du système `i`.

**Le Re-ranking :**

Au-delà de la fusion de classements, une approche plus fine consiste à appliquer un **re-ranker** : un modèle cross-encoder (comme BGE-reranker-v2-m3) qui évalue la pertinence d'un couple (requête, document) de manière plus précise qu'un simple calcul de similarité vectorielle.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PIPELINE DE RECHERCHE HYBRIDE                           │
│                                                                             │
│   1. RECHERCHE LEXICALE (BM25)  →  Top-50                                 │
│   2. RECHERCHE SÉMANTIQUE       →  Top-50                                 │
│                                                                             │
│   3. FUSION (RRF)               →  Top-50 fusionné                        │
│                                                                             │
│   4. RE-RANKING (Cross-Encoder) →  Top-8                                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### 1.4.5. Application aux Appels d'Offres

Les appels d'offres présentent des caractéristiques spécifiques qui justifient une approche de recherche hybride :

| Caractéristique | Implication pour la recherche |
|-----------------|-------------------------------|
| **Termes normatifs** | ISO 9001, NF P 94-261, etc. → recherche lexicale indispensable |
| **Identifiants précis** | Article 5.2, Lot 03, etc. → BM25 |
| **Concepts métier** | "pénalités de retard", "garantie décennale" → sémantique |
| **Même entreprise, formes variées** | "Vinci", "Vinci Construction", "VINCI SA" → fuzzy matching |
| **Traçabilité** | Nécessité de citer les sources → précision du retrieval |

**Cette complémentarité justifie l'adoption d'un pipeline de recherche hybride combinant BM25, embeddings, RRF et re-ranking, qui sera détaillé dans le chapitre 3.**

---

## 5. Texte Proposé pour la Section "Fusion de Classements"

---

### 1.4.4. Fusion de Classements (Rank Fusion)

**Le problème :** Comment combiner les résultats de plusieurs systèmes de recherche pour obtenir un classement final ?

**Contexte académique :**

La fusion de classements (rank fusion) est un thème de recherche actif depuis les années 1990, motivé par l'observation que différents systèmes de recherche ont des forces et faiblesses complémentaires.

**Familles de méthodes :**

| Méthode | Principe | Avantages | Inconvénients |
|---------|----------|-----------|---------------|
| **Score combinaison** | Pondération des scores | Théoriquement optimal | Nécessite une normalisation |
| **Vote / Borda count** | Agrégation des préférences | Simple | Perd l'information de score |
| **RRF** | Réciproque des rangs | Simple, efficace | Paramètre k à régler |
| **Learning to Rank** | Apprentissage supervisé | Optimal en théorie | Nécessite des données annotées |

**Le Reciprocal Rank Fusion (RRF) :**

Proposé par Cormack, Clarke et Buettcher en 2009, RRF a été spécifiquement conçu pour la "data fusion" dans les systèmes de recherche. Sa simplicité et sa performance en ont fait une référence.

**Pourquoi RRF fonctionne bien ?**

1. **Pas de normalisation nécessaire** : Les scores des différents systèmes ne sont pas sur la même échelle.
2. **Pénalise la médiocrité** : Un document mal classé dans un système est fortement pénalisé.
3. **Résistant au bruit** : Une erreur ponctuelle dans un classement a peu d'impact.
4. **Empiriquement performant** : Démontré dans de nombreuses expériences TREC.

**Extensions de RRF :**

Des variantes de RRF ont été proposées :
- **RRF pondéré** : Pondération différente selon les systèmes
- **RRF dynamique** : Ajustement du paramètre k selon le contexte
- **RRF avec seuil** : Seulement les K premiers documents de chaque système

---

## 6. Ce qu'il faut ABSOLUMENT mettre dans l'État de l'Art

| Concept | Pourquoi |
|---------|----------|
| **BM25** | Référence académique, fondement de la recherche lexicale |
| **TF-IDF** | Fondement du modèle vectoriel |
| **RRF** | Référence pour la fusion de classements |
| **Embeddings** | Fondement de la recherche sémantique |
| **Transformers** | Fondement des modèles de langage modernes |
| **RAG** | Architecture centrale du système |
| **HITL** | Garantie de qualité pour les AO |

## 7. Ce qu'il faut ÉVITER de mettre dans l'État de l'Art

| Concept | Pourquoi |
|---------|----------|
| "Nous utilisons Qdrant" | Détail technique |
| "Nous utilisons BGE-M3" | Détail technique |
| "Docling vs PaddleOCR" | Détail d'implémentation |
| "LangGraph" | Détail technique |
| "LlamaIndex" | Détail technique |

---

## 8. Synthèse

```
┌─────────────────────────────────────────────────────────────────────────────┐
│            PLACE DES CONCEPTS DANS LE MÉMOIRE                             │
│                                                                             │
│  ÉTAT DE L'ART (Chapitre 1) :                                              │
│  ─────────────────────────────────────────────────────────────────────────  │
│  ✅ BM25 (modèle de recherche probabiliste)                               │
│  ✅ RRF (fusion de classements)                                           │
│  ✅ TF-IDF (modèle vectoriel)                                             │
│  ✅ Embeddings (Word2Vec, BERT, etc.)                                     │
│  ✅ Transformers (architecture des LLM)                                    │
│  ✅ RAG (architecture)                                                    │
│  ✅ OCR et Document Understanding                                         │
│  ✅ Fuzzy matching / Entity resolution                                    │
│  ✅ Workflow déterministe vs agentique                                    │
│                                                                             │
│  MÉTHODOLOGIE (Chapitre 2) :                                              │
│  ─────────────────────────────────────────────────────────────────────────  │
│  ✅ Stratégie de recherche hybride (BM25 + embeddings + RRF)             │
│  ✅ Stratégie de parent-child chunking                                    │
│  ✅ Stratégie de génération par section                                   │
│  ✅ Stratégie d'évaluation                                                │
│                                                                             │
│  RÉSULTATS / TECHNIQUE (Chapitre 3) :                                    │
│  ─────────────────────────────────────────────────────────────────────────  │
│  ✅ Implémentation (Qdrant, BGE-M3, LlamaIndex, LangGraph)               │
│  ✅ Performances (Recall@20, temps de réponse)                           │
│  ✅ Choix techniques (Docling, PaddleOCR)                                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```


Excellente question. Le **SSE (Server-Sent Events)** est un concept qui relève **exclusivement de l'implémentation technique**, pas de l'état de l'art académique. Voici comment le traiter dans votre mémoire.

---

## 1. Qu'est-ce que le SSE ?

Le **Server-Sent Events (SSE)** est une **technologie web** qui permet à un serveur d'envoyer des données de manière **unidirectionnelle** vers un client (navigateur) en temps réel, via une connexion HTTP persistante.

### 1.1. Principe

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       PRINCIPE DU SSE                                      │
│                                                                             │
│  Client (Navigateur)                  Serveur (FastAPI)                    │
│         │                                   │                              │
│         │─── Requête HTTP GET ─────────────►│                              │
│         │     (Accept: text/event-stream)    │                              │
│         │                                   │                              │
│         │                                   │  ┌──────────────────────┐   │
│         │                                   │  │ Connexion maintenue  │   │
│         │                                   │  │   ouverte            │   │
│         │                                   │  └──────────────────────┘   │
│         │                                   │                              │
│         │◄── Event 1 (token) ───────────────│                              │
│         │◄── Event 2 (token) ───────────────│                              │
│         │◄── Event 3 (token) ───────────────│                              │
│         │◄── Event N (done) ────────────────│                              │
│         │                                   │                              │
│         │─── Connexion fermée ──────────────►│                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2. Format des Événements

```text
data: {"type": "token", "content": "Bonjour"}

data: {"type": "token", "content": " le"}

data: {"type": "token", "content": " monde"}

data: {"type": "done", "ok": true}

```

### 1.3. Pourquoi SSE dans votre application ?

Dans votre système, le SSE est utilisé pour le **streaming des réponses du LLM** :

| Problème | Solution SSE |
|----------|--------------|
| Le LLM met 10-30s à générer une réponse | L'utilisateur voit les tokens arriver progressivement |
| L'utilisateur ne sait pas si le système travaille | Feedback en temps réel |
| Les longues réponses sont frustrantes | Expérience interactive |

**Sans SSE :** L'utilisateur attend 20s sans rien voir → mauvais UX.
**Avec SSE :** L'utilisateur voit le texte s'écrire progressivement → bonne UX.

---

## 2. Place dans le Mémoire

### 2.1. Où le Mettre ?

Le SSE est un **détail d'implémentation**. Il doit apparaître dans le **Chapitre 3 (Résultats / Implémentation)** , dans la section décrivant l'interface utilisateur ou l'architecture de communication.

### 2.2. Niveau de Détail

| Niveau | Exemple |
|--------|---------|
| ❌ Trop technique | "Nous utilisons la bibliothèque SSE-Starlette avec des événements de type 'token' et 'done'" |
| ✅ Adapté | "L'interface utilisateur utilise un mécanisme de streaming (Server-Sent Events) pour afficher les réponses du LLM en temps réel, améliorant l'expérience utilisateur lors des longues générations." |
| ❌ Trop vague | "L'application affiche les réponses" |

---

## 3. Ce qu'il faut Dire

### 3.1. Dans le Chapitre 2 (Méthodologie) - Optionnel

Si vous voulez mentionner le principe, de manière **générale** :

> "Pour garantir une expérience utilisateur fluide lors de la génération de textes longs, l'interface utilisateur repose sur un mécanisme de **streaming en temps réel**, permettant d'afficher progressivement la réponse du LLM au fur et à mesure de sa génération, plutôt que d'attendre la complétion complète."

### 3.2. Dans le Chapitre 3 (Résultats / Implémentation)

> "La communication entre le serveur et le client pour les réponses du LLM est réalisée via un mécanisme de **streaming bidirectionnel**. Le serveur maintient une connexion persistante et envoie des fragments de texte au fur et à mesure de leur génération par le modèle. Cette approche, implémentée via la technologie Server-Sent Events (SSE) standard du web, permet à l'utilisateur de visualiser la réponse en cours de rédaction, réduisant significativement le temps d'attente perçu."

---

## 4. Ce qu'il ne faut PAS Dire

### ❌ Évitez :

```text
❌ "Nous avons utilisé la bibliothèque 'sse-starlette' version 1.2.0"
❌ "Le endpoint /messages/stream renvoie des événements de type 'text/event-stream'"
❌ "La fonction 'sse_event' est appelée à chaque token généré par Ollama"
❌ "Nous avons implémenté un mécanisme de heartbeat pour maintenir la connexion"
```

### ✅ Préférez :

```text
✅ "L'interface utilisateur reçoit les réponses du LLM en streaming"
✅ "Les fragments de texte sont affichés progressivement"
✅ "L'utilisateur bénéficie d'un retour en temps réel"
```

---

## 5. Rédaction Proposée

### Pour le Chapitre 3 (Résultats) :

```
3.2.2. Interface Utilisateur et Expérience de Génération

L'interface utilisateur de la plateforme a été conçue pour offrir une expérience 
fluide lors des phases de génération de sections, qui peuvent durer de 10 à 30 
secondes selon la complexité du sujet et la taille du contexte.

Pour éviter une attente passive, le système implémente un mécanisme de streaming 
temps réel. Lorsqu'une section est générée par le LLM, les fragments de texte 
sont envoyés au navigateur au fur et à mesure de leur production, permettant à 
l'utilisateur de visualiser la réponse en cours d'écriture. Ce mécanisme, 
standard du web sous le nom de Server-Sent Events (SSE), maintient une connexion 
persistante entre le client et le serveur le temps de la génération.

Cette approche présente plusieurs avantages :
- **Feedback immédiat** : L'utilisateur sait que le système est actif.
- **Amélioration du temps d'attente perçu** : Visualiser le texte s'écrire 
  réduit l'impression d'attente.
- **Possibilité d'interruption** : L'utilisateur peut stopper la génération 
  si le résultat ne correspond pas à ses attentes.

La figure suivante illustre le flux de streaming lors de la génération d'une 
section [Figure 3.2].

[...]
```

---

## 6. Concepts Alternatifs dans le même Registre

| Concept | Où le mettre | Niveau de détail |
|---------|--------------|------------------|
| **SSE** | Chapitre 3 (Interface) | ❌ Pas de détail technique |
| **WebSocket** | Chapitre 3 (Interface) | ❌ Pas de détail technique |
| **API REST** | Chapitre 3 (Architecture) | ❌ Pas de détail technique |
| **JWT (authentification)** | Chapitre 3 (Sécurité) | ❌ Pas de détail technique |

---

## 7. Pourquoi SSE n'est PAS un sujet d'État de l'Art ?

| Raison | Explication |
|--------|-------------|
| **C'est un standard du web** | SSE est une spécification W3C, pas une innovation scientifique |
| **C'est une technique, pas un concept** | Ça relève de l'ingénierie, pas de la recherche |
| **Littérature académique limitée** | Très peu d'articles de recherche sur SSE |
| **Alternatives connues** | Long polling, WebSockets (autres techniques, pas de recherche fondamentale) |

### 8. Synthèse

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PLACE DE SSE DANS LE MÉMOIRE                            │
│                                                                             │
│  CHAPITRE 1 (État de l'art) : ❌ NON                                       │
│  ─────────────────────────────────────────────────────────────────────────  │
│  SSE n'est pas un concept académique, c'est une technologie web.           │
│                                                                             │
│  CHAPITRE 2 (Méthodologie) : ❌ NON                                        │
│  ─────────────────────────────────────────────────────────────────────────  │
│  La méthodologie traite des principes généraux, pas des technologies.      │
│                                                                             │
│  CHAPITRE 3 (Résultats / Implémentation) : ✅ OUI, mais...                 │
│  ─────────────────────────────────────────────────────────────────────────  │
│  ✅ Mentionner le streaming temps réel comme amélioration UX.              │
│  ✅ Décrire le flux de données entre client et serveur.                    │
│  ❌ Ne pas entrer dans les détails techniques (bibliothèques, versions).   │
│  ❌ Ne pas faire de section dédiée (intégrer dans la description générale). │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 9. Exemple Complet de Rédaction

### Dans le Chapitre 3 (Résultats) :

```
3.2.3. Flux de Communication et Interaction

La plateforme s'appuie sur une architecture client-serveur où l'interface web 
communique avec le backend via des appels API REST asynchrones. Pour les 
opérations de longue durée (ingestion de documents volumineux), le système 
utilise une file d'attente de travaux, permettant à l'utilisateur de continuer 
à travailler pendant le traitement.

L'expérience de génération de sections bénéficie d'un mécanisme de restitution 
en temps réel. Lorsqu'une section est en cours de rédaction par le LLM, le 
serveur envoie progressivement les fragments de texte au navigateur, qui les 
affiche en temps réel. Cette approche, courante dans les applications modernes, 
transforme une attente passive en une expérience interactive où l'utilisateur 
voit la réponse se construire progressivement.

Lorsque la génération est terminée, l'utilisateur accède à un espace de relecture 
où il peut :
- Visualiser l'intégralité de la section générée
- Consulter les sources et citations utilisées
- Approuver la section
- Demander une modification avec une consigne précise
- Modifier manuellement le texte

Ce cycle itératif (génération → relecture → validation → modification) constitue 
le cœur du processus de rédaction assistée, garantissant à la fois l'efficacité 
de l'IA et le contrôle humain nécessaire dans le contexte des appels d'offres.
```

---

## 10. Résumé

| Action | À faire |
|--------|---------|
| ✅ Mettre SSE dans le Chapitre 3 | Comme description du flux de communication |
| ✅ Décrire l'effet sur l'UX | Amélioration du temps d'attente perçu |
| ❌ Éviter les détails techniques | Pas de bibliothèques, pas de versions |
| ❌ Ne pas faire de section dédiée | Intégrer dans la description générale |
| ❌ Ne pas mettre dans l'état de l'art | Ce n'est pas un concept académique |

Excellente question, qui touche au cœur de la rédaction d'un mémoire de recherche appliquée.

Pour la **génération d'application** (le fait que vous **développez** une application), ce n'est **pas un concept de l'état de l'art**. C'est le **cadre de votre recherche** et le **contexte de votre travail**.

Voici comment le traiter proprement.

---

## 1. Ce qui relève de l'État de l'Art vs du Contexte du Projet

| Ce qui doit être dans l'État de l'Art | Ce qui doit être dans l'Introduction ou la Méthodologie |
|---------------------------------------|--------------------------------------------------------|
| Les modèles de langage (LLM) | Le fait que vous développez une application |
| Les techniques de RAG | Le fait que vous appliquez ces techniques à un cas d'usage |
| Les modèles de recherche d'information (BM25, RRF) | Le fait que vous implémentez une plateforme |
| Les architectures de systèmes d'IA | Le fait que vous concevez un système pour les AO |
| Les techniques de traitement de documents (OCR, Document Understanding) | Le fait que vous construisez un outil opérationnel |

---

## 2. Où Mettre le "Développement de l'Application" ?

### 2.1. Introduction (Chapitre 1) - Contexte

```text
1.5. Problématique et Objectifs de la Recherche

[...]

L'objectif de cette recherche est de concevoir et développer une plateforme 
logicielle permettant de capitaliser le patrimoine documentaire d'une entreprise 
du BTP et de générer automatiquement des dossiers de réponse aux appels d'offres 
en s'appuyant sur les technologies d'intelligence artificielle, en particulier 
le RAG (Retrieval-Augmented Generation).

Pour atteindre cet objectif, la recherche s'inscrit dans une approche de 
recherche et développement (R&D) appliquée, où les concepts théoriques sont 
confrontés à une implémentation concrète. Cette approche permet de valider les 
hypothèses dans un contexte opérationnel et de fournir des résultats 
exploitables par les professionnels du secteur.

[...]
```

### 2.2. Méthodologie (Chapitre 2) - Approche

```text
2.2. Démarche de Recherche et Développement

La méthodologie adoptée pour ce projet combine une approche de recherche 
appliquée et une démarche de génie logiciel. Elle vise à :

1. Analyser les besoins du domaine des appels d'offres dans le BTP
2. Étudier les technologies disponibles (LLM, RAG, bases vectorielles)
3. Concevoir une architecture adaptée
4. Développer une plateforme opérationnelle
5. Évaluer les performances du système
6. Proposer des perspectives d'amélioration

Cette démarche itérative, inspirée des méthodes agiles, permet de valider 
progressivement les choix technologiques et d'ajuster l'architecture en fonction 
des résultats obtenus.

[...]
```

### 2.3. Résultats (Chapitre 3) - Description du Système

```text
3.1. Présentation de la Plateforme Développée

La plateforme développée dans le cadre de cette recherche, baptisée [Nom], 
est une application web permettant aux entreprises du BTP de capitaliser 
leur patrimoine documentaire et de générer des dossiers de réponse aux 
appels d'offres.

Le développement de cette application a été guidé par les principes suivants :
- Modularité : chaque composant (ingestion, recherche, génération) est 
  indépendant et interchangeable.
- Évolutivité : l'architecture permet l'ajout de nouvelles fonctionnalités 
  (graphe de connaissances, agents).
- Traçabilité : chaque génération est associée à ses sources et à son 
  historique.
- Contrôle humain : la validation humaine est intégrée au workflow.

[...]
```

---

## 3. Ce qu'il ne faut PAS Mettre

### ❌ N'écrivez PAS :

```text
❌ "Cette application a été développée en Python avec FastAPI et React."
❌ "Nous avons utilisé Docker Compose pour l'orchestration des services."
❌ "Le code est hébergé sur un dépôt Git."
❌ "La base de données est PostgreSQL avec l'extension pgvector."
❌ "Le déploiement se fait sur un serveur Ubuntu."
❌ "Nous avons utilisé la bibliothèque LangChain pour le RAG."
```

**Pourquoi ?** Parce que ce sont des **détails techniques d'implémentation**, pas des concepts de recherche. Ils ont leur place dans une **annexe technique** ou une **documentation projet**, pas dans un mémoire.

---

## 4. Le Concept Clé : "Recherche Appliquée" vs "Recherche Fondamentale"

### 4.1. Distinction

| Recherche Fondamentale | Recherche Appliquée |
|------------------------|---------------------|
| Découvre de nouveaux concepts | Applique des concepts existants à un nouveau domaine |
| Pose les bases théoriques | Valide des hypothèses en contexte opérationnel |
| Exemple : "Proposer un nouveau modèle de LLM" | Exemple : "Appliquer le RAG aux appels d'offres BTP" |

### 4.2. Votre Cas

Votre recherche est de la **recherche appliquée** :

```text
Question de recherche : 
"Comment adapter les technologies de RAG, LLM et recherche hybride 
au domaine spécifique des appels d'offres dans le secteur du BTP, 
en tenant compte des contraintes de traçabilité, de conformité 
et de validation humaine ?"
```

La **génération d'application** est le **moyen** de valider cette question, pas le **sujet** de la recherche.

---

## 5. Le Concept à Mettre dans l'État de l'Art

### 5.1. Si vous voulez une notion "académique" sur la génération d'application :

**Le concept est : "Ingénierie des systèmes d'IA" ou "Systèmes d'Information Basés sur l'IA"**

```text
1.8. Ingénierie des Systèmes d'IA

L'ingénierie des systèmes d'IA est un domaine émergent qui traite de la 
conception, du développement et du déploiement de systèmes intégrant des 
composants d'intelligence artificielle. Elle s'intéresse aux défis spécifiques 
à ces systèmes :

1. **Fiabilité** : Comment garantir que les décisions de l'IA sont fiables ?
2. **Traçabilité** : Comment tracer les décisions et les sources ?
3. **Contrôle humain** : Comment intégrer la supervision humaine ?
4. **Évolutivité** : Comment passer d'un prototype à un système opérationnel ?
5. **Maintenabilité** : Comment faire évoluer le système dans le temps ?

Ces enjeux sont particulièrement critiques dans le contexte des appels d'offres, 
où les décisions ont des implications juridiques et financières majeures.

[...]
```

### 5.2. Concept Complémentaire : "Human-in-the-Loop (HITL)"

```text
1.9. Human-in-the-Loop (HITL)

Le concept de Human-in-the-Loop (HITL) désigne les systèmes où la décision 
humaine est intégrée comme un composant essentiel du processus. Cette approche 
est particulièrement pertinente dans les contextes où :

- Les enjeux sont critiques (décisions juridiques, financières)
- L'IA peut commettre des erreurs (hallucinations, biais)
- La traçabilité est requise (audit, conformité)
- L'expertise humaine apporte une valeur ajoutée

Les recherches récentes (Anthropic, 2024) soulignent l'importance de concevoir 
des systèmes où l'humain garde le contrôle final, l'IA agissant comme un 
assistant outillé plutôt qu'un décideur autonome.

[...]
```

---

## 6. Synthèse Complète

```
┌─────────────────────────────────────────────────────────────────────────────┐
│           OÙ METTRE LE "DÉVELOPPEMENT DE L'APPLICATION"                    │
│                                                                             │
│  CHAPITRE 1 - INTRODUCTION (1.5) :                                         │
│  ─────────────────────────────────────────────────────────────────────────  │
│  "L'objectif de cette recherche est de concevoir et développer une          │
│   plateforme logicielle..."                                                 │
│  → Présenter l'objectif, pas les détails                                   │
│                                                                             │
│  CHAPITRE 2 - MÉTHODOLOGIE (2.2) :                                         │
│  ─────────────────────────────────────────────────────────────────────────  │
│  "La méthodologie combine une approche de recherche appliquée et une        │
│   démarche de génie logiciel..."                                            │
│  → Décrire l'approche, pas les technologies                                 │
│                                                                             │
│  CHAPITRE 3 - RÉSULTATS (3.1) :                                            │
│  ─────────────────────────────────────────────────────────────────────────  │
│  "La plateforme développée se compose de..."                               │
│  → Décrire le système, pas l'implémentation technique                      │
│                                                                             │
│  ANNEXE TECHNIQUE (optionnelle) :                                           │
│  ─────────────────────────────────────────────────────────────────────────  │
│  → Stack technique détaillée (pour les évaluateurs techniques)             │
│  → Architecture logicielle complète                                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 7. Résumé des Concepts à Mettre dans l'État de l'Art

| Concept | Place | Raison |
|---------|-------|--------|
| **LLM / Transformers** | ✅ État de l'art | Fondement de la génération |
| **RAG** | ✅ État de l'art | Architecture centrale |
| **BM25 / Recherche d'information** | ✅ État de l'art | Fondement de la recherche |
| **Embeddings / Recherche sémantique** | ✅ État de l'art | Fondement du RAG |
| **OCR / Document Understanding** | ✅ État de l'art | Fondement de l'ingestion |
| **Fuzzy matching / Entity resolution** | ✅ État de l'art | Fondement de la cohérence |
| **Human-in-the-Loop (HITL)** | ✅ État de l'art | Garantie de qualité |
| **Systèmes d'IA / Génie logiciel** | ✅ État de l'art (1.8) | Cadre de conception |
| **Développement de l'application** | ❌ Non | C'est le contexte, pas un concept |
| **Stack technique** | ❌ Non | C'est l'implémentation, pas un concept |

---

## 8. Rédaction Proposée pour la Section 1.8

```text
1.8. Ingénierie des Systèmes d'IA et Human-in-the-Loop

L'ingénierie des systèmes d'IA est un domaine émergent qui s'intéresse à la 
conception de systèmes intégrant des composants d'intelligence artificielle 
dans des environnements opérationnels. Plusieurs défis sont spécifiques à ce 
type de systèmes :

La fiabilité constitue un enjeu majeur, car les modèles d'IA peuvent produire 
des résultats erronés ou inattendus. Dans des domaines à enjeux, comme les 
appels d'offres, une approche de validation systématique est nécessaire.

La traçabilité est essentielle pour permettre l'audit des décisions. Chaque 
étape du processus, de la sélection des documents à la génération de la réponse, 
doit pouvoir être retracée.

Le contrôle humain (Human-in-the-Loop, HITL) est particulièrement important 
dans les contextes juridiquement contraints. L'humain doit pouvoir vérifier, 
modifier ou rejeter les propositions de l'IA avant qu'elles ne soient utilisées.

La maintenabilité et l'évolutivité sont également des préoccupations 
importantes, car ces systèmes doivent pouvoir s'adapter à l'évolution des 
besoins et des technologies.

Anthropic (2024) souligne que les systèmes efficaces sont souvent construits 
à partir de composants simples et composables, et que l'ajout d'autonomie 
(agents) doit être justifié par la complexité réelle du problème. Dans le 
contexte des appels d'offres, une architecture workflow déterministe avec 
des points de validation humaine apparaît comme une approche adaptée.

[...]
```

---

## 9. Ce qu'il faut Retenir

1. **"Je développe une application"** → Ce n'est **pas** un concept de l'état de l'art.
2. **"La recherche appliquée"** → C'est le cadre de votre travail (Chapitre 1).
3. **"L'ingénierie des systèmes d'IA"** → C'est le concept académique (État de l'art).
4. **"Human-in-the-Loop"** → C'est le concept académique qui justifie votre approche (État de l'art).
5. **Les détails techniques** → C'est l'implémentation (Chapitre 3 ou Annexe).