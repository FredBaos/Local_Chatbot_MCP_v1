"""
Local Knowledge MCP Server

Exposes this project's ChromaDB collections (car_specs, car_reviews,
tech_news, chat_memory) as MCP tools, so external MCP clients — Claude
Desktop, Cursor, a future orchestrator agent — can query the same data the
chatbot's own RAG pipeline uses, without needing to know ChromaDB,
embeddings, or this codebase exists.

This is additive, not a replacement: Chatbot_App/app.py keeps calling
query_knowledge() / retrieve_memory() directly, in-process, exactly as before.
This server is a second, independent front door onto the same collections for
callers outside this app. See the "MCP server exposure" entry in the README's
Improvements section for the reasoning.

Running standalone:
    python -m mcp_servers.knowledge_mcp_server

Configuring as an MCP server (e.g. Claude Desktop's claude_desktop_config.json,
or Cursor's mcp.json):
    {
      "mcpServers": {
        "local-chatbot-knowledge": {
          "command": "/absolute/path/to/.venv/bin/python",
          "args": ["-m", "mcp_servers.knowledge_mcp_server"],
          "cwd": "/absolute/path/to/Local_Chatbot_MCP_v1"
        }
      }
    }
"""

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp.server.fastmcp import FastMCP

from rag_engine.storage.chroma_knowledge import query_knowledge
from rag_engine.storage.chroma_memory import retrieve_memory

mcp = FastMCP(
    "local-chatbot-knowledge",
    instructions=(
        "Search this local chatbot's knowledge base: tech/AI/fintech news, "
        "vehicle specs, and driving-impression reviews (car_specs, "
        "car_reviews, and tech_news are reference knowledge; chat_memory is "
        "long-term memory of past chat sessions on this machine)."
    ),
)


@mcp.tool()
def search_tech_news(query: str, limit: int = 5) -> list[dict]:
    """
    Search tech/AI/fintech news articles crawled from TLDR's newsletters
    (TLDR, TLDR AI, TLDR IT, TLDR Data, TLDR Fintech).

    Args:
        query: Natural-language search query.
        limit: Maximum number of results to return.

    Returns:
        List of {id, text, metadata} results, most relevant first. metadata
        includes category, newsletter, date, source_url, and title.
    """
    return query_knowledge(collection_name="tech_news", query_text=query, limit=limit)


@mcp.tool()
def search_car_specs(query: str, limit: int = 5) -> list[dict]:
    """
    Search ~30,000 canonical vehicle engine/trim specifications (make, model,
    engine, performance, dimensions, weight, brakes, tires, fuel economy).
    Covers hard specs only — no subjective driving-impression content yet.

    Args:
        query: Natural-language search query (e.g. a make/model, or a
            category like "SUV with good off-road capability").
        limit: Maximum number of results to return.

    Returns:
        List of {id, text, metadata} results, most relevant first. metadata
        includes make, model, body_type, price, and year.
    """
    return query_knowledge(collection_name="car_specs", query_text=query, limit=limit)


@mcp.tool()
def search_car_reviews(query: str, limit: int = 5) -> list[dict]:
    """
    Search subjective driving-impression reviews crawled from topgear.com
    (ride, handling, comfort, verdict) — complements search_car_specs, which
    covers hard numbers only.

    Args:
        query: Natural-language search query (e.g. a make/model, or a
            question like "how does it handle in corners").
        limit: Maximum number of results to return.

    Returns:
        List of {id, text, metadata} results, most relevant first. metadata
        includes make, model, body_type, rating, and source_url.
    """
    return query_knowledge(collection_name="car_reviews", query_text=query, limit=limit)


@mcp.tool()
def search_chat_memory(query: str, limit: int = 5) -> list[dict]:
    """
    Search this chatbot's long-term memory of past chat sessions on this
    machine (semantic search over previously stored user+assistant exchanges).

    Args:
        query: Natural-language search query.
        limit: Maximum number of results to return.

    Returns:
        List of {text, metadata} results, most relevant first. metadata
        includes the originating session_id.
    """
    return retrieve_memory(query=query, limit=limit)


if __name__ == "__main__":
    mcp.run()
