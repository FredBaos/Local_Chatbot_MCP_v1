# Installation steps

## Initial setup

- Projects folder created
- Git installed via MacOS tool
- Git config name and email + SSH
- brew installed as package manager on Mac
- Orbstack installed for docker containers management

## Setup of python, Jupyter and venv

- UV used for python venvs (installed with brew)
-- uv env
-- source .venv/bin/activate
-- (deactivate)
- Some packages installed
-- uv pip install "mcp[cli]" flask transformers torch pydantic
-- also installed mlx-lm (Apple open souce ML framework)

## Setup of Docker container to then run images of compiled code

TODO

## Other things to explore, include or change in my project

- keep chatbot state in some (vector) DB? 
- enable context as each input to model independent
- check for optimal folder structure to have MCP RAG Vector DB etc.
- connect model to internet and create a vector db with news (TLDR) articles about AI and Tech and then use RAG
- check other things to do (paper on google drive about AI concepts)
- include some RAG capabilities
- study MCP question and understand concrete applications

## Other ideas of things to do

- see to do some data engineering project, create some vector DB, check latest techs (dbt)