-- Migration 006 — rubriques de pièces administratives ajoutées à la main.
-- Additive uniquement, idempotent (rejouable sans casse).
--
-- Motivation : dossier_pieces.source n'acceptait que 'rc' (extrait du
-- règlement de consultation) ou 'standard' (liste par défaut) — aucune
-- valeur pour une pièce ajoutée manuellement par un utilisateur (ex. une
-- attestation spécifique à ce marché, non prévue par la liste standard ni
-- détectée dans le RC). 'manuel' comble ce trou (§ section pièces
-- administratives — ajout de rubrique dynamique avant dépôt).

BEGIN;

ALTER TABLE dossier_pieces DROP CONSTRAINT IF EXISTS dossier_pieces_source_check;
ALTER TABLE dossier_pieces ADD CONSTRAINT dossier_pieces_source_check
    CHECK (source IN ('rc', 'standard', 'manuel'));

COMMIT;
