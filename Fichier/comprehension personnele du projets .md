# Erreur quil faisait 

Il ne donnait pas suite a une page parse qui a plus de 8000 caractere 

donc c'etait perdu 

pour le traitement de mise en bd neo4j il ne fait aucun fuzzy match 

donc il pase a coter de btp construction vs btp constructions 

un documents peu avoir 1000 parent mais lui ne prends que 12 



# MES NOTES A MOI 

LE FICHIER EST UPLOAD VIA API et stocker dans minio 

Les meta donnes du document sont stockés dans postgres nom du fichier et chemin et un job redis arq est directement ajouter dans le queue.


ensuite le document est reccuperer de minio et parser par 

le processus docling paddle pypdf 

on commence d'abord par voir si le pdf est numerique ou scanner 

seuil : 40 caractères / page.
PDF_TEXT_MIN_CHARS_PER_PAGE = 40

≥ 40 → PDF numérique
< 40 → PDF scan 

docling c'est pas de OCR c'est du document understanding 

PARSE FIN
  → CHUNKING  (chunk.py : chunk_document)
  → Postgres  (table chunks)
  → Ollama embeddings
  → Qdrant
  → status = ready
  → enqueue extract_graph (Neo4j)

  PDF
  pypdf extract_text()  ← jamais d’OCR
       │
       ├─ densité ≥ 40  (numérique)
       │     Docling → si OK : markdown structuré
       │     sinon pypdf
       │
       └─ densité < 40  (scan)
             Paddle GPU → si cuDNN KO → Paddle CPU
             si Paddle KO → Docling
             si tout KO + un peu de texte → pypdf-sparse
             sinon failed

Ensuite (toujours) : chunk → Postgres → embed → Qdrant → ready → graphe



DONC APRES LE PARSE on applique directement le chunking parent child avant de stocker en BD : 

parse_file → ParsedDocument.pages[]
                ↓
         chunk_document(parsed)   ← ICI parent/child
                ↓
         Postgres (tous)
         Qdrant (surtout les enfants)

on fonctionne par page donc la page une sera par exemple parse , si c'est superieure a 1100 , on procede par chunking parent enfants 

1. parse_file() 
   → ParsedDocument (pages structurées)

2. chunk_document()
   → Pour chaque page :
      a. Créer un parent (texte complet, 8000 max)
      b. Découper en fenêtres de 1100 caractères avec chevauchement de 120
      c. Créer un enfant par fenêtre
      d. Retourner [parent, enfant1, enfant2, ...]

3. Stockage Postgres :
   → Tous les chunks (parents + enfants)

4. Embeddings + Qdrant :
   → Seulement les enfants (ou tous si pas d'enfants)
   → Pour la recherche sémantique

5. Enqueue extract_graph :
   → Job Neo4j pour construire le graphe de connaissances


   COnstruction du graph 


   seulement les enfant dans le embedd car la recherche semantique est plus efficace sur court chunks 


# NEO4J EXTRACTION 

   Postgres (chunks parents)
    ↓
Ollama (extraction entités/relations)
    ↓
Neo4j (MERGE des entités et relations)
    ↓
Document marqué graph_extracted = True


Pourquoi seulement les parents ?

Les parents contiennent le texte complet des sections (jusqu'à 8000 caractères)

Les enfants sont des fragments pour la recherche sémantique

Pour l'extraction de graphe, on veut le contexte global, pas des fragments




# HORLOGE B : 

Quand le user entre son texte on detecte dabord intention de son texte 

1. Historique → _message_history(conv)
   └─ Récupère tous les messages triés chronologiquement

2. Exécution du graph → _run_graph(query, tenant_id, history)
   └─ Appelle le workflow LangGraph

3. Analyse de l'intention retournée
   ├─ "export" → export du document
   ├─ "run_section" → rédaction d'une section
   ├─ "smalltalk" → réponse conversationnelle
   └─ "hybrid_rag" → réponse RAG classique

4. Traitement selon l'intention


START
  ↓
route_node()  ← Détection de l'intention
  ↓
├─ Intent: "smalltalk" → chitchat_node → END
├─ Intent: "run_section" → retrieve_node → generate_node → END
├─ Intent: "export" → export_node → END
└─ Intent: "hybrid_rag" → retrieve_node → generate_node → END

┌─────────────────────────────────────────────────────────────────────┐
│                          UTILISATEUR                               │
│                      "Rédige la section immobilier"                │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   1. ROUTE (détection d'intention)                 │
│  • "rédige" → run_section                                          │
│  • pick_section() → key="immobilier", title="Immobilier"           │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   2. RETRIEVE (recherche vectorielle)              │
│  • Requête: "section immobilier patrimoine"                        │
│  • Récupération: 8 chunks pertinents                               │
│  • Formatage des citations                                         │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   3. BUILD PROMPT                                  │
│  • Contexte: chunks récupérés                                      │
│  • Historique: 3 derniers messages                                 │
│  • Instruction: rédiger la section immobilier                      │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   4. OLLAMA GENERATION (Streaming)                 │
│  • Appel à llama3.2                                                │
│  • Tokens envoyés en SSE au client                                 │
│  • Construction progressive du markdown                            │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   5. PERSISTANCE                                   │
│  • ensure_dossier() → création/récupération du dossier            │
│  • save_generation() → sauvegarde en base                          │
│  • Ajout du message assistant                                      │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   6. RÉPONSE                                       │
│  • SSE preview: aperçu complet                                     │
│  • SSE done: confirmation                                          │
│  • Message: "Section « Immobilier » rédigée."                     │
└─────────────────────────────────────────────────────────────────────┘