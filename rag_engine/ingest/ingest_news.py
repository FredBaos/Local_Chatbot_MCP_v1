import os
import hashlib
import requests
from bs4 import BeautifulSoup
import chromadb

CHROMA_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "storage", "chroma_db")

def chunk_text(text: str, chunk_size: int = 600, overlap: int = 60):
    """Chunks text into consistent lengths with a sliding character overlap."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += (chunk_size - overlap)
    return chunks

def ingest_web_article(url: str):
    print(f"[*] Fetching and parsing: {url}")
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
    except Exception as e:
        print(f"[-] Failed to fetch target page: {e}")
        return

    soup = BeautifulSoup(response.text, "html.parser")
    title = soup.title.string if soup.title else "Unknown Technical Article"
    
    # Strip unnecessary footer/navigation elements
    for element in soup(["nav", "footer", "script", "style", "header"]):
        element.decompose()
        
    article_text = " ".join(soup.get_text().split())
    text_chunks = chunk_text(article_text)
    
    # Connect to local ChromaDB
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    collection = client.get_or_create_collection(name="tech_news")
    
    documents = []
    metadatas = []
    ids = []
    
    url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
    
    for idx, chunk in enumerate(text_chunks):
        documents.append(chunk)
        metadatas.append({
            "source_url": url,
            "title": title,
            "chunk_index": idx
        })
        ids.append(f"news_{url_hash}_{idx}")
        
    if documents:
        collection.add(documents=documents, metadatas=metadatas, ids=ids)
        print(f"[+] Successfully loaded {len(documents)} chunks from '{title}' into tech_news collection.")

if __name__ == "__main__":
    # Test script standalone verification
    target_url = "https://ollama.com/blog/llama3.2"
    ingest_web_article(target_url)