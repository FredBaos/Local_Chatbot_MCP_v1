"""
Automobile Specs Ingestion

Ingests a comprehensive, canonical vehicle-specs dataset (one row per engine/
trim variant, ~30,000 variants across ~7,200 models and 124 brands) into the
`car_specs` collection, replacing the earlier India used-car resale dataset.

Source: https://github.com/ilyasozkurt/automobile-models-and-specs
(scraped from autoevolution.com, republished as an open dataset on GitHub;
local copies of its three CSVs live in rag_engine/storage/data/automobile_specs/)

Note: the published header row in automobiles.csv does not match its actual
column content (verified by inspection and cross-checked against brands.csv).
This module reads automobiles.csv positionally rather than trusting its header.
"""

import csv
import html
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rag_engine.storage.chroma_knowledge import get_chroma_client

csv.field_size_limit(10_000_000)

DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "storage", "data", "automobile_specs"
)
DEFAULT_BRANDS_CSV = os.path.join(DATA_DIR, "brands.csv")
DEFAULT_AUTOMOBILES_CSV = os.path.join(DATA_DIR, "automobiles.csv")
DEFAULT_ENGINES_CSV = os.path.join(DATA_DIR, "engines.csv")

BATCH_SIZE = 2000

# Body type isn't a structured field in this dataset, but model titles and
# descriptions frequently name it directly (e.g. "428 Convertible"), so a
# keyword match against title + description does reasonable work here —
# unlike the old dataset, where the words never appeared anywhere at all.
BODY_TYPE_KEYWORDS = [
    ("suv", "SUV"),
    ("crossover", "SUV"),
    ("pickup", "Pickup"),
    ("truck", "Pickup"),
    ("minivan", "MUV/MPV"),
    ("van", "MUV/MPV"),
    ("wagon", "Wagon"),
    ("convertible", "Convertible"),
    ("roadster", "Convertible"),
    ("spider", "Convertible"),
    ("cabriolet", "Convertible"),
    ("coupe", "Coupe"),
    ("hatchback", "Hatchback"),
    ("sedan", "Sedan"),
    ("saloon", "Sedan"),
]

_TITLE_SUFFIX_RE = re.compile(r"\s*photos,\s*engines\s*&\s*full specs\s*$", re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"\s+")


def _clean_model_name(raw_name: str) -> str:
    name = html.unescape(raw_name or "")
    name = _TITLE_SUFFIX_RE.sub("", name)
    return _WHITESPACE_RE.sub(" ", name).strip()


def _clean_description(raw_html: str, max_chars: int = 500) -> str:
    if not raw_html:
        return ""
    text = BeautifulSoup(raw_html, "html.parser").get_text(separator=" ", strip=True)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    if len(text) > max_chars:
        # Cut at the nearest sentence boundary before the limit, else hard cut
        cut = text.rfind(". ", 0, max_chars)
        text = text[: cut + 1] if cut > 0 else text[:max_chars]
    return text


def infer_body_type(model_name: str, description: str) -> str:
    haystack = f"{model_name} {description}".lower()
    for keyword, body_type in BODY_TYPE_KEYWORDS:
        if keyword in haystack:
            return body_type
    return "Unknown"


def load_brands(brands_csv: str) -> dict[str, str]:
    """Returns {brand_id: brand_name}."""
    brands: dict[str, str] = {}
    with open(brands_csv, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            brands[row["id"]] = row.get("name", "").strip()
    return brands


def load_automobiles(automobiles_csv: str) -> dict[str, dict[str, str]]:
    """
    Returns {automobile_id: {"brand_id", "name", "description"}}.

    Reads positionally — see module docstring on the header mismatch.
    Column order by content: id, url_hash, url, brand_id, name, description,
    price, images(json), created_at, updated_at, (trailing empty).
    """
    automobiles: dict[str, dict[str, str]] = {}
    with open(automobiles_csv, encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader, None)  # skip the (mislabeled) header row
        for row in reader:
            if len(row) < 6:
                continue
            automobile_id, _url_hash, _url, brand_id, raw_name, raw_description = row[:6]
            automobiles[automobile_id] = {
                "brand_id": brand_id,
                "name": _clean_model_name(raw_name),
                "description": _clean_description(raw_description),
            }
    return automobiles


def _render_specs_sections(specs: dict[str, Any]) -> str:
    parts = []
    for section_name, fields in specs.items():
        if not isinstance(fields, dict) or not fields:
            continue
        rendered_fields = []
        for key, value in fields.items():
            if not value:
                continue
            clean_key = key.rstrip(":").strip()
            clean_value = str(value).replace("\r\n", ", ").replace("\n", ", ").strip()
            rendered_fields.append(f"{clean_key} {clean_value}")
        if rendered_fields:
            parts.append(f"{section_name}: " + "; ".join(rendered_fields) + ".")
    return " ".join(parts)


def _format_variant(brand_name: str, automobile: dict[str, str], engine_name: str, specs: dict[str, Any]) -> tuple[str, str]:
    """Returns (document_text, body_type) for one engine/trim variant."""
    model_name = automobile["name"]
    description = automobile["description"]
    body_type = infer_body_type(model_name, description)
    body_phrase = f" ({body_type})" if body_type != "Unknown" else ""

    # The source title already includes the brand name (e.g. "AC Aceca 1998-2000"),
    # so strip it before re-prepending brand_name to avoid "AC AC Aceca ...".
    display_model = model_name
    if brand_name and model_name.lower().startswith(brand_name.lower()):
        display_model = model_name[len(brand_name):].strip()

    header = f"{brand_name} {display_model}{body_phrase} — {engine_name}."
    specs_text = _render_specs_sections(specs)

    sentences = [header]
    if description:
        sentences.append(description)
    if specs_text:
        sentences.append(specs_text)

    return " ".join(sentences), body_type


def ingest_automobile_specs(
    brands_csv: str | None = None,
    automobiles_csv: str | None = None,
    engines_csv: str | None = None,
    collection_name: str = "car_specs",
    limit: int | None = None,
) -> int:
    """
    Ingests the canonical automobile specs dataset into ChromaDB.

    Args:
        limit: if set, only process the first N engine/trim rows (useful for testing)

    Returns:
        Number of documents ingested
    """
    brands_csv = brands_csv or DEFAULT_BRANDS_CSV
    automobiles_csv = automobiles_csv or DEFAULT_AUTOMOBILES_CSV
    engines_csv = engines_csv or DEFAULT_ENGINES_CSV

    for path in (brands_csv, automobiles_csv, engines_csv):
        if not os.path.exists(path):
            print(f"[-] Required data file not found: {path}")
            return 0

    print("[*] Loading brands and automobiles reference tables...")
    brands = load_brands(brands_csv)
    automobiles = load_automobiles(automobiles_csv)
    print(f"[+] Loaded {len(brands)} brands and {len(automobiles)} models")

    client = get_chroma_client()
    collection = client.get_or_create_collection(name=collection_name)

    documents, metadatas, ids = [], [], []
    body_type_counts: dict[str, int] = {}
    total_ingested = 0
    processed = 0
    skipped_missing_automobile = 0
    skipped_bad_specs = 0

    with open(engines_csv, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if limit is not None and processed >= limit:
                break
            processed += 1

            automobile = automobiles.get(row.get("automobile_id", ""))
            if automobile is None:
                skipped_missing_automobile += 1
                continue

            try:
                specs = json.loads(row.get("specs") or "{}")
            except (json.JSONDecodeError, TypeError):
                skipped_bad_specs += 1
                continue

            brand_name = brands.get(automobile["brand_id"], "Unknown")
            engine_name = html.unescape((row.get("name") or "").strip())

            document_text, body_type = _format_variant(brand_name, automobile, engine_name, specs)
            if not document_text:
                continue

            body_type_counts[body_type] = body_type_counts.get(body_type, 0) + 1

            documents.append(document_text)
            metadatas.append(
                {
                    "source_type": "automobile_specs",
                    "brand": brand_name,
                    "model": automobile["name"],
                    "engine": engine_name,
                    "body_type": body_type,
                }
            )
            ids.append(f"csv_{collection_name}_{row['automobile_id']}_{row['id']}")

            if len(documents) >= BATCH_SIZE:
                collection.add(documents=documents, metadatas=metadatas, ids=ids)
                total_ingested += len(documents)
                print(f"[+] Ingested {total_ingested} variants so far...")
                documents, metadatas, ids = [], [], []

    if documents:
        collection.add(documents=documents, metadatas=metadatas, ids=ids)
        total_ingested += len(documents)

    print(f"[+] Successfully integrated {total_ingested} engine/trim variants into '{collection_name}' collection.")
    print(f"[+] Body type breakdown: {body_type_counts}")
    if skipped_missing_automobile:
        print(f"[*] Skipped {skipped_missing_automobile} rows with no matching model")
    if skipped_bad_specs:
        print(f"[*] Skipped {skipped_bad_specs} rows with unparseable specs")

    return total_ingested


if __name__ == "__main__":
    ingest_automobile_specs()
