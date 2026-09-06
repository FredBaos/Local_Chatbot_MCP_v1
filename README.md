# Local Chatbot MCP

A fully local, privacy-preserving chatbot for Apple Silicon Macs. Inference runs on-device via MLX, with a Retrieval-Augmented Generation (RAG) layer over external knowledge (tech newsletters, vehicle specs, driving-impression reviews) and a two-tier memory system (short-term session history, long-term cross-chat recall) — no data leaves the machine. Every response reports the sources it drew on, with a relative confidence score per source.

## Features

- **Local inference** — Llama-3.2-3B-Instruct (4-bit) served via MLX, no cloud API calls
- **RAG pipeline** — chunking, embedding, and ChromaDB storage for semantic retrieval over external knowledge
- **Multi-collection knowledge base** — `tech_news` (TLDR newsletters, web-crawled), `car_specs` (~30,000 canonical vehicle trim/engine specs), and `car_reviews` (TopGear driving impressions), each independently refreshable
- **Dual memory architecture** — SQLite for short-term session history, ChromaDB for long-term cross-chat recall
- **Distance-thresholded retrieval** — configurable similarity cutoff to keep irrelevant results out of the prompt
- **Citations & confidence scores** — every response reports which documents it drew on (source, title, link when available) with a relative confidence score, persisted across page reloads

## Architecture

Every message flows through three context sources before reaching the model, which are assembled into a single prompt for generation:

```text
                     [ User Sends Message ]
                                │
       ┌────────────────────────┼────────────────────────┐
       ▼                        ▼                        ▼
[ Short-Term Memory ]  [ Cross-Chat Memory ]   [ Reference Knowledge ]
  SQLite DB Query        ChromaDB: chat_memory   ChromaDB: tech_news / car_specs / car_reviews
(Get last 10 messages  (Scan chat history for   (Retrieve relevant articles,
 from current session)    matching topics)        vehicle specs & driving reviews)
       │                        │                        │
       └────────────────────────┼────────────────────────┘
                                ▼
                       [ Assemble Prompt ]
     [Knowledge Context] + [Memory Context] + [SQLite Window] + [Question]
                                │
                                ▼
                     [ Run Model Inference ]
                ──► Return {response, citations} to the client
                ──► Save raw exchange + citations to SQLite (short-term)
                ──► Index prompt/response embedding to ChromaDB (long-term)
```

## Data & Knowledge Architecture

ChromaDB serves two distinct roles, split across four collections:

| Collection | Role | Populated by |
| --- | --- | --- |
| `chat_memory` | Long-term memory — semantic recall of past exchanges across *other* chat sessions | `add_paired_memory()` in `rag_engine/storage/chroma_memory.py`, called after every response |
| `tech_news` | Reference knowledge — tech/AI/fintech news articles | `rag_engine/ingest/ingest_tldr_web.py`, crawling TLDR's public newsletter archive |
| `car_specs` | Reference knowledge — canonical vehicle trim/engine specifications | `rag_engine/ingest/ingest_automobile_specs.py`, from the [automobile-models-and-specs](https://github.com/ilyasozkurt/automobile-models-and-specs) dataset |
| `car_reviews` | Reference knowledge — subjective driving impressions (ride, handling, comfort, verdict) | `rag_engine/ingest/ingest_topgear_reviews.py`, crawling topgear.com's public review pages |

**`tech_news`** crawls 5 TLDR newsletters directly from tldr.tech over HTTP — no email account or credentials required: **TLDR** (`tech`), **TLDR AI** (`ai`), **TLDR IT** (`it`), **TLDR Data** (`data`), and **TLDR Fintech** (`fintech`). Each article is parsed into headline, summary, and source link, sponsored placements are filtered out, and documents carry `category`, `newsletter`, `date`, and `source_url` metadata. Already-ingested articles are tracked in `processed_tldr_articles.json` so repeat runs only add new ones.

**`car_specs`** holds ~30,000 individual engine/trim variants across 124 brands and ~7,200 models (one row per real-world configuration, not per resale listing) — engine, performance (0-62 acceleration, top speed), transmission, brakes, tires, dimensions, weight, and fuel economy, rendered as natural-language paragraphs. Body type (SUV, Sedan, Coupe, etc.) isn't a structured field in the source data either, so it's inferred by keyword match against the model title and description, which — unlike a bare spec table — usually mention it directly.

This dataset covers specs comprehensively but not subjective driving impressions (handling, ride comfort, steering feel) — that gap is filled by `car_reviews` below.

**`car_reviews`** holds subjective driving-impression content — ride, handling, comfort, and overall verdict — crawled from topgear.com's review pages. Canonical review URLs (e.g. `/car-reviews/audi/rs5`) are discovered via topgear.com's public XML sitemap; each page is a Next.js SSR page that embeds a `<script id="__NEXT_DATA__">` JSON blob with structured `drivingText`, `verdict`, `verdictText`, `verdictTextFor`/`verdictTextAgainst`, `whatWeSayText`, and `rating` fields — extracted directly from that blob rather than scraping the visible DOM, which uses hashed styled-components classes with no stable selectors. The full catalog has 1,000+ reviews; each run fetches 25 new ones by default (`--limit`) and is meant to be re-run repeatedly, like `ingest_tldr_web.py`, to build up coverage over time. Already-ingested reviews are tracked in `processed_topgear_reviews.json`, checked at discovery time so repeat runs skip straight to unfetched URLs.

*Provenance note:* the specs dataset above was originally scraped from autoevolution.com and republished as an open dataset on GitHub by a third party; autoevolution.com's own `robots.txt` disallows scraping, though the republished data itself is presented as free to use. Its `automobiles.csv` also ships with a header row that doesn't match its actual column content — `ingest_automobile_specs.py` reads it positionally rather than trusting the header; see the module docstring for the verified column order.

All three reference-knowledge collections support an optional `CHROMA_DISTANCE_THRESHOLD` environment variable (a float, e.g. `0.35`) that filters out retrieval results above that distance before they reach the prompt. Lower distance means higher similarity; leave it unset to disable filtering.

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

The knowledge collections start empty. `tech_news` populates itself by crawling TLDR directly, but `car_specs` needs its source data downloaded first (~125MB, not committed to the repo):

```bash
mkdir -p rag_engine/storage/data/automobile_specs
curl -sL "https://raw.githubusercontent.com/ilyasozkurt/automobile-models-and-specs/master/automobiles.csv.zip" -o /tmp/automobiles.csv.zip
unzip -oq /tmp/automobiles.csv.zip -d /tmp/automobiles_extract
cp /tmp/automobiles_extract/{brands,automobiles,engines}.csv rag_engine/storage/data/automobile_specs/
rm -rf /tmp/automobiles.csv.zip /tmp/automobiles_extract
```

See [Refreshing the knowledge base](#refreshing-the-knowledge-base) below for the ingestion commands.

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

**Car specs** — one-time ingestion of the ~30,000-variant specs dataset (see [Initial data population](#initial-data-population) to download it first; takes roughly 5 minutes):

```bash
python -m rag_engine.ingest.ingest_automobile_specs
```

**Car reviews** — crawls topgear.com's driving-impression reviews, 25 new ones per run by default:

```bash
python -m rag_engine.ingest.ingest_topgear_reviews              # 25 new reviews
python -m rag_engine.ingest.ingest_topgear_reviews --dry-run     # test the pipeline with sample data, no network calls
python -m rag_engine.ingest.ingest_topgear_reviews --limit 100
```

Safe to run repeatedly (e.g. on a daily cron) — already-ingested reviews are skipped automatically via `processed_topgear_reviews.json`. The full catalog has 1,000+ reviews, so repeated runs are the intended way to build up coverage over time.

### MCP server

`mcp_servers/knowledge_mcp_server.py` exposes `car_specs`, `car_reviews`, `tech_news`, and `chat_memory` as MCP tools (`search_car_specs`, `search_car_reviews`, `search_tech_news`, `search_chat_memory`) via FastMCP, so external MCP clients — Claude Desktop, Cursor, a future orchestrator agent — can query this project's knowledge base directly. This is additive: `Chatbot_App/app.py`'s own RAG pipeline is unchanged and doesn't use this server; it calls `query_knowledge()` / `retrieve_memory()` directly, in-process, exactly as before.

Run standalone (mainly useful for testing — a real MCP client launches it for you):

```bash
python -m mcp_servers.knowledge_mcp_server
```

#### Connecting it to Claude Desktop

**1. Get the two paths the config needs.** From the project root, with the venv activated:

```bash
cd /path/to/Local_Chatbot_MCP_v1
source .venv/bin/activate
pwd                        # → this is your "cwd" value
echo "$(pwd)/.venv/bin/python"   # → this is your "command" value
```

There's nothing to look up beyond that — `args` is always the same fixed value (it just tells Python which module to run), and there's no API key, port, or account involved since the server only talks to Claude Desktop over stdio and reads your local ChromaDB.

**2. Open Claude Desktop's config file.** In Claude Desktop: **Settings → Developer → Edit Config** — this opens (and creates, if it doesn't exist yet) `claude_desktop_config.json` in your editor. On macOS it lives at:

```
~/Library/Application Support/Claude/claude_desktop_config.json
```

**3. Add this server** under `mcpServers`, using the two values from step 1 (if the file already has other servers configured, add this alongside them rather than replacing the file):

```json
{
  "mcpServers": {
    "local-chatbot-knowledge": {
      "command": "/Users/you/Documents/Projects/Local_Chatbot_MCP_v1/.venv/bin/python",
      "args": ["-m", "mcp_servers.knowledge_mcp_server"],
      "cwd": "/Users/you/Documents/Projects/Local_Chatbot_MCP_v1"
    }
  }
}
```

**4. Restart Claude Desktop completely** (quit, don't just close the window) so it picks up the new config.

**5. Verify it connected.** Open a new chat and look for a tools/plug icon near the message box — `local-chatbot-knowledge` should be listed with its four tools. A quick functional check: ask Claude something only this data would know, e.g. *"Using the car specs tool, look up the Porsche 911 (992) Carrera"* — a working connection returns real spec data; if the server isn't wired up, Claude has no such tool to call.

Cursor works the same way via its own `mcp.json`, with the identical `command`/`args`/`cwd` shape.

### Configuration

| Variable | Purpose | Default |
| --- | --- | --- |
| `CHROMA_DISTANCE_THRESHOLD` | Max Chroma distance for retrieval results before they're excluded from the prompt | unset (no filtering) |

## Improvements

Shipped work is tracked in [CHANGELOG.md](CHANGELOG.md). What's still ahead:

| Priority | Change | Why |
| --- | --- | --- |
| Medium | Streaming optimization | Extend streaming support to RAG result formatting and chunked memory injection |
| Medium | Deduplication engine | Similarity-based deduplication in `tech_news` and other ingestion pipelines, to catch the same story appearing under multiple newsletters |
| Medium | Documentation generation | Use gitingest + LLM to auto-generate project documentation with examples |
| Medium | Docker container | See [Containerization & deployment](#containerization--deployment-planned) above |
| Low | Rename `chat_memory` → `chroma_memory` | Naming consistency across the codebase |
| Exploratory | Inline citation markers | Have the model emit `[1]`/`[2]`-style markers tied to specific claims in its answer, rather than attaching the full list of retrieved sources per turn as done today — needs a prompt change, not just response-shape plumbing |
| Exploratory | Agent orchestration state of the art | Explore current multi-agent orchestration techniques and frameworks (e.g. Langchain, CrewAI) beyond single-tool MCP calls — routing, delegation, and combining outputs across specialized agents. One candidate: a car-research assistant pairing a specs-lookup agent (`search_car_specs`) with a driving-impressions agent (`search_car_reviews`), orchestrated to answer comparative questions ("996 vs 991 Carrera — specs and how they drive") |
| Future | Internet-connected model | Explore real-time web integration for up-to-date contextual responses |
| Future | Lazy-load MLX model | Defer model initialization until first inference request — faster startup, testable without GPU |
| Future | Vector DB optimization | Profile chunking strategies, embedding model choice, and indexing parameters |
| Future | Data engineering pipeline | Explore dbt, data validation, and versioning for knowledge bases |
