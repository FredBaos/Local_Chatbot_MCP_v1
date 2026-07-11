import os
import csv

from rag_engine.storage.chroma_memory import get_chroma_client

def ingest_structured_csv(file_path: str, collection_name: str = "car_specs"):
    """
    Transforms structured dataset entries into readable paragraphs 
    to preserve data integrity for embedding similarity matches.
    """
    if not os.path.exists(file_path):
        print(f"[-] Data file not found at: {file_path}")
        return
        
    client = get_chroma_client()
    collection = client.get_or_create_collection(name=collection_name)
    
    documents = []
    metadatas = []
    ids = []
    
    print(f"[*] Processing data mapping from: {file_path}")
    with open(file_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader):
            # Formulate a cohesive narrative text structure out of row parameters
            description_sentences = []
            for key, value in row.items():
                if value:
                    description_sentences.append(f"{key.replace('_', ' ').title()}: {value}")
            
            row_text = " | ".join(description_sentences)
            
            # Identify single primary identifiers safely if available
            row_id = row.get("id") or row.get("model_id") or f"row_{idx}"
            
            documents.append(row_text)
            metadatas.append({
                "source_file": os.path.basename(file_path),
                "row_index": idx
            })
            ids.append(f"csv_{collection_name}_{row_id}")
            
    if documents:
        collection.add(documents=documents, metadatas=metadatas, ids=ids)
        print(f"[+] Successfully integrated {len(documents)} structured items into '{collection_name}' collection.")

if __name__ == "__main__":
    # Setup placeholder data context to execute proof-of-concept run
    dummy_csv_path = "sample_cars.csv"
    with open(dummy_csv_path, "w", newline="", encoding="utf-8") as df:
        writer = csv.writer(df)
        writer.writerow(["id", "brand", "model", "engine_type", "horsepower"])
        writer.writerow(["001", "Tesla", "Model 3", "Electric", "283"])
        writer.writerow(["002", "Porsche", "911 GT3", "Gasoline", "502"])
        
    ingest_structured_csv(dummy_csv_path)
    if os.path.exists(dummy_csv_path):
        os.remove(dummy_csv_path)