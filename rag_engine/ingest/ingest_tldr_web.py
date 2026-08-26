"""
TLDR News Web Crawler

Scrapes TLDR's public newsletter archive (tldr.tech) directly over HTTP and
converts articles into searchable vector embeddings in ChromaDB. Replaces the
old Outlook/IMAP-based scraper — no email account or credentials required.

Features:
- Fetches daily issues straight from tldr.tech for one or more categories
- Parses headline, summary, and outbound source link for each article
- Filters out sponsored placements
- Chunks content into overlapping segments
- Tracks already-ingested articles so re-runs only add new ones
- Stores vectors in ChromaDB's 'tech_news' collection
"""

import os
import re
import sys
import json
import hashlib
from datetime import date
from pathlib import Path
from typing import Optional, Set
from urllib.parse import urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rag_engine.storage.chroma_knowledge import get_chroma_client


BASE_URL = "https://tldr.tech"
DEFAULT_CATEGORIES = ["tech", "ai"]
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"

# File to track already-ingested article IDs
PROCESSED_ARTICLES_FILE = os.path.join(
    os.path.dirname(__file__), "..", "storage", "data", "processed_tldr_articles.json"
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


def load_processed_articles() -> Set[str]:
    """Load set of already-processed article IDs from tracking file."""
    if not os.path.exists(PROCESSED_ARTICLES_FILE):
        return set()

    try:
        with open(PROCESSED_ARTICLES_FILE, "r") as f:
            data = json.load(f)
            return set(data.get("article_ids", []))
    except Exception as e:
        print(f"⚠ Could not load processed articles file: {e}")
        return set()


def save_processed_articles(article_ids: Set[str]) -> None:
    """Save processed article IDs to tracking file."""
    try:
        os.makedirs(os.path.dirname(PROCESSED_ARTICLES_FILE), exist_ok=True)
        with open(PROCESSED_ARTICLES_FILE, "w") as f:
            json.dump({"article_ids": list(article_ids)}, f, indent=2)
        print(f"✓ Saved {len(article_ids)} processed article IDs")
    except Exception as e:
        print(f"⚠ Could not save processed articles file: {e}")


def clean_source_url(url: str) -> str:
    """Strip tracking query params (utm_*, access tokens, etc.) from an outbound link."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


_LATEST_DATE_CACHE: dict[str, str] = {}


def resolve_latest_date(category: str) -> Optional[str]:
    """
    Find the most recent published issue date for a category.

    tldr.tech/{category} (no date) serves a generic landing page rather than
    the latest issue, so instead we scan its outbound issue links
    (e.g. href="/tech/2026-08-25") and take the newest date listed.
    """
    if category in _LATEST_DATE_CACHE:
        return _LATEST_DATE_CACHE[category]

    response = requests.get(BASE_URL, headers={"User-Agent": USER_AGENT}, timeout=15)
    response.raise_for_status()

    dates = re.findall(rf'href="/{re.escape(category)}/(\d{{4}}-\d{{2}}-\d{{2}})"', response.text)
    latest = max(dates) if dates else None
    if latest:
        _LATEST_DATE_CACHE[category] = latest
    return latest


def get_article_id(article: dict) -> str:
    """Derive a stable ID for an article from its category, date, and source link."""
    key = f"{article['category']}:{article['date']}:{article['source_url']}"
    return hashlib.md5(key.encode()).hexdigest()[:12]


def fetch_issue(category: str, issue_date: Optional[str] = None) -> list[dict]:
    """
    Fetch and parse one day's TLDR issue for a category.

    Args:
        category: TLDR newsletter category slug (e.g. 'tech', 'ai')
        issue_date: ISO date string (YYYY-MM-DD); defaults to the latest issue

    Returns:
        List of article dicts with headline, summary, source_url, category, date
    """
    resolved_date = issue_date or resolve_latest_date(category)
    if not resolved_date:
        print(f"✗ Could not resolve a latest issue date for '{category}'")
        return []

    url = f"{BASE_URL}/{category}/{resolved_date}"
    print(f"[*] Fetching {url}")
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    articles = []

    for art in soup.find_all("article"):
        link = art.find("a", class_="font-bold")
        if not link or not link.get("href"):
            continue

        h3 = link.find("h3")
        headline_full = h3.get_text(strip=True) if h3 else link.get_text(strip=True)

        # Skip sponsored placements — they carry "(Sponsor)" instead of a read-time suffix
        if "sponsor" in headline_full.lower():
            continue

        # Strip the trailing "(N minute read)" suffix from the headline
        headline = re.sub(r"\s*\([^()]*read\)\s*$", "", headline_full).strip()

        summary_div = art.find(class_="newsletter-html")
        summary = summary_div.get_text(" ", strip=True) if summary_div else ""

        if not headline or not summary:
            continue

        articles.append(
            {
                "headline": headline,
                "summary": summary,
                "source_url": clean_source_url(link["href"]),
                "category": category,
                "date": resolved_date,
            }
        )

    print(f"[+] Parsed {len(articles)} articles from '{category}' ({resolved_date})")
    return articles


def _ingest_articles_to_chroma(
    articles: list[dict],
    collection_name: str,
    chunk_size: int,
    chunk_overlap: int,
    processed_ids: Set[str],
) -> int:
    """
    Helper function to ingest parsed articles into ChromaDB.

    Args:
        articles: List of article dicts from fetch_issue()
        collection_name: ChromaDB collection name
        chunk_size: Characters per chunk
        chunk_overlap: Overlap between chunks
        processed_ids: Set of already-processed article IDs

    Returns:
        Number of chunks ingested
    """
    if not articles:
        print("✗ No articles to process")
        save_processed_articles(processed_ids)
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

    for article in articles:
        article_id = get_article_id(article)

        if article_id in processed_ids:
            skipped += 1
            continue

        document = f"Headline: {article['headline']}\n\n{article['summary']}"
        chunks = chunk_text(document, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

        for i, chunk in enumerate(chunks):
            all_documents.append(chunk)
            all_metadatas.append(
                {
                    "source": "tldr_web",
                    "source_url": article["source_url"],
                    "title": article["headline"],
                    "category": article["category"],
                    "date": article["date"],
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                }
            )
            all_ids.append(f"tldr_web_{article_id}_{i}")

        new_processed.add(article_id)

    if skipped:
        print(f"⊘ Skipped {skipped} already-processed articles")

    total_ingested = len(all_documents)
    if all_documents:
        try:
            collection.add(documents=all_documents, metadatas=all_metadatas, ids=all_ids)
            print(f"\n{'='*60}")
            print(f"✓ Successfully ingested {total_ingested} chunks from {len(articles) - skipped} new articles")
            print(f"✓ Collection: '{collection_name}'")
            print(f"{'='*60}\n")
        except Exception as e:
            print(f"✗ Error adding documents to ChromaDB: {e}")
            total_ingested = 0

    save_processed_articles(new_processed)
    return total_ingested


def ingest_tldr_web(
    categories: Optional[list[str]] = None,
    issue_date: Optional[str] = None,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
    collection_name: str = "tech_news",
    dry_run: bool = False,
) -> int:
    """
    Main function to crawl TLDR's web archive and ingest new articles into ChromaDB.

    Args:
        categories: TLDR category slugs to crawl (default: ['tech', 'ai'])
        issue_date: ISO date string (YYYY-MM-DD) to fetch a specific past issue;
            defaults to each category's latest issue
        chunk_size: Size of text chunks (default: 500 characters)
        chunk_overlap: Overlap between chunks (default: 50 characters)
        collection_name: ChromaDB collection name (default: 'tech_news')
        dry_run: Test mode - parses sample data instead of hitting the network

    Returns:
        Number of chunks successfully ingested
    """
    print(f"\n{'='*60}")
    print("📰 TLDR News Web Crawler")
    print(f"{'='*60}\n")

    categories = categories or DEFAULT_CATEGORIES
    processed_ids = load_processed_articles()
    print(f"📋 Found {len(processed_ids)} previously processed articles\n")

    if dry_run:
        print("🧪 DRY-RUN MODE - using sample data, no network calls\n")
        sample_date = issue_date or date.today().isoformat()
        sample_articles = [
            {
                "headline": "Sample AI Breakthrough Announced",
                "summary": "A demonstration article used to verify the ingestion pipeline end-to-end.",
                "source_url": "https://example.com/sample-ai-breakthrough",
                "category": categories[0],
                "date": sample_date,
            },
        ]
        return _ingest_articles_to_chroma(
            sample_articles, collection_name, chunk_size, chunk_overlap, processed_ids
        )

    all_articles = []
    for category in categories:
        try:
            all_articles.extend(fetch_issue(category, issue_date))
        except Exception as e:
            print(f"✗ Failed to fetch category '{category}': {e}")

    return _ingest_articles_to_chroma(
        all_articles, collection_name, chunk_size, chunk_overlap, processed_ids
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Crawl TLDR's web archive into ChromaDB")
    parser.add_argument("--date", dest="issue_date", default=None, help="Issue date YYYY-MM-DD (default: latest)")
    parser.add_argument(
        "--categories",
        default=",".join(DEFAULT_CATEGORIES),
        help="Comma-separated TLDR categories (default: tech,ai)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Test the pipeline with sample data, no network calls")
    args = parser.parse_args()

    ingest_tldr_web(
        categories=[c.strip() for c in args.categories.split(",") if c.strip()],
        issue_date=args.issue_date,
        dry_run=args.dry_run,
    )
