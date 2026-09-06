from pathlib import Path

from rag_engine.ingest import ingest_topgear_reviews as topgear
from rag_engine.storage.chroma_knowledge import get_chroma_client


def test_is_canonical_review_url_filters_correctly() -> None:
    assert topgear.is_canonical_review_url("https://www.topgear.com/car-reviews/audi/rs5")
    assert not topgear.is_canonical_review_url("https://www.topgear.com/car-reviews/audi/rs5/specs")
    assert not topgear.is_canonical_review_url("https://www.topgear.com/car-reviews/find/body/suv")
    assert not topgear.is_canonical_review_url(
        "https://www.topgear.com/car-reviews/alfa-romeo/giulia-saloon-2022/"
        "29-v6-biturbo-quadrifoglio-4dr-auto/first-drive"
    )
    assert not topgear.is_canonical_review_url("https://www.example.com/car-reviews/audi/rs5")


def test_build_review_document_includes_available_sections() -> None:
    review = {
        "make": "Audi",
        "model": "RS5",
        "body_type": "Saloon",
        "rating": 8,
        "driving_text": "Handles very well.",
        "verdict": "A convincing all-rounder.",
        "verdict_text": "Torque vectors its way out of trouble.",
        "verdict_text_for": "Goes, handles, stops.",
        "verdict_text_against": "Heavy, expensive.",
        "what_we_say_text": "Belongs to a world hell bent on disguising mass.",
    }
    document = topgear._build_review_document(review)

    assert "Audi RS5 (Saloon)" in document
    assert "Handles very well." in document
    assert "TopGear rating: 8/10." in document


def test_build_review_document_omits_missing_sections() -> None:
    review = {
        "make": "SampleMake",
        "model": "SampleModel",
        "body_type": "Unknown",
        "rating": None,
        "driving_text": "Only driving text present.",
        "verdict": "",
        "verdict_text": "",
        "verdict_text_for": "",
        "verdict_text_against": "",
        "what_we_say_text": "",
    }
    document = topgear._build_review_document(review)

    assert "Only driving text present." in document
    assert "Pros:" not in document
    assert "Cons:" not in document
    assert "TopGear rating" not in document


def test_ingest_reviews_to_chroma_skips_already_processed(tmp_path: Path, monkeypatch) -> None:
    # Redirect the dedup tracking file so this test never touches real project state.
    monkeypatch.setattr(topgear, "PROCESSED_REVIEWS_FILE", str(tmp_path / "processed_topgear_reviews.json"))

    collection_name = "car_reviews_test"
    client = get_chroma_client()
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass

    review = {
        "url": "https://www.topgear.com/car-reviews/sample/model",
        "make": "SampleMake",
        "model": "SampleModel",
        "body_type": "Saloon",
        "rating": None,
        "driving_text": "A sample driving impression long enough to chunk on its own.",
        "verdict": "",
        "verdict_text": "",
        "verdict_text_for": "",
        "verdict_text_against": "",
        "what_we_say_text": "",
    }
    review_id = topgear.get_review_id(review["url"])

    total_first = topgear._ingest_reviews_to_chroma([review], collection_name, 500, 50, processed_ids=set())
    assert total_first >= 1

    total_second = topgear._ingest_reviews_to_chroma(
        [review], collection_name, 500, 50, processed_ids={review_id}
    )
    assert total_second == 0

    collection = client.get_collection(name=collection_name)
    assert collection.count() == total_first

    # No metadata value should ever be None (rating omitted here) — Chroma rejects those.
    stored = collection.get(limit=total_first, include=["metadatas"])
    for metadata in stored["metadatas"]:
        assert "rating" not in metadata
        assert all(value is not None for value in metadata.values())
