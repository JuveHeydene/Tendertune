# Horloge B — la génération (conversation, agents, rédaction)

Ce chapitre décrit tout ce qui se passe quand un utilisateur pose une question
ou demande de rédiger une section du mémoire technique. C'est la partie la
plus riche du système : elle met en scène un **superviseur**, **cinq
experts**, un mécanisme d'auto-vérification appelé **CRAG**, et un
générateur final qui produit le texte de la section. Tous les faits ci-dessous
sont vérifiés dans `backend_ao/app/` au 13/09/2026.

## Un point important avant de commencer : deux chemins possibles

Le code contient **deux façons** de traiter un message, héritées de deux
générations de développement du projet :

- **Un flux historique ("V1")**, dans `app/workflow/graph.py` — un système
  plus simple, avec un routage par mots-clés et un seul appel au LLM, sans
  superviseur ni CRAG. Il reste **techniquement accessible** via une route de
  l'API (`POST /conversations/{id}/messages`, sans streaming), mais **plus
  aucun bouton ni écran de l'interface ne l'appelle** — le code JavaScript
  correspondant existe côté client mais n'est utilisé nulle part dans les
  pages réellement affichées. C'est donc un chemin vivant côté serveur mais
  orphelin côté produit : à mentionner si la question est posée en
  soutenance, plutôt qu'à cacher.
- **Le flux réellement utilisé ("V2", agentique)**, celui que ce chapitre
  détaille : `POST /conversations/{id}/messages/stream`, avec superviseur,
  experts, CRAG, agrégation et génération contrainte par schéma.

## Vue d'ensemble du trajet (flux V2, réellement utilisé)

```
Utilisateur envoie un message dans une conversation (SSE — voir §9)
   │
   ▼
0. Le message est d'abord enregistré et VALIDÉ en base (commit, pas un simple
   brouillon en mémoire) — nécessaire car les étapes suivantes vont écrire
   des traces qui référencent ce message
   │
   ▼
1. Réécriture de la question (résoudre "ça", "le dernier"...)
   │
   ▼
2. Le SUPERVISEUR décide : bavardage ? export ? clarification nécessaire ?
   question libre ? demande de rédaction ? → et découpe en sous-questions
   │
   ▼
3. Chaque sous-question est envoyée à un ou plusieurs des 5 EXPERTS
   (juridique / technique / financier / graphe / patrimoine), chacun
   effectuant sa propre recherche, avec auto-vérification (CRAG)
   │
   ▼
4. Fusion des résultats (RRF) puis reclassement (reranking)
   │
   ▼
5. Agrégation : tous les meilleurs extraits sont assemblés en un contexte
   unique, avec un plafond de taille
   │
   ▼
6a. Question libre → réponse rédigée en flux continu (vrai streaming)
6b. Demande de rédaction → génération d'une section complète, au format
    structuré, validée avant d'être affichée
   │
   ▼
7. Sauvegarde (nouvelle version), affichage, export possible en PDF/Word
```

## 0. Réception du message

**Fichier** : `app/services/chat_pipeline.py`, fonction `stream_message`.

Le message de l'utilisateur est d'abord écrit en base de données avec une
**validation immédiate** (un "commit", pas une simple mise en attente) —
c'est nécessaire car, un peu plus loin, chacun des cinq experts va écrire une
trace de sa recherche (table `retrieval_traces`) qui pointe vers ce message
précis ; si le message n'était pas encore réellement validé en base à ce
moment-là, cette écriture échouerait.

## 1. Réécriture de la question

**Fichier** : `app/workflow/nodes/rewrite.py`.

Avant toute recherche, la question est reformulée pour être **autonome** —
c'est-à-dire compréhensible sans avoir besoin de l'historique de la
conversation. Par exemple, si l'utilisateur avait déjà parlé d'un projet
précis et demande ensuite "et pour celui-ci, quel était le délai ?", cette
étape remplace "celui-ci" par le nom réel du projet, déduit de l'historique.

Le prompt exact demande explicitement de **produire une phrase de recherche,
pas une réponse à la question**, et de ne jamais casser un identifiant exact
(référence de marché, article de loi, sigle). Le texte complet du prompt est
dans [03_Interventions_du_LLM.md](03_Interventions_du_LLM.md).

**Un détail de conception qui a son importance** : cette version réécrite
("phrase de recherche neutre") est utilisée pour la recherche documentaire,
mais **pas** pour certaines décisions déterministes plus loin dans le
pipeline (choisir quelle section rédiger, ou décider si l'utilisateur demande
vraiment un export). La raison : reformuler "Rédige la présentation de
l'entreprise" en "présentation de l'entreprise" (une phrase de recherche
neutre) fait disparaître le mot "rédige", qui est justement le mot-clé dont
ces décisions ont besoin. Le texte **brut, original**, tel que tapé par
l'utilisateur, est donc conservé et réutilisé précisément pour ces
décisions-là — un choix de conception né d'un bug réel observé et corrigé.

Si cet appel au LLM échoue (service indisponible, réponse invalide), la
question brute est simplement utilisée telle quelle — jamais de blocage.

## 2. Le Superviseur

**Fichier** : `app/workflow/nodes/superviseur.py`.

C'est le "chef d'orchestre" du pipeline. Il ne répond **jamais** directement
à l'utilisateur ; son seul rôle est de classifier le message et, si
nécessaire, de le découper en sous-questions de recherche indépendantes.

Il répond au format JSON avec :
- une **intention** (`intent`) parmi : `smalltalk` (bavardage, "bonjour"),
  `export` (demande de télécharger le document), `clarification_needed` (la
  demande est trop ambiguë pour être traitée telle quelle), `hybrid_rag`
  (question libre sur le patrimoine), `run_section` (demande de rédiger une
  section du mémoire) ;
- une liste de **sous-questions**, chacune associée aux experts à consulter
  et à un niveau de complexité (`simple` ou `complexe`).

Dix règles précises encadrent cette décomposition (par exemple : ne jamais
créer plus de 4 sous-questions, ne jamais laisser un pronom non résolu dans le
texte d'une sous-question, ne jamais transformer une simple demande de
synthèse finale en une "sous-question de recherche" qui n'a rien à
rechercher). Le texte intégral du prompt, avec ses dix règles, est reproduit
dans [03_Interventions_du_LLM.md](03_Interventions_du_LLM.md).

**Un principe de conception essentiel, à mettre en avant en soutenance** : le
résultat du LLM n'est **jamais** appliqué tel quel. Une série de **garde-fous
déterministes**, écrits en code normal (pas de l'IA), corrige
systématiquement le résultat après coup — par exemple :
- si le LLM propose plus de 4 sous-questions, elles sont tronquées à 4 ;
- si le LLM répond `export` mais qu'aucun mot-clé d'export réel (« exporte »,
  « télécharge »...) n'apparaît dans le message original, l'intention est
  requalifiée en `hybrid_rag` — pour éviter un téléchargement déclenché par
  erreur sur un faux positif ;
- si le LLM répond `clarification_needed` mais a quand même produit des
  sous-questions concrètes, l'intention est requalifiée en `hybrid_rag` (la
  clarification et des sous-questions concrètes sont contradictoires) ;
- le champ `is_compound` (question composée ou non) est **toujours
  recalculé** à partir du nombre réel de sous-questions produites, jamais
  simplement recopié depuis ce que le LLM affirme.

Chacune de ces règles correspond à un comportement erroné réellement observé
en test, corrigé une fois pour toutes par du code plutôt que reposé sur la
seule fiabilité du LLM. Si l'appel au LLM échoue complètement, un repli
déterministe reprend l'ancien routage par mots-clés (le flux "V1"), avec une
seule sous-question générique confiée à l'expert `patrimoine`.

## 3. Les cinq experts

**Fichiers** : `app/rag/experts.py` (juridique, technique, financier,
patrimoine) et `app/rag/graph_expert.py` (graphe).

Chaque expert est spécialisé sur une portion du patrimoine documentaire :

| Expert | Ce qu'il interroge |
|---|---|
| **Juridique** | Chunks classés `rc` (règlement de consultation) et `ccap` (clauses administratives) |
| **Technique** | Chunks classés `cctp` (clauses techniques) |
| **Financier** | Chunks classés `dpgf`/`bpu` (documents de prix) |
| **Patrimoine** | Documents de rôle `patrimoine` ou `dao_archive` (anciens projets, références) |
| **Graphe** | La base Neo4j (relations entre entités) |

### Les quatre premiers experts (recherche hybride)

Pour chaque sous-question, un expert interroge **en parallèle** :
- **Qdrant** (recherche par sens/similarité vectorielle) ;
- **Postgres**, via une recherche plein texte classique ("full-text search",
  qui cherche les mots exacts et leurs variantes).

Les deux listes de résultats sont ensuite **fusionnées** (voir §4) puis
reclassées (voir §4 également).

Deux modes de fonctionnement selon la complexité de la sous-question (décidée
par le superviseur) :
- **Simple** : une seule passe de recherche, pas de vérification
  supplémentaire — on fait confiance directement au meilleur résultat trouvé.
- **Complexe** : une boucle avec jusqu'à **3 tentatives**, chaque tentative
  étant évaluée par le mécanisme CRAG (§5) avant de décider si le résultat
  est suffisant, s'il faut élargir la recherche, ou la reformuler.

Chaque expert ouvre sa propre connexion à la base de données (plutôt que d'en
partager une entre tous les experts qui tournent en même temps), car
plusieurs experts travaillent réellement **en parallèle** (via une technique
de programmation asynchrone) et partager une même connexion entre plusieurs
tâches simultanées ne serait pas fiable.

### L'expert graphe

Cet expert suit une logique différente, propre aux bases de graphe :
1. Il commence par demander au LLM d'**extraire les entités nommées** dans la
   sous-question (par exemple, un nom d'entreprise ou de projet).
2. Il **rapproche** ces entités de celles déjà connues dans Neo4j (la même
   cascade de rapprochement flou que celle utilisée à l'ingestion, voir
   [01_Horloge_A_Ingestion.md](01_Horloge_A_Ingestion.md) §6).
3. Il interroge Neo4j avec des **requêtes fixes et prédéfinies** (jamais
   générées librement par le LLM) : une requête "un saut" si une seule entité
   est identifiée, une requête "deux sauts bornés" pour les questions de
   conformité, ou une requête "chemin entre deux entités" si deux entités
   précises sont nommées dans la question.
4. **Chaque relation trouvée dans le graphe est systématiquement reliée au
   chunk de texte qui l'a produite** — le principe appliqué ici est qu'un
   fait de graphe ne se cite jamais sans le passage exact du document qui le
   prouve, pour rester vérifiable.

Cet expert ne fait qu'une seule tentative (pas de boucle CRAG) : soit il
trouve une réponse via le graphe, soit il s'abstient (aucune entité extraite,
aucune entité rapprochée avec assez de confiance, ou aucune relation trouvée).

## 4. Fusion (RRF) et reclassement (reranking)

**Fichiers** : `app/rag/fusion.py`, `app/rag/rerank.py`.

**⚠️ Piège de vocabulaire à ne pas confondre en soutenance** : le sigle
**RRF** (*Reciprocal Rank Fusion*, fusion par rang réciproque) n'a **aucun
rapport** avec la métrique d'évaluation **MRR** (*Mean Reciprocal Rank*)
qu'on trouve dans la littérature sur l'évaluation des systèmes de recherche.
RRF est une **technique de fusion de résultats** utilisée en production dans
ce système ; MRR est une métrique d'évaluation qui n'est, à ce jour, pas
calculée dans ce système (voir le document séparé sur les métriques
d'évaluation). Les deux termes partagent juste la racine "rang réciproque",
rien de plus.

**RRF, comment ça marche concrètement** : la recherche vectorielle (Qdrant) et
la recherche plein texte (Postgres) donnent chacune un **classement** de
résultats, mais avec des échelles de score totalement différentes et non
comparables entre elles (un score de similarité cosinus n'a rien à voir avec
un score de pertinence textuelle). Plutôt que de comparer ces scores
directement, RRF ne regarde que le **rang** de chaque résultat dans chaque
liste (1er, 2e, 3e...) et calcule un score combiné selon la formule
`1 / (60 + rang)` pour chaque liste où le document apparaît, puis additionne
ces scores — un document bien classé dans les deux listes remonte
naturellement en tête du classement fusionné.

**Le reclassement (reranking), un point de transparence important** : la
cible technique documentée dans la configuration est un modèle spécialisé de
reclassement appelé `BAAI/bge-reranker-v2-m3` — un "cross-encoder", une IA
capable de comparer précisément une question et un extrait pour juger de leur
pertinence. **Ce modèle n'est aujourd'hui pas réellement branché** dans le
pipeline, en raison d'un conflit technique entre deux librairies (PaddleOCR et
la librairie utilisée pour ce type de modèle ont besoin de deux versions
incompatibles d'un composant NVIDIA appelé cuDNN sur la même machine). Le
reclassement **réellement actif** aujourd'hui est plus simple : un score de
**recouvrement lexical** (combien de mots significatifs de la question se
retrouvent dans l'extrait, hors mots vides comme "le", "de", "un") est
combiné à parts égales (50/50) avec le score RRF déjà calculé. C'est un
compromis fonctionnel, pas la solution cible idéale, et c'est un point à
assumer clairement plutôt qu'à présenter comme déjà résolu.

## 5. CRAG — l'auto-vérification de la pertinence

**Fichier** : `app/rag/grading.py`.

CRAG (*Corrective Retrieval-Augmented Generation*) est le mécanisme qui évite
qu'une recherche ratée ne produise silencieusement une réponse bancale. Après
chaque tentative de recherche complexe, le meilleur score obtenu est comparé
à deux seuils fixes :

- Si le meilleur score est **au moins 0,7** → le résultat est jugé
  **correct**, on s'arrête là.
- Si le meilleur score est **sous 0,3** → le résultat est jugé **incorrect**
  directement, sans appel supplémentaire au LLM.
- **Entre les deux** (la zone grise, ni clairement bon ni clairement
  mauvais) → un appel au LLM est fait, agissant comme un "juge", qui répond
  simplement `correct`, `ambigu` ou `incorrect` en évaluant si le contexte
  fourni permet réellement de répondre à la question posée. (Prompt complet
  dans [03_Interventions_du_LLM.md](03_Interventions_du_LLM.md).)

Ce qui se passe ensuite dépend du verdict :
- **Correct** → on garde ce résultat, terminé pour cette sous-question.
- **Ambigu** → la recherche est **élargie** (on retire d'abord la contrainte
  de type de section, puis celle de rôle de document) — mais la question
  elle-même n'est **pas** reformulée : l'idée est que le bon contenu existe
  probablement, juste hors du périmètre initialement ciblé.
- **Incorrect** → la question est **reformulée** différemment par le LLM et
  une nouvelle recherche est relancée avec cette formulation alternative.
- Après **3 tentatives** sans obtenir un verdict "correct", l'expert
  **s'abstient** explicitement pour cette sous-question — plutôt que de
  forcer une réponse avec un contexte de mauvaise qualité, le système
  documente honnêtement qu'aucune information fiable n'a été trouvée. Cette
  abstention n'arrête pas tout le pipeline : seule cette sous-question
  particulière reste sans réponse, les autres continuent normalement.

Chaque tentative, quel que soit son verdict, est enregistrée dans la table
`retrieval_traces` (sous-question, expert, tentative, requête utilisée,
filtres, verdict, méthode de verdict, résultats retournés, abstention ou
non) — une trace complète du raisonnement de recherche, utile pour le débogage
et potentiellement pour de futures évaluations de qualité.

## 6. Agrégation du contexte

**Fichier** : `app/workflow/nodes/aggregate.py`.

Une fois toutes les sous-questions traitées par leurs experts respectifs, les
meilleurs extraits trouvés sont assemblés en un seul contexte texte, numéroté
`[1]`, `[2]`, `[3]`... — c'est ce contexte numéroté qui sera montré au LLM
pour la génération finale.

Deux plafonds protègent contre un contexte trop volumineux (qui, sans
limite, dépasserait silencieusement la capacité du modèle et tronquerait des
instructions importantes en fin de message) :
- Chaque **chunk individuel** est limité à 12 000 caractères.
- Le **total cumulé** de tous les extraits est plafonné à **20 000
  caractères** — dès que ce plafond est atteint, les extraits suivants ne
  sont plus ajoutés ni au texte du contexte, ni à la liste des identifiants
  citables : un extrait que le LLM n'a jamais vu ne doit jamais pouvoir être
  cité comme source valide.

## 7. Génération d'une réponse à une question libre (hybrid_rag)

**Fichier** : `app/services/chat_pipeline.py`.

Quand l'intention est une simple question (pas une demande de rédaction), la
réponse est **écrite en flux continu**, token par token, directement affichée
à mesure qu'elle est produite par le modèle — c'est le "vrai" streaming, sans
contrainte de format à valider avant affichage. Le prompt exact utilisé
(reproduit intégralement dans
[03_Interventions_du_LLM.md](03_Interventions_du_LLM.md)) demande
explicitement au modèle de répondre en Markdown, de ne rien inventer (montant,
SIRET, date), d'utiliser uniquement les extraits numérotés fournis, de citer
`[1]`, `[2]`... quand il s'appuie dessus, et de dire explicitement si les
extraits ne suffisent pas plutôt que d'improviser.

## 8. Génération d'une section du mémoire (run_section)

**Fichier** : `app/workflow/nodes/generate_section.py`.

C'est la partie la plus rigoureuse du système : contrairement à une réponse
de chat, une section du mémoire doit être **structurée** (des paragraphes,
des listes, des tableaux, des sous-titres identifiés comme tels) et **fiable
au format**, pas juste au contenu.

### Le format de sortie exigé

Le modèle doit produire un objet avec :
- `blocs` : une liste de blocs typés (`paragraphe`, `liste`, `tableau_md`,
  `sous_titre`, `image`), chacun avec son texte ;
- `citations` : la liste des extraits numérotés réellement utilisés ;
- `exigences_couvertes` : les exigences du dossier auxquelles cette section
  répond ;
- `abstentions` : les points que la recherche n'a pas permis de couvrir, à
  signaler honnêtement plutôt que de les improviser.

### Une garantie technique clé : le schéma JSON contraint

C'est ici, et **uniquement ici** dans le système actuel, que le format de
sortie est imposé au LLM par une **contrainte de décodage** : le modèle
génère son texte "mot par mot" en étant physiquement empêché de produire une
structure qui ne correspond pas exactement au format attendu. C'est une
garantie beaucoup plus forte que de simplement demander poliment "réponds en
JSON" — cette dernière méthode, utilisée ailleurs dans le système (voir
[01_Horloge_A_Ingestion.md](01_Horloge_A_Ingestion.md)), n'empêche pas un
petit modèle de dériver vers une structure sans rapport avec ce qui est
demandé. Cette contrainte plus stricte a été ajoutée précisément après avoir
observé, en test, que le modèle produisait parfois des champs entièrement
inventés au lieu du format attendu — un problème directement résolu par
cette technique.

### Deux modes de fidélité au contexte

- **Mode strict** (par défaut) : le modèle doit utiliser *uniquement* les
  extraits numérotés fournis, sans rien inventer.
- **Mode "proposition"** : activé automatiquement si le message de
  l'utilisateur contient des mots comme "propose", "suggère", "imagine" — car
  toute information ne se trouve pas forcément déjà dans le patrimoine
  documentaire de l'entreprise, et il faut parfois pouvoir structurer une
  proposition plausible plutôt que de bloquer totalement la rédaction. Même
  dans ce mode, il reste **interdit d'inventer un fait vérifiable** (un
  chiffre précis, une certification, une date, un nom de projet réel) : ces
  éléments doivent être remplacés par un marqueur explicite du type
  `[À COMPLÉTER : ...]`. Une note est aussi automatiquement ajoutée pour
  signaler qu'il s'agit d'une proposition à valider par un humain — et un
  bandeau d'avertissement visuel est ajouté par le code (pas laissé à la
  discrétion du LLM) chaque fois qu'une section est marquée comme
  "proposition".

### Un détail technique subtil : comment sont gérées les citations

Le LLM ne voit **jamais** l'identifiant réel d'un extrait (un identifiant
technique long et opaque) — il ne voit que le **numéro affiché**, `[1]`,
`[2]`... Il lui est donc explicitement demandé de citer ce numéro, pas un
autre identifiant qu'il ne connaît de toute façon pas. Une fois la réponse du
LLM reçue, le code **traduit** chaque numéro cité vers le véritable
identifiant de l'extrait correspondant, avant d'enregistrer quoi que ce soit
— ce qui garantit que chaque citation affichée à l'utilisateur pointe
réellement vers un passage retrouvable.

### Validation et auto-correction

Après traduction des citations, une série de vérifications déterministes
(pas de l'IA, du code classique) contrôle le résultat : une citation
inexistante, un sous-titre trop profond, un titre écrit en dur dans le texte
au lieu d'être un vrai bloc "sous-titre", une image sans identifiant valide.
Si un problème est détecté, ou si le format JSON lui-même est invalide, le
système **retente** — jusqu'à 2 tentatives au total — en renvoyant au LLM,
dans le nouveau prompt, le détail précis de l'erreur à corriger. Si les deux
tentatives échouent malgré tout, un contenu de repli minimal est produit
(« Génération non aboutie — voir logs ») plutôt que de faire planter la
conversation.

## 9. Choix de la section à rédiger

**Fichier** : `app/workflow/sections.py`.

Le plan type par défaut du mémoire comporte cinq sections : **présentation de
l'entreprise**, **moyens humains**, **références** (projets similaires déjà
réalisés), **méthodologie**, **planning**. Quand un dossier a un plan
extrait spécifiquement de son règlement de consultation (voir
[01_Horloge_A_Ingestion.md](01_Horloge_A_Ingestion.md) §7), ce plan
personnalisé est utilisé à la place.

La détection de la section demandée par l'utilisateur ("génère la section sur
nos moyens humains") se fait par une recherche de mots-clés simple et
déterministe sur le texte **brut** de la demande (voir §1 pour la raison de
ce choix) : des mots comme "moyen", "personnel", "équipe", "effectif"
orientent vers la section moyens humains ; "référence", "chantier similaire"
vers les références ; et ainsi de suite. Une demande contenant "tout le
mémoire" ou "toutes les sections" déclenche l'enchaînement de toutes les
sections du plan, l'une après l'autre.

## 10. Sortie vers l'utilisateur

La communication entre le serveur et le navigateur se fait par un mécanisme
appelé **SSE** (*Server-Sent Events*, événements envoyés par le serveur) : le
navigateur reste connecté et reçoit une série de petits événements au fur et
à mesure (utilisateur, intention détectée, jeton de texte, début/fin de
section, document exporté, erreur, terminé).

**Nuance importante** : pour une question libre, le texte est réellement
généré et affiché **token par token** en direct (le vrai streaming décrit en
§7). Pour une **section de mémoire**, en revanche, le format structuré doit
être **entièrement généré et validé** avant de pouvoir être affiché — il est
donc techniquement impossible de l'afficher au fur et à mesure de sa
rédaction réelle. Ce que l'utilisateur voit défiler à l'écran dans ce cas est
un découpage artificiel du texte final déjà complet, envoyé par petits
morceaux pour donner une sensation de continuité — pas un vrai flux en
direct.

## 11. Sauvegarde et versions

Chaque génération de section crée une **nouvelle version** en base — jamais de
modification en place d'une version existante. Cela permet de conserver
l'historique complet de toutes les rédactions successives d'une même section,
et de revenir en arrière si nécessaire.

## 12. Export

Quatre formats sont proposés :
- **DOCX** (Word), produit avec la librairie **python-docx**.
- **PDF**, produit avec **WeasyPrint** — le contenu HTML est d'abord généré à
  partir d'un modèle de mise en page (Jinja2), puis converti en PDF. C'est le
  **seul** format qui exploite réellement la structure fine des blocs
  générés (vraies listes, vrais tableaux HTML) plutôt que du texte simplement
  aplati.
- **Markdown** et **texte brut**, produits par simple assemblage de texte,
  sans librairie externe.

## 13. Le modèle LLM, un seul pour tout

Un unique modèle, **`granite3.3:2b`**, est utilisé pour absolument **toutes**
les tâches de génération et de décision décrites dans ce chapitre : la
réécriture de question, le superviseur, la reformulation en cas d'échec de
recherche, le juge CRAG, l'extraction d'entités pour l'expert graphe, la
génération de section, et la réponse conversationnelle libre. Il n'existe
aujourd'hui aucune configuration permettant d'utiliser un modèle différent
selon la tâche — un choix de simplicité opérationnelle qui a pour
contrepartie directe le besoin des garde-fous déterministes décrits tout au
long de ce chapitre : un petit modèle unique demande plus de filets de
sécurité en code autour de lui.

## Ce qu'il faut retenir pour la soutenance

- Le superviseur ne décide jamais seul : chaque décision qu'il prend est
  systématiquement vérifiée et corrigée si besoin par du code déterministe.
- CRAG n'est pas une case cochée en façade : il modifie réellement le
  comportement (élargir vs reformuler) selon le diagnostic, avec une
  traçabilité complète de chaque tentative.
- Le reranking par cross-encoder annoncé dans la configuration n'est pas
  branché aujourd'hui, remplacé par une heuristique lexicale plus simple —
  une limite connue, assumée, avec une cause technique précise (conflit de
  librairies GPU).
- Seule la génération de section bénéficie aujourd'hui d'un schéma JSON
  réellement contraint ; les autres appels LLM du système (Horloge A comme
  Horloge B) demandent un JSON sans cette garantie renforcée.
