-- Migration 005 — corrélation retrieval_traces <-> génération de section.
-- Additive uniquement, idempotent (rejouable sans casse).
--
-- Motivation : `retrieval_traces` (une ligne par tentative CRAG — requête,
-- filtres, grade, chunks retournés, abstention) était déjà écrite depuis le
-- début (app/rag/experts.py) mais jamais consultable : ni endpoint, ni
-- lien fiable vers la génération qu'elle a nourrie. `generation_id` existe
-- bien sur la table mais ne peut PAS servir de clé de liaison directe : la
-- retrieval se fait dans une transaction séparée, commitée avant même que
-- la Generation existe (chaque appel run_expert ouvre sa propre session et
-- commit). Une vraie FK generation_id ne peut donc jamais être satisfaite
-- à l'insertion. `trace_batch_id` est une clé de corrélation SANS contrainte
-- FK, générée côté appelant AVANT la recherche et recopiée dans
-- generations.context_snapshot une fois la génération sauvegardée — c'est
-- cette clé, pas generation_id, qui relie une génération à ses traces.

BEGIN;

ALTER TABLE retrieval_traces ADD COLUMN IF NOT EXISTS trace_batch_id UUID;
CREATE INDEX IF NOT EXISTS idx_retrieval_traces_batch ON retrieval_traces (trace_batch_id);

COMMIT;
