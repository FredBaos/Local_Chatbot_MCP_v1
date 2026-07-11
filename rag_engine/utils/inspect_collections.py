import json
import os
import sys
import sqlite3
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rag_engine.storage.chroma_memory import get_chroma_client


def inspect_sqlite_db(db_path: str | None = None) -> dict[str, Any]:
    db_path = db_path or os.path.join(os.path.dirname(os.path.dirname(__file__)), "storage", "chat_history.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [row[0] for row in cursor.fetchall()]

    summary: dict[str, Any] = {"db_path": db_path, "tables": tables}
    if "messages" in tables:
        cursor.execute("SELECT COUNT(*) FROM messages")
        summary["message_count"] = cursor.fetchone()[0]
        cursor.execute("SELECT session_id, COUNT(*) FROM messages GROUP BY session_id ORDER BY COUNT(*) DESC LIMIT 10")
        summary["top_sessions"] = [{"session_id": row[0], "message_count": row[1]} for row in cursor.fetchall()]

    conn.close()
    return summary


def inspect_chroma_collection(collection_name: str) -> dict[str, Any]:
    client = get_chroma_client()
    try:
        collection = client.get_collection(name=collection_name)
    except Exception:
        return {"collection_name": collection_name, "count": 0}

    return {"collection_name": collection_name, "count": collection.count()}


def summarize_collections() -> list[dict[str, Any]]:
    client = get_chroma_client()
    try:
        collections = client.list_collections()
    except Exception:
        return []

    return [{"collection_name": item.name, "count": item.count()} for item in collections]


def print_overview() -> None:
    sqlite_summary = inspect_sqlite_db()
    print("SQLite overview")
    print(json.dumps(sqlite_summary, indent=2))

    print("\nChroma collections")
    print(json.dumps(summarize_collections(), indent=2))


if __name__ == "__main__":
    print_overview()
