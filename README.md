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
        - `tech_news`: Automated ingestion from 5 TLDR newsletters (TLDR, TLDR AI, TLDR IT, TLDR Data, TLDR Fintech — articles, summaries, source links) via `ingest_tldr_web.py`
        - `car_specs`: Structured collection from [Kaggle Vehicle dataset](https://www.kaggle.com/datasets/nehalbirla/vehicle-dataset-from-cardekho) via `ingest_csv.py`, enriched with an inferred body type (SUV, Sedan, Hatchback, etc.) and rendered as natural-language listings

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
  - Renders each used-car listing as a natural-language paragraph rather than a raw pipe-delimited field dump
  - Infers a body type (SUV, Sedan, Hatchback, MUV/MPV, Coupe, Convertible, Sports Car) from make + model, since the source dataset has no such column — this is what makes "what SUV..." style questions actually retrievable
  - Also tags each row with `make`, `model`, `body_type`, `price`, and `year` metadata
- **`ingest_tldr_web.py`**: Crawls TLDR's public newsletter archive (tldr.tech) → `tech_news` collection
  - Fetches daily issues directly over HTTP — no email account or credentials needed
  - Crawls 5 newsletters by default: **TLDR** (`tech`), **TLDR AI** (`ai`), **TLDR IT** (`it`), **TLDR Data** (`data`), **TLDR Fintech** (`fintech`)
  - Parses headline, summary, and outbound source link per article; filters out sponsored placements
  - Chunks and vectorizes for semantic search
  - Enriches documents with metadata: `category` (slug), `newsletter` (display name), `date`, `source_url`, `title`

### Using the TLDR Web Crawler

**No credentials required** — this crawls TLDR's public site directly, unlike the old email-based scraper.

**Quick Test (Dry-Run Mode):**

Test the pipeline without making any network calls:
```bash
cd /Users/fredericmyotte/Documents/Projects/Local_Chatbot_MCP_v1
source .venv/bin/activate
python -m rag_engine.ingest.ingest_tldr_web --dry-run
```

This demonstrates the full ingestion pipeline with sample data, verifying:
- ✅ ChromaDB connection works
- ✅ Article chunking logic works
- ✅ Document ingestion to `tech_news` collection works
- ✅ Processed article tracking initializes correctly

**Real Usage:**
```bash
python -m rag_engine.ingest.ingest_tldr_web
```

By default this crawls the latest issue of all 5 newsletters (`tech`, `ai`, `it`, `data`, `fintech`). Pick different categories or a specific past issue:
```bash
python -m rag_engine.ingest.ingest_tldr_web --categories tech,ai,dev
python -m rag_engine.ingest.ingest_tldr_web --date 2026-08-20
```

**Incremental Updates (Process Only New Articles):**

The crawler automatically tracks ingested articles in:
```
rag_engine/storage/data/processed_tldr_articles.json
```

On each run:
- ✅ Previously ingested articles are **skipped** (matched by category + date + source URL)
- ✅ Only **new articles** are fetched and ingested
- ✅ Processed article IDs are persisted for next run
- ✅ You can safely run the crawler multiple times (e.g. on a daily cron) without duplicate ingestion

**Example Workflow:**
```bash
# First run: Fetches the latest issue of all 5 newsletters
python -m rag_engine.ingest.ingest_tldr_web
# Output: ✓ Successfully ingested X chunks from Y new articles

# Later: Run again after the next day's issue is published
python -m rag_engine.ingest.ingest_tldr_web
# Output: ⊘ Skipped N already-processed articles, ✓ Successfully ingested M new chunks
```

**Customization:**

Pass these as arguments to `ingest_tldr_web()` (or extend the CLI) to change:
- `categories`: TLDR category slugs to crawl (default: `["tech", "ai", "it", "data", "fintech"]`)
- `chunk_size`: Characters per chunk (default: 500)
- `chunk_overlap`: Overlap between chunks (default: 50)

## MCP Server for Vector DB Access (Planned — not yet implemented)

> **Note on MCP + RAG Architecture:** RAG (Retrieval-Augmented Generation) and MCP (Model Context Protocol) serve complementary purposes. RAG is the **retrieval mechanism** (how you search and fetch relevant documents), while MCP is the **protocol/interface** (how other agents/services access your tools). Consider implementing a local MCP server that exposes the ChromaDB vector DB as a searchable resource — this would allow:
> - External AI agents to query your `tech_news`, `car_specs`, and `chat_memory` collections
> - Other tools/services in your ecosystem to access your knowledge base
> - A common interface for multi-agent systems (e.g., CrewAI, AutoGPT)
> - Future scaling to expose your RAG engine as a micro-service
>
> **Example:** An MCP tool named `search_tech_news(query: str)` → calls ChromaDB, returns top-K relevant chunks with metadata. This decouples your RAG implementation from external consumers.

### 🔌 Proposed Local MCP Server Design

Design sketch for a future local FastMCP server (`mcp_servers/knowledge_mcp_server.py`) exposing unified tool endpoints over stdio for external AI agents (Claude Desktop, VS Code, Cursor) — see the Planned Improvements table below for status:

* **`search_tech_news(query)`**: On-demand semantic vector search across ingested newsletter archives (`tech_news` collection in ChromaDB).
* **`search_car_specs(query)`**: Structured knowledge retrieval across technical specifications and datasets (`car_specs` collection).
* **`search_chat_memory(query)`**: On-demand cross-chat memory retrieval (`chat_memory` collection), allowing external agents to query past conversation topics, user preferences, and historical session logs without context pollution.

## Planned Improvements

### Currently Implemented ✅
- **RAG Pipeline**: Chunking, vectorization, and ChromaDB storage for semantic retrieval
- **Multi-Collection Knowledge**: Separate collections for `car_specs` (2,059 docs), `tech_news` (growing via TLDR web crawl), and `chat_memory` (growing per session)
- **Dual Memory Architecture**: SQLite (short-term) + ChromaDB (long-term + reference knowledge)

See [Done Changes](#done-changes) at the end of this doc for the full shipped-improvements log.

| Priority | Change | Why |
| --- | --- | --- |
| High | Citation & Metadata Tracking | Enhance RAG to include source tracking, document chunks, and confidence scores in responses |
| High | MCP Server Implementation | Expose RAG/memory tools via MCP endpoints (aligns with project name vision) |
| High | Car Dataset Expansion | Explore additional vehicle datasets or user-provided specs for richer domain coverage |
| Medium | Multi-Agent Systems | Integrate Langchain or CrewAI for complex reasoning chains (e.g., comparative analysis agents) |
| Medium | Streaming Optimization | Extend streaming support to RAG result formatting and chunked memory injection |
| Medium | Deduplication Engine | Implement similarity-based deduplication in `tech_news` and other ingestion pipelines to avoid vector DB bloat |
| Medium | Documentation Generation | Use gitingest + LLM to auto-generate project documentation with examples |
| Medium | Setup of Docker container | Using OrbStack, to then run images of compiled code |
| Low | Rename `chat_memory` → `chroma_memory` or update README | Consistency across codebase |
| Future | Internet-Connected Model | Explore real-time web integration for up-to-date contextual responses |
| Future | Lazy-load MLX model | Defer MLX model initialization until first inference request — faster startup, testable without GPU |
| Future | Vector DB Optimization | Profile chunking strategies, embedding model choice, and indexing parameters |
| Future | Data Engineering Pipeline | Explore dbt, data validation, and versioning for knowledge bases |

## Done Changes

Archive of shipped improvements, most recent first.

| Priority | Change | Why |
| --- | --- | --- |
| High | Enrich `car_specs` and fix RAG hallucination on sparse/generic questions | `car_specs` is now rendered as natural-language paragraphs with an inferred `body_type` (was a raw pipe-delimited dump with no body-type field at all, so "SUV" questions silently returned sedans). Also rewrote the system prompt for both `tech_news` and `car_specs` context blocks (numbered lists, explicit "don't invent items" framing, and — the fix that actually mattered — restating the constraint in the final user turn, since the model weights instructions near generation far more than ones earlier in the system messages) after live-testing showed generic questions ("tell me about the Honda Amaze", "what SUV should I buy") still triggered fabricated cars/specs even with a good context block. `car_specs` was wiped and freshly re-ingested under the new format. |
| High | Replace Outlook email scraper with TLDR web crawler | New `ingest_tldr_web.py` crawls tldr.tech's public archive directly over HTTP — no email account, IMAP, or credentials needed. Crawls 5 newsletters (TLDR, TLDR AI, TLDR IT, TLDR Data, TLDR Fintech) by default, tagging each document with `category` and `newsletter` metadata. Parses headline/summary/source link per article, filters sponsors, and ingests into `tech_news` with **incremental tracking** via `processed_tldr_articles.json`. The old `ingest_outlook_news.py` (IMAP-based) is archived on the `email_crawler` git branch, not deleted outright. `tech_news` was wiped and freshly re-ingested under the new schema. |
| High | Implement TLDR Outlook news scraper (superseded) | Original `ingest_outlook_news.py` connected to Outlook IMAP, fetched from the 'News' folder, parsed HTML, and ingested into `tech_news` with secure password prompting and incremental email tracking. Replaced by the web crawler above — see `email_crawler` branch for the source. |
| High | Add Chroma distance threshold before injecting RAG/memory | Implemented `CHROMA_DISTANCE_THRESHOLD` (env var) and per-call filtering in `rag_engine/storage/chroma_memory.py` and `rag_engine/storage/chroma_knowledge.py` to avoid irrelevant injections. Optional env var can be set to a float (e.g., `0.35`) to filter by distance; lower distance = higher similarity (cosine space). |
| High | Sync `pyproject.toml` with real deps | Added `chromadb`, `mlx-lm`, `pydantic`, and `mcp` to `pyproject.toml` to better reflect runtime/test requirements. |
| Medium | Pair user+assistant in long-term memory | New `add_paired_memory()` stores a single combined document for user+assistant replies to improve retrieval associations. |
| Medium | Add streaming to `/analyze` | `/analyze` supports a `stream` flag; when enabled it returns a chunked `text/plain` response. Note: generation still runs to completion first — the response is chunked afterward, not streamed token-by-token from the model. |
| Medium | Use real chat turns in `apply_chat_template()` | Now we pass recent chat turns as real `role`/`content` messages into `tokenizer.apply_chat_template()` for improved conversational context. |

## Archived Branches

- **`email_crawler`**: Snapshot of `main` before the Outlook/IMAP news scraper was removed. Holds `ingest_outlook_news.py` in full (IMAP connection, HTML cleaning, secure password prompt, `processed_emails.json` tracking) for reference or in case email-based ingestion is ever revisited. Superseded on `main` by `ingest_tldr_web.py`, which crawls TLDR's public archive over HTTP instead.
