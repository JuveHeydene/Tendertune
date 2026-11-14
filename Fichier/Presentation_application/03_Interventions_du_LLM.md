# Toutes les interventions du LLM — inventaire complet

Ce chapitre liste **exhaustivement** chaque endroit du système où l'IA
générative (le LLM, modèle `granite3.3:2b` exécuté par Ollama, sauf mention
contraire) est appelée. Pour chacune : où elle se situe, ce qu'elle fait,
le prompt exact qui lui est donné, le format de sortie exigé, à qui appartient
et sert le résultat, et comment un échec est géré. C'est le chapitre à
consulter si une question précise porte sur "que dit-on exactement au LLM à
tel endroit ?".

**Vocabulaire technique récurrent dans ce chapitre** :
- `timeout` : le temps maximum accordé à l'appel avant de considérer qu'il a
  échoué.
- `num_ctx` : la taille de la "fenêtre de contexte" allouée au modèle pour cet
  appel, exprimée en unités de texte appelées "tokens" — sans cette valeur
  réglée explicitement, un prompt long risquerait d'être tronqué en silence.
- `format="json"` : on demande poliment au modèle de répondre en JSON, sans
  garantie stricte de structure.
- `schema=...` : un **schéma JSON contraint** est fourni, qui force
  physiquement le modèle à produire exactement la structure attendue (voir
  [02_Horloge_B_Generation.md](02_Horloge_B_Generation.md) §8 pour
  l'explication complète de cette technique).

---

## Vue d'ensemble — tableau récapitulatif

| # | Intervention | Horloge | Fichier | Format | num_ctx | Timeout |
|---|---|---|---|---|---|---|
| 1 | Classification de section | A | `ingest/classify_section.py` | `"json"` | (défaut) | 60s |
| 2 | Extraction d'outline | A | `workflow/extract_structure.py` | `"json"` | 2048 | 90s |
| 3 | Extraction d'exigences | A | `workflow/extract_structure.py` | `"json"` | 4096 | 150s |
| 4 | Checklist administrative | A | `workflow/extract_structure.py` | `"json"` | 2048 | 90s |
| 5 | Classification exigences↔sections | A | `workflow/extract_structure.py` | `"json"` | 4096 | 150s |
| 6 | Extraction du graphe (entités/relations) | A | `graph/extract.py` | `"json"` | 2048 | 180s |
| 7 | Réécriture de la question | B | `workflow/nodes/rewrite.py` | `"json"` | 4096 | 60s |
| 8 | Superviseur (routage + décomposition) | B | `workflow/nodes/superviseur.py` | `"json"` | 4096 | 90s |
| 9 | Reformulation d'expert (échec de recherche) | B | `rag/experts.py` | `"json"` | 2048 | 45s |
| 10 | Extraction d'entités (expert graphe) | B | `rag/graph_expert.py` | `"json"` | 2048 | (non précisé/défaut) |
| 11 | Juge CRAG (grading) | B | `rag/grading.py` | `"json"` | 4096 | 60s |
| 12 | Génération de section du mémoire | B | `workflow/nodes/generate_section.py` | **schéma contraint** | 8192 | 180s |
| 13 | Réponse conversationnelle libre | B | `services/chat_pipeline.py` | texte libre (Markdown) | 8192 | (défaut) |

**Seule l'intervention n°12 utilise un schéma JSON réellement contraint** —
toutes les autres demandent un JSON "poliment", sans garantie stricte de
structure.

---

## 1. Classification de section (Horloge A)

**Fichier** : `app/ingest/classify_section.py`.
**Appelée pour** : deviner à quelle famille de document (RC, CCTP, DPGF...)
appartient un chunk parent, uniquement quand une simple recherche de
mots-clés n'a rien donné.
**Consommateur du résultat** : la colonne `section_type` du chunk en base —
réutilisée ensuite comme filtre doux par les experts de recherche (Horloge B).

Prompt exact :
```
Tu classes un extrait de dossier d'appel d'offres BTP dans UNE catégorie.
Catégories autorisées, choisis UNIQUEMENT parmi : rc, ccap, cctp, dpgf, bpu, memoire, reference, autre.
Réponds UNIQUEMENT en JSON : {"section_type": "..."}
Texte : {texte, limité aux 2000 premiers caractères}
```

Réponse attendue : `{"section_type": "cctp"}` (une des 8 valeurs listées).
En cas d'échec (réseau, JSON invalide) : la fonction retourne "aucun résultat"
sans jamais lever d'erreur — le chunk reste simplement non classé.

---

## 2. Extraction d'outline (Horloge A)

**Fichier** : `app/workflow/extract_structure.py`.
**Appelée pour** : extraire la liste ordonnée des titres de section demandés
par le règlement de consultation, quand celui-ci contient des indices qu'il
décrit une structure de réponse attendue.
**Consommateur du résultat** : la table `outline_items` — devient le plan
personnalisé du mémoire pour ce dossier, remplaçant le plan type par défaut.

Prompt exact :
```
Le texte suivant est un extrait de règlement de consultation d'appel d'offres BTP. Il décrit la structure attendue du mémoire technique. Extrais la liste ORDONNÉE des titres demandés.
Réponds UNIQUEMENT en JSON : {"titres": ["...", "..."]}
Texte : {texte, limité à 4000 caractères}
```

En cas d'échec ou de liste vide : repli automatique sur le plan type par
défaut (présentation, moyens humains, références, méthodologie, planning).

---

## 3. Extraction d'exigences (Horloge A)

**Fichier** : `app/workflow/extract_structure.py`.
**Appelée pour** : extraire chaque obligation précise du dossier (technique,
administrative, financière, de délai...).
**Consommateur du résultat** : la table `exigences` — alimente la checklist
de conformité affichée à l'utilisateur, et la génération de section (via la
liaison exigences↔sections, intervention n°5).

Le texte est envoyé par lots (jusqu'à 14 000 caractères cumulés, plusieurs
extraits pouvant être regroupés dans un même appel), chaque extrait étant
introduit par un séparateur `--- Extrait page N ---`.

Prompt exact :
```
Tu extraies les exigences d'extraits d'un dossier d'appel d'offres BTP (DAO). Le texte ci-dessous peut contenir PLUSIEURS extraits séparés par "--- Extrait page N ---" : traite-les tous et cumule toutes les exigences trouvées dans une seule liste.
Catégories de type autorisées uniquement : eliminatoire, technique, administrative, financiere, delai, reference.
Réponds UNIQUEMENT en JSON :
{"exigences": [{"libelle": "...", "type": "...", "obligatoire": true, "reference_dao": "..."}]}
Pas d'exigence si rien de clair. Texte : {texte, limité à 15000 caractères au total}
```

Les doublons entre lots successifs sont ensuite fusionnés par la même
cascade de rapprochement flou (exact → Levenshtein → Jaccard → embedding) que
celle utilisée pour les entités du graphe.

---

## 4. Checklist administrative (Horloge A)

**Fichier** : `app/workflow/extract_structure.py`.
**Appelée pour** : extraire la liste des pièces administratives demandées
(KBIS, attestations, formulaires...), uniquement si le règlement de
consultation contient des indices d'une liste explicite.
**Consommateur du résultat** : la table `dossier_pieces` — la checklist
administrative affichée à l'utilisateur.

Prompt exact :
```
Le texte suivant énumère les pièces administratives demandées dans un appel d'offres BTP. Extrais la liste des pièces.
Réponds UNIQUEMENT en JSON : {"pieces": ["...", "..."]}
Texte : {texte, limité à 4000 caractères}
```

Si aucun indice n'est trouvé, ou en cas d'échec : une liste standard par
défaut (KBIS, attestation décennale, régularité fiscale/URSSAF, DC1, DC2) est
utilisée à la place.

---

## 5. Classification exigences ↔ sections (Horloge A)

**Fichier** : `app/workflow/extract_structure.py`.
**Appelée pour** : décider quelles sections du plan doivent explicitement
répondre à chaque exigence identifiée.
**Consommateur du résultat** : la table `exigence_sections`, lue ensuite par
la génération de section (intervention n°12) pour savoir précisément quelles
exigences traiter dans chaque partie du mémoire.

Traitée par lots de 25 exigences à la fois.

Prompt exact :
```
Tu associes des exigences d'un dossier d'appel d'offres BTP aux sections du mémoire technique qui doivent y répondre explicitement. Une exigence peut concerner PLUSIEURS sections, ou aucune si elle ne correspond à rien de rédactionnel (ex. une pièce administrative pure comme un KBIS n'a souvent aucune section dédiée) — dans ce cas omets-la simplement, ne force pas une association.
Sections disponibles (index. titre [archétype]) : {liste des sections}
Exigences à classer (index. libellé [type]) : {liste des exigences}
Réponds UNIQUEMENT en JSON :
{"associations": [{"exigence_index": 1, "section_indices": [2, 5]}]}
```

Point de robustesse : l'insertion en base utilise une technique
(`ON CONFLICT DO NOTHING`) qui **ne modifie jamais** une association déjà
établie manuellement par un humain — une relance de cette classification ne
peut qu'ajouter de nouvelles associations, jamais écraser une décision
humaine existante.

---

## 6. Extraction du graphe — entités et relations (Horloge A)

**Fichier** : `app/graph/extract.py`.
**Appelée pour** : repérer les entités nommées (entreprises, projets,
certifications, personnes, exigences, lots, sites) et leurs relations dans
chaque chunk parent d'un document.
**Consommateur du résultat** : le code (jamais le LLM lui-même) construit
ensuite les requêtes `MERGE` vers Neo4j à partir de ce résultat — les entités
et relations extraites deviennent des nœuds et arêtes du graphe de
connaissances.

Le texte du chunk est limité à 3500 caractères.

Prompt exact :
```
Tu extraies des entités BTP depuis le texte.
Types d'entités autorisés uniquement : ENTREPRISE, PROJET, CLIENT, CERTIFICATION, PERSONNE, EXIGENCE, LOT, SITE
Types de relations autorisés uniquement : A_TRAVAILLE_SUR, PORTE, CONCERNE, SITUE_A, SATISFAITE_PAR, CONTIENT
Pour les relations, réutilise autant que possible les noms EXACTS des entités listées.
Réponds UNIQUEMENT en JSON :
{"entities":[{"type":"PROJET","name":"..."}],"relations":[{"type":"CONCERNE","from":"...","to":"..."}]}
Pas d'entité si rien de clair. Texte : {texte}
```

Toute relation dont l'entité de départ ou d'arrivée ne trouve **aucune**
correspondance suffisamment fiable (voir la cascade de rapprochement décrite
au chapitre Horloge A) est abandonnée — jamais de création d'entité fantôme
pour "sauver" une relation orpheline.

---

## 7. Réécriture de la question (Horloge B)

**Fichier** : `app/workflow/nodes/rewrite.py`.
**Appelée pour** : rendre la question de l'utilisateur autonome et
compréhensible sans l'historique de conversation, avant toute recherche
documentaire.
**Consommateur du résultat** : les experts de recherche (la version réécrite
sert de base à leurs requêtes) — mais **pas** les décisions déterministes en
aval (choix de section, détection d'export), qui réutilisent le texte brut
original (voir [02_Horloge_B_Generation.md](02_Horloge_B_Generation.md) §1).

Prompt exact :
```
Tu réécris la question d'un utilisateur pour la rendre autonome,
sans te baser sur l'historique de conversation pour la comprendre.

Règles STRICTES :
- Remplace "ça", "le dernier", "celui-ci"... par ce qu'ils désignent, déduit
  de l'historique.
- Ne CASSE JAMAIS un identifiant exact (référence de marché, article, sigle).
- Produis une PHRASE DE RECHERCHE, pas une réponse à la question.
- Si la question est déjà autonome, renvoie-la telle quelle.

Réponds UNIQUEMENT en JSON : {"query_clean": "..."}

Historique :
{history}

Question brute : {question}
```

En cas d'échec ou de question vide : le texte brut original est utilisé sans
modification.

---

## 8. Le Superviseur (Horloge B)

**Fichier** : `app/workflow/nodes/superviseur.py`.
**Appelée pour** : classifier l'intention du message et le décomposer en
sous-questions de recherche indépendantes, chacune confiée à un ou plusieurs
des 5 experts.
**Consommateur du résultat** : tout le reste du pipeline Horloge B — c'est la
décision la plus structurante de tout le trajet d'un message.

Prompt exact :
```
Tu es le routeur d'un système de recherche documentaire pour des
dossiers d'appels d'offres BTP. Tu ne réponds JAMAIS à la question de
l'utilisateur. Ton seul travail : classifier son message et, si nécessaire,
le découper en sous-questions de recherche.

Tu dois répondre EXCLUSIVEMENT en JSON, selon ce schéma strict :
{
  "intent": "smalltalk" | "export" | "clarification_needed" | "hybrid_rag" | "run_section",
  "is_compound": boolean,
  "sous_questions": [
    {"texte": string, "experts": [string], "complexite": "simple" | "complexe"}
  ],
  "message_clarification": string ou null
}

Experts disponibles (jamais un nom hors de cette liste) :
  - "juridique"  : clauses, pénalités, délais, RC/CCAP
  - "technique"  : spécifications, méthodologie, CCTP
  - "financier"  : chiffres exacts, DPGF/BPU
  - "graphe"     : relations entre entités (qui a fait quoi, quelle certif
                   couvre quelle exigence)
  - "patrimoine" : références, projets passés, CV, certifications

Règles STRICTES (chacune ferme un cas d'erreur précis) :
R1. Décompose UNIQUEMENT si les parties de la question demandent des
    recherches INDÉPENDANTES (le résultat de l'une n'est pas nécessaire
    pour formuler l'autre). Sinon is_compound=false, 1 seule sous-question.
R2. Chaque texte de sous-question doit être COMPLET et AUTONOME : aucun
    pronom ni référence implicite sans le nommer explicitement.
R3. Maximum 4 sous-questions. Si plus seraient nécessaires : regroupe,
    ou réponds intent="clarification_needed" avec message_clarification.
R4. is_compound=false → EXACTEMENT 1 sous-question. is_compound=true →
    ENTRE 2 ET 4 sous-questions. Jamais 0, jamais 1 avec is_compound=true.
R5. Une comparaison/calcul/synthèse finale demandée N'EST PAS une
    sous-question de recherche — ne crée jamais de sous-question sans
    recherche factuelle propre.
R6. Si intent ∈ {"smalltalk","export"} : sous_questions=[] et
    message_clarification=null, TOUJOURS.
R7. Si intent="clarification_needed" : sous_questions=[] et
    message_clarification OBLIGATOIRE (jamais null).
R8. "complexite" s'évalue PAR sous-question : une question factuelle simple
    = "simple" (1 seule passe) ; plusieurs critères, entité rare, ou
    run_section = "complexe" (boucle de correction complète).
R9. "experts" PEUT être vide ([]) — UNIQUEMENT si le message de l'utilisateur
    (ou l'historique immédiat) contient DÉJÀ le contenu factuel spécifique
    nécessaire à CETTE sous-question précise. Dans le doute, NE PAS mettre
    experts=[] : une recherche redondante coûte peu, une génération privée
    d'information disponible coûte cher en confiance.
R10. Le champ "texte" de chaque sous-question DOIT être écrit en FRANÇAIS,
    même si tu raisonnes en anglais — ne traduis JAMAIS la question.

Historique :
{history}

Message de l'utilisateur : {question}
```

En cas d'échec ou de réponse invalide : repli sur le routage par mots-clés
historique (flux V1), avec une seule sous-question générique confiée à
l'expert `patrimoine`. Après un succès, une série de garde-fous déterministes
corrige encore le résultat (détaillés dans
[02_Horloge_B_Generation.md](02_Horloge_B_Generation.md) §2) — le prompt,
même bien conçu, n'est jamais considéré comme suffisant à lui seul.

---

## 9. Reformulation d'un expert après un échec de recherche (Horloge B)

**Fichier** : `app/rag/experts.py`.
**Appelée pour** : reformuler différemment une sous-question, uniquement
quand le mécanisme CRAG (intervention n°11) a jugé le résultat précédent
franchement "incorrect".
**Consommateur du résultat** : une nouvelle tentative de recherche hybride
(Qdrant + Postgres) avec cette formulation alternative.

Cette intervention est déclenchée dans la boucle de recherche complexe
(jusqu'à 3 tentatives).

Prompt exact :
```
Reformule cette requête de recherche documentaire
avec un angle différent (synonymes, reformulation), pour retrouver des
passages qu'une première recherche aurait pu manquer (RAG-08 §4, multi-query).
Réponds UNIQUEMENT en JSON : {"query": "..."}

Requête initiale : {query}
```

Sa fonction est de produire une variante de la requête initiale (synonymes,
angle différent), suffisamment différente pour explorer une autre façon de
nommer ou formuler le besoin, sans changer le scope de recherche
(contrairement au cas "ambigu", où c'est le scope de filtres qui est élargi,
pas la formulation de la requête elle-même).

---

## 10. Extraction d'entités pour l'expert graphe (Horloge B)

**Fichier** : `app/rag/graph_expert.py`.
**Appelée pour** : repérer, dans la sous-question posée, les entités
nommées à rechercher dans le graphe de connaissances Neo4j.
**Consommateur du résultat** : la cascade de rapprochement flou (partagée
avec l'ingestion), puis les requêtes Cypher fixes (un saut, deux sauts
bornés, ou chemin entre deux entités).

La structure de réponse attendue est limitée aux mêmes types d'entités que
ceux utilisés à l'ingestion (`ENTREPRISE`, `PROJET`, `CLIENT`,
`CERTIFICATION`, `PERSONNE`, `EXIGENCE`, `LOT`, `SITE`), afin que les
entités trouvées côté lecture puissent effectivement se rapprocher de celles
créées côté écriture.

---

## 11. Le juge CRAG (Horloge B)

**Fichier** : `app/rag/grading.py`.
**Appelée pour** : trancher, dans la zone grise entre un score clairement bon
et un score clairement mauvais, si le contexte trouvé permet réellement de
répondre à la question.
**Consommateur du résultat** : la boucle de recherche complexe (décide de
s'arrêter, d'élargir le scope, ou de reformuler la requête — voir
[02_Horloge_B_Generation.md](02_Horloge_B_Generation.md) §5).

Le contexte fourni au juge est limité à 5 chunks de 1500 caractères chacun.

Prompt exact :
```
Tu évalues si un contexte documentaire permet de répondre à
une question. Réponds UNIQUEMENT en JSON : {"grade": "correct"|"ambigu"|"incorrect"}

- "correct" : le contexte permet de répondre précisément à la question.
- "ambigu" : le contexte est lié au sujet mais insuffisant ou incertain.
- "incorrect" : le contexte ne répond pas à la question, même s'il semble proche.

Question : {query}

Contexte :
{context}
```

En cas d'échec de l'appel : repli automatique sur le verdict `ambigu` (le
choix le plus prudent — ni accepter aveuglément, ni rejeter à tort une
recherche peut-être bonne).

---

## 12. Génération de la section du mémoire (Horloge B)

**Fichier** : `app/workflow/nodes/generate_section.py`.
**Appelée pour** : rédiger le contenu structuré d'une section du mémoire
technique (présentation, moyens humains, méthodologie...), à partir du
contexte agrégé par les experts.
**Consommateur du résultat** : la table `generations` (nouvelle version de la
section), puis l'export DOCX/PDF/MD/TXT.

**C'est la seule intervention du système qui utilise un schéma JSON
réellement contraint** — le format n'est pas seulement demandé, il est
physiquement forcé au niveau du décodage du modèle. Le schéma utilisé est
généré directement depuis la définition Python du format attendu
(`SectionGeneree.model_json_schema()`), garantissant que le code et le format
imposé au modèle ne peuvent jamais diverger.

Prompt exact (les portions entre accolades sont remplies dynamiquement selon
la section et le dossier) :
```
Tu es rédacteur d'un mémoire technique d'appel d'offres BTP (français).

Section à rédiger : « {titre} » (clé : {section_key}).
Le TITRE est FIXE, tu ne l'écris PAS toi-même dans les blocs (pas de H1/H2).
Consigne spécifique à ce type de section : {guidance selon l'archétype de la section}

Règles STRICTES :
{règle de fidélité au contexte — mode strict ou mode proposition, voir 02_Horloge_B_Generation.md}
- Le contexte patrimoine fourni est un EXEMPLE de travaux/méthodes déjà
  réalisés par l'entreprise, PAS un texte à recopier : ce projet est
  NOUVEAU, rédige un texte adapté à SES spécificités qui s'inspire du
  patrimoine sans le paraphraser mot pour mot.
- Un bloc type="sous_titre" ne dépasse jamais heading_level=3.
- Un bloc type="image" a pour document_id le NUMÉRO entre crochets de
  l'extrait du contexte (ex: 3) — jamais un autre identifiant, tu ne connais
  pas l'identifiant réel de l'extrait, seulement son numéro.
- Dans "citations" et pour "document_id" d'une image : utilise UNIQUEMENT le
  NUMÉRO entre crochets affiché devant chaque extrait du contexte (1, 2,
  3...), jamais un autre texte — tu n'as accès à aucun autre identifiant.
{consigne complémentaire éventuelle}
{rappel des exigences précises à couvrir pour cette section, si connues}
{contenu déjà existant de la section, si une régénération est demandée}
Réponds UNIQUEMENT en JSON, selon ce schéma :
{
  "section_key": "{section_key}",
  "titre": "{titre}",
  "blocs": [{"type": "paragraphe|liste|tableau_md|sous_titre|image", "heading_level": null, "document_id": null, "texte": "..."}],
  "citations": ["1", "2"],
  "exigences_couvertes": [],
  "abstentions": ["..."]
}

{historique de conversation, s'il y en a un}

Contexte (extraits numérotés, avec l'expert qui les a trouvés) :
{context}

Abstentions déjà connues (aucune recherche ne les a couvertes, à mentionner) :
{abstentions}
```

Deux variantes de la règle de fidélité, selon que la demande contient ou non
un mot déclencheur du mode "proposition" (`propose`, `suggère`,
`imagine`...) :

- **Mode strict** (par défaut) :
  > « Utilise UNIQUEMENT les extraits numérotés... n'invente RIEN. »
- **Mode proposition** :
  > autorise une structuration plausible même sans source précise, tout en
  > interdisant absolument d'inventer un fait vérifiable (chiffre,
  > certification, date, nom de projet réel) — à remplacer par
  > `[À COMPLÉTER : ...]` — et impose de signaler dans les abstentions qu'il
  > s'agit d'une proposition à valider par un humain.

**Le champ `is_proposal` de la réponse finale n'est jamais laissé au LLM** :
il est positionné directement par le code, après coup, selon que le mode
proposition a été activé ou non pour cet appel — une garantie qu'aucune
erreur du modèle ne peut faire disparaître cet avertissement.

En cas d'échec de validation (citation invalide, format incorrect...) ou
d'erreur JSON, une nouvelle tentative est faite (jusqu'à 2 au total), avec le
message d'erreur précis ajouté au prompt pour orienter la correction. Si les
deux tentatives échouent, un contenu de repli minimal est produit plutôt que
de faire échouer la conversation.

---

## 13. Réponse conversationnelle libre (hybrid_rag, Horloge B)

**Fichier** : `app/services/chat_pipeline.py`.
**Appelée pour** : répondre à une question libre de l'utilisateur sur le
patrimoine documentaire, en s'appuyant sur le contexte agrégé par les
experts.
**Consommateur du résultat** : directement affiché à l'utilisateur, en flux
continu (vrai streaming token par token) — pas de format structuré à
respecter ici, juste du texte Markdown.

Prompt exact :
```
Tu es un assistant BTP pour préparer un dossier d'appel d'offres. Français.
Réponds en Markdown, pas de titre H1. Pas d'invention de montants, SIRET ou dates.
Utilise UNIQUEMENT les extraits numérotés. Cite [1], [2]... quand tu t'appuies dessus.
Si les extraits ne suffisent pas, dis-le explicitement plutôt que d'inventer.
{historique de conversation}
Question :
{query_clean}

Extraits :
{context_text}

Réponse Markdown :
```

Cette intervention utilise `num_ctx=8192` — la même valeur que la génération
de section (intervention n°12) — car elle embarque le même type de contexte
agrégé, potentiellement volumineux (jusqu'à 20 000 caractères, plafonné par
l'agrégation, voir [02_Horloge_B_Generation.md](02_Horloge_B_Generation.md)
§6).

---

## Récapitulatif des enseignements transversaux

- **Un seul modèle de langage** (`granite3.3:2b`) exécute les 13
  interventions ci-dessus — aucune spécialisation de modèle par tâche.
- **Douze interventions sur treize** demandent un JSON "librement", sans
  garantie stricte de structure ; **une seule** (la génération de section)
  bénéficie d'un schéma JSON réellement contraint.
- Chaque intervention a un **comportement de repli** défini en cas d'échec
  (jamais de plantage brut de la conversation) : soit une valeur par défaut
  raisonnable, soit un repli vers une méthode plus simple et déterministe
  (mots-clés plutôt que LLM), soit une nouvelle tentative avec correction.
- Le `num_ctx` (taille de fenêtre de contexte) est choisi au cas par cas
  selon la longueur attendue du prompt : 2048 pour les prompts courts déjà
  tronqués en amont, 4096 pour les prompts avec historique de conversation,
  8192 pour les deux interventions qui embarquent le contexte documentaire
  agrégé complet (génération de section et réponse conversationnelle libre).
