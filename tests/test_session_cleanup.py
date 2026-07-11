from rag_engine.storage import chroma_memory


class FakeCollection:
    def __init__(self):
        self.deleted_ids = []

    def get(self, where=None, include=None):
        assert where == {"session_id": "session-123"}
        return {
            "ids": ["id-1", "id-2"],
            "documents": ["one", "two"],
            "metadatas": [{"session_id": "session-123"}, {"session_id": "session-123"}],
        }

    def delete(self, ids=None):
        self.deleted_ids.extend(ids or [])


def test_delete_session_memory_removes_session_embeddings(monkeypatch):
    fake_collection = FakeCollection()
    monkeypatch.setattr(chroma_memory, "get_memory_collection", lambda: fake_collection)

    deleted_count = chroma_memory.delete_session_memory("session-123")

    assert deleted_count == 2
    assert fake_collection.deleted_ids == ["id-1", "id-2"]
