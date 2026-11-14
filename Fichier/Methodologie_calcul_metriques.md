# Comment calculer ces métriques — méthodologie et prérequis

Pour chaque métrique du tableau : sa définition, ce qui existe déjà dans le
code qui peut servir de brique, ce qui manque pour la calculer réellement, la
méthode de calcul concrète, et un ordre de grandeur d'effort. Objectif :
savoir précisément quoi construire, pas juste "il faudrait évaluer ça".

**Principe transversal** : toutes les métriques de la catégorie Récupération
(Recall, Precision, Hit@5, MRR) et Faithfulness/Hallucination/Answer
Relevancy ont un point commun — elles nécessitent une forme de **vérité
terrain** (un jeu de test annoté à la main, ou un juge externe) qui
n'existe pas aujourd'hui. Le système trace les données brutes
(`retrieval_traces`) mais personne n'a encore dit "pour CETTE requête, LE
bon document est CELUI-LÀ". Sans ce jeu de référence, aucun calcul n'est
possible — ce n'est pas une case à cocher dans le code, c'est un travail
d'annotation humaine à planifier en premier.

---

## 1. Recall & Precision (récupération)

**Définition** : Recall = part des documents pertinents qui ont été
retrouvés. Precision = part des documents retrouvés qui sont pertinents.

**Ce qu'on a déjà** :
- `_hybrid_pass()` (`app/rag/experts.py`) retourne pour chaque requête une
  liste de chunks scorés (dense + sparse + RRF + rerank).
- `RetrievalTrace` (table `retrieval_traces`) enregistre déjà
  `query_utilisee` et `chunks_retournes` (id + score) pour CHAQUE tentative
  réelle faite en production — une base d'observation qui existe déjà,
  juste jamais exploitée pour un calcul agrégé.

**Ce qui manque** : un **jeu de test annoté** — une liste de
`(question réaliste, ensemble des chunk_id réellement pertinents)`. Ça ne
se déduit d'aucune donnée existante : il faut qu'un humain qui connaît le
patrimoine documentaire lise 30 à 50 questions représentatives (couvrant les
5 experts : juridique/technique/financier/graphe/patrimoine) et pointe à la
main quels chunks y répondent vraiment.

**Méthode de calcul** (une fois le jeu de test prêt) :
1. Script `scripts/eval_retrieval.py` (à créer) : pour chaque question du
   jeu de test, appeler directement `_hybrid_pass()` (ou `run_expert` pour
   tester la boucle CRAG complète) et récupérer le top-k de chunk_id.
2. Pour chaque requête :
   `Recall@k = |top_k ∩ pertinents| / |pertinents|`
   `Precision@k = |top_k ∩ pertinents| / k`
3. Moyenne sur l'ensemble du jeu de test → Recall/Precision globaux.

**Effort** : le harnais de calcul est simple (quelques dizaines de lignes,
`_hybrid_pass` existe déjà et retourne exactement ce qu'il faut). L'effort
réel est humain : construire et maintenir le jeu de 30-50 questions
annotées. C'est le vrai coût, pas le code.

---

## 2. Hit@5

**Définition** : le document pertinent apparaît-il dans les 5 premiers
résultats (oui/non par requête, moyenné).

**Ce qu'on a déjà / ce qui manque** : identique à Recall/Precision — même
jeu de test requis, même script.

**Méthode de calcul** :
`Hit@5 = (1/N) × Σ [1 si au moins un chunk pertinent est dans le top-5, sinon 0]`

C'est un sous-produit gratuit du même script que Recall/Precision — pas de
travail supplémentaire une fois le jeu de test et le harnais en place.

---

## 3. MRR (Mean Reciprocal Rank)

**⚠️ Point à clarifier absolument avant de se lancer** : `app/rag/fusion.py`
implémente déjà **RRF (Reciprocal Rank Fusion)** — une **technique de
fusion de classements** (combiner recherche dense + lexicale en un seul
classement). Ce n'est **pas** la métrique MRR. Les deux se ressemblent par
le nom, l'un est un mécanisme de retrieval déjà en prod, l'autre est une
métrique d'évaluation qui n'existe pas encore. Ne pas confondre les deux
dans un rapport ou une soutenance.

**Ce qui manque** : même jeu de test annoté que Recall/Precision/Hit@5.

**Méthode de calcul** : pour chaque requête, trouver le RANG du premier
chunk pertinent dans le classement final (celui produit par RRF puis
rerank — `app/rag/rerank.py`) :

`MRR = (1/N) × Σ (1 / rang_du_premier_pertinent)`

Si aucun résultat pertinent n'apparaît du tout, ce terme vaut 0. Encore une
fois : sous-produit du même harnais que les 3 métriques précédentes, avec
en plus la fusion RRF déjà en place comme entrée naturelle du calcul (le
classement sur lequel on calcule le rang, c'est justement la sortie de RRF
+ rerank).

**Effort combiné (Recall + Precision + Hit@5 + MRR)** : UN seul jeu de test
annoté, UN seul script d'évaluation qui boucle dessus et sort les 4
chiffres en une passe. À traiter comme un seul chantier, pas quatre.

---

## 4. Faithfulness (fidélité au contexte)

**Définition** : proportion des affirmations d'une réponse générée qui sont
réellement soutenues par le contexte récupéré (aucune invention).

**Ce qu'on a déjà** :
- `_validate()` (`app/workflow/nodes/generate_section.py`) vérifie déjà que
  chaque citation `[n]` pointe vers un extrait RÉELLEMENT présent dans le
  contexte — mais ça valide que l'ID existe, pas que l'affirmation associée
  est vraiment soutenue par le texte cité.
- `Generation.context_snapshot` conserve le contexte exact utilisé pour
  chaque génération (maintenant plafonné à 20000 caractères — voir le
  correctif de troncature de cette session) — c'est la pièce qui manquait
  le plus souvent dans ce genre d'évaluation (rejouer l'évaluation SANS
  avoir le contexte d'origine est impossible).
- Le prompt de génération interdit déjà explicitement d'inventer — c'est
  une mesure PRÉVENTIVE (réduire le risque), pas une MESURE (donner un
  score après coup). Les deux sont complémentaires, pas substituables.

**Ce qui manque** : un évaluateur qui compare le texte généré au contexte
et juge, affirmation par affirmation, si elle est soutenue.

**Méthode de calcul recommandée pour ce système précis** (LLM-juge, la plus
réaliste vu l'infrastructure existante) :
1. Nouveau job (offline, pas dans le chemin critique de génération) : pour
   chaque `Generation` à évaluer, découper `content.blocs[].texte` en
   phrases/affirmations.
2. Prompt du juge : "Voici un contexte et une affirmation. Réponds
   UNIQUEMENT en JSON : `{"soutenue": true|false}`" pour chaque affirmation,
   avec `context_snapshot` en entrée.
3. `Faithfulness = affirmations_soutenues / affirmations_totales`.
4. Stocker le résultat (nouvelle colonne `Generation.faithfulness_score` ou
   table séparée `generation_evaluations` si on veut garder le détail
   affirmation par affirmation).

**⚠️ Piège méthodologique à anticiper** : cette session a montré que le
petit modèle local (granite3.3:2b) est peu fiable pour respecter des
formats stricts et prendre des décisions de jugement (cf. le bug de
`grade_context`/superviseur corrigé). Utiliser CE MÊME modèle comme juge de
fidélité risque de donner un score de fidélité... peu fidèle. Recommandé :
un modèle plus grand pour cette tâche de jugement spécifique (elle peut
tourner en batch offline, la latence importe peu, contrairement à la
génération en direct).

**Effort** : moyen — pas de jeu de test à annoter à la main (le juge
travaille sur des générations déjà produites en prod), mais il faut écrire
le prompt de jugement, le job, le stockage du score, et valider que le
juge lui-même est fiable (en le comparant à quelques évaluations humaines
sur un petit échantillon, pour calibrer la confiance qu'on lui accorde).

---

## 5. Hallucination

**Définition** : proportion d'affirmations NON fondées sur les sources —
c'est le complément de Faithfulness, pas une métrique indépendante à
construire séparément.

**Méthode de calcul** : `Hallucination ≈ 1 − Faithfulness`, à partir du
même évaluateur que la section précédente (le même appel au juge donne
les deux chiffres). Il n'y a pas de raison de construire deux pipelines
différents.

**Nuance à garder pour la soutenance** : "non soutenue par le contexte"
n'est pas rigoureusement identique à "fausse" — une affirmation peut être
vraie mais absente du contexte fourni (le modèle la connaît par ailleurs).
Le prompt de génération traite déjà ce cas via `abstentions` (dire
explicitement ce qui manque plutôt que d'improviser) — un bon juge de
fidélité doit distinguer "invention pure" de "vrai mais hors contexte", ce
qui complique légèrement le prompt du juge (prévoir 3 catégories plutôt que
2 : soutenue / hors-contexte-mais-signalée-en-abstention / inventée).

---

## 6. Answer Relevancy

**Définition** : la réponse répond-elle réellement à la question posée
(indépendamment de sa véracité).

**Ce qu'on a déjà** : le pipeline d'embeddings existe déjà et tourne en
routine (`nomic-embed-text` via Ollama, `app/ingest/index_qdrant.py`
`embed_texts()`) — réutilisable tel quel pour cette métrique.

**Ce qui manque** : le calcul lui-même.

**Méthode de calcul (approche RAGAS classique, adaptée à l'existant)** :
1. Demander au LLM de générer 3 à 5 questions hypothétiques auxquelles la
   réponse produite serait une bonne réponse ("reverse-engineer" la
   question à partir de la réponse).
2. Embedder ces questions générées ET la question originale avec
   `embed_texts()` (déjà en place).
3. `Answer Relevancy = similarité_cosinus_moyenne(question_originale,
   questions_générées)`.

**Alternative plus simple, moins coûteuse** : LLM-juge direct, "cette
réponse traite-t-elle réellement la question posée, sur une échelle de 1 à
5 ?" — moins rigoureux mais beaucoup plus rapide à mettre en place, et
suffisant pour une première mesure.

**Effort** : faible à moyen selon l'approche choisie — pas de jeu de test à
annoter, l'infrastructure d'embedding est déjà en place, il manque juste le
prompt/script et le stockage du score.

---

## 7. Conformité (couverture des exigences)

**C'est la seule métrique du tableau qui a déjà un vrai calcul en
production** — mais avec une réserve qu'il faut absolument connaître.

**Ce qu'on a déjà** :
- `DossierOut.exigences_couvertes / exigences_total` — calculé et affiché
  pour chaque dossier (`app/api/dossiers.py`, `_to_dossier_out`).
- Depuis cette session : la fonctionnalité de consultation des preuves
  (bouton "N preuves" dans l'onglet Exigences) — elle permet à un humain de
  VÉRIFIER manuellement, extrait par extrait, si un statut "couverte" est
  réellement justifié. C'est exactement l'outil qu'il faut pour l'audit
  décrit ci-dessous, il existe déjà, il suffit de s'en servir pour ça.

**Ce qui manque pour que ce chiffre soit une vraie métrique VALIDÉE (et pas
un ratio auto-déclaré)** — il faut en réalité distinguer DEUX métriques
différentes que le mot "Conformité" mélange aujourd'hui :

1. **Rappel d'extraction** : est-ce que `extract_exigences` a bien trouvé
   TOUTES les exigences réelles du DAO ?
   `= (exigences correctement extraites) / (exigences réelles du DAO, comptées à la main par un expert métier qui lit le RC/CCTP)`
   → nécessite qu'un humain lise intégralement 3 à 5 DAO réels et fasse sa
   propre liste de référence, à comparer à ce que le système a extrait.

2. **Précision de couverture** : parmi les exigences marquées "couverte"
   par le système, combien le sont VRAIMENT ?
   `= (exigences correctement marquées couverte, vérifiées via les preuves) / (exigences marquées couverte par le système)`
   → s'appuie directement sur la fonctionnalité "Preuves" déjà construite :
   un humain ouvre chaque preuve affichée et juge "oui/non, ça justifie
   vraiment cette exigence".

**Pourquoi cette distinction compte** : le ratio actuellement affiché
(`exigences_couvertes / exigences_total`) ne mesure NI l'un NI l'autre
proprement — c'est un chiffre interne au système, qui suppose implicitement
que l'extraction est complète (jamais vérifié) et que chaque "couverte"
est correcte (jamais audité). Cette session a justement trouvé et corrigé
un cas où une recherche en échec (abstention CRAG) pouvait être comptée à
tort comme "couverte" — la preuve concrète que ce ratio, sans audit externe,
peut être optimiste.

**Effort** : le calcul lui-même est déjà là. Le vrai travail est l'audit
manuel (points 1 et 2), sur un échantillon de dossiers réels — quelques
heures de relecture experte par dossier, pas du développement.

---

## 8. Réduction du temps (≥ 70 %)

**Définition** : gain de productivité sur le cycle complet
analyse-du-DAO → mémoire rédigé, par rapport à un processus manuel.

**Ce qu'on a déjà** :
- `pipeline_stages` (JSONB sur `documents`) : horodatage début/fin de
  chaque phase de traitement MACHINE (parse, chunk, embed, index, graphe) —
  donne le temps de calcul de l'outil, pas le temps humain économisé.
- `Review.created_at` par action (approve/edit/regen) et `Dossier.status` —
  permet de reconstituer, pour un dossier donné, le temps écoulé entre sa
  création et son export final DANS L'OUTIL.

**Ce qui manque, et c'est le plus dur des 9 métriques** : une **référence
de comparaison** — le temps qu'aurait pris la RÉDACTION MANUELLE du même
mémoire, sans l'outil. Rien dans les logs ne peut donner ça par
construction : le système ne peut pas observer un monde où il n'a pas été
utilisé.

**Méthode de calcul réaliste** :
1. **Ne pas** essayer de déduire ce chiffre uniquement des timestamps
   applicatifs — au mieux ils donnent le temps DANS l'outil, jamais le
   temps ÉCONOMISÉ.
2. Étude comparative à organiser en dehors du code : chronométrer 2 à 3
   rédacteurs sur un dossier comparable, une fois SANS l'outil (méthode
   actuelle) et une fois AVEC, ou comparer un historique de dossiers
   traités manuellement avant l'existence de l'outil à des dossiers
   récents traités avec.
3. `Réduction = 1 − (temps_avec_outil / temps_sans_outil)`, avec
   `temps_avec_outil` reconstitué depuis `Dossier.created_at` →
   dernière approbation de section (`Review`), et `temps_sans_outil`
   mesuré ou estimé par les rédacteurs eux-mêmes (déclaratif, à défaut de
   mieux).

**Effort** : aucun développement à proprement parler — c'est un protocole
d'étude à organiser (qui chronomètre quoi, sur quel échantillon de
dossiers), pas une fonctionnalité à coder. Le seul développement utile
serait un petit script qui reconstitue automatiquement `temps_avec_outil`
depuis les tables existantes, pour ne pas avoir à le calculer à la main
dossier par dossier.

---

## Récapitulatif — par où commencer si le temps est compté

| Métrique | Bloqueur principal | Type d'effort |
|---|---|---|
| Recall / Precision / Hit@5 / MRR | Jeu de test annoté (30-50 questions) | Humain (annotation), code minime |
| Faithfulness / Hallucination | Prompt + job de jugement LLM | Code moyen, pas d'annotation |
| Answer Relevancy | Prompt + réutilisation de l'embedding existant | Code faible |
| Conformité (vraie mesure) | Audit manuel d'un échantillon de dossiers réels | Humain (relecture experte), code quasi nul |
| Réduction du temps | Protocole d'étude comparative | Humain (organisation), code quasi nul |

Si l'objectif est de pouvoir dire quelque chose de solide en soutenance
avec un minimum de travail : la **Conformité** (l'outil "Preuves" existe
déjà, il suffit d'auditer un échantillon) et l'**Answer Relevancy** (code
le plus léger, infra d'embedding déjà en place) sont les deux chantiers au
meilleur rapport effort/résultat. Recall/Precision/Hit@5/MRR sont les plus
"nobles" académiquement mais demandent le plus de travail humain
(annotation) avant même d'écrire une ligne de calcul.
