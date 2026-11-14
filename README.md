# Tendertune — AI assistant for construction tender files

> ENSPY × Elatech school–industry partnership. Elatech, a construction company, asked the National Advanced School of Engineering of Yaoundé (ENSPY) for help answering public tenders; I was selected to design and build the solution end to end.

Answering a public tender means reading hundreds of pages (specifications, bills of quantities, schedules, administrative rules — often scanned) and proving, requirement by requirement, that the company complies. Tendertune reads the whole tender file, retrieves the relevant passages, and **drafts cited compliance answers that an engineer reviews before export**.

The project has two phases:

1. **Assistant (RAG)** — ingestion, OCR, hybrid retrieval, GraphRAG and a LangGraph workflow with human-in-the-loop.
2. **Fine-tuning (TenderTune)** — LoRA fine-tuning of IBM Granite 3.3 2B (the assistant's production model) on French tender Q&A, compared against the base model, Granite 3.3 8B, RAG, and fine-tuned + RAG. See [GUIDE.md](GUIDE.md).

## Architecture

```text
 Upload (PDF, DOCX, XLSX, scans)
        |
        v
 FastAPI ---> MinIO (raw files)
        |
        v  ARQ job queue (Redis)
 Worker: parse (Docling) -> OCR (PaddleOCR PP-Structure) -> classify section -> chunk
        |                                   |
        v                                   v
 Qdrant (nomic-embed-text vectors)    Neo4j (entities + relations, fuzzy matching)
        \                                   /
         v                                 v
   Filtered dense retrieval + parent-page expansion + BGE-reranker-v2-m3 / GraphRAG
                         |
                         v
      LangGraph supervisor + experts: extract requirements -> draft cited answers
                         |
                         v
      Human review (approve / edit) -> export (DOCX / PDF)
```

## Stack

| Layer | Tools |
|---|---|
| API and jobs | FastAPI, ARQ + Redis, PostgreSQL (SQLAlchemy, pgvector), MinIO |
| Documents | Docling, PaddleOCR (PP-Structure), PyMuPDF, python-docx, openpyxl |
| Retrieval | Qdrant, nomic-embed-text embeddings, metadata filters (section type, document role), parent-page expansion, BGE-reranker-v2-m3 cross-encoder, LlamaIndex |
| Graph | Neo4j, RapidFuzz entity matching |
| Orchestration | LangGraph, LangChain |
| LLM | IBM Granite 3.3 2B via Ollama (fine-tuned LoRA in phase 2) |
| Hardware | NVIDIA RTX A5000 Laptop (16 GB VRAM), 64 GB RAM |
| Front end | React 19 + Vite |
| Delivery | Docker Compose (7 services), optional GPU overlay |

## Quick start

```bash
cp .env.example .env                       # then change every secret
ollama pull granite3.3:2b
ollama pull nomic-embed-text
docker compose up -d                       # CPU
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d   # NVIDIA GPU
```

- API: `http://localhost:8000/docs`
- Front end: `http://localhost:5174`

Changing `EMBED_MODEL` requires re-indexing and setting `EMBED_DIM` (the API refuses to mix vector sizes in one collection).

## Evaluation

Methodology in [`Fichier/Methodologie_calcul_metriques.md`](Fichier/Methodologie_calcul_metriques.md): a gold set of questions built with Elatech engineers, each linked to the passages that answer it.

| Metric | What it measures |
|---|---|
| Recall@10, MRR@10 | Does retrieval find the right passages, and how high are they ranked? |
| Faithfulness (RAGAS) | Is every claim in the answer supported by the retrieved passages? |
| CER on scanned pages | OCR character error rate |
| Time to first draft | Engineer time to produce a compliance memo, with vs. without the assistant |

## Data and confidentiality

Elatech's tender files are **not** in this repository. Use public tender documents (for example ARMP in Cameroon or BOAMP in France) to try the assistant.

## Author

Adriel Juve SALONG — [github.com/JuveHeydene](https://github.com/JuveHeydene)
