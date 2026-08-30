def chitchat(state: dict) -> dict:
    return {
        **state,
        "answer": (
            "Bonjour. Posez une question sur le patrimoine indexé, demandez de rédiger une section "
            "(« rédige la présentation de l'entreprise ») ou d'exporter le document (« exporte le DOCX »)."
        ),
    }
