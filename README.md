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

## Setup of Docker container to then run images of compiled code

TODO

echo >> /Users/fredericmyotte/.zprofile
    echo 'eval "$(/opt/homebrew/bin/brew shellenv zsh)"' >> /Users/fredericmyotte/.zprofile
    eval "$(/opt/homebrew/bin/brew shellenv zsh)"