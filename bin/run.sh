#!/bin/bash
set -e

# Get the directory where the script is located
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$DIR")"

>&2 echo "PROJECT ROOT: ${PROJECT_ROOT}"
# Activate virtual environment
source "$PROJECT_ROOT/.venv/bin/activate"

# Run the python script
# We set PYTHONPATH to include src so imports work if needed, 
# though running as a script usually handles local imports relative to the script.
# However, since we are running src/main.py, we should be careful about imports.
# Ideally, we run it as a module or directly.

export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"

uv run "$PROJECT_ROOT/src/main.py" "$@"
