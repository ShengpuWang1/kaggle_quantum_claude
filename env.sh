# Source this file from the competition folder: source env.sh
export COMPETITION_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-${(%):-%x}}")" && pwd)"
export UV_CACHE_DIR="$COMPETITION_ROOT/.cache/uv"
export UV_PYTHON_INSTALL_DIR="$COMPETITION_ROOT/.python"
export TMPDIR="$COMPETITION_ROOT/.cache/tmp"
export XDG_CACHE_HOME="$COMPETITION_ROOT/.cache"
export MPLCONFIGDIR="$COMPETITION_ROOT/.cache/matplotlib"
export IPYTHONDIR="$COMPETITION_ROOT/.cache/ipython"
export JUPYTER_CONFIG_DIR="$COMPETITION_ROOT/.cache/jupyter/config"
export JUPYTER_DATA_DIR="$COMPETITION_ROOT/.cache/jupyter/data"
export JUPYTER_RUNTIME_DIR="$COMPETITION_ROOT/.cache/jupyter/runtime"
export KAGGLE_CONFIG_DIR="$COMPETITION_ROOT/.secrets/kaggle"
export KAGGLEHUB_CACHE="$COMPETITION_ROOT/.cache/kagglehub"
mkdir -p "$TMPDIR" "$MPLCONFIGDIR" "$IPYTHONDIR" "$JUPYTER_CONFIG_DIR" "$JUPYTER_DATA_DIR" "$JUPYTER_RUNTIME_DIR"
# Do not source .venv/bin/activate: a copied venv retains its old absolute path.
export VIRTUAL_ENV="$COMPETITION_ROOT/.venv"
export PATH="$VIRTUAL_ENV/bin:$PATH"
if [ -f "$COMPETITION_ROOT/.secrets/autoresearch.env" ]; then
    set -a
    source "$COMPETITION_ROOT/.secrets/autoresearch.env"
    set +a
fi
