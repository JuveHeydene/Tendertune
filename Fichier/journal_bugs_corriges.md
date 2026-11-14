# Journal des bugs trouvés et corrigés — BTP_RAG

Ce document catalogue les problèmes réels rencontrés pendant le développement
et les tests en conditions réelles de la plateforme (pas des bugs théoriques :
tous ont été observés en exécutant le système, souvent sur de vrais DAO
volumineux). Chaque entrée suit le même format : **Symptôme** (ce qu'on a
observé) → **Cause** (pourquoi) → **Correction** (ce qui a été changé) →
**Leçon** (le principe général à retenir, pour éviter de refaire la même
erreur ailleurs).

Classés par catégorie plutôt que par ordre chronologique, car plusieurs bugs
de la même famille sont apparus à des endroits différents du code.

---

## 1. Appels LLM séquentiels sans plafond (la famille de bugs la plus coûteuse)

C'est la même erreur de conception, répétée à deux endroits différents :
**boucler sur tous les éléments d'un document et faire un appel LLM bloquant
par élément, sans jamais limiter le nombre total d'appels.** Sur un petit
document de test, ça passe inaperçu (quelques appels). Sur un vrai DAO de
150+ pages, ça explose.

### 1.1 Extraction des exigences (`extract_exigences`)

- **Symptôme** : le job d'analyse d'un dossier tournait pendant plus d'une
  heure sans jamais produire de résultat visible, puis se faisait tuer par
  un timeout et redémarrait de zéro — en boucle infinie, sans jamais aboutir.
- **Cause** : la fonction faisait **un appel LLM par chunk "parent"** du
  document (jusqu'à 154 appels pour un DAO de 156 pages), en séquence, chacun
  synchrone et bloquant. Le job ARQ a un `job_timeout` (~1h) : au-delà, ARQ
  tue le job et le relance depuis zéro (nouvelle tentative = on recommence
  les 154 appels depuis le début).
- **Correction** : regroupement (*batching*) — plusieurs chunks combinés dans
  un seul prompt (jusqu'à ~14 000 caractères, avec `num_ctx=4096` explicite
  pour ne pas dépasser la fenêtre de contexte réelle du modèle), ce qui
  réduit ~154 appels à quelques dizaines. Contrepartie assumée : l'exigence
  extraite est rattachée à la page du **début du lot**, pas à sa page exacte
  (attribution moins fine mais bien plus rapide).
- **Leçon** : dès qu'une boucle fait un appel réseau/LLM par élément d'une
  collection dont la taille dépend du document utilisateur (pas d'un nombre
  fixe et petit), il faut soit un plafond, soit un regroupement — sinon le
  temps total est imprévisible et peut dépasser n'importe quel timeout.

### 1.2 Classification automatique `section_type` (`classify_section_type`)

- **Symptôme** : exactement le même type de blocage, cette fois pendant
  l'**ingestion** (pas l'analyse) d'un document de 739 pages — plus aucun
  log pendant 8+ minutes, aucune progression visible.
- **Cause** : la classification a 2 couches — une heuristique par mots-clés
  (quasi gratuite) puis, si elle échoue, un appel LLM. Pour un document
  technique dont les paragraphes ne contiennent pas littéralement "RC" ou
  "CCAP" dans leur titre, la couche 1 échoue presque tout le temps → la
  couche 2 (LLM, 60s de timeout chacun) tourne sur la quasi-totalité des 739
  chunks parents.
- **Correction** : plafond dur de 40 appels LLM par document. Au-delà, le
  `section_type` reste vide. C'est acceptable car ce champ est documenté
  comme un **signal doux** (jamais un filtre bloquant) : une classification
  manquante ne casse rien, la recherche continue de fonctionner normalement
  sur ce chunk.
- **Leçon** : avant d'ajouter un plafond, vérifier si la donnée manquante est
  réellement critique. Ici, la documentation du code disait déjà "signal
  doux, jamais un filtre bloquant" — ça a rendu la décision de plafonner
  facile et sans risque de régression fonctionnelle.

---

## 2. Appels bloquants dans du code asynchrone (asyncio)

- **Symptôme** : pendant qu'un job d'extraction tournait, le worker ARQ
  n'émettait plus ses battements de vie ("recording health") — comme si le
  process entier était figé.
- **Cause** : `ollama_generate_json` utilise `urllib.request.urlopen`, une
  fonction **synchrone**. Appelée directement (sans précaution) depuis une
  fonction `async def`, elle bloque tout le thread — donc toute la boucle
  d'événements asyncio du worker, y compris les autres tâches qui devraient
  pouvoir s'exécuter en parallèle.
- **Correction** : englober chaque appel avec
  `await asyncio.to_thread(ollama_generate_json, ...)` — délègue l'appel
  bloquant à un thread séparé, sans bloquer la boucle asyncio principale.
  Appliqué aux 3 appels LLM de `extract_structure.py` et à la classification
  dans `ingest.py`.
- **Leçon** : dans une fonction `async def`, **toute** fonction qui fait de
  l'I/O sans le mot-clé `await` (fichier, réseau, DB synchrone) doit passer
  par `asyncio.to_thread(...)` — sinon elle bloque tout le worker, pas
  seulement la tâche en cours.

---

## 3. Mauvaise utilisation d'une API tierce (comportement non documenté)

### 3.1 Filtre Qdrant `min_should` mal construit

- **Symptôme** : dès qu'une conversation liée à un dossier tentait une
  recherche (dense retrieval), erreur de validation Pydantic côté Qdrant :
  `Input should be a valid dictionary or instance of MinShould`.
- **Cause** : le code combinait `Filter(should=[...], min_should=1)`. Or
  `should=[...]` **seul** signifie déjà "au moins une de ces conditions doit
  matcher" (OR). `min_should` est un champ **différent**, qui attend un objet
  `MinShould(conditions=..., min_count=...)`, pas un entier — la combinaison
  n'a jamais eu de sens, c'était une confusion entre deux mécanismes proches.
- **Correction** : suppression du `min_should=1` partout — `should=[...]`
  suffisait déjà à exprimer l'intention initiale.
- **Leçon** : quand une bibliothèque a deux paramètres au nom proche
  (`should` / `min_should`), vérifier leur signature exacte au lieu de
  supposer qu'ils se combinent naturellement. L'erreur de validation Pydantic
  était en fait très explicite — elle pointait déjà vers la solution.

### 3.2 PaddleOCR renvoie `[None]`, pas `[]`, sur une page sans texte

- **Symptôme** : l'ingestion d'un DAO scanné plantait entièrement dès qu'une
  seule page (page de garde, tampon, page blanche) ne contenait aucun texte
  détecté — `TypeError: 'NoneType' object is not iterable`.
- **Cause** : le code se protégeait contre `result` étant `None`/vide
  (`if result else []`), mais PaddleOCR peut renvoyer `[None]` — une liste
  non vide dont le premier élément est `None`. Le garde-fou existant ne
  couvrait pas ce cas précis.
- **Correction** : `page_items = (result[0] if result else None) or []` —
  couvre les trois cas (`result` vide, `result[0]` est `None`, `result[0]`
  est déjà une liste vide) en une seule expression.
- **Leçon** : un garde-fou contre "la valeur est absente" doit être testé
  contre **toutes** les formes que "absente" peut prendre dans l'API
  utilisée (`None`, `[]`, `[None]`, `{}`...), pas seulement la plus évidente.
  Ce bug n'était visible qu'avec un vrai scan multi-pages — jamais reproduit
  par un test unitaire synthétique.

---

## 4. Ordonnancement des transactions / visibilité entre connexions DB

- **Symptôme** : dans une conversation liée à un dossier, la première
  question posée provoquait une erreur silencieuse (rien n'était enregistré,
  aucune réponse) : `ForeignKeyViolationError` sur `retrieval_traces`,
  `message_id` introuvable dans `messages`.
- **Cause** : le message utilisateur était ajouté à la session puis
  seulement **flush** (envoyé à Postgres mais pas encore validé/committé).
  Les experts de récupération (CRAG) tournent en parallèle
  (`asyncio.gather`), chacun avec **sa propre connexion DB** (nécessaire pour
  la sécurité de concurrence asyncio — une session SQLAlchemy async n'est pas
  partageable entre coroutines concurrentes). Une transaction non validée sur
  une connexion est invisible depuis une autre connexion (isolation
  Postgres) : les experts ne voyaient donc pas encore le message dont ils
  avaient besoin pour écrire leur trace.
- **Correction** : `await session.commit()` (pas juste `flush()`) tout de
  suite après avoir ajouté le message utilisateur, avant de lancer le
  pipeline agentique.
- **Leçon** : dès que deux connexions DB différentes doivent voir la même
  ligne dans la même requête utilisateur, un `flush()` ne suffit jamais — il
  faut un vrai `commit()`. Le signe qui doit alerter : "connexion A" et
  "connexion B" dans la même phrase.

---

## 5. Conditions de course (race conditions) applicatives

### 5.1 Deux analyses concurrentes sur le même dossier

- **Symptôme** : les logs montraient deux jobs `extract_dossier_structure`
  démarrés à 4 secondes d'intervalle pour le **même** dossier. L'un a réussi
  (95 exigences insérées), l'autre a planté en pleine écriture (collision
  probable sur la contrainte d'unicité `outline_items`). Une tentative de
  relance ultérieure (automatisée, pour vérifier l'avancement) était en fait
  redondante — l'analyse avait déjà réussi 15 minutes plus tôt — et menaçait
  de dupliquer les 95 exigences si on l'avait laissée finir.
- **Cause profonde (frontend)** : le bouton "Analyser le DAO" redevenait
  cliquable dès que la requête HTTP `POST /analyser` répondait — or cette
  requête ne fait qu'**enfiler** le job (réponse quasi immédiate, `status:
  "analyzing"` + `job_id`), elle n'attend pas que l'extraction (qui prend
  plusieurs minutes) soit terminée. Le composant remettait `busy` à `false`
  dans le `finally`, bien avant la fin réelle du travail.
- **Correction** :
  1. **Backend** : `POST /dossiers/{id}/analyser` renvoie maintenant `409
     Conflict` si `dossier.status == "analyzing"` — un job est déjà en cours,
     on refuse d'en enfiler un deuxième.
  2. **Frontend** : le bouton est maintenant désactivé tant que
     `dossier.status === "analyzing"` (pas seulement `busy`), et ce champ est
     rafraîchi automatiquement toutes les 3s tant que l'analyse tourne — état
     réel du serveur, pas juste la durée de l'appel HTTP.
- **Leçon** : dans une architecture "requête HTTP rapide + job de fond long"
  (pattern déjà utilisé partout ici — upload, ingestion, analyse), **ne
  jamais piloter l'état "en cours" d'un bouton sur la durée de l'appel HTTP**
  — il faut le piloter sur l'état réel de la ressource (ici
  `dossier.status`), avec un polling ou une notification. Et côté serveur,
  toujours prévoir un garde-fou d'idempotence (409) pour le cas où le
  frontend ne suffit pas (autre onglet, autre appareil, requête rejouée).

---

## 6. Erreur d'architecture : ordre logique inversé

- **Symptôme** : on pouvait démarrer une conversation et "rédiger" une
  section avant même d'avoir chargé un DAO — le système créait alors un
  dossier fantôme avec un plan générique inventé, sans aucune exigence.
- **Cause** : le dossier n'existait **que** comme sous-produit paresseux
  d'une conversation (`ensure_dossier`, appelé au premier message écrit) —
  jamais comme entité créée explicitement en amont. Par ailleurs, même quand
  un DAO était uploadé avec le rôle `dao_courant`, rien ne reliait
  réellement ce document au dossier (`dossier.dao_document_id` n'était
  jamais renseigné nulle part dans le code) : `analyser_dossier` ne pouvait
  donc jamais fonctionner en pratique.
- **Correction** : inversion complète du flux — `POST /dossiers` crée un
  dossier vide et indépendant (sans plan inventé) ; l'upload d'un DAO avec
  `dossier_id` renseigne enfin `dao_document_id` ; une conversation doit
  choisir un dossier existant à sa création (ou rester "recherche libre").
  `ensure_dossier` (création silencieuse) supprimé, remplacé par
  `require_dossier` qui refuse explicitement d'écrire sans dossier.
- **Leçon** : quand une entité importante (ici : le dossier de réponse à un
  AO) n'a pas de point de création explicite dans l'interface, elle finit
  presque toujours par être créée implicitement "quelque part", dans un état
  incomplet — et ça se voit tard, seulement quand quelqu'un essaie d'utiliser
  la fonctionnalité qui dépend de cet état complet (ici : l'analyse).

---

## Résumé express (pour relecture rapide)

| # | Bug | Catégorie | Corrigé par |
|---|-----|-----------|-------------|
| 1.1 | 154 appels LLM séquentiels (exigences) | Passage à l'échelle | Regroupement (batching) + `num_ctx` explicite |
| 1.2 | Jusqu'à 739 appels LLM (classification) | Passage à l'échelle | Plafond de 40 appels |
| 2 | Appels `urllib` bloquants dans `async def` | Concurrence asyncio | `asyncio.to_thread(...)` |
| 3.1 | `Filter(should=..., min_should=1)` invalide | API tierce mal comprise | Suppression de `min_should` |
| 3.2 | PaddleOCR renvoie `[None]` pas `[]` | API tierce, cas limite | `(result[0] if result else None) or []` |
| 4 | Message flush() mais pas commit() | Transactions / isolation DB | `commit()` avant dispatch parallèle |
| 5.1 | Double analyse concurrente | Race condition | Garde 409 côté API + état réel côté UI |
| 6 | Dossier créé en sous-produit de conversation | Architecture / ordre logique | Création de dossier indépendante, `require_dossier` |

Le fil conducteur : presque tous ces bugs ne sont apparus qu'en testant avec
de **vrais** documents volumineux (150+ pages, scans réels) — jamais avec de
petits fichiers de test synthétiques. Une boucle qui fait 3 appels LLM
pendant un test unitaire et une boucle qui en fait 700 sur un vrai DAO,
c'est exactement le même code — seul le volume révèle le problème.
