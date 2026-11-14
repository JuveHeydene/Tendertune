# Questions de jury — préparation soutenance

Ce document se met à la place d'un examinateur qui connaît le dossier et qui
cherche les failles. Chaque section couvre une partie du système ; les
questions marquées **⚠️ PIÈGE** sont celles conçues pour faire dire une
contre-vérité ou révéler une compréhension superficielle — un ⚠️ est suivi
d'une note expliquant où est le piège exactement, pas d'une réponse toute
faite : le but est de comprendre le mécanisme assez pour répondre sans filet,
pas de réciter.

---

## 1. Architecture générale

1. Pourquoi cinq bases de données différentes (Postgres, Qdrant, Neo4j,
   Redis, MinIO) plutôt qu'une seule ? Qu'est-ce que ça coûte en complexité
   opérationnelle ?
2. Postgres sert à la fois de base relationnelle ET de file d'événements
   implicite (JSONB partout : `pipeline_stages`, `ocr_progress`,
   `context_snapshot`...) — n'est-ce pas un signe qu'il manque une vraie
   modélisation ?
3. Pourquoi ARQ (Redis) pour les jobs asynchrones plutôt que Celery ou un
   simple `BackgroundTasks` FastAPI partout ?
   **⚠️ PIÈGE** : le code utilise justement LES DEUX — `BackgroundTasks`
   pour `cover_exigence` (une recherche, quelques secondes) et ARQ pour
   l'ingestion/l'extraction de structure (minutes, doit survivre à un
   redémarrage de process). Si la réponse ne distingue pas les deux cas
   d'usage, c'est qu'il y a une incompréhension du "pourquoi" derrière le
   choix, pas juste du "quoi".
4. Le worker qui fait l'OCR tourne "en hybride" sur l'hôte plutôt que dans
   Docker — pourquoi ? Quel est le compromis ?
   **⚠️ PIÈGE** : la réponse attendue est GPU (accès direct au device CUDA
   sans la complexité du passthrough Docker), MAIS il faut assumer que ce
   worker a un bug non résolu (repli silencieux sur CPU, erreur cudnn) —
   dire que "le GPU marche" sans nuance est un mensonge facile à détecter si
   le jury demande une démonstration en direct.
5. Qu'est-ce qui garantit l'isolation entre tenants (deux entreprises
   clientes de la plateforme) ?
   **⚠️ PIÈGE** : la réponse "un `tenant_id` sur chaque table" est
   incomplète — il faut pouvoir citer un endroit où CE FILTRE N'EST PAS
   appliqué explicitement dans le code (ex. `list_users`/`list_sessions` de
   l'admin plateforme n'ont AUCUN filtre tenant — c'est voulu, l'admin est
   multi-tenant, mais si on ne le sait pas et qu'on affirme "tout est
   cloisonné par tenant partout", le jury peut vous montrer le contre-exemple).

## 2. Ingestion et traitement des documents

6. Que se passe-t-il si on dépose deux fois exactement le même fichier ?
7. Que se passe-t-il si l'ingestion d'un PDF scanné de 200 pages est
   interrompue à la page 150 (crash worker, timeout) ?
8. **⚠️ PIÈGE** : "Si je relance l'ingestion après une interruption, est-ce
   que ça reprend à la bonne page, ou est-ce que ça recommence tout et
   double les données ?" — la bonne réponse doit mentionner DEUX mécanismes
   distincts : la reprise page par page (`ocr_progress`) ET la purge des
   vecteurs Qdrant avant réindexation (`delete_by_document`) — dire "ça
   reprend" sans mentionner la purge Qdrant laisse penser qu'on n'a pas vu
   le bug réel qui existait AVANT cette purge (vecteurs orphelins dupliqués).
9. **⚠️ PIÈGE, le plus retors de cette section** : "Vous avez ajouté
   `doc.ocr_progress = {}` après une ingestion réussie pour nettoyer l'état
   de reprise. Ça marche à tous les coups ?" — la bonne réponse : NON, ça a
   été un bug réel : SQLAlchemy compare la nouvelle valeur à l'ancienne PAR
   VALEUR pour une colonne JSONB simple, et quand les deux valent `{}`
   (objet différent, contenu identique), l'ORM ne génère PAS de UPDATE pour
   cette colonne — la ligne semblait "nettoyée" en mémoire mais restait
   polluée en base. Corrigé avec `flag_modified()`. Une réponse qui dit
   "oui ça marche toujours" sans connaître ce cas précis s'effondre si le
   jury demande "et si la nouvelle valeur est égale à l'ancienne ?".
10. Pourquoi les documents administratifs (KBIS, attestations) ne sont-ils
    pas indexés dans Qdrant comme les autres ?
    **⚠️ PIÈGE** : il faut assumer que c'est un choix APRÈS COUP (pas dès la
    conception) — au départ, TOUS les documents passaient par l'ingestion
    RAG complète, y compris les pièces administratives, ce qui gaspillait du
    calcul sur des documents qui n'ont aucune valeur de recherche
    sémantique. Si la réponse prétend que c'était prévu dès le début, c'est
    faux et vérifiable dans l'historique de conception.
11. Comment savez-vous qu'un document est un PDF scanné plutôt qu'un PDF
    texte natif ? Qui décide de passer par l'OCR ?
12. Le worker de logs semble parfois "silencieux" après l'initialisation de
    PaddleOCR — pourquoi ?
    **⚠️ PIÈGE** : c'est un bug SUSPECTÉ mais jamais formellement confirmé
    (corruption du module `logging` global par PaddleOCR/une dépendance) —
    une bonne réponse admet l'incertitude plutôt que d'affirmer une cause
    root-cause qui n'a été validée qu'indirectement (contournée par des
    `print()` bruts, jamais réellement expliquée).

## 3. Recherche documentaire (RAG / CRAG)

13. Qu'est-ce que le CRAG apporte par rapport à un RAG "naïf" (top-k puis
    génération directe) ?
14. Expliquez le seuil 0.7/0.3 du grading — pourquoi ces valeurs, et que se
    passe-t-il dans la zone grise ?
15. **⚠️ PIÈGE central de cette section** : "Un expert qui abandonne après 3
    tentatives sans jamais trouver de contexte 'correct' — que devient le
    résultat, concrètement, dans la réponse finale ?" — la bonne réponse
    doit dire que `run_expert` retourne quand même les CANDIDATS de la
    dernière tentative (même jugés incorrects/ambigus), avec juste un
    marqueur `source=abstention`. Si le code appelant (ex. `cover_exigence`
    AVANT correction) ne vérifie que "y a-t-il des chunks ?" sans regarder
    `source`, une recherche qui a ÉCHOUÉ peut être traitée comme un SUCCÈS.
    C'est un bug réel trouvé et partiellement corrigé cette session — une
    réponse qui prétend que l'abstention est toujours propre et sans
    ambiguïté est fausse.
16. Pourquoi 3 tentatives (`MAX_ITER`) et pas 1 ou 10 ?
17. Le mode "simple" (Adaptive, top-8 sans grading) — n'est-ce pas risqué de
    faire confiance aveuglément à un top-8 sans vérification ?
18. Comment le graphe Neo4j est-il réellement utilisé dans une recherche ?
    Le LLM génère-t-il du Cypher librement ?
    **⚠️ PIÈGE** : NON — le Cypher est TOUJOURS un template fixe
    (`BOUNDED_TWO_HOP`, `ONE_HOP`...), jamais généré par le LLM. Le LLM sert
    uniquement à EXTRAIRE les entités de la question. Répondre "le LLM
    génère la requête Cypher" est faux et une faille de sécurité potentielle
    si c'était vrai (injection Cypher) — bien préciser que ce risque a été
    délibérément évité par design.
19. Que se passe-t-il si Ollama est injoignable pendant une recherche ?
    Le système plante-t-il ?
20. Le superviseur (routeur d'intention) est un LLM — n'est-ce pas fragile
    de faire reposer TOUT le routage sur un petit modèle ?
    **⚠️ PIÈGE** : oui, et ça s'est vérifié en pratique — un message aussi
    simple que "pourquoi ?" a été classé comme une demande d'EXPORT et a
    déclenché un téléchargement à la place d'une réponse. Corrigé par des
    garde-fous déterministes (mots-clés) qui corrigent la sortie du LLM
    APRÈS coup plutôt que de lui faire une confiance aveugle. Une réponse
    qui prétend que le routage LLM est fiable à 100% est réfutée par ce cas
    réel documenté.

## 4. Extraction et couverture des exigences

21. Une exigence marquée "couverte" — cela signifie-t-il qu'un humain a
    validé la preuve ?
    **⚠️ PIÈGE** : NON, c'est 100% automatique. Une bonne réponse doit
    savoir dire précisément qui/quoi décide (une recherche CRAG côté
    patrimoine), et surtout admettre la conséquence : le statut peut être
    un faux positif si la recherche a abusivement traité une abstention
    comme une couverture (voir question 15).
22. Le statut "à revoir" existe dans le schéma — à quoi sert-il, qui le
    déclenche ?
    **⚠️ PIÈGE** : pendant longtemps, RIEN ne le déclenchait — c'était un
    statut prévu au schéma mais jamais câblé côté backend, uniquement
    affiché côté frontend. Il a été branché cette session précisément pour
    distinguer "recherche qui a abouti à un résultat validé" de "recherche
    qui a abouti à des candidats non confirmés" (abstention avec des
    chunks quand même). Prétendre qu'il a toujours fonctionné serait faux.
23. Comment la déduplication des exigences fonctionne-t-elle entre un RC et
    un CCAP qui répètent souvent la même clause ?
24. Que se passe-t-il si on relance l'analyse d'un dossier déjà analysé —
    les exigences sont-elles dupliquées ?
    **⚠️ PIÈGE** : il faut savoir qu'il y a eu un bug réel là-dessus (une
    ré-analyse doublait les exigences avant l'ajout d'une purge explicite
    avant réinsertion) — et savoir where exactement cette purge a lieu.
25. Pourquoi la page source d'une exigence n'est-elle pas toujours exacte ?
    **⚠️ PIÈGE** : c'est un compromis ASSUMÉ, pas un bug — les chunks sont
    regroupés en lots pour limiter le nombre d'appels LLM sur un DAO
    volumineux, et la page retenue est celle du DÉBUT du lot, pas la page
    précise de l'exigence. Une réponse qui prétend que c'est toujours exact
    est fausse ; une réponse qui dit "c'est un bug qu'on n'a pas eu le temps
    de corriger" rate aussi la nuance — c'est un choix de vitesse
    explicitement documenté.
26. La classification "quelle exigence concerne quelle section" est faite
    par un LLM — que se passe-t-il si elle se trompe ? Un humain peut-il
    corriger ?
27. Si on relance la classification après qu'un humain a déjà exclu une
    proposition de l'IA, cette proposition revient-elle ?
    **⚠️ PIÈGE** : NON, et il faut savoir pourquoi précisément — le lien
    exclu n'est jamais supprimé de la base (juste marqué `exclue`), et la
    réinsertion utilise `ON CONFLICT DO NOTHING` sur la contrainte unique
    (exigence, section) : la ligne existe déjà, donc rien n'est réécrit.
    Une réponse qui dit "l'IA pourrait reproposer la même chose" est fausse
    et montre qu'on n'a pas compris le mécanisme de préservation des
    décisions humaines.

## 5. Génération de contenu (rédaction des sections)

28. Le modèle peut-il inventer un chiffre d'affaires ou une certification
    qui n'existe pas ?
29. Qu'est-ce que le mode "proposition" et en quoi relâche-t-il
    l'anti-hallucination ? N'est-ce pas dangereux ?
    **⚠️ PIÈGE, question produit** : la bonne réponse doit citer la
    limite ABSOLUE conservée même en mode proposition (interdiction
    d'inventer un FAIT VÉRIFIABLE précis — chiffre, certification, date —
    ces éléments doivent apparaître en `[À COMPLÉTER]`) et le bandeau
    d'avertissement systématique posé par le CODE (pas laissé à la
    discrétion du LLM). Si la réponse ne distingue pas "structuration
    plausible" de "fait vérifiable inventé", elle rate l'essentiel du
    garde-fou.
30. **⚠️ PIÈGE, très facile à rater** : "Le bandeau d'avertissement du mode
    proposition — s'affiche-t-il TOUJOURS quand c'est pertinent, ou
    dépend-il du bon vouloir du modèle ?" — bonne réponse : le CODE pose ce
    bandeau inconditionnellement (`section_to_markdown`) dès que
    `is_proposal=True`, indépendamment de ce que le modèle a produit — le
    prompt demande AUSSI au modèle de le mentionner dans les abstentions,
    mais ce n'est pas la garantie réelle. Confondre les deux mécanismes
    (instruction du prompt vs contrôle du code) est le piège.
31. Comment le mécanisme de citations `[1]`, `[2]` fonctionne-t-il en
    interne ? Le modèle connaît-il l'identifiant réel du document cité ?
    **⚠️ PIÈGE majeur, bug réel de cette session** : NON — le modèle ne
    voit JAMAIS l'UUID réel d'un chunk, seulement un numéro d'affichage. Un
    schéma qui lui demandait de citer un `"chunk_id"` était donc
    STRUCTURELLEMENT impossible à respecter correctement. Corrigé en lui
    demandant le NUMÉRO qu'il voit réellement, traduit en id réel côté
    code après coup. Une réponse qui ne voit pas le problème ("le modèle
    cite juste le bon id") n'a pas compris pourquoi les citations
    échouaient en pratique.
32. "Ajouter du contenu" à une section déjà rédigée — comment ça marche
    concrètement ? Le modèle réécrit-il tout depuis zéro ?
    **⚠️ PIÈGE** : par défaut OUI, chaque génération repart de zéro — le
    mode "enrichissement" (mots-clés "ajoute"/"complète") est un
    comportement SPÉCIAL qui injecte le texte existant dans le prompt.
    Sans ce mot-clé, même une demande qui ressemble à un ajout ("rédige un
    paragraphe de plus sur X") régénère toute la section.
33. Pourquoi avoir choisi un modèle aussi petit (2B paramètres) pour la
    génération ? Quelles limites cela impose-t-il concrètement ?
    **⚠️ PIÈGE** : il faut être capable de citer un TAUX D'ÉCHEC RÉEL
    observé (avant correction : environ 50 à 75% des générations
    échouaient avec `[Génération non aboutie]`) et sa cause exacte
    (dérive du format JSON libre, pas de contrainte de schéma réelle) —
    une réponse vague ("c'est plus rapide, moins cher") sans admettre les
    limites concrètes de fiabilité observées est incomplète.
34. Comment garantissez-vous que le JSON produit par le modèle respecte
    exactement le schéma attendu (bons champs, bons types) ?
    **⚠️ PIÈGE, LA question technique la plus pointue de tout le dossier** :
    la réponse "on utilise `format: json` côté Ollama" est INCOMPLÈTE et
    en réalité fausse pour ce besoin précis — ce mode garantit du JSON
    SYNTAXIQUEMENT valide, PAS une forme précise. La vraie solution
    (trouvée et appliquée cette session) est de passer le VRAI schéma JSON
    (`SectionGeneree.model_json_schema()`) en valeur de `format`, ce qui
    contraint le décodage token par token. Si le jury demande "quelle est
    la différence entre passer la chaîne `'json'` et un objet schéma ?" et
    que la réponse ne sait pas l'expliquer, c'est rédhibitoire vu que
    c'est LE changement qui a fait passer la fiabilité de ~30% à 100% sur
    les tests réalisés.
35. Combien de tentatives le système fait-il avant d'abandonner une
    génération ? Que se passe-t-il à l'abandon ?
36. Un consultant peut-il générer une section depuis le chat ?
    **⚠️ PIÈGE redoutable** : la réponse naïve est "non, il n'a pas les
    droits". EN RÉALITÉ : rien n'empêche un consultant de taper "génère la
    section X" dans le chat — le calcul LLM se lance et le texte s'affiche
    dans SA conversation, mais n'est jamais persisté comme une vraie
    section (le contrôle de rôle n'intervient qu'au moment de la
    sauvegarde, pas avant l'appel au modèle). Un consultant croit donc
    avoir une vraie section alors que c'est éphémère — comportement non
    corrigé, à assumer comme une limite connue si le jury la trouve.

## 6. Fiabilité, troncature et bugs récents (zone à fort risque de piège)

37. Qu'est-ce que `num_ctx` et pourquoi son absence est-elle dangereuse ?
    **⚠️ PIÈGE** : sans lui, Ollama applique SA valeur par défaut (2048
    tokens) et TRONQUE LE PROMPT EN SILENCE — aucune erreur, aucun log,
    juste un modèle qui répond à partir d'un prompt amputé, souvent
    exactement là où se trouve le schéma JSON attendu (en fin de prompt).
    Une réponse qui ne mentionne pas le mot "silencieux"/"sans erreur"
    rate l'aspect le plus dangereux du bug (indétectable sans creuser).
38. Le contexte patrimoine assemblé pour une génération — a-t-il une
    taille maximale ? Pourquoi ce chiffre précis ?
    **⚠️ PIÈGE** : AVANT correction, chaque chunk individuel était plafonné
    (12000 caractères) mais AUCUNE limite n'existait sur le nombre de
    chunks cumulés ni sur le total — un contexte pouvait donc devenir
    arbitrairement gros (jusqu'à 4 sous-questions × 50 chunks). Le plafond
    global (20000 caractères) a été ajouté après coup, pas dès la
    conception initiale.
39. Ce plafond de contexte laisse-t-il tomber des informations
    silencieusement ? Est-ce grave ?
    **⚠️ PIÈGE** : oui, des extraits moins prioritaires sont abandonnés
    sans le signaler à l'utilisateur final (seulement un log serveur) — un
    bon candidat doit pouvoir juger si c'est acceptable et proposer une
    piste d'amélioration (ex. remonter l'info dans les `abstentions`)
    plutôt que de prétendre que rien n'est perdu.
40. La réponse conversationnelle normale (pas la génération de section) —
    est-elle concernée par les mêmes problèmes de troncature ?
    **⚠️ PIÈGE** : OUI, et c'est facile à oublier — `ollama_generate_stream`
    (utilisée pour CHAQUE réponse de chat en streaming) n'avait même pas
    la possibilité technique de fixer `num_ctx` avant correction (le
    paramètre n'existait pas dans la fonction). Une réponse qui ne corrige
    que `generate_section` en pensant avoir traité tout le problème est
    incomplète.
41. Pourquoi la classification d'intention (superviseur) ne voit-elle pas
    directement votre message tapé au clavier ?
    **⚠️ PIÈGE** : elle voit `query_clean`, une réécriture par un AUTRE
    appel LLM (`rewrite_query`) dont le rôle est de produire "une PHRASE DE
    RECHERCHE, pas une réponse" — ce qui peut effacer le verbe d'action
    ("rédige") nécessaire à la classification. Corrigé en donnant AUSSI le
    texte brut au superviseur pour ses propres garde-fous. Une réponse qui
    ne sait pas qu'il existe DEUX représentations du même message
    (`text` brut et `query_clean` réécrit) circulant dans le pipeline
    passe à côté d'une bonne partie des bugs de routage trouvés cette
    session.

## 7. Traçabilité et audit

42. Une table `audit_logs` existe dans le schéma depuis le début — quand
    a-t-elle commencé à être réellement utilisée ?
    **⚠️ PIÈGE** : elle a existé PENDANT TRÈS LONGTEMPS sans qu'AUCUN code
    n'y écrive quoi que ce soit — une table d'audit entièrement vide,
    jamais branchée. Prétendre qu'elle a toujours servi à tracer les
    actions sensibles est faux et vérifiable (aucune ligne d'insertion
    dans l'historique avant cette session).
43. La table `retrieval_traces` enregistre chaque tentative de recherche —
    à quoi sert-elle concrètement pour l'utilisateur final ?
    **⚠️ PIÈGE** : pendant longtemps, à RIEN de visible — elle était
    écrite mais jamais lue par aucun endpoint ni aucune page. Une
    fonctionnalité "prévue pour l'évaluation" mais jamais exploitée avant
    d'être explicitement exposée (bouton "Pourquoi cette réponse ?").
44. Pourquoi ne peut-on pas relier une trace de recherche à une génération
    via une simple clé étrangère `generation_id` (qui existe pourtant sur
    la table) ?
    **⚠️ PIÈGE technique fin** : parce que la recherche est effectuée et
    COMMITÉE (transaction distincte, une session par expert) AVANT que la
    ligne `Generation` n'existe en base — une vraie contrainte de clé
    étrangère ne pourrait donc JAMAIS être satisfaite à l'insertion.
    Solution retenue : une clé de corrélation sans contrainte
    (`trace_batch_id`), générée par l'appelant et recopiée après coup dans
    `context_snapshot`. Une réponse qui propose "il suffit de mettre à
    jour `generation_id` après coup" révèle qu'on n'a pas compris la
    contrainte de séquencement transactionnel.
45. Supprimer une conversation ayant des messages — cela a-t-il toujours
    fonctionné sans erreur ?
    **⚠️ PIÈGE, bug 100% reproductible trouvé en testant** : NON — la
    relation ORM entre `Conversation` et `Message` n'avait pas de cascade
    configurée correctement ; supprimer une conversation dont les messages
    étaient déjà chargés en mémoire (ce qui est systématiquement le cas)
    faisait tenter à SQLAlchemy de mettre `conversation_id` à NULL sur les
    messages au lieu de les supprimer — crash immédiat car la colonne est
    NOT NULL. Corrigé avec `cascade="all, delete-orphan",
    passive_deletes=True`. C'est un bug qui a été DÉCOUVERT PAR ACCIDENT en
    nettoyant des données de test, pas anticipé.

## 8. Sécurité, rôles et permissions

46. Quels rôles existent et que peut faire chacun ?
47. Un utilisateur peut-il changer son propre rôle admin par erreur ou
    malveillance ?
48. Comment un mot de passe oublié est-il traité côté admin ?
49. Que trace-t-on exactement lors d'une connexion échouée ?
50. **⚠️ PIÈGE** : "Le champ `ip_address` existe sur la table `Session`
    depuis le début — était-il toujours rempli ?" — NON, il ne l'était pas
    (jamais passé au constructeur lors de la connexion), corrigé cette
    session en même temps que le reste de l'audit. Une donnée de sécurité
    présente dans le schéma mais silencieusement vide n'est pas la même
    chose qu'une donnée qui n'existe pas — et c'est justement le genre de
    trou qu'un audit de sécurité sérieux doit débusquer.
51. Le graphe de connaissances contient des relations entre entités
    extraites automatiquement — une entité mal résolue (deux orthographes
    du même nom d'entreprise) peut-elle polluer les résultats ?

## 9. Choix contestables à assumer sans détour

52. Vous avez un fichier "journal des bugs corrigés" — n'est-ce pas
    l'aveu que le système est fragile ?
    *(Bonne posture de réponse : c'est au contraire la preuve d'une
    méthode — chaque correctif a été testé en conditions réelles avant/
    après, avec preuve chiffrée à l'appui, pas juste "corrigé et espéré".
    Le vrai risque serait de PRÉTENDRE qu'il n'y a jamais eu de bug.)*
53. LlamaIndex apparaît dans les dépendances — est-il utilisé ?
    **⚠️ PIÈGE** : NON, confirmé mort dans le code — une dépendance
    présente mais jamais appelée. Prétendre qu'il joue un rôle dans le
    pipeline RAG serait facilement démontable en demandant "montrez-moi où
    il est importé et utilisé".
54. Existe-t-il un chemin de code (endpoint, fonction) qui n'est plus
    jamais appelé par le frontend réel ?
    **⚠️ PIÈGE** : oui — `process_message_sync` / le graphe LangGraph
    compilé (`compiled_graph`) sont accessibles via un endpoint HTTP mais
    le frontend n'appelle QUE la version streaming. C'est du code mort du
    point de vue utilisateur, jamais nettoyé.
55. Deux régénérations de la même section lancées en même temps par deux
    utilisateurs — que se passe-t-il ?
    **⚠️ PIÈGE** : rien ne l'empêche — contrairement à la recherche
    d'exigence ou à la classification (qui ont un verrou "en_cours"), la
    génération de section n'a AUCUNE protection contre la concurrence.
    Risque réel de conflit sur le numéro de version. Admettre que c'est un
    trou non couvert est plus solide que d'inventer une protection qui
    n'existe pas.
56. Quelle est votre couverture de tests automatisés ? Est-ce suffisant
    pour un système de cette complexité ?
    *(27 tests — à situer honnêtement : suffisant pour valider des
    fonctions déterministes isolées, très insuffisant pour couvrir les
    chemins agentiques/LLM qui ont justement été la source de la majorité
    des bugs trouvés — ceux-là n'ont été débusqués qu'en testant en
    conditions réelles contre un vrai Ollama, jamais par un test unitaire.)*

## 10. Questions "pourquoi pas X à la place" (alternatives non retenues)

57. Pourquoi ne pas laisser un agent entièrement autonome décider de tout
    (recherche, génération, découpage) plutôt que ce routage largement
    déterministe (mots-clés, lookups par archétype) ?
58. Pourquoi ne pas fusionner Qdrant et Neo4j (bases vectorielles avec
    support de graphe existent) ?
59. Pourquoi ne pas utiliser un modèle plus gros pour toutes les tâches
    plutôt que le même petit modèle partout ?
60. Pourquoi stocker les pièces administratives en PDF fusionné plutôt
    qu'un ZIP des fichiers originaux (plus simple, sans perte de format) ?
    *(La fusion PDF a un vrai coût de complexité — conversion image→PDF,
    pages de titre générées, gestion des formats non convertibles — à
    savoir justifier par le besoin exprimé : un seul document déposable,
    pas une archive à recomposer soi-même.)*

## 11. Questions de clôture (les plus larges, souvent les plus difficiles)

61. Si vous deviez retirer UNE seule fonctionnalité par manque de temps,
    laquelle et pourquoi ?
62. Quelle est, selon vous, la fragilité la plus grave qui reste dans le
    système aujourd'hui ?
    *(Réponse honnête attendue plutôt qu'une esquive — plusieurs
    candidats légitimes : absence de verrou sur les générations
    concurrentes, dépendance totale à un petit modèle local pour des
    décisions à fort impact métier, statuts "couverte"/"à revoir" pas
    toujours vérifiables par l'utilisateur.)*
63. Qu'est-ce qui, dans ce projet, vous a le plus surpris en le
    construisant ?
64. Si un jury technique demandait une démonstration EN DIRECT de la
    correction d'un bug précis (ex. réinjecter volontairement un
    contexte trop long pour vérifier qu'il n'y a plus de troncature
    silencieuse) — êtes-vous capable de le faire sans préparation ?
