-- Migration 004 — liaison exigences ↔ sections du plan.
-- Additive uniquement, idempotent (rejouable sans casse).
--
-- Motivation : les exigences du DAO (table `exigences`) et les sections du
-- mémoire technique (`outline_items`) vivaient jusqu'ici dans deux circuits
-- totalement indépendants — couvrir une exigence (recherche patrimoine)
-- n'avait aucun effet sur la rédaction, et `generate_section` composait son
-- prompt sans savoir quelles exigences du DAO cette section devait traiter.
-- Cette migration ajoute la table de liaison N:N qui permet : (1) une
-- classification automatique par LLM (quelle exigence concerne quelle
-- section), (2) une confirmation/exclusion humaine de ces propositions,
-- (3) des liens ajoutés/retirés manuellement, indépendamment du LLM, et
-- (4) l'injection de la liste réelle d'exigences dans le prompt de
-- génération (app/workflow/nodes/generate_section.py).

BEGIN;

-- ============================================================================
-- 1. exigence_sections — table de liaison N:N exigence <-> section (outline)
-- ============================================================================
CREATE TABLE IF NOT EXISTS exigence_sections (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    exigence_id     UUID NOT NULL REFERENCES exigences (id) ON DELETE CASCADE,
    outline_item_id UUID NOT NULL REFERENCES outline_items (id) ON DELETE CASCADE,
    -- 'llm' = proposé par la classification automatique ; 'humain' = ajouté
    -- manuellement (auto-confirmé, un humain qui ajoute a déjà décidé).
    origine         VARCHAR(16) NOT NULL DEFAULT 'humain'
                    CHECK (origine IN ('llm', 'humain')),
    -- 'proposee' (LLM, pas encore relu) et 'confirmee' sont TOUTES LES DEUX
    -- des liaisons actives (injectées dans le prompt) — la revue humaine est
    -- une couche de confiance additionnelle, pas un verrou bloquant. Seule
    -- 'exclue' désactive la liaison ; on la CONSERVE (pas de DELETE) pour
    -- qu'une reclassification ultérieure ne resuggère pas ce qu'un humain a
    -- déjà explicitement rejeté (voir ON CONFLICT DO NOTHING côté appelant).
    statut          VARCHAR(16) NOT NULL DEFAULT 'confirmee'
                    CHECK (statut IN ('proposee', 'confirmee', 'exclue')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT unique_exigence_section UNIQUE (exigence_id, outline_item_id)
);

CREATE INDEX IF NOT EXISTS idx_exigence_sections_outline ON exigence_sections (outline_item_id, statut);
CREATE INDEX IF NOT EXISTS idx_exigence_sections_exigence ON exigence_sections (exigence_id, statut);

-- ============================================================================
-- 2. dossiers.classification_status / classification_error — suivi du job
--    "classifier les exigences par section" (même esprit que dao_status,
--    mais ici un vrai job ARQ dédié donc un vrai statut stocké).
-- ============================================================================
ALTER TABLE dossiers ADD COLUMN IF NOT EXISTS classification_status VARCHAR(32);
ALTER TABLE dossiers ADD COLUMN IF NOT EXISTS classification_error TEXT;

COMMIT;
