import os
import chromadb

CHROMA_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "storage", "chroma_db")


def get_chroma_client():
    return chromadb.PersistentClient(path=CHROMA_PATH)


def query_knowledge(collection_name: str, query_text: str, limit: int = 3):
    """
    Queries a targeted external knowledge collection and outputs citations and content text.
    """
    client = get_chroma_client()
    try:
        collection = client.get_collection(name=collection_name)
        results = collection.query(query_texts=[query_text], n_results=limit)

        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        ids = results.get("ids", [[]])[0]

        return [
            {"id": idx, "text": doc, "metadata": meta}
            for idx, doc, meta in zip(ids, documents, metadatas)
        ]
    except Exception as e:
        print(f"Error reading collection {collection_name}: {e}")
        return []
