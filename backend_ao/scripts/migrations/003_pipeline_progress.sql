-- Migration V2.1 — traçabilité fine du pipeline d'ingestion + reprise OCR
-- Additive uniquement, idempotent (rejouable sans casse).
--
-- Motivation : un document dont l'extraction du graphe a échoué (ou dont
-- l'OCR a été interrompu par un timeout de tâche sur un gros scan) n'avait
-- aucun moyen d'être relancé proprement depuis l'interface, et une
-- ré-ingestion complète laissait des vecteurs orphelins dans la base
-- vectorielle (jamais supprimés avant réinsertion — corrigé côté code,
-- voir app/workers/ingest.py).

BEGIN;

-- ============================================================
-- 1. documents.pipeline_stages — horodatage début/fin par phase
-- ============================================================
-- Structure : {"parse": {"started_at": "...", "finished_at": "..."},
--              "chunk": {...}, "classify": {...}, "embed": {...},
--              "index": {...}, "graph": {...}}
-- JSONB plutôt que des colonnes rigides : une phase future s'ajoute sans
-- nouvelle migration.
ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS pipeline_stages JSONB NOT NULL DEFAULT '{}'::jsonb;

-- ============================================================
-- 2. documents.ocr_progress — reprise page par page d'un OCR interrompu
-- ============================================================
-- Structure : {"resume_page": N, "pages": {"1": {"text": "...", "confidence": 0.9}, ...}}
-- Vidé (remis à '{}') dès qu'une ingestion se termine avec succès — ne sert
-- que pendant une tentative en cours ou après un échec/interruption.
ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS ocr_progress JSONB NOT NULL DEFAULT '{}'::jsonb;

COMMIT;
