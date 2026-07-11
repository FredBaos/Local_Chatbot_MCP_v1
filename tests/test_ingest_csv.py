from pathlib import Path
import csv
import zipfile

from openpyxl import Workbook

from rag_engine.ingest.ingest_csv import ingest_structured_csv, load_rows_from_path
from rag_engine.storage.chroma_memory import get_chroma_client


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def test_load_rows_from_csv_zip_and_xlsx(tmp_path: Path) -> None:
    csv_path = tmp_path / "cars.csv"
    write_csv(csv_path, [{"id": "1", "make": "Tesla", "model": "Model 3"}])

    zip_path = tmp_path / "cars.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("nested/cars.csv", "id,make,model\n2,Ford,Mustang\n")

    xlsx_path = tmp_path / "cars.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["id", "make", "model"])
    sheet.append(["3", "BMW", "M3"])
    workbook.save(xlsx_path)

    assert load_rows_from_path(csv_path) == [{"id": "1", "make": "Tesla", "model": "Model 3"}]
    assert load_rows_from_path(zip_path) == [{"id": "2", "make": "Ford", "model": "Mustang"}]
    assert load_rows_from_path(xlsx_path) == [{"id": "3", "make": "BMW", "model": "M3"}]


def test_ingest_structured_csv_skips_already_ingested_source(tmp_path: Path) -> None:
    collection_name = "car_specs_test"
    client = get_chroma_client()
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass

    csv_path = tmp_path / "cars.csv"
    write_csv(csv_path, [{"id": "1", "make": "Tesla", "model": "Model 3"}])

    ingest_structured_csv(str(csv_path), collection_name=collection_name, metadata={"source_url": "https://example.com/cars.csv"})
    ingest_structured_csv(str(csv_path), collection_name=collection_name, metadata={"source_url": "https://example.com/cars.csv"})

    collection = client.get_collection(name=collection_name)
    assert collection.count() == 1
