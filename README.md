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

## Setup of Docker container to then run images of compiled code

TODO

## Other things to explore, include or change in my project

- prettify the UI, retake html css and js files
- move to a bigger local model to have a better chatbot
-- use other torch models or apple MLX with Llama 3.2 or Qwen 2.5 
- include some RAG capabilities
- study MCP question and understand concrete applications

## Other ideas of things to do

- see to do some data engineering project, create some vector DB, check latest techs (dbt)