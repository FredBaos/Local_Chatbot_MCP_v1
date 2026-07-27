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
