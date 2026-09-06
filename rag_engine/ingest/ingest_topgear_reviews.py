"""
TopGear Driving-Feel Review Crawler

Scrapes topgear.com's car review pages directly over HTTP and converts their
driving-impression content (ride, handling, verdict) into searchable vector
embeddings in ChromaDB. Complements `car_specs` (hard numbers only) with the
subjective driving-feel commentary that dataset doesn't have.

Features:
- Discovers canonical review URLs (e.g. /car-reviews/audi/rs5) via topgear.com's
  public XML sitemap
- Extracts driving-feel content from the page's embedded Next.js JSON data
  blob (__NEXT_DATA__) rather than fragile CSS selectors
- Chunks content into overlapping segments
- Tracks already-ingested reviews so re-runs only add new ones, and skips
  already-seen URLs during discovery itself to avoid wasted fetches
- Stores vectors in ChromaDB's 'car_reviews' collection
"""

import os
import re
import sys
import json
import time
import hashlib
from pathlib import Path
from typing import Optional, Set
from urllib.parse import urlsplit

import requests
from bs4 import BeautifulSoup

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rag_engine.storage.chroma_knowledge import get_chroma_client


SITEMAP_INDEX_URL = "https://www.topgear.com/sitemap.xml"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
REQUEST_DELAY_SECONDS = 0.75

# File to track already-ingested review IDs
PROCESSED_REVIEWS_FILE = os.path.join(
    os.path.dirname(__file__), "..", "storage", "data", "processed_topgear_reviews.json"
)


def chunk_text(text: str, chunk_size: int = 500, chunk_overlap: int = 50) -> list[str]:
    """
    Split text into overlapping chunks.

    Args:
        text: Text to chunk
        chunk_size: Size of each chunk in characters
        chunk_overlap: Overlap between chunks

    Returns:
        List of text chunks
    """
    if not text or chunk_size <= 0:
        return [text] if text else []

    chunks = []
    start = 0
    text_length = len(text)

    while start < text_length:
        end = min(start + chunk_size, text_length)
        chunks.append(text[start:end])
        start = end - chunk_overlap if end < text_length else text_length

    return chunks


def load_processed_reviews() -> Set[str]:
    """Load set of already-processed review IDs from tracking file."""
    if not os.path.exists(PROCESSED_REVIEWS_FILE):
        return set()

    try:
        with open(PROCESSED_REVIEWS_FILE, "r") as f:
            data = json.load(f)
            return set(data.get("review_ids", []))
    except Exception as e:
        print(f"⚠ Could not load processed reviews file: {e}")
        return set()


def save_processed_reviews(review_ids: Set[str]) -> None:
    """Save processed review IDs to tracking file."""
    try:
        os.makedirs(os.path.dirname(PROCESSED_REVIEWS_FILE), exist_ok=True)
        with open(PROCESSED_REVIEWS_FILE, "w") as f:
            json.dump({"review_ids": list(review_ids)}, f, indent=2)
        print(f"✓ Saved {len(review_ids)} processed review IDs")
    except Exception as e:
        print(f"⚠ Could not save processed reviews file: {e}")


def get_review_id(url: str) -> str:
    """Derive a stable ID for a review from its canonical URL."""
    return hashlib.md5(url.encode()).hexdigest()[:12]


def is_canonical_review_url(url: str) -> bool:
    """
    True for a canonical single-car review page (e.g.
    https://www.topgear.com/car-reviews/audi/rs5), false for sub-tabs
    (/specs, /driving, /interior, /buying), first-drive articles with extra
    path segments, and the /car-reviews/find/... listing pages.
    """
    parts = urlsplit(url)
    if parts.netloc != "www.topgear.com":
        return False
    segments = [p for p in parts.path.split("/") if p]
    return len(segments) == 3 and segments[0] == "car-reviews" and segments[1] != "find"


def _extract_sub_sitemap_urls(index_xml: str) -> list[str]:
    return re.findall(r"<loc>([^<]+)</loc>", index_xml)


def discover_review_urls(limit: int, processed_ids: Set[str]) -> list[str]:
    """
    Walk topgear.com's sitemap to find new (not-yet-ingested) canonical
    review URLs, stopping once `limit` are found.
    """
    print(f"[*] Fetching sitemap index {SITEMAP_INDEX_URL}")
    response = requests.get(SITEMAP_INDEX_URL, headers={"User-Agent": USER_AGENT}, timeout=15)
    response.raise_for_status()
    sub_sitemaps = _extract_sub_sitemap_urls(response.text)
    print(f"[+] Found {len(sub_sitemaps)} sub-sitemaps")

    new_urls: list[str] = []
    for sitemap_url in sub_sitemaps:
        try:
            sub_response = requests.get(sitemap_url, headers={"User-Agent": USER_AGENT}, timeout=15)
            sub_response.raise_for_status()
        except Exception as e:
            print(f"✗ Failed to fetch sub-sitemap '{sitemap_url}': {e}")
            continue

        for url in _extract_sub_sitemap_urls(sub_response.text):
            if not is_canonical_review_url(url):
                continue
            if get_review_id(url) in processed_ids:
                continue
            if url in new_urls:
                continue
            new_urls.append(url)
            if len(new_urls) >= limit:
                return new_urls

    return new_urls


def _html_to_text(raw_html: str) -> str:
    """Strip embedded HTML tags (e.g. <p>...</p>) down to plain text."""
    if not raw_html:
        return ""
    return BeautifulSoup(raw_html, "html.parser").get_text(" ", strip=True)


def fetch_review(url: str) -> Optional[dict]:
    """
    Fetch one review page and extract its driving-feel content from the
    page's embedded Next.js JSON data blob.

    Returns:
        A review dict, or None if the page has no useful driving-feel
        content (or the expected data blob isn't present).
    """
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    script_tag = soup.find("script", id="__NEXT_DATA__")
    if not script_tag or not script_tag.string:
        return None

    try:
        data = json.loads(script_tag.string)
    except json.JSONDecodeError:
        return None

    content = data.get("props", {}).get("pageProps", {}).get("content", {}) or {}

    driving_text = _html_to_text(content.get("drivingText", ""))
    verdict = _html_to_text(content.get("verdict", ""))
    if not driving_text and not verdict:
        return None

    return {
        "url": url,
        "make": (content.get("make") or {}).get("title") or "Unknown",
        "model": content.get("carName") or content.get("title") or "Unknown",
        "body_type": (content.get("bodyStyle") or {}).get("title") or "Unknown",
        "rating": content.get("rating"),
        "driving_text": driving_text,
        "verdict": verdict,
        "verdict_text": content.get("verdictText") or "",
        "verdict_text_for": content.get("verdictTextFor") or "",
        "verdict_text_against": content.get("verdictTextAgainst") or "",
        "what_we_say_text": content.get("whatWeSayText") or "",
    }


def _build_review_document(review: dict) -> str:
    """Render a review dict into one natural-language document string."""
    header = f"{review['make']} {review['model']} ({review['body_type']}) — TopGear driving impressions."
    parts = [header]

    if review["driving_text"]:
        parts.append(f"Driving feel: {review['driving_text']}")
    if review["what_we_say_text"]:
        parts.append(f"What we say: {review['what_we_say_text']}")
    if review["verdict_text"]:
        parts.append(f"Verdict summary: {review['verdict_text']}")
    if review["verdict"]:
        parts.append(f"Full verdict: {review['verdict']}")
    if review["verdict_text_for"]:
        parts.append(f"Pros: {review['verdict_text_for']}")
    if review["verdict_text_against"]:
        parts.append(f"Cons: {review['verdict_text_against']}")
    if review["rating"] is not None:
        parts.append(f"TopGear rating: {review['rating']}/10.")

    return "\n\n".join(parts)


def _ingest_reviews_to_chroma(
    reviews: list[dict],
    collection_name: str,
    chunk_size: int,
    chunk_overlap: int,
    processed_ids: Set[str],
) -> int:
    """
    Helper function to ingest parsed reviews into ChromaDB.

    Args:
        reviews: List of review dicts from fetch_review()
        collection_name: ChromaDB collection name
        chunk_size: Characters per chunk
        chunk_overlap: Overlap between chunks
        processed_ids: Set of already-processed review IDs

    Returns:
        Number of chunks ingested
    """
    if not reviews:
        print("✗ No reviews to process")
        save_processed_reviews(processed_ids)
        return 0

    client = get_chroma_client()
    try:
        collection = client.get_or_create_collection(name=collection_name)
    except Exception as e:
        print(f"✗ Error accessing collection '{collection_name}': {e}")
        return 0

    all_documents, all_metadatas, all_ids = [], [], []
    new_processed = set(processed_ids)
    skipped = 0

    for review in reviews:
        review_id = get_review_id(review["url"])

        if review_id in processed_ids:
            skipped += 1
            continue

        document = _build_review_document(review)
        chunks = chunk_text(document, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

        for i, chunk in enumerate(chunks):
            metadata = {
                "source": "topgear_web",
                "source_url": review["url"],
                "make": review["make"],
                "model": review["model"],
                "body_type": review["body_type"],
                "chunk_index": i,
                "total_chunks": len(chunks),
            }
            # ChromaDB rejects None metadata values, so only include rating
            # when the page actually had one.
            if review["rating"] is not None:
                metadata["rating"] = review["rating"]

            all_documents.append(chunk)
            all_metadatas.append(metadata)
            all_ids.append(f"topgear_web_{review_id}_{i}")

        new_processed.add(review_id)

    if skipped:
        print(f"⊘ Skipped {skipped} already-processed reviews")

    total_ingested = len(all_documents)
    if all_documents:
        try:
            collection.add(documents=all_documents, metadatas=all_metadatas, ids=all_ids)
            print(f"\n{'='*60}")
            print(f"✓ Successfully ingested {total_ingested} chunks from {len(reviews) - skipped} new reviews")
            print(f"✓ Collection: '{collection_name}'")
            print(f"{'='*60}\n")
        except Exception as e:
            print(f"✗ Error adding documents to ChromaDB: {e}")
            total_ingested = 0

    save_processed_reviews(new_processed)
    return total_ingested


def ingest_topgear_reviews(
    limit: int = 25,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
    collection_name: str = "car_reviews",
    dry_run: bool = False,
) -> int:
    """
    Main function to crawl topgear.com's reviews and ingest new driving-feel
    content into ChromaDB.

    Args:
        limit: Max new reviews to fetch this run (default: 25). The full
            catalog has 1,000+ reviews — meant to be re-run repeatedly
            (e.g. on a cron) to build up coverage over time, same as
            ingest_tldr_web.py.
        chunk_size: Size of text chunks (default: 500 characters)
        chunk_overlap: Overlap between chunks (default: 50 characters)
        collection_name: ChromaDB collection name (default: 'car_reviews')
        dry_run: Test mode - parses sample data instead of hitting the network

    Returns:
        Number of chunks successfully ingested
    """
    print(f"\n{'='*60}")
    print("🏁 TopGear Driving-Feel Review Crawler")
    print(f"{'='*60}\n")

    processed_ids = load_processed_reviews()
    print(f"📋 Found {len(processed_ids)} previously processed reviews\n")

    if dry_run:
        print("🧪 DRY-RUN MODE - using sample data, no network calls\n")
        sample_reviews = [
            {
                "url": "https://example.com/car-reviews/sample/model",
                "make": "SampleMake",
                "model": "SampleModel",
                "body_type": "Saloon",
                "rating": 8,
                "driving_text": "A demonstration review used to verify the ingestion pipeline end-to-end.",
                "verdict": "Handles well and rides comfortably in this sample verdict text.",
                "verdict_text": "A convincing all-rounder, on paper at least.",
                "verdict_text_for": "Handles well, comfortable",
                "verdict_text_against": "Expensive, sample data only",
                "what_we_say_text": "A solid demonstration of the pipeline.",
            },
        ]
        return _ingest_reviews_to_chroma(
            sample_reviews, collection_name, chunk_size, chunk_overlap, processed_ids
        )

    review_urls = discover_review_urls(limit, processed_ids)
    print(f"[+] Discovered {len(review_urls)} new review URLs to fetch\n")

    reviews = []
    for i, url in enumerate(review_urls):
        try:
            print(f"[*] Fetching {url}")
            review = fetch_review(url)
            if review:
                reviews.append(review)
            else:
                print(f"⊘ No driving-feel content found at '{url}'")
        except Exception as e:
            print(f"✗ Failed to fetch review '{url}': {e}")

        if i < len(review_urls) - 1:
            time.sleep(REQUEST_DELAY_SECONDS)

    return _ingest_reviews_to_chroma(
        reviews, collection_name, chunk_size, chunk_overlap, processed_ids
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Crawl topgear.com's driving-feel reviews into ChromaDB")
    parser.add_argument("--limit", type=int, default=25, help="Max new reviews to fetch this run (default: 25)")
    parser.add_argument("--dry-run", action="store_true", help="Test the pipeline with sample data, no network calls")
    args = parser.parse_args()

    ingest_topgear_reviews(limit=args.limit, dry_run=args.dry_run)
