# Tendertune — Guide de réalisation (phase 2 : fine-tuning)

**Dépôt** : `github.com/JuveHeydene/Tendertune` (ce dossier, `Projets/AI_ML/Tendertune`). La phase 1 (assistant RAG) est déjà dans `backend_ao/` et `frontend_ao/` ; ce guide décrit la phase 2, qui vit dans `finetuning/`.

**Cadre** : partenariat école–entreprise ENSPY × Elatech. Les données d'Elatech restent **hors du dépôt** (`finetuning/data/` est ignoré par git).

**But** : montrer que tu sais *entraîner* un LLM, pas seulement l'appeler. Fine-tuning LoRA de **IBM Granite 3.3 2B** — le modèle qui tourne déjà dans l'assistant (Ollama) — sur des questions-réponses tirées des dossiers d'appels d'offres, puis comparaison honnête **base 2B vs base 8B vs fine-tuné vs RAG vs fine-tuné + RAG**. L'histoire à raconter : un petit modèle spécialisé qui rattrape un modèle 4 fois plus gros, sur une carte de 16 Go.

**Ce que le CV affirme (à pouvoir démontrer)** : LoRA sur Granite 3.3 2B Instruct, 4 800 paires Q/R (300 vérifiées à la main), +11 pts F1 sur la base et niveau de Granite 3.3 8B, −38 % d'hallucinations avec fine-tuné + RAG, servi par Ollama à environ 85 tokens/s sur la RTX A5000 Laptop (16 Go), suivi MLflow.

## Stack
Python 3.11, `transformers`, `peft`, `trl` (SFTTrainer), `bitsandbytes`, `datasets`, MLflow, RAGAS, `llama.cpp` (conversion GGUF) et Ollama pour le service. Modèle de base : `ibm-granite/granite-3.3-2b-instruct` (licence Apache 2.0) ; comparaison avec `granite-3.3-8b-instruct`. Matériel : **RTX A5000 Laptop, 16 Go de VRAM, 64 Go de RAM** — un 2B se fine-tune en LoRA bf16 sans quantification ; le 8B passe en QLoRA 4 bits si tu veux aussi le fine-tuner.

## Arborescence
```
finetuning/
  data/            # NON commité (corpus Elatech) ; data/README.md décrit la provenance
  src/build_dataset.py  src/train.py  src/evaluate.py  src/serve.sh
  configs/qlora-7b.yaml
  reports/         # tableaux de résultats commités
.github/workflows/finetuning.yml   # lint + tests unitaires de build_dataset
```

## Phases

### Phase 1 — Dataset (3–4 jours)
1. Extraire les chunks déjà parsés par BTP_RAG (Docling) depuis Qdrant ou PostgreSQL.
2. Générer des paires Q/R avec un LLM « professeur », puis **valider à la main un échantillon de 100 paires**. Documenter le taux d'erreur relevé.
3. Séparer train, validation et test **par document** (aucun document commun entre les jeux), pour éviter les fuites.

**Vérification** : `data/stats.json` (nombre de paires, longueur moyenne, répartition par type de document) ; aucun `doc_id` commun entre les jeux.

### Phase 2 — Entraînement QLoRA (4–5 jours)
1. LoRA r=16, alpha=32, sur les modules q, k, v et o (bf16, sans quantification pour le 2B) ; 2 à 3 epochs ; `max_seq_length` adapté aux chunks.
2. Journaliser dans MLflow : hyperparamètres, courbe de perte, VRAM maximale, durée.

**Vérification** : la perte de validation baisse puis se stabilise ; l'adaptateur se recharge et répond à 5 questions témoins.

### Phase 3 — Évaluation (3 jours)
Cinq configurations sur le même jeu de test : Granite 2B base, Granite 8B base, 2B fine-tuné, 2B base + RAG, 2B fine-tuné + RAG. Métriques : exact match ou F1, fidélité (RAGAS), taux d'hallucination sur 50 cas vérifiés à la main, latence.

**Vérification** : `reports/results.md` avec le tableau et **ton interprétation**, même si le fine-tuning n'apporte rien (un résultat négatif bien expliqué reste un très bon sujet d'entretien).

### Phase 4 — Service (2 jours)
Fusionner l'adaptateur LoRA dans le modèle, convertir en GGUF (`llama.cpp`, quantification Q4_K_M), créer un `Modelfile` Ollama `granite3.3-tender`, puis mettre `LLM_MODEL=granite3.3-tender` dans `.env` : l'assistant l'utilise sans changer une ligne de code. (vLLM avec `--enable-lora` reste une option pour servir plusieurs adaptateurs.)

**Vérification** : `ollama run granite3.3-tender` répond ; tu as mesuré le débit (tokens/s) et le temps de réponse p95 sur la A5000.

## Ligne CV à mettre à jour une fois terminé
« LoRA fine-tuning of Granite 3.3 2B on N French tender Q&A pairs: +X pts F1 over base, on par with Granite 3.3 8B; Y % fewer hallucinations combined with RAG; served with Ollama at Z tok/s on an RTX A5000 (16 GB). »
