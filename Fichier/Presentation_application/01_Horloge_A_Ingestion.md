# Horloge A — l'ingestion d'un document

Ce chapitre décrit tout ce qui se passe entre le moment où un fichier est
déposé dans l'application et le moment où il devient réellement exploitable
pour répondre à des questions. Tous les faits ci-dessous sont vérifiés dans
`backend_ao/app/` au 13/09/2026.

## Vue d'ensemble du trajet

```
Dépôt du fichier (navigateur)
   │
   ▼
1. Validations + déduplication + stockage brut (MinIO) + mise en file (Redis)
   │
   ▼  (traité par un processus séparé, le "worker")
2. Extraction du texte (parsing) — méthode différente selon le type de fichier
   │
   ▼
3. Découpage en chunks (parent / enfant)
   │
   ▼
4. Classification du type de section (RC, CCTP, DPGF...)
   │
   ▼
5. Transformation en empreintes numériques (embeddings) + indexation Qdrant
   │
   ▼
   document status = "ready"  →  déjà utilisable pour les questions
   │
   ▼  (en tâche de fond supplémentaire, n'empêche pas d'être "ready")
6. Extraction d'un graphe de connaissances → Neo4j
```

Et, uniquement pour les documents rattachés à un dossier d'appel d'offres
(le "DAO" du dossier) :

```
7. Extraction de la structure du mémoire attendu (plan, exigences, pièces
   administratives requises) — voir §6 de ce chapitre
```

## 1. Le dépôt (upload)

**Fichiers concernés** : `app/api/documents.py`, `app/services/document_upload.py`.

Quand un fichier est déposé, l'application vérifie d'abord plusieurs règles
avant d'accepter quoi que ce soit :

- Le **rôle du document** doit être l'un de : `patrimoine` (référence
  générale de l'entreprise), `dao_courant` (le dossier de l'AO en cours),
  `dao_archive` (un ancien DAO conservé comme référence), `annexe` (une
  pièce jointe à un dossier précis). Toute autre valeur est refusée.
- Le **type de document** (s'il est précisé) doit être l'un de : `rc`,
  `cctp`, `ccap`, `memoire`, `reference`, `dpgf`, `bpu`, `administratif`,
  `autre`.
- Un document `annexe` **doit obligatoirement** être rattaché à un dossier —
  une annexe sans dossier n'a pas de sens dans ce système.
- Un utilisateur ayant le rôle **consultant** (lecture seule) ne peut
  **jamais** déposer de fichier — refusé avec un message explicite.
- Un fichier vide (0 octet) est refusé.

**Déduplication** : avant tout stockage, le contenu du fichier est haché en
SHA-256 (une empreinte unique du contenu). Si un fichier avec exactement ce
même hash existe déjà pour la même entreprise (le même "tenant"), **aucun**
nouvel envoi n'est fait — ni vers le stockage, ni vers la base de données, ni
vers la file d'attente. Le document existant est simplement renvoyé. Cela
évite qu'un même PDF déposé deux fois par erreur ne soit indexé deux fois.

**Stockage du fichier brut** : le fichier est envoyé vers **MinIO** (un
stockage d'objets, similaire à ce que serait un espace de stockage cloud, mais
hébergé par l'entreprise elle-même), dans un espace nommé `ao-raw`, sous une
clé de la forme `<identifiant_entreprise>/<identifiant_unique>/<nom_du_fichier>`.
L'identifiant unique évite toute collision, même entre deux fichiers de même
nom déposés à des moments différents.

**Écriture en base** : une ligne est créée dans la table `documents` de
Postgres, avec un statut initial `pending` ("en attente") — sauf pour un
document de type `administratif` (une pièce comme un KBIS ou une attestation)
qui n'a pas besoin d'être découpé/indexé pour la recherche : il passe
directement à `ready`.

**Mise en file d'attente** : le document est ensuite placé dans une file de
tâches (via Redis, avec un système appelé ARQ) pour être traité par le
"worker" — un processus séparé de l'API, justement pour que l'upload réponde
immédiatement à l'utilisateur sans le faire attendre le traitement complet
(qui peut prendre de longues minutes sur un gros PDF scanné). Si la file
d'attente elle-même est indisponible au moment de l'envoi, le document est
marqué `failed` avec une explication — mais l'upload en lui-même n'échoue pas
côté utilisateur.

## 2. L'extraction du texte (parsing)

**Fichier** : `app/ingest/parse.py`.

Le fichier est repris par le worker, téléchargé depuis MinIO, puis traité
selon son type :

| Type de fichier | Méthode utilisée |
|---|---|
| `.xlsx` (Excel) | **openpyxl** — une "page" de texte par feuille, plafonnée à 400 lignes |
| `.docx` (Word) | **python-docx** — découpé section par section selon les titres du document |
| `.txt` / `.md` | Lecture brute du texte |
| Image (`.jpg`, `.png`, `.tiff`...) | Passage direct par la reconnaissance de texte sur image (OCR, voir plus bas) |
| `.pdf` | Un cas particulier détaillé ci-dessous, car un PDF peut être du texte numérique OU une image scannée |

### Le cas du PDF : comment distingue-t-on un PDF "texte" d'un PDF "scanné" ?

C'est une question précise qui mérite une réponse précise. Un PDF **numérique
natif** (créé depuis Word, un traitement de texte, etc.) contient du texte que
l'ordinateur peut lire directement. Un PDF **scanné** (une photo ou un scan
d'un document papier) ne contient, du point de vue de l'ordinateur, qu'une
image — aucun texte n'est directement extractible sans reconnaissance optique
de caractères (OCR).

La décision se fait ainsi (`parse.py`) :

1. On tente d'abord d'extraire le texte de **toutes les pages** du PDF avec la
   librairie **pypdf**.
2. On calcule la **densité** : le nombre total de caractères extraits divisé
   par le nombre de pages — donc une moyenne de caractères par page, pas un
   total sur l'ensemble du document.
3. On compare cette densité à un seuil fixe : **`PDF_TEXT_MIN_CHARS_PER_PAGE
   = 40`** caractères par page.
   - **Si la densité atteint 40 caractères/page ou plus** → le PDF est
     considéré comme du texte numérique. On essaie alors d'utiliser
     **Docling** (une librairie plus riche, capable de reconnaître les
     titres et les tableaux avec plus de précision) ; si elle n'est pas
     disponible sur la machine, on garde simplement le résultat de pypdf.
   - **Si la densité est sous 40 caractères/page** → le PDF est considéré
     comme un **scan**. On tente alors, dans l'ordre : **PaddleOCR** (le
     moteur de reconnaissance optique de caractères), puis Docling si Paddle
     n'est pas disponible, puis, en dernier recours, le texte pypdf s'il en
     a quand même extrait un peu (mieux qu'échouer complètement), et sinon
     une erreur explicite invitant à installer les librairies manquantes.

Ce même seuil de 40 caractères est aussi réutilisé, sous un autre nom de
constante mais avec la même valeur, pour les **images déposées directement**
(pas des pages de PDF) : si l'OCR extrait moins de 40 caractères d'une image,
celle-ci est traitée non pas comme un échec, mais comme un **actif visuel**
(une photo de chantier, un logo) — le document est marqué `ready` avec zéro
chunk de texte, ce qui est un comportement voulu, pas un bug.

### PaddleOCR — GPU ou CPU ?

La reconnaissance de texte sur les scans peut tourner sur carte graphique
(GPU, beaucoup plus rapide) ou sur processeur (CPU, plus lent mais toujours
fonctionnel). Le réglage `USE_GPU` dans la configuration du serveur détermine
si le GPU est tenté en premier. **Point important pour la fiabilité** : si le
GPU est configuré mais indisponible ou en erreur (typiquement une erreur liée
à `cuda`/`cudnn`, les librairies NVIDIA), le système **bascule silencieusement
vers le CPU** plutôt que d'échouer — l'ingestion continue, simplement plus
lentement, avec une trace dans les logs mais aucune interruption visible pour
l'utilisateur.

## 3. Le découpage en chunks

**Fichier** : `app/ingest/chunk.py`.

Le texte extrait est découpé selon une logique **parent / enfant**, avec des
tailles précises :

- Un **parent** représente une section logique du document (par exemple une
  page, ou un chapitre reconnu). S'il dépasse **8000 caractères**, il est
  lui-même redécoupé en segments successifs de 8000 caractères.
- Chaque parent est ensuite découpé en fenêtres **enfants** de **1100
  caractères**, avec un **chevauchement de 120 caractères** entre deux
  fenêtres consécutives (pour ne jamais couper une idée exactement à la
  frontière entre deux morceaux et perdre le sens).
- Si un parent est déjà assez petit pour tenir dans une seule fenêtre de 1100
  caractères, aucun enfant n'est créé — seul le parent existe, pour éviter un
  doublon inutile.

Ce sont les chunks **enfants** qui seront transformés en empreintes
numériques et cherchés lors d'une question (voir §5) ; les chunks **parents**
servent de contexte plus large et sont utilisés pour l'extraction du graphe
de connaissances et l'extraction de structure du dossier (voir §6 et §7).

## 4. La classification du type de section

**Fichier** : `app/ingest/classify_section.py`.

Pour chaque chunk parent, le système tente de deviner à quelle **famille de
document** il appartient parmi : `rc`, `ccap`, `cctp`, `dpgf`, `bpu`,
`memoire`, `reference`, `autre`. Cette classification sert ensuite de "signal
doux" de routage pendant les recherches (Horloge B) — jamais un filtre dur qui
exclurait totalement une information, juste une aide à prioriser.

Deux méthodes, appliquées dans l'ordre :

1. **Une heuristique par mots-clés** : une simple recherche de termes
   caractéristiques (par exemple, la présence du terme "règlement de
   consultation" oriente vers `rc`) sur le chemin de titre du chunk et ses 200
   premiers caractères.
2. **Si l'heuristique ne trouve rien**, un appel à l'IA générative (le LLM) :
   on lui donne les 2000 premiers caractères du chunk et on lui demande de
   répondre uniquement par un JSON du type `{"section_type": "cctp"}`. Le
   prompt exact et tous les paramètres de cet appel sont documentés dans
   [03_Interventions_du_LLM.md](03_Interventions_du_LLM.md).

Pour éviter qu'un très gros dossier (des centaines de parents) ne déclenche
des centaines d'appels au LLM et ne bloque le traitement pendant des heures,
un plafond est fixé : **au maximum 40 appels au LLM par document**. Au-delà,
les parents restants sont simplement laissés non classés plutôt que de
continuer indéfiniment.

## 5. Les empreintes numériques (embeddings) et l'indexation

**Fichier** : `app/ingest/index_qdrant.py`.

Chaque chunk **enfant** est transformé en une liste de 768 nombres (un
"vecteur") qui représente son sens, via le modèle **`nomic-embed-text`**,
exécuté par Ollama. Deux textes qui parlent de la même chose auront des
vecteurs proches, même s'ils n'utilisent pas exactement les mêmes mots — c'est
ce qui permet, plus tard, de retrouver un passage pertinent même si la
question posée ne reprend pas mot pour mot le vocabulaire du document.

Ces vecteurs sont stockés dans **Qdrant**, dans une unique collection nommée
**`ao_chunks`**, avec une mesure de distance dite "cosinus" (qui compare
l'orientation de deux vecteurs plutôt que leur longueur). Chaque point stocké
dans Qdrant porte, en plus du vecteur lui-même, des informations
d'accompagnement (le "payload") essentielles pour filtrer et citer les
sources plus tard : l'identifiant du chunk et du document d'origine,
l'identifiant de l'entreprise (pour ne jamais mélanger les données de deux
clients différents), le rôle du document, la position dans le document (page,
chemin de titre), et un aperçu du texte lui-même (tronqué à 2000 caractères,
pour éviter un aller-retour supplémentaire vers Postgres à chaque recherche).

Avant de réindexer un document (par exemple après une correction), tous les
anciens points Qdrant de ce document sont d'abord supprimés, car chaque
nouveau passage de traitement génère de nouveaux identifiants de chunk — sans
cette purge préalable, d'anciens points orphelins resteraient indéfiniment
dans la base vectorielle.

**C'est à ce stade que le document passe au statut `ready`** — il devient
utilisable pour répondre à des questions, même si l'étape suivante (le
graphe) n'est pas encore terminée.

## 6. L'extraction du graphe de connaissances

**Fichiers** : `app/graph/extract.py`, `app/graph/entity_match.py`,
`app/graph/cypher.py`.

En tâche de fond supplémentaire (après le passage à `ready`), le système tente
de reconnaître des **entités** (des choses nommées : une entreprise, un
projet, une certification, une personne, une exigence, un lot de travaux, un
site) et des **relations** entre elles (par exemple : cette entreprise "a
travaillé sur" ce projet), pour construire un graphe de connaissances dans
**Neo4j**.

Pour chaque chunk parent du document (il n'y a plus de limite au nombre de
parents traités — une ancienne limite à 12 a été supprimée), le texte
(tronqué à 3500 caractères) est envoyé au LLM avec un prompt qui liste
explicitement les types d'entités et de relations autorisés (le détail exact
est dans [03_Interventions_du_LLM.md](03_Interventions_du_LLM.md)). Le LLM
répond en JSON avec la liste d'entités et de relations qu'il a trouvées.

**Important, à assumer clairement en soutenance** : cet appel utilise
`"format": "json"` — c'est-à-dire qu'on demande au LLM de répondre en JSON
"gentiment", sans **garantie stricte** que la structure exacte attendue soit
respectée (contrairement à la génération de section du mémoire, voir
[02_Horloge_B_Generation.md](02_Horloge_B_Generation.md), où un mécanisme plus
robuste — un schéma contraint — a été mis en place). L'extraction de graphe
n'a, à ce jour, pas encore reçu ce même renforcement.

**Résolution d'entités** : pour éviter que "Dupont Construction" et "DUPONT
CONSTRUCTION SARL" ne deviennent deux entités différentes dans le graphe, une
cascade de rapprochement est appliquée avant toute création :
1. Correspondance **exacte** (même nom, ou même nom normalisé).
2. Similarité de type **Levenshtein** (distance d'édition entre deux chaînes
   de caractères — combien de lettres il faut changer pour passer de l'une à
   l'autre), avec un seuil de correspondance de 85 %.
3. Similarité de type **Jaccard/ensemble de mots**, seuil 80 %.
4. En dernier recours, similarité par **embedding** (le même type d'empreinte
   numérique que pour les chunks), seuil 0,82.

Si aucune de ces méthodes ne trouve de correspondance suffisante pour une
entité mentionnée dans une relation, cette relation est simplement
**abandonnée** plutôt que de créer une entité fantôme non fiable dans le
graphe.

**Un principe de conception explicitement documenté dans le code** : le LLM
n'écrit jamais lui-même de requête vers Neo4j (le langage utilisé s'appelle
Cypher). Il se contente d'extraire des entités et relations dans un format
borné ; c'est le **code**, pas le LLM, qui construit ensuite les requêtes
Neo4j à partir de gabarits fixes et prédéfinis. Cette même prudence — ne
jamais laisser le LLM générer librement une requête vers une base de données —
se retrouve côté lecture (Horloge B, l'expert graphe), avec trois gabarits de
requêtes fixes réutilisés à l'identique dans les deux sens (écriture à
l'ingestion, lecture pendant une conversation).

## 7. L'extraction de structure du dossier (côté DAO)

**Fichier** : `app/workflow/extract_structure.py`.

Cette étape ne concerne pas un document isolé mais un **dossier d'appel
d'offres** dans son ensemble, une fois que son DAO (règlement de
consultation, CCTP...) a été ingéré. Trois à quatre extractions
supplémentaires, chacune via un appel LLM séparé (prompts détaillés dans
[03_Interventions_du_LLM.md](03_Interventions_du_LLM.md)) :

1. **Le plan attendu du mémoire** (`extract_outline`) : si le règlement de
   consultation contient des indices qu'il décrit une structure de réponse
   attendue (des expressions comme "le mémoire technique comprendra..."), le
   LLM en extrait la liste ordonnée des titres demandés. En cas d'échec ou
   d'absence d'indice, un plan type par défaut est utilisé (présentation,
   moyens humains, références, méthodologie, planning).
2. **Les exigences du dossier** (`extract_exigences`) : chaque exigence
   identifiée (une obligation précise à respecter) est extraite avec son
   libellé, son type (éliminatoire, technique, administrative, financière,
   délai, référence), et si elle est obligatoire. Les chunks sont regroupés
   en lots (jusqu'à 14 000 caractères cumulés) pour limiter le nombre
   d'appels sur un gros dossier. Les doublons entre lots sont ensuite
   fusionnés en réutilisant la même cascade de rapprochement flou que pour
   les entités du graphe (§6).
3. **La checklist administrative** (`extract_checklist_administrative`) : la
   liste des pièces à fournir (KBIS, attestations, formulaires DC1/DC2...),
   soit une liste standard par défaut, soit une liste extraite du règlement
   de consultation si des indices le permettent.
4. **La classification exigences ↔ sections** (`classify_exigences_sections`,
   un job séparé et rejouable) : pour chaque exigence, quelles sections du
   plan doivent explicitement y répondre — une exigence purement
   administrative (comme un KBIS) peut n'être associée à aucune section
   rédactionnelle. Cette classification alimente directement la génération
   de section (Horloge B) qui doit savoir quelles exigences précises traiter
   pour chaque partie du mémoire.

Point de robustesse notable : toute association déjà validée par un humain
n'est jamais écrasée par une relance de cette classification (technique
`ON CONFLICT DO NOTHING` en base) — un correctif humain reste acquis.

## 8. Suivi et robustesse

- Chaque document porte une colonne `pipeline_stages` qui horodate le début
  et la fin de chaque étape (`parse`, `chunk`, `classify`, `embed`, `index`,
  `graph`) — utile pour diagnostiquer précisément où un traitement a échoué
  ou est resté bloqué.
- Une colonne `ocr_progress` permet de **reprendre l'OCR page par page** si le
  traitement est interrompu (crash, redémarrage) plutôt que de tout
  recommencer depuis la première page d'un gros scan.
- Les statuts possibles d'un document : `pending` (en attente) →
  `processing` (en cours) → `ready` (utilisable) ou `failed` (échoué, avec un
  message d'erreur explicite conservé). Le champ `graph_extracted` est
  **séparé** du statut principal : un document peut être `ready` (utilisable
  pour le RAG) sans que son graphe de connaissances soit encore terminé.

## 9. Modèles actuellement configurés

| Rôle | Valeur actuelle |
|---|---|
| Génération de texte / décisions (LLM) | `granite3.3:2b` (IBM Granite 3.3, 2 milliards de paramètres, via Ollama) |
| Empreintes numériques (embeddings) | `nomic-embed-text` (dimension 768) |
| Reranking (voir Horloge B) | `BAAI/bge-reranker-v2-m3` **configuré comme cible mais pas réellement branché** aujourd'hui — voir [02_Horloge_B_Generation.md](02_Horloge_B_Generation.md) pour la raison précise (conflit de librairies) |

## 10. Suppression d'un document

Quand un document est supprimé (réservé aux rôles admin/manager), le nettoyage
se fait dans un ordre précis pour ne jamais laisser de traces orphelines :
1. Suppression des points **Qdrant** liés au document.
2. Suppression des relations **Neo4j** dont la source est ce document, puis
   des entités devenues orphelines (qui n'ont plus aucune relation) pour
   cette entreprise — jamais une entité encore reliée à un autre document.
3. Suppression du fichier brut dans **MinIO**.
4. Suppression des chunks puis de la ligne document dans **Postgres**.

## Ce qu'il faut retenir pour la soutenance

- Le seuil de détection "PDF scanné" est une constante simple et documentée
  (40 caractères par page en moyenne), pas un modèle d'IA — un choix
  pragmatique et vérifiable.
- La bascule GPU→CPU pour l'OCR est silencieuse par conception : l'ingestion
  ne doit jamais échouer juste parce que le GPU est momentanément
  indisponible.
- Un seul point de vigilance technique honnête à assumer : l'extraction de
  graphe et l'extraction de structure du dossier utilisent encore un JSON
  "non contraint" (demandé poliment au LLM), alors qu'un mécanisme plus
  fiable (schéma JSON contraint) existe déjà dans le code et est utilisé pour
  la génération finale des sections du mémoire — une amélioration identifiée
  mais pas encore généralisée partout.
