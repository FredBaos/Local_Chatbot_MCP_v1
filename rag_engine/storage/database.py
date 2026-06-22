import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "chat_history.db")


def init_db():
    """Initializes the SQLite database schema if it doesn't exist."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    conn.close()


def save_message(session_id, role, content):
    """Persists a new chat token row into the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
        (session_id, role, str(content)),
    )
    conn.commit()
    conn.close()


def get_session_history(session_id, limit=1000):
    """Retrieves the recent N turns in chronological order for one session."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id ASC LIMIT ?",
        (session_id, limit),
    )
    rows = cursor.fetchall()
    conn.close()
    return [{"role": row[0], "content": row[1]} for row in rows]


def get_recent_global_history(limit=1000):
    """Retrieves the most recent turns across all sessions."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT session_id, role, content FROM messages ORDER BY id ASC LIMIT ?",
        (limit,),
    )
    rows = cursor.fetchall()
    conn.close()
    return [
        {"session_id": row[0], "role": row[1], "content": row[2]}
        for row in rows
    ]


def get_all_sessions():
    """Returns the list of sessions that have stored messages."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT DISTINCT session_id FROM messages ORDER BY session_id ASC"
    )
    sessions = [row[0] for row in cursor.fetchall()]
    conn.close()
    return sessions


def delete_session_history(session_id):
    """Deletes all stored messages for a session."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM messages WHERE session_id = ?",
        (session_id,),
    )
    conn.commit()
    conn.close()