from rag_engine.utils.rag_support import get_rag_setup_context


def test_detects_rag_setup_questions():
    text = "How do I enable RAG with my car_specs collection?"
    context = get_rag_setup_context(text)
    assert context is not None
    assert "car_specs" in context
    assert "RAG" in context


def test_ignores_unrelated_questions():
    text = "What is the weather today?"
    assert get_rag_setup_context(text) is None
