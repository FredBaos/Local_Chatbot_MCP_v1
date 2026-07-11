import csv
import io
import os
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rag_engine.storage.chroma_memory import get_chroma_client

SUPPORTED_EXTENSIONS = {".csv", ".zip", ".xlsx", ".xls"}
DEFAULT_LOCAL_CAR_SPECS_CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "storage", "data", "car details.csv")


def _normalize_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _rows_from_csv_text(text: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(text))
    return [
        {key: _normalize_value(value) for key, value in row.items() if key is not None}
        for row in reader
    ]


def _rows_from_xlsx(path: str) -> list[dict[str, str]]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    sheet = workbook.active
    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        return []

    headers = [
        _normalize_value(cell) or f"column_{index}"
        for index, cell in enumerate(rows[0])
    ]

    result = []
    for row in rows[1:]:
        values = [
            _normalize_value(cell)
            for cell in row
        ]
        normalized = {
            header: values[index] if index < len(values) else ""
            for index, header in enumerate(headers)
        }
        result.append(normalized)
    return result


def load_rows_from_path(file_path: str | os.PathLike[str]) -> list[dict[str, str]]:
    path = str(file_path)

    if os.path.isdir(path):
        collected_rows: list[dict[str, str]] = []
        for child in sorted(Path(path).rglob("*")):
            if child.is_file() and child.suffix.lower() in SUPPORTED_EXTENSIONS:
                collected_rows.extend(load_rows_from_path(str(child)))
        return collected_rows

    if not os.path.exists(path):
        raise FileNotFoundError(f"Data file not found at: {path}")

    suffix = Path(path).suffix.lower()
    if suffix == ".csv":
        with open(path, mode="r", encoding="utf-8-sig", newline="") as handle:
            return _rows_from_csv_text(handle.read())

    if suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            for member_name in archive.namelist():
                lowered = member_name.lower()
                if lowered.endswith(".csv"):
                    return _rows_from_csv_text(archive.read(member_name).decode("utf-8-sig", errors="replace"))
                if lowered.endswith(".xlsx"):
                    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as handle:
                        handle.write(archive.read(member_name))
                        temp_path = handle.name
                    try:
                        return load_rows_from_path(temp_path)
                    finally:
                        if os.path.exists(temp_path):
                            os.remove(temp_path)
        return []

    if suffix in {".xlsx", ".xls"}:
        return _rows_from_xlsx(path)

    raise ValueError(f"Unsupported file type for ingestion: {path}")


def _build_source_id(file_path: str, metadata: dict[str, Any] | None = None) -> str:
    source_url = metadata.get("source_url") if metadata else None
    if source_url:
        return f"url::{source_url}"
    return f"path::{os.path.abspath(file_path)}"


def _source_already_ingested(collection: Any, source_id: str) -> bool:
    try:
        results = collection.get(where={"source_id": source_id}, include=["metadatas"], limit=1)
        return bool(results.get("ids"))
    except Exception:
        return False


def ingest_structured_csv(file_path: str, collection_name: str = "car_specs", metadata: dict[str, Any] | None = None):
    """
    Transforms structured dataset entries into readable paragraphs
    to preserve data integrity for embedding similarity matches.
    """
    if not file_path:
        print("[-] No data path provided")
        return

    try:
        rows = load_rows_from_path(file_path)
    except FileNotFoundError as exc:
        print(f"[-] Data file not found at: {file_path}")
        print(exc)
        return
    except ValueError as exc:
        print(f"[-] Unsupported ingestion target: {file_path}")
        print(exc)
        return

    client = get_chroma_client()
    collection = client.get_or_create_collection(name=collection_name)
    source_id = _build_source_id(file_path, metadata)

    if _source_already_ingested(collection, source_id):
        print(f"[*] Source already ingested, skipping: {file_path}")
        return

    documents = []
    metadatas = []
    ids = []

    print(f"[*] Processing data mapping from: {file_path}")
    for idx, row in enumerate(rows):
        description_sentences = []
        for key, value in row.items():
            if value:
                description_sentences.append(f"{key.replace('_', ' ').title()}: {value}")

        row_text = " | ".join(description_sentences)
        if not row_text:
            continue

        row_id = (
            row.get("id")
            or row.get("model_id")
            or row.get("vehicle_id")
            or row.get("test_vehicle_id")
            or f"row_{idx}"
        )

        documents.append(row_text)
        metadata_entry = {
            "source_file": os.path.basename(str(file_path)),
            "source_id": source_id,
            "row_index": idx,
        }
        if metadata:
            metadata_entry.update(metadata)
        metadatas.append(metadata_entry)
        ids.append(f"csv_{collection_name}_{row_id}")

    if documents:
        collection.add(documents=documents, metadatas=metadatas, ids=ids)
        print(f"[+] Successfully integrated {len(documents)} structured items into '{collection_name}' collection.")


def ingest_local_car_specs(csv_path: str | None = None, collection_name: str = "car_specs"):
    target_path = csv_path or DEFAULT_LOCAL_CAR_SPECS_CSV
    print(f"[*] Ingesting local car specs from: {target_path}")
    ingest_structured_csv(
        target_path,
        collection_name=collection_name,
        metadata={
            "source_file": os.path.basename(target_path),
            "source_type": "local_csv",
        },
    )


if __name__ == "__main__":
    ingest_local_car_specs()