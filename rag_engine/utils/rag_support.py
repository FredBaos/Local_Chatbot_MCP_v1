import re
from typing import Optional


def get_rag_setup_context(user_text: str) -> Optional[str]:
    text = (user_text or "").strip().lower()
    if not text:
        return None

    triggers = [
        "enable rag",
        "use rag",
        "rag with",
        "car_specs",
        "car specs",
        "knowledge base",
        "vector database",
        "retrieval",
    ]

    if any(trigger in text for trigger in triggers):
        return (
            "RAG is already enabled for this app through the car_specs collection. "
            "The app queries the Chroma collection named 'car_specs' in the /analyze endpoint "
            "and uses it as external context for relevant questions."
        )

    return None
