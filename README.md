# Installation steps

## Initial setup

- Projects folder created
- Git installed via MacOS tool
- Git config name and email + SSH
- brew installed as package manager on Mac
- Orbstack installed for docker containers management

## Setup of Python, Virtual Environments, and Storage

- **UV Integration** used for lightning-fast package and virtual environment management (installed via Homebrew):
    - `uv venv --python 3.14`
    - `source .venv/bin/activate`
    - `deactivate`
- **Core Dependencies Architecture**:
    - App server & tools: `uv pip install "mcp[cli]" flask flask-cors pydantic numpy`
    - Local Computation & Vector store: `uv pip install mlx-lm chromadb`
- **Multi-Tiered Data & Knowledge Architecture**:
    - **SQLite Database**: Serves as the application's **Short-Term Memory (Truth Layer)** tracking real-time conversations per session.
    - **ChromaDB (Vector DB)**: Operates both as the **Long-Term Memory (Association Layer)** for past chat records and as a **Reference Knowledge Layer** separating custom data ingestions into distinct collections:
        - `chat_memory`: Semantic matching of cross-chat historical prompts and conversation memory
        - `tech_news`: Automated ingestion from Outlook's 'News' folder (TLDR newsletters, tech articles, AI summaries) via `ingest_outlook_news.py`
        - `car_specs`: Structured collection from [Kaggle Vehicle dataset](https://www.kaggle.com/datasets/nehalbirla/vehicle-dataset-from-cardekho) via `ingest_csv.py`

## Data Flow & Context Pipeline

```text
                     [ User Sends Message ]
                                │
       ┌────────────────────────┼────────────────────────┐
       ▼                        ▼                        ▼
[ Short-Term Memory ]  [ Cross-Chat Memory ]   [ Reference Knowledge ]
  SQLite DB Query        ChromaDB: memory        ChromaDB: tech_news / car_specs
(Get last 10 messages  (Scan chat history for   (Retrieve unstructured articles 
 from current session)    matching topics)        & structured narrative facts)
       │                        │                        │
       └────────────────────────┼────────────────────────┘
                                ▼
                       [ Assemble Prompt ]
     [Knowledge Context] + [Memory Context] + [SQLite Window] + [Question]
                                │
                                ▼
                     [ Run Model Inference ]
                ──► Stream AI Local Response
                ──► Save raw exchange to SQLite (Short-Term)
                ──► Index prompt/response embedding to ChromaDB (Long-Term)
```

## Data Ingestion Modules

The `rag_engine/ingest/` directory contains modular pipelines for populating ChromaDB collections:

- **`ingest_csv.py`**: Processes tabular data (CSV files) → `car_specs` collection (2,059 documents from Kaggle vehicle dataset)
- **`ingest_outlook_news.py`**: Scrapes TLDR/tech newsletters from Outlook's 'News' folder → `tech_news` collection
  - Connects via IMAP to `outlook.office365.com`
  - Parses HTML, removes clutter (ads, unsubscribe links)
  - Chunks and vectorizes for semantic search
  - Enriches documents with metadata (sender, subject, date)
- **`ingest_news.py`**: [Extensible for future news sources]

## Other Things to Explore & Improve

### Currently Implemented ✅
- **RAG Pipeline**: Chunking, vectorization, and ChromaDB storage for semantic retrieval
- **Multi-Collection Knowledge**: Separate collections for `car_specs` (2,059 docs), `tech_news` (growing via Outlook), and `chat_memory` (46 docs)
- **Distance Thresholding**: Configured via `CHROMA_DISTANCE_THRESHOLD` to filter irrelevant results
- **Dual Memory Architecture**: SQLite (short-term) + ChromaDB (long-term + reference knowledge)
- **News Ingestion Pipeline**: Automated TLDR/Outlook email scraping with HTML parsing and metadata enrichment

### High Priority (Next Phase)
- **Citation & Metadata Tracking**: Enhance RAG to include source tracking, document chunks, and confidence scores in responses
- **MCP Server Implementation**: Expose RAG/memory tools via MCP endpoints (aligns with project name vision)
- **Car Dataset Expansion**: Explore additional vehicle datasets or user-provided specs for richer domain coverage

### Medium Priority (Polish & Scale)
- **Multi-Agent Systems**: Integrate Langchain or CrewAI for complex reasoning chains (e.g., comparative analysis agents)
- **Streaming Optimization**: Extend streaming support to RAG result formatting and chunked memory injection
- **Deduplication Engine**: Implement similarity-based deduplication in `tech_news` and other ingestion pipelines
- **Documentation Generation**: Use gitingest + LLM to auto-generate project documentation with examples
- **Setup of Docker container**: using OrbStack, to then run images of compiled code

### Lower Priority (Exploration)
- **Internet-Connected Model**: Explore real-time web integration for up-to-date contextual responses
- **Lazy Model Loading**: Defer MLX model initialization until first inference request
- **Vector DB Optimization**: Profile chunking strategies, embedding model choice, and indexing parameters
- **Data Engineering Pipeline**: Explore dbt, data validation, and versioning for knowledge bases

## Planned Improvements

| Priority | Status | Change | Why |
| --- | --- | --- | --- |
| High | DONE | Add Chroma distance threshold before injecting RAG/memory | Implemented `CHROMA_DISTANCE_THRESHOLD` (env var) and per-call filtering in `rag_engine/storage/chroma_memory.py` and `rag_engine/storage/chroma_knowledge.py` to avoid irrelevant injections. Optional env var can be set to a float (e.g., `0.35`) to filter by distance; lower distance = higher similarity (cosine space). |
| High | DONE | Sync `pyproject.toml` with real deps | Added `chromadb`, `mlx-lm`, `pydantic`, and `mcp` to `pyproject.toml` to better reflect runtime/test requirements. |
| High | DONE | Implement TLDR Outlook news scraper | New `ingest_outlook_news.py` connects to Outlook IMAP, fetches from 'News' folder, parses HTML, removes clutter, and ingests into `tech_news` collection with full metadata tracking. Supports configurable email limits, chunk sizes, and IMAP parameters. |
| Medium | DONE | Use real chat turns in `apply_chat_template()` | Now we pass recent chat turns as real `role`/`content` messages into `tokenizer.apply_chat_template()` for improved conversational context. |
| Medium | DONE | Add streaming to `/analyze` | `/analyze` supports `stream` flag; when enabled it returns a streaming text/plain response. |
| Medium | DONE | Pair user+assistant in long-term memory | New `add_paired_memory()` stores a single combined document for user+assistant replies to improve retrieval associations. |
| Low | TODO | Deduplicate news ingest | Avoid vector DB bloat with duplicate/similar articles |
| Low | TODO | Rename `chat_memory` → `chroma_memory` or update README | Consistency across codebase |
| Future | TODO | Lazy-load MLX model | Faster startup, testable without GPU |
| Future | TODO | Implement MCP server exposing RAG/memory tools | Matches project name and README vision |
