import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rag_engine.storage.database import DB_PATH as SQLITE_DB_PATH, init_db
from rag_engine.storage.database import get_all_sessions, get_session_history
from rag_engine.storage.chroma_memory import CHROMA_PATH, get_memory_collection
from Chatbot_App.app import model, tokenizer
from mlx_lm import generate


def print_sqlite_summary():
    init_db()
    conn = sqlite3.connect(SQLITE_DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='messages'"
    )
    tables = cursor.fetchall()

    cursor.execute(
        "SELECT session_id, COUNT(*) FROM messages GROUP BY session_id ORDER BY session_id"
    )
    session_counts = cursor.fetchall()

    cursor.execute(
        "SELECT session_id, role, COUNT(*) FROM messages GROUP BY session_id, role ORDER BY session_id, role"
    )
    role_counts = cursor.fetchall()

    total_messages = sum(count for _, count in session_counts)

    print("SQLite summary:")
    print(f"  DB file: {SQLITE_DB_PATH}")
    print(f"  Tables present: {tables}")
    print(f"  Total messages: {total_messages}")
    print("  Conversations and message counts:")
    for session_id, count in session_counts:
        print(f"    - {session_id}: {count} messages")

    print("  Role breakdown:")
    for session_id, role, count in role_counts:
        print(f"    - {session_id} [{role}]: {count}")

    conn.close()


def print_chroma_summary():
    collection = get_memory_collection()
    count = collection.count()

    print("ChromaDB summary:")
    print(f"  Storage path: {CHROMA_PATH}")
    print(f"  Collection name: {collection.name}")
    print(f"  Number of entries: {count}")
    print("  Notes:")
    print("    - Chroma is a vector database (embedding-based similarity search).")
    print(
        "    - Each entry stores text + metadata and can be queried by semantic similarity."
    )


def summarize_conversation(text: str, max_tokens: int = 90) -> str:
    prompt = tokenizer.apply_chat_template(
        [
            {
                "role": "system",
                "content": (
                    "You summarize conversational text into one short, clear sentence. "
                    "Focus on the main idea and key facts."
                ),
            },
            {
                "role": "user",
                "content": f"Summarize this conversation:\n\n{text}",
            },
        ],
        tokenize=False,
        add_generation_prompt=True,
    )
    output = generate(
        model,
        tokenizer,
        prompt=prompt,
        max_tokens=max_tokens,
        verbose=False,
    )
    return output.strip()


def print_session_summaries():
    print("Session summaries (LLM-generated):")
    for session_id in get_all_sessions():
        history = get_session_history(session_id, limit=1000)
        convo_text = "\n".join(
            f"{message['role']}: {message['content']}" for message in history
        )
        summary = summarize_conversation(convo_text)
        print(f"  - {session_id}: {summary}")


def main():
    print_sqlite_summary()
    print()
    print_chroma_summary()
    print()
    print_session_summaries()


if __name__ == "__main__":
    main()
