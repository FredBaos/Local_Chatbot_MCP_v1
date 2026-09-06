import os
import chromadb
from typing import Any

CHROMA_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "storage", "chroma_db")

# Read optional env var for a default threshold (None means no filtering)
_env_threshold = os.environ.get("CHROMA_DISTANCE_THRESHOLD")
try:
    DEFAULT_CHROMA_DISTANCE_THRESHOLD: float | None = float(_env_threshold) if _env_threshold is not None else None
except Exception:
    DEFAULT_CHROMA_DISTANCE_THRESHOLD = None


def get_chroma_client() -> Any:
    return chromadb.PersistentClient(path=CHROMA_PATH)


def query_knowledge(collection_name: str, query_text: str, limit: int = 3, distance_threshold: float | None = None):
    """
    Queries a targeted external knowledge collection and outputs citations and content text.

    If `distance_threshold` or the env-var `CHROMA_DISTANCE_THRESHOLD` is set,
    results with distances greater than the threshold are excluded.
    """
    client = get_chroma_client()
    try:
        collection = client.get_collection(name=collection_name)
        results = collection.query(query_texts=[query_text], n_results=max(limit * 2, 6), include=["documents", "metadatas", "distances"]) 

        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]
        ids = results.get("ids", [[]])[0]

        effective_threshold = distance_threshold if distance_threshold is not None else DEFAULT_CHROMA_DISTANCE_THRESHOLD

        items = []
        for _id, doc, meta, dist in zip(ids, documents, metadatas, distances):
            if doc is None:
                continue
            if effective_threshold is not None:
                try:
                    if dist is None or float(dist) > float(effective_threshold):
                        continue
                except Exception:
                    pass

            items.append({
                "id": _id,
                "text": doc,
                "metadata": meta,
                # Raw Chroma distance (default L2 space, unbounded) — kept for
                # callers that want a relative relevance signal. Not a
                # calibrated probability; see app.py's confidence transform.
                "distance": float(dist) if dist is not None else None,
            })

            if len(items) >= limit:
                break

        return items
    except Exception as e:
        print(f"Error reading collection {collection_name}: {e}")
        return []
