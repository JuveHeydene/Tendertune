# Comprendre l'application — introduction et mode d'emploi de ces documents

## À qui s'adresse ce document

Tu n'as pas besoin de savoir coder pour lire ce qui suit. Chaque terme technique
est expliqué la première fois qu'il apparaît, et un glossaire complet se trouve
en fin de ce fichier. L'objectif : que tu puisses expliquer, avec assurance et
sans réciter par cœur, **ce que fait l'application, comment, et pourquoi elle a
été construite ainsi** — y compris ses limites actuelles, qui font partie
intégrante d'un travail honnête et sont d'excellents points à assumer en
soutenance plutôt qu'à cacher.

Tout ce qui est écrit ici a été vérifié directement dans le code source réel de
l'application au 13 septembre 2026 — pas dans une documentation qui aurait pu
devenir obsolète, pas de mémoire. Chaque affirmation technique importante est
accompagnée du nom du fichier de code où elle a été constatée, pour qu'on
puisse toujours vérifier.

## Ce que fait l'application, en une phrase

C'est un assistant qui aide une entreprise du BTP à répondre à un **appel
d'offres (AO)** : on lui donne le dossier de consultation (le cahier des
charges envoyé par le client), l'entreprise garde en mémoire ses anciens
projets, ses certifications, ses méthodes de travail (son **patrimoine**), et
l'application aide à rédiger le **mémoire technique** (le document de
candidature) section par section, en s'appuyant sur ce patrimoine et sur les
exigences précises du dossier en cours.

## Les deux "horloges"

Le cœur du fonctionnement se comprend en deux grands mouvements, qu'on appelle
ici par commodité **Horloge A** et **Horloge B** — ce ne sont pas des noms
techniques du code, mais une façon de séparer clairement les deux temps forts
du système :

```
HORLOGE A — L'INGESTION (en arrière-plan, dès qu'un document est déposé)
─────────────────────────────────────────────────────────────────────
Un PDF/DOCX/XLSX est déposé
   → le système le lit, le découpe en petits morceaux de texte ("chunks")
   → il transforme chaque morceau en une empreinte numérique ("embedding")
   → il range ces empreintes dans une base spécialisée pour la recherche
     par similarité de sens (Qdrant)
   → en parallèle, il essaie de reconnaître les entités importantes
     (entreprises, projets, certifications...) et leurs relations, et les
     range dans une base de graphe (Neo4j)
   → le document est prêt à être utilisé pour répondre à des questions

HORLOGE B — LA GÉNÉRATION (en direct, pendant une conversation)
─────────────────────────────────────────────────────────────────────
L'utilisateur pose une question ou demande de rédiger une section
   → le système comprend l'intention (question libre ? rédaction ? export ?)
   → il découpe la demande en sous-questions précises si besoin
   → il interroge le patrimoine déjà indexé (Horloge A) via 5 "experts"
     spécialisés, avec un mécanisme d'auto-vérification de la pertinence
   → il assemble les meilleurs extraits trouvés
   → il rédige une réponse ou une section de mémoire, en citant ses sources
   → le résultat est affiché, sauvegardé, et peut être exporté en PDF/Word
```

Horloge A tourne **en tâche de fond** (un "worker" séparé, pour ne jamais
bloquer l'interface pendant qu'un gros PDF est traité). Horloge B tourne **en
direct**, pendant que l'utilisateur regarde sa conversation se remplir de
texte en temps réel.

## Les briques techniques, vue d'ensemble

L'application n'utilise pas une seule base de données, mais **cinq systèmes de
stockage différents**, chacun choisi pour un usage précis (le détail complet
est dans [04_Bases_de_donnees.md](04_Bases_de_donnees.md)) :

| Système | Rôle en une phrase |
|---|---|
| **Postgres** | La base de données "classique" — utilisateurs, documents, dossiers, exigences, conversations, tout ce qui a une structure de type tableau |
| **Qdrant** | Une base spécialisée dans la recherche "par sens" (recherche vectorielle) — retrouver un passage pertinent même si les mots exacts diffèrent |
| **Neo4j** | Une base de graphe — pour représenter des relations entre entités (« telle entreprise a travaillé sur tel projet ») |
| **MinIO** | Le "disque dur" des fichiers bruts (PDF originaux, exports générés) |
| **Redis (+ ARQ)** | La file d'attente des tâches de fond (ingestion, extraction de graphe) |

Et un seul moteur d'intelligence artificielle générative, **Ollama**, qui fait
tourner localement (pas dans le cloud) un modèle de langage nommé
**`granite3.3:2b`** (IBM Granite 3.3, 2 milliards de paramètres) pour tout ce
qui demande de la génération de texte ou de la décision, et un second modèle,
**`nomic-embed-text`**, uniquement pour transformer du texte en empreintes
numériques (embeddings). Le fait qu'un seul petit modèle serve à toutes les
tâches de génération est un choix assumé (coût, confidentialité, exécution
locale) qui a des conséquences directes sur la fiabilité — abordées en détail
dans [03_Interventions_du_LLM.md](03_Interventions_du_LLM.md).

## Comment lire la suite

| Fichier | Contenu |
|---|---|
| [01_Horloge_A_Ingestion.md](01_Horloge_A_Ingestion.md) | Tout le trajet d'un document, de l'upload jusqu'à son indexation complète |
| [02_Horloge_B_Generation.md](02_Horloge_B_Generation.md) | Tout le trajet d'une question ou d'une demande de rédaction, avec les agents, le superviseur et le CRAG |
| [03_Interventions_du_LLM.md](03_Interventions_du_LLM.md) | La liste complète et exhaustive de chaque endroit où l'IA générative est appelée : le prompt exact donné, le format de réponse exigé, à qui appartient le résultat |
| [04_Bases_de_donnees.md](04_Bases_de_donnees.md) | Où chaque donnée est stockée, et pourquoi cet endroit précis a été choisi |

Les diagrammes de séquence mis à jour se trouvent dans
`Fichier/diagrams/drawio et plantuml/diagramme_sequence_ingestion&Horloge/`
(fichiers `01_diagramme_sequence_ingestion.puml` et
`02_diagramme_sequence_generation.puml`) — ils illustrent visuellement ce que
ces documents décrivent avec des mots.

## Glossaire (dans l'ordre où les termes deviennent utiles)

- **AO (appel d'offres)** : une procédure où un client (souvent public)
  demande à plusieurs entreprises de proposer une offre pour un projet de
  construction ; l'entreprise qui répond doit convaincre avec un dossier de
  candidature.
- **DAO (dossier d'appel d'offres)** : l'ensemble des documents envoyés par le
  client pour décrire ce qu'il demande (règlement de consultation, cahier des
  charges, bordereau de prix...).
- **RC / CCAP / CCTP / DPGF / BPU** : les grandes familles de documents dans
  un DAO — RC = Règlement de Consultation (les règles du jeu de l'AO),
  CCAP = Cahier des Clauses Administratives Particulières (contrat, pénalités,
  délais), CCTP = Cahier des Clauses Techniques Particulières (les
  spécifications techniques à respecter), DPGF/BPU = les documents de prix
  (Décomposition du Prix Global et Forfaitaire / Bordereau des Prix
  Unitaires).
- **Mémoire technique** : le document que l'entreprise rédige pour candidater,
  expliquant son savoir-faire, ses moyens, sa méthodologie — c'est ce que
  l'application aide à écrire.
- **Patrimoine** : l'ensemble des documents de référence de l'entreprise
  (anciens projets, CV, certifications) qui ne concernent pas un AO précis,
  mais servent d'exemple/de preuve pour tous les AO futurs.
- **Exigence** : une obligation précise extraite du DAO ("l'entreprise doit
  fournir une attestation décennale", "le délai d'exécution est de 18 mois").
- **Chunk** : un petit morceau de texte issu du découpage d'un document — on
  ne peut pas donner un PDF de 200 pages entier à une IA, donc on le découpe.
- **Embedding** : la transformation d'un texte en une liste de nombres (un
  "vecteur") qui capture son sens, de façon à ce que deux textes proches en
  sens aient des vecteurs proches, même si les mots utilisés sont différents.
- **RAG (Retrieval-Augmented Generation, génération augmentée par
  récupération)** : la technique qui consiste à d'abord *chercher* les
  passages pertinents dans une base documentaire, puis à donner ces passages
  à une IA générative pour qu'elle rédige sa réponse en s'appuyant dessus —
  plutôt que de laisser l'IA "inventer" depuis ses seules connaissances
  générales.
- **LLM (Large Language Model, grand modèle de langage)** : le type d'IA
  générative utilisée (ici, `granite3.3:2b`, exécuté via Ollama).
- **Ollama** : le logiciel qui fait tourner les modèles de langage
  localement, sur le serveur de l'entreprise, sans passer par un service
  cloud externe.
- **Prompt** : le texte d'instructions envoyé au LLM pour lui dire quoi faire
  et sous quelle forme répondre.
- **CRAG (Corrective RAG, RAG correctif)** : un mécanisme qui, après une
  recherche, évalue si ce qui a été trouvé est réellement pertinent, et si
  non, corrige le tir (reformule la question, élargit la recherche) avant de
  répondre — détaillé dans [02_Horloge_B_Generation.md](02_Horloge_B_Generation.md).
- **Expert (dans ce système)** : un des cinq "spécialistes" de recherche
  documentaire (juridique, technique, financier, graphe, patrimoine),
  chacun limité à une portion du patrimoine documentaire pertinente pour son
  domaine.
- **Superviseur** : le composant qui décide, pour chaque message reçu, quelle
  est l'intention de l'utilisateur et comment découper la demande en
  sous-questions à envoyer aux experts.
- **Citation `[n]`** : dans une réponse générée, un renvoi numéroté vers
  l'extrait de document qui justifie une affirmation — l'utilisateur peut
  ainsi vérifier la source de chaque fait avancé.
- **Schéma JSON contraint** : une technique où on force le LLM, au niveau du
  décodage (mot par mot), à ne produire QUE du texte qui respecte
  exactement une structure attendue — par opposition à lui demander
  "gentiment" de répondre en JSON sans garantie qu'il obéisse.
- **Multi-tenant** : l'application peut héberger plusieurs entreprises
  clientes ("tenants") sur la même installation, chacune voyant strictement
  ses propres documents et jamais ceux d'une autre.
