"""Tests classification section_type — couche 1 (heuristique), déterministe,
sans réseau. La couche 2 (LLM) n'est pas testée ici (nécessite Ollama)."""

from __future__ import annotations

from app.ingest.classify_section import classify_section_type_heuristic


def test_detects_ccap_from_heading():
    result = classify_section_type_heuristic(
        "Cahier des Clauses Administratives Particulières", "Article 8 — Pénalités"
    )
    assert result == "ccap"


def test_detects_cctp_from_body_text_no_heading():
    result = classify_section_type_heuristic(None, "Le présent CCTP définit les spécifications...")
    assert result == "cctp"


def test_detects_rc_variant_reglement_de_la_consultation():
    result = classify_section_type_heuristic("Règlement de la consultation", "Article 1")
    assert result == "rc"


def test_detects_dpgf():
    result = classify_section_type_heuristic(
        None, "DÉCOMPOSITION DU PRIX GLOBAL ET FORFAITAIRE\nLot 1 : Gros œuvre"
    )
    assert result == "dpgf"


def test_detects_bpu():
    result = classify_section_type_heuristic("Bordereau des prix unitaires", "")
    assert result == "bpu"


def test_detects_memoire_technique():
    result = classify_section_type_heuristic(None, "Le présent mémoire technique décrit...")
    assert result == "memoire"


def test_detects_reference_chantier():
    result = classify_section_type_heuristic(
        None, "Attestation de bonne exécution — Chantier Gare de Nantes"
    )
    assert result == "reference"


def test_returns_none_when_no_canonical_keyword():
    result = classify_section_type_heuristic("Introduction générale", "Bonjour, ceci est un texte quelconque.")
    assert result is None


def test_case_insensitive():
    result = classify_section_type_heuristic(None, "cahier des clauses techniques particulieres")
    assert result == "cctp"
