import sqlite3

from rag_engine.storage import database


def test_get_session_history_returns_most_recent_messages(tmp_path, monkeypatch):
    db_path = tmp_path / "chat_history.db"
    monkeypatch.setattr(database, "DB_PATH", str(db_path))
    database.init_db()

    session_id = "session-test"
    for index in range(15):
        database.save_message(session_id, "user", f"message-{index}")

    history = database.get_session_history(session_id, limit=10)

    assert len(history) == 10
    assert [message["content"] for message in history] == [
        f"message-{index}" for index in range(5, 15)
    ]


def test_get_recent_global_history_returns_most_recent_messages(tmp_path, monkeypatch):
    db_path = tmp_path / "chat_history.db"
    monkeypatch.setattr(database, "DB_PATH", str(db_path))
    database.init_db()

    for index in range(12):
        database.save_message(f"session-{index % 3}", "user", f"message-{index}")

    history = database.get_recent_global_history(limit=5)

    assert len(history) == 5
    assert [message["content"] for message in history] == [
        f"message-{index}" for index in range(7, 12)
    ]


def test_citations_round_trip_through_save_and_get(tmp_path, monkeypatch):
    db_path = tmp_path / "chat_history.db"
    monkeypatch.setattr(database, "DB_PATH", str(db_path))
    database.init_db()

    session_id = "session-citations"
    citations = [{"source": "tech_news", "title": "Example Article", "confidence": 87.5}]
    database.save_message(session_id, "user", "What's new in AI?")
    database.save_message(session_id, "assistant", "Here's what's new.", citations=citations)

    history = database.get_session_history(session_id)

    assert "citations" not in history[0]
    assert history[1]["citations"] == citations


def test_init_db_migrates_pre_existing_table_without_citations_column(tmp_path, monkeypatch):
    db_path = tmp_path / "chat_history.db"
    monkeypatch.setattr(database, "DB_PATH", str(db_path))

    # Simulate a database created before the citations column existed.
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE messages (
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

    # Should not raise, and should be safe to call repeatedly.
    database.init_db()
    database.init_db()

    database.save_message("session-migrated", "user", "hello")
    history = database.get_session_history("session-migrated")
    assert history == [{"role": "user", "content": "hello"}]
