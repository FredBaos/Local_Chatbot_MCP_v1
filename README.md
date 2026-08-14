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
        - `chroma_memory`: Dedicated to semantic matching of cross-chat historical prompts.
        - `tech_news`: Dedicated unstructured collection for scraped web data and technical documentation summaries.
        - `car_specs`: Dedicated structured collection capturing tabular data narrative segments, source is [Kaggle Vehicle dataset](https://www.kaggle.com/datasets/nehalbirla/vehicle-dataset-from-cardekho)

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

## Setup of Docker container to then run images of compiled code

TODO

## Other things to explore, include or change in my project

- create some knowledge or documentation and add the below + pdf from drive
RAG : Chunking -> vectorize with embeddings in vector DB, then you can query it to retrieve relevant chunks from DB. also check interest of citation tracking and metadata usage. 
- check for optimal folder structure to have MCP RAG Vector DB etc.
- connect model to internet and create a vector db with news (TLDR) articles about AI and Tech and then use RAG
- other vector DB about cars specs
- check other things to do (paper on google drive about AI concepts)
- include some RAG capabilities
- study MCP question and understand concrete applications
- check multi-agents systems: Langchain & crewai
- use gitingest.com and some LLM to generate a nice documentation (Gemini output) once RAG and MCP and multiagent added

## Planned Improvements

| Priority | Change | Why |
| --- | --- | --- |
| High | Add Chroma distance threshold before injecting RAG/memory — DONE | Implemented `CHROMA_DISTANCE_THRESHOLD` (env var) and per-call filtering in `rag_engine/storage/chroma_memory.py` and `rag_engine/storage/chroma_knowledge.py` to avoid irrelevant injections. |
| High | Sync `pyproject.toml` with real deps — DONE | Added `chromadb`, `mlx-lm`, `pydantic`, and `mcp` to `pyproject.toml` to better reflect runtime/test requirements. |
| Medium | Use real chat turns in `apply_chat_template()` | Better model behavior |
| Medium | Add streaming to `/analyze` | Matches README, better UX |
| Medium | Pair user+assistant in long-term memory | Better cross-chat recall |
| Low | Deduplicate news ingest | Avoid vector DB bloat |
| Low | Rename `chat_memory` → `chroma_memory` or update README | Consistency |
| Future | Lazy-load MLX model | Faster startup, testable without GPU |
| Future | Implement MCP server exposing RAG/memory tools | Matches project name and README vision |

## Other ideas of things to do

- see to do some data engineering project, create some vector DB, check latest techs (dbt)
