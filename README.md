# Installation steps

## Initial setup

- Projects folder created
- Git installed via MacOS tool
- Git config name and email + SSH
- brew installed as package manager on Mac
- Orbstack installed for docker containers management

## Setup of python, Jupyter and venv

- UV used for python venvs (installed with brew)
    - uv init
    - source .venv/bin/activate
    - (deactivate)
- Some packages installed
    - uv pip install "mcp[cli]" flask transformers torch pydantic
    - also installed mlx-lm (Apple open souce ML framework)
- SQLite database  as app's Short-Term Memory (Truth Layer), ChromaDB (Vector DB) as Long-Term Memory (Association Layer)
- tests folder containing tests files such as test_db to test implementation

[ User Sends Message ]
1. Query SQLite (Get last 10 messages from ONLY this chat_session_xyz)
2. Query ChromaDB (Vector scan ALL historical chats for matching topics)
3. Assemble Prompt: [Chroma Context] + [SQLite 10-Msg Window] + [New Question]
4. Run model ──► Stream AI Response ──► Save everything back to SQLite & ChromaDB

| User Scenario | SQLite Action (Short-Term) | ChromaDB Action (Long-Term) | What the User Experiences |
| :--- | :--- | :--- | :--- |
| **Active Back-and-Forth Chatting** | Provides the last 10 lines of the ongoing topic to keep immediate context. | Returns low relevance scores; no external context is injected. | Fast, highly coherent tracking of the immediate conversation stream. |
| **Continuing a Deep Chat (Message 50+)** | Pulls messages 40–49 to maintain local paragraph and pronoun continuity. | Fetches core project configurations or rules discussed back in messages 1–10. | Seamless tracking. The assistant remembers project boundaries even though raw text drifted out of the sliding window. |
| **Opening a Brand New Chat Tab** | Returns 0 messages, establishing a completely clean conversation slate. | Scans across all historical chat sessions and extracts semantically matching records. | **Cross-chat memory.** The assistant instantly recalls relevant ideas or parameters established in old, closed chat threads. |

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

## Other ideas of things to do

- see to do some data engineering project, create some vector DB, check latest techs (dbt)
