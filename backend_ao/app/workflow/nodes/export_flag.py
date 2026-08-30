def export_doc(state: dict) -> dict:
    return {
        **state,
        "export_requested": True,
        "answer": "Préparation de l'export DOCX du dossier lié à cette conversation.",
    }
