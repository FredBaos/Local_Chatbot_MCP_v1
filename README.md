# Local Chatbot MCP

A fully local, privacy-preserving chatbot for Apple Silicon Macs. Inference runs on-device via MLX, with a Retrieval-Augmented Generation (RAG) layer over external knowledge (tech newsletters, a vehicle dataset) and a two-tier memory system (short-term session history, long-term cross-chat recall) — no data leaves the machine.

## Features

- **Local inference** — Llama-3.2-3B-Instruct (4-bit) served via MLX, no cloud API calls
- **RAG pipeline** — chunking, embedding, and ChromaDB storage for semantic retrieval over external knowledge
- **Multi-collection knowledge base** — `tech_news` (TLDR newsletters, web-crawled) and `car_specs` (enriched vehicle listings), each independently refreshable
- **Dual memory architecture** — SQLite for short-term session history, ChromaDB for long-term cross-chat recall
- **Distance-thresholded retrieval** — configurable similarity cutoff to keep irrelevant results out of the prompt

## Architecture

Every message flows through three context sources before reaching the model, which are assembled into a single prompt for generation:

```text
                     [ User Sends Message ]
                                │
       ┌────────────────────────┼────────────────────────┐
       ▼                        ▼                        ▼
[ Short-Term Memory ]  [ Cross-Chat Memory ]   [ Reference Knowledge ]
  SQLite DB Query        ChromaDB: chat_memory   ChromaDB: tech_news / car_specs
(Get last 10 messages  (Scan chat history for   (Retrieve relevant articles
 from current session)    matching topics)        & vehicle listings)
       │                        │                        │
       └────────────────────────┼────────────────────────┘
                                ▼
                       [ Assemble Prompt ]
     [Knowledge Context] + [Memory Context] + [SQLite Window] + [Question]
                                │
                                ▼
                     [ Run Model Inference ]
                ──► Stream response to the client
                ──► Save raw exchange to SQLite (short-term)
                ──► Index prompt/response embedding to ChromaDB (long-term)
```

## Data & Knowledge Architecture

ChromaDB serves two distinct roles, split across three collections:

| Collection | Role | Populated by |
| --- | --- | --- |
| `chat_memory` | Long-term memory — semantic recall of past exchanges across *other* chat sessions | `add_paired_memory()` in `rag_engine/storage/chroma_memory.py`, called after every response |
| `tech_news` | Reference knowledge — tech/AI/fintech news articles | `rag_engine/ingest/ingest_tldr_web.py`, crawling TLDR's public newsletter archive |
| `car_specs` | Reference knowledge — used-vehicle listings | `rag_engine/ingest/ingest_csv.py`, from the [Kaggle Vehicle dataset](https://www.kaggle.com/datasets/nehalbirla/vehicle-dataset-from-cardekho) |

**`tech_news`** crawls 5 TLDR newsletters directly from tldr.tech over HTTP — no email account or credentials required: **TLDR** (`tech`), **TLDR AI** (`ai`), **TLDR IT** (`it`), **TLDR Data** (`data`), and **TLDR Fintech** (`fintech`). Each article is parsed into headline, summary, and source link, sponsored placements are filtered out, and documents carry `category`, `newsletter`, `date`, and `source_url` metadata. Already-ingested articles are tracked in `processed_tldr_articles.json` so repeat runs only add new ones.

**`car_specs`** renders each used-car listing as a natural-language paragraph rather than a raw pipe-delimited field dump, and infers a body type (SUV, Sedan, Hatchback, MUV/MPV, Coupe, Convertible, Sports Car) from make and model — the source dataset has no body-type column at all, so without this, a query like "what SUV should I buy" has nothing to match against.

Both collections support an optional `CHROMA_DISTANCE_THRESHOLD` environment variable (a float, e.g. `0.35`) that filters out retrieval results above that cosine distance before they reach the prompt. Lower distance means higher similarity; leave it unset to disable filtering.

## Prerequisites

- **Apple Silicon Mac** (M-series) — MLX requires Apple's GPU/Neural Engine and does not run on Intel Macs or other platforms
- **macOS** with [Homebrew](https://brew.sh) installed
- **Git**, configured with your name, email, and SSH key
- **[uv](https://docs.astral.sh/uv/)** for Python environment and package management (`brew install uv`)

## Setup

### Environment

```bash
uv venv --python 3.14
source .venv/bin/activate
uv sync
```

This installs every dependency pinned in `pyproject.toml` / `uv.lock` — Flask, ChromaDB, MLX, and the rest.

### Initial data population

The knowledge collections start empty. Populate them once before first use — see [Refreshing the knowledge base](#refreshing-the-knowledge-base) below for the exact commands.

### Containerization & deployment (planned)

Not yet implemented. The intent is to containerize the app with Docker, managed locally via [OrbStack](https://orbstack.dev), for a reproducible, portable deployment — tracked in [Improvements](#improvements).

## Usage

### Running the chatbot

```bash
source .venv/bin/activate
python Chatbot_App/app.py
```

Then open `http://127.0.0.1:5000` in a browser. Each new chat tab gets its own session ID; conversations persist in SQLite and are recoverable across restarts.

### Refreshing the knowledge base

**Tech news** — crawls the latest issue of all 5 TLDR newsletters by default:

```bash
python -m rag_engine.ingest.ingest_tldr_web              # latest issue, all 5 newsletters
python -m rag_engine.ingest.ingest_tldr_web --dry-run     # test the pipeline with sample data, no network calls
python -m rag_engine.ingest.ingest_tldr_web --categories tech,ai,dev
python -m rag_engine.ingest.ingest_tldr_web --date 2026-08-20
```

Safe to run repeatedly (e.g. on a daily cron) — already-ingested articles are skipped automatically via `processed_tldr_articles.json`.

**Car specs** — one-time ingestion of the local vehicle dataset (re-running skips a source already ingested):

```bash
python -m rag_engine.ingest.ingest_csv
```

### Configuration

| Variable | Purpose | Default |
| --- | --- | --- |
| `CHROMA_DISTANCE_THRESHOLD` | Max cosine distance for retrieval results before they're excluded from the prompt | unset (no filtering) |

## Improvements

Shipped work is tracked in [CHANGELOG.md](CHANGELOG.md). What's still ahead:

| Priority | Change | Why |
| --- | --- | --- |
| High | Citation & metadata tracking | Enhance RAG to include source tracking, document chunks, and confidence scores in responses |
| High | Car dataset expansion | Explore additional vehicle datasets or user-provided specs for richer domain coverage |
| Medium | Multi-agent systems | Integrate Langchain or CrewAI for complex reasoning chains (e.g., comparative analysis agents) |
| Medium | Streaming optimization | Extend streaming support to RAG result formatting and chunked memory injection |
| Medium | Deduplication engine | Similarity-based deduplication in `tech_news` and other ingestion pipelines, to catch the same story appearing under multiple newsletters |
| Medium | Documentation generation | Use gitingest + LLM to auto-generate project documentation with examples |
| Medium | Docker container | See [Containerization & deployment](#containerization--deployment-planned) above |
| Low | Rename `chat_memory` → `chroma_memory` | Naming consistency across the codebase |
| Exploratory | MCP server exposure | Expose the RAG/memory collections via an MCP server for *external* agents or tools (e.g. Claude Desktop, Cursor) to query directly. Not required for this chatbot's own RAG pipeline, which already calls ChromaDB directly with no protocol overhead — concrete use case still to be determined |
| Future | Internet-connected model | Explore real-time web integration for up-to-date contextual responses |
| Future | Lazy-load MLX model | Defer model initialization until first inference request — faster startup, testable without GPU |
| Future | Vector DB optimization | Profile chunking strategies, embedding model choice, and indexing parameters |
| Future | Data engineering pipeline | Explore dbt, data validation, and versioning for knowledge bases |
