import os
import uuid

import chromadb
from chromadb.config import Settings

CHROMA_PATH = os.path.join(os.path.dirname(__file__), "chroma_db")
COLLECTION_NAME = "chat_memory"


def get_chroma_client():
    return chromadb.PersistentClient(
        path=CHROMA_PATH,
        settings=Settings(allow_reset=True, anonymized_telemetry=False),
    )


def get_memory_collection():
    client = get_chroma_client()
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def add_memory(session_id: str, role: str, content: str):
    collection = get_memory_collection()
    text = content.strip()
    if not text:
        return
    stable_id = str(
        uuid.uuid5(
            uuid.NAMESPACE_DNS,
            f"{session_id}|{role}|{text}",
        )
    )
    collection.upsert(
        documents=[text],
        metadatas=[{"session_id": session_id, "role": role}],
        ids=[stable_id],
    )


def retrieve_memory(query: str, limit: int = 5, exclude_session_id: str = None):
    collection = get_memory_collection()
    results = collection.query(
        query_texts=[query],
        n_results=max(limit * 4, 12),
    )
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]

    seen = set()
    filtered = []
    normalized_query = query.strip()
    for doc, meta in zip(docs, metas):
        if not doc:
            continue
        if exclude_session_id and meta and meta.get("session_id") == exclude_session_id:
            continue

        normalized = doc.strip()
        if normalized in seen:
            continue

        # Ignore exact copies of the current user query, even if the payload is
        # stored as plain text or with role tags in the embedding content.
        if normalized.casefold() == normalized_query.casefold():
            continue

        seen.add(normalized)
        filtered.append({"text": normalized, "metadata": meta})
        if len(filtered) >= limit:
            break

    return filtered
