# Où chaque donnée est stockée, et pourquoi

L'application n'utilise pas une seule base de données : elle en combine
**cinq**, chacune choisie pour ce qu'elle sait faire de mieux. Ce chapitre
explique où vit chaque type de donnée et pourquoi cet endroit précis a été
choisi plutôt qu'un autre. Tous les faits ci-dessous sont vérifiés dans
`backend_ao/` au 13/09/2026.

## Vue d'ensemble

| Système | Ce qu'il sait faire de mieux | Ce qui y est stocké |
|---|---|---|
| **Postgres** | Stocker des données structurées avec des relations strictes entre elles, garantir qu'une donnée n'est jamais perdue ou incohérente | Utilisateurs, documents (métadonnées), chunks (texte), dossiers, exigences, plan du mémoire, conversations, messages, générations, relectures, exports, traces de recherche, journal d'audit |
| **Qdrant** | Retrouver un passage par similarité de sens, même avec des mots différents | Les empreintes numériques (vecteurs) de chaque chunk de texte |
| **Neo4j** | Représenter et parcourir des relations entre entités | Les entités BTP (entreprises, projets, certifications...) et leurs relations |
| **MinIO** | Stocker de gros fichiers bruts efficacement | Les fichiers déposés (PDF, DOCX...) et les documents exportés (PDF/DOCX finaux) |
| **Redis (+ ARQ)** | Mettre des tâches en attente et les distribuer à des workers | Les tâches d'ingestion et d'extraction de graphe en attente de traitement |

Il n'y a **pas d'Alembic** (un outil courant de gestion automatique de
l'évolution du schéma de base de données) dans ce projet : le schéma
Postgres est géré directement en SQL écrit à la main (`scripts/init_db.sql`
pour la base initiale, puis cinq fichiers d'évolution successifs dans
`scripts/migrations/`, tous datés entre le 30 août et le 11 septembre 2026 —
une évolution récente et rapide, concentrée sur le passage vers
l'architecture "agentique" décrite au chapitre Horloge B).

## 1. Postgres — 18 tables

Toutes définies dans un seul fichier, `app/models/sql.py`.

### Identité et sécurité

- **`tenants`** — une ligne par entreprise cliente de la plateforme. C'est la
  racine de tout le cloisonnement multi-entreprise : presque toutes les
  autres tables portent un identifiant de tenant qui pointe ici, pour
  garantir qu'une entreprise ne voit jamais les données d'une autre.
- **`users`** — les comptes utilisateurs, avec leur rôle (voir §7) et des
  permissions fines optionnelles qui peuvent surcharger le comportement par
  défaut du rôle.
- **`sessions`** — une session active par connexion réussie, avec un jeton
  haché (jamais le jeton d'authentification en clair) — permet de révoquer
  immédiatement l'accès d'un utilisateur (déconnexion, expiration) sans
  attendre que le jeton expire naturellement.
- **`refresh_tokens`** — prévu pour permettre à une session de se renouveler
  sans reconnexion complète ; la structure existe en base mais n'est pas
  encore branchée dans le flux de connexion actuel.
- **`audit_logs`** — le journal de "qui a fait quoi" : chaque action
  sensible (connexion, déconnexion, et d'autres actions notables) y est
  enregistrée, avec le type d'action, la ressource concernée, le résultat
  (succès/échec) et un détail structuré. C'est la trace de conformité et de
  traçabilité du système.

### Les documents et leur contenu

- **`documents`** — la table pivot de toute l'ingestion : un fichier déposé,
  avec son statut (`pending`/`processing`/`ready`/`failed`), son rôle
  (patrimoine, DAO courant, archive, annexe), et le suivi détaillé de son
  traitement (`pipeline_stages`, `ocr_progress`, voir chapitre Horloge A). Le
  choix de tout centraliser dans une seule table, quel que soit le type de
  fichier, simplifie énormément la recherche et l'affichage côté interface.
- **`chunks`** — les fragments de texte issus du découpage (parent/enfant,
  voir chapitre Horloge A). C'est ici que vit le **texte réellement cité**
  dans les réponses générées — Qdrant, lui, ne stocke qu'une empreinte
  numérique et un court aperçu, pas le texte complet. Une colonne technique
  supplémentaire (`text_fts`) existe en base pour la recherche plein texte
  classique (utilisée par les experts de recherche, en complément de la
  recherche par similarité de Qdrant).

### Le dossier d'appel d'offres et sa préparation

- **`dossiers`** — un dossier d'AO en cours de traitement : nom du client, du
  projet, référence de l'AO, échéance, statut. C'est le pivot central de
  toute la partie "agentique" du système : exigences, plan, générations et
  exports en dépendent tous.
- **`exigences`** — chaque obligation extraite du règlement de consultation,
  avec son statut de couverture (à couvrir / couverte) et les extraits de
  preuve associés.
- **`outline_items`** — le plan (sommaire) du mémoire technique à rédiger
  pour ce dossier, avec un "archétype" par section (factuelle, narrative,
  institutionnelle, conformité) qui oriente précisément la façon dont le
  LLM doit rédiger cette section (voir chapitre Horloge B).
- **`exigence_sections`** — la table qui relie chaque exigence aux sections
  du plan censées y répondre. Elle porte une colonne `origine` (proposée par
  le LLM ou confirmée/ajoutée par un humain) — une distinction volontaire
  pour toujours savoir qui a établi tel lien.
- **`dossier_pieces`** — la checklist des pièces administratives requises
  (KBIS, attestations...), distincte des `exigences` : ici on rattache un
  **document entier** déjà déposé au patrimoine, pas une simple citation de
  passage.

### La conversation et la rédaction

- **`conversations`** — un fil de discussion, éventuellement rattaché à un
  dossier précis.
- **`messages`** — chaque message d'une conversation (utilisateur ou
  assistant), avec la reformulation de la question et des métadonnées
  (citations, indicateur d'upload...).
- **`generations`** — chaque génération de contenu pour une section du
  mémoire : le contenu structuré, les citations, un instantané du contexte
  utilisé au moment de la génération, la version, et des métriques (temps de
  génération, nombre de tokens, estimation de coût).
- **`reviews`** — chaque action de relecture humaine sur une génération
  (valider, modifier le texte, demander une régénération avec une
  instruction précise) — la trace du contrôle humain sur ce que produit
  l'IA, un point important pour la fiabilité globale du système.
- **`exports`** — chaque export PDF/DOCX/MD/TXT généré d'un dossier, avec sa
  version et son emplacement de stockage.

### Observabilité

- **`retrieval_traces`** — une ligne par tentative de recherche faite par un
  expert (voir chapitre Horloge B, mécanisme CRAG) : quelle sous-question,
  quel expert, quelle tentative, quelle requête effectivement utilisée,
  quels filtres, quel verdict et par quelle méthode, quels résultats,
  abstention ou non. C'est la base d'observation la plus riche du système
  pour comprendre, après coup, pourquoi une recherche a réussi ou échoué.

## 2. Qdrant — la recherche par similarité de sens

Une seule collection, nommée **`ao_chunks`**. Chaque point stocké représente
un chunk de texte, sous la forme d'un vecteur de 768 nombres (produit par le
modèle `nomic-embed-text`), comparé par une mesure de distance appelée
"cosinus" — qui compare l'orientation de deux vecteurs, une façon efficace de
mesurer si deux textes "parlent du même sujet".

En plus du vecteur, chaque point porte des informations d'accompagnement
utiles pour filtrer et afficher les résultats sans repasser systématiquement
par Postgres :
- l'identifiant du chunk et du document d'origine (pour retrouver le texte
  complet et la traçabilité) ;
- l'identifiant de l'entreprise (tenant) — un filtre **obligatoire** à chaque
  recherche, pour garantir qu'aucune donnée d'une entreprise ne puisse
  jamais apparaître dans les résultats d'une autre ;
- le rôle du document (patrimoine, DAO courant...) — pour restreindre la
  recherche selon le contexte de la question ;
- la position dans le document (page, chemin de titre) — pour permettre à
  l'utilisateur de retrouver précisément la source d'une citation ;
- un aperçu du texte lui-même, tronqué à 2000 caractères — un compromis pour
  éviter un aller-retour supplémentaire vers Postgres à chaque recherche,
  sans dupliquer le texte complet.

## 3. Neo4j — le graphe de connaissances

- Un seul type de nœud, `Entity`, avec un type précis en propriété
  (ENTREPRISE, PROJET, CLIENT, CERTIFICATION, PERSONNE, EXIGENCE, LOT, SITE).
- Un seul type de relation Neo4j au sens strict, `REL`, mais avec une
  propriété `type` qui porte la vraie sémantique (A_TRAVAILLE_SUR, PORTE,
  CONCERNE, SITUE_A, SATISFAITE_PAR, CONTIENT) — un choix qui simplifie la
  structure du graphe tout en gardant une sémantique riche.
- Chaque relation porte aussi une référence vers le **chunk de texte source**
  qui l'a produite — le principe appliqué systématiquement : un fait de
  graphe ne se cite jamais sans le passage exact qui le prouve.
- Le cloisonnement par entreprise existe aussi ici, mais au niveau d'une
  propriété (`tenant_id`) sur chaque entité, plutôt qu'au niveau de la
  structure du graphe elle-même.
- Un même code (les mêmes templates de requêtes Cypher fixes) est réutilisé
  à la fois pour écrire dans le graphe (Horloge A, à l'ingestion) et pour le
  lire (Horloge B, l'expert graphe) — "un seul outil partagé entre les deux
  horloges", comme le documente un commentaire du code.

## 4. MinIO — le stockage des fichiers

Deux espaces de stockage ("buckets") :
- **`ao-raw`** — les fichiers bruts déposés par les utilisateurs (DAO,
  annexes, patrimoine).
- **`ao-exports`** — les documents finaux exportés (PDF, DOCX du mémoire
  technique).

Chaque fichier brut est rangé sous une clé de la forme
`<identifiant_entreprise>/<identifiant_unique>/<nom_du_fichier>` — le nom
original est conservé pour la lisibilité, l'identifiant unique évite toute
collision entre deux fichiers de même nom déposés à des moments différents.
Chaque export est rangé sous `<identifiant_entreprise>/exports/<dossier>/v<version>.<format>`
— la version fait explicitement partie du chemin de stockage, pour ne jamais
écraser un export précédent.

## 5. Redis + ARQ — la file d'attente des tâches de fond

Quatre types de tâches peuvent être mises en file d'attente et traitées par
les processus "worker" séparés de l'API :
1. **`ingest_document`** — le pipeline complet d'ingestion d'un document
   (lecture, extraction de texte, découpage, classification, empreintes
   numériques, indexation) — voir chapitre Horloge A.
2. **`extract_graph`** — l'extraction du graphe de connaissances à partir des
   chunks déjà ingérés, pouvant être relancée indépendamment sans refaire
   tout le parsing.
3. **`extract_dossier_structure`** — l'extraction du plan, des exigences et
   de la checklist administrative d'un dossier.
4. **`classify_dossier_sections`** — la classification des exigences vers les
   sections du plan, rejouable indépendamment de l'extraction précédente.

Le worker peut traiter jusqu'à 2 tâches en parallèle, avec un délai maximum
d'une heure par tâche — une marge nécessaire pour un très gros DAO scanné
nécessitant beaucoup de reconnaissance optique de caractères.

## 6. Le cloisonnement multi-entreprise (multi-tenant), concrètement

Une même installation de l'application peut héberger plusieurs entreprises
clientes, chacune ne voyant strictement jamais les données d'une autre. Ce
cloisonnement n'est **pas** géré par un mécanisme automatique global : il est
appliqué **explicitement, à chaque endroit du code** qui accède aux données —
chaque requête qui liste ou charge une donnée vérifie que son identifiant
d'entreprise correspond bien à celui de l'utilisateur connecté. C'est un
choix qui demande de la rigueur (chaque nouvel endpoint doit penser à ce
filtre), compensé par le fait que la colonne d'entreprise est présente
partout où c'est pertinent, y compris dans Qdrant (filtre de recherche) et
Neo4j (propriété sur chaque entité) — pas seulement dans Postgres.

## 7. Les rôles utilisateurs

Quatre rôles existent : **admin**, **manager**, **redacteur** (rôle par
défaut à la création d'un compte), **consultant**.

| Rôle | Peut lire | Peut écrire/rédiger/exporter | Peut supprimer un document |
|---|---|---|---|
| **admin** | Oui | Oui | Oui, toujours |
| **manager** | Oui | Oui | Oui, sauf restriction fine explicitement configurée sur son compte |
| **redacteur** | Oui | Oui | Non |
| **consultant** | Oui | Non — explicitement bloqué à plusieurs endroits (dépôt de document, promotion en patrimoine, relance d'ingestion, dépôt en conversation) | Non |

Le rôle **admin** a en plus l'exclusivité de certaines actions
d'administration, comme changer le rôle d'un autre utilisateur.

## Ce qu'il faut retenir pour la soutenance

- Le choix de cinq bases différentes n'est pas de la complexité gratuite :
  chacune répond à un besoin qu'aucune des quatre autres ne couvre aussi
  bien (relationnel strict, recherche par sens, relations entre entités,
  gros fichiers, file d'attente).
- Le cloisonnement multi-entreprise est appliqué de façon cohérente à
  travers **toutes** les bases, pas seulement dans la base relationnelle
  principale — un point de rigueur à souligner.
- L'absence d'un outil de migration automatique (Alembic) est un choix
  assumé sur ce projet, pas un oubli : le suivi se fait par des fichiers SQL
  numérotés et rejouables, avec un historique clair de chaque évolution
  récente du schéma.
