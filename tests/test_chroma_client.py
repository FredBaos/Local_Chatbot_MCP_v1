import importlib


def test_chroma_clients_can_be_created_with_same_settings():
    memory_module = importlib.import_module("rag_engine.storage.chroma_memory")
    knowledge_module = importlib.import_module("rag_engine.storage.chroma_knowledge")

    memory_client = memory_module.get_chroma_client()
    knowledge_client = knowledge_module.get_chroma_client()

    assert memory_client is not None
    assert knowledge_client is not None
