import os
import uuid
from typing import Any

import chromadb

CHROMA_PATH = os.path.join(os.path.dirname(__file__), "chroma_db")
COLLECTION_NAME = "chat_memory"
_CHROMA_CLIENT = None

# Configurable distance threshold (can be set with environment variable).
# If unset, no distance-based filtering will be applied.
_env_threshold = os.environ.get("CHROMA_DISTANCE_THRESHOLD")
try:
    CHROMA_DISTANCE_THRESHOLD: float | None = float(_env_threshold) if _env_threshold is not None else None
except Exception:
    CHROMA_DISTANCE_THRESHOLD = None


def get_chroma_client() -> Any:
    global _CHROMA_CLIENT
    if _CHROMA_CLIENT is None:
        _CHROMA_CLIENT = chromadb.PersistentClient(path=CHROMA_PATH)
    return _CHROMA_CLIENT


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


def add_paired_memory(session_id: str, user_text: str, assistant_text: str):
    """
    Store a paired user+assistant exchange as a single long-term memory entry.

    This helps the vector DB associate user prompts with the assistant reply
    as a single semantic unit for future retrieval.
    """
    collection = get_memory_collection()
    combined = f"User: {user_text.strip()}\nAssistant: {assistant_text.strip()}"
    if not combined.strip():
        return
    stable_id = str(
        uuid.uuid5(
            uuid.NAMESPACE_DNS,
            f"{session_id}|paired|{combined}",
        )
    )
    metadata = {"session_id": session_id, "paired": True}
    collection.upsert(documents=[combined], metadatas=[metadata], ids=[stable_id])


def delete_session_memory(session_id: str) -> int:
    collection = get_memory_collection()
    results = collection.get(where={"session_id": session_id}, include=["metadatas"])
    ids = results.get("ids", []) or []
    if ids:
        collection.delete(ids=ids)
    return len(ids)


def retrieve_memory(query: str, limit: int = 5, exclude_session_id: str = None, distance_threshold: float | None = None):
    """
    Retrieve semantically-similar long-term memory entries from Chroma.

    - `distance_threshold` (float) if provided will filter out results whose
      returned distance is greater than the threshold. If omitted, the
      environment-level `CHROMA_DISTANCE_THRESHOLD` will be used. If neither
      is set, no distance filtering is applied.
    """
    collection = get_memory_collection()
    # Query for a larger set and filter/limit locally to reduce false positives
    results = collection.query(
        query_texts=[query],
        n_results=max(limit * 4, 12),
        include=["documents", "metadatas", "distances"],
    )

    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    effective_threshold = distance_threshold if distance_threshold is not None else CHROMA_DISTANCE_THRESHOLD

    seen = set()
    filtered = []
    normalized_query = query.strip()
    for doc, meta, dist in zip(docs, metas, distances):
        if not doc:
            continue
        if exclude_session_id and meta and meta.get("session_id") == exclude_session_id:
            continue

        # If a threshold is configured, drop items with distance greater than it
        if effective_threshold is not None:
            try:
                if dist is None or float(dist) > float(effective_threshold):
                    continue
            except Exception:
                # If distance parsing fails, skip distance filtering conservatively
                pass

        normalized = doc.strip()
        if normalized in seen:
            continue

        # Ignore exact copies of the current user query
        if normalized.casefold() == normalized_query.casefold():
            continue

        seen.add(normalized)
        filtered.append({
            "text": normalized,
            "metadata": meta,
            "distance": float(dist) if dist is not None else None,
        })
        if len(filtered) >= limit:
            break

    return filtered
