#!/usr/bin/env bash
# install.sh — set up the 4 maral-* MCP servers on this Mac and pull required models on Maral.
#
# Usage:
#   ./install.sh                 # install everything
#   ./install.sh skip-models     # skip the ollama pulls on Maral
#
# After running, register the servers with Claude Code by running the commands
# printed at the end (or copy from the bottom of this script).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MARAL_HOST="${MARAL_HOST:-youruser@maral.local}"
OLLAMA_HOST="${OLLAMA_HOST:-http://maral.local:11434}"

# Models to pull on Maral
VISION_MODEL="${VISION_MODEL:-qwen2.5vl:7b}"
EMBED_MODEL="${EMBED_MODEL:-nomic-embed-text}"

skip_models=0
if [[ "${1:-}" == "skip-models" ]]; then
    skip_models=1
fi

echo "==> install location: $SCRIPT_DIR"

# 1. uv (fast Python package manager)
if ! command -v uv >/dev/null 2>&1; then
    echo "==> installing uv (Python package manager)"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
else
    echo "==> uv already installed: $(uv --version)"
fi

# 2. Python venv with all dependencies
cd "$SCRIPT_DIR"
if [[ ! -d .venv ]]; then
    echo "==> creating .venv"
    uv venv --python 3.12
fi
echo "==> installing Python deps"
uv pip install --upgrade \
    "mcp>=1.2.0" \
    "httpx>=0.27.0" \
    "pypdf>=4.0.0" \
    "pillow>=10.0.0" \
    "sqlite-vec>=0.1.6" \
    "watchdog>=3.0.0" \
    "pdf2image>=1.17.0" || true

VENV_PY="$SCRIPT_DIR/.venv/bin/python"
echo "==> venv python: $VENV_PY"

# 3. Pull required models on Maral
if [[ $skip_models -eq 0 ]]; then
    echo "==> pulling $VISION_MODEL on Maral (~5GB, may take a few min)"
    ssh -o LogLevel=ERROR "$MARAL_HOST" "~/bin/ollama pull $VISION_MODEL" || {
        echo "WARN: vision model pull failed. Run manually on Maral: ollama pull $VISION_MODEL"
    }
    echo "==> pulling $EMBED_MODEL on Maral (~270MB)"
    ssh -o LogLevel=ERROR "$MARAL_HOST" "~/bin/ollama pull $EMBED_MODEL" || {
        echo "WARN: embed model pull failed. Run manually on Maral: ollama pull $EMBED_MODEL"
    }
else
    echo "==> SKIPPED model pulls (run later: ssh $MARAL_HOST '~/bin/ollama pull $VISION_MODEL $EMBED_MODEL')"
fi

# 4. Smoke test imports
echo "==> smoke testing each server's Python imports"
for srv in maral-vision maral-rag maral-review maral-memory; do
    if "$VENV_PY" -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR/$srv')
import server
print('OK: $srv')
"; then
        true
    else
        echo "FAIL: $srv import check"
    fi
done

# 5. Print Claude Code registration commands
cat <<EOF

============================================================
Install complete. Register the servers with Claude Code by
running these commands in a shell (NOT inside an active CC
session):

claude mcp add maral-vision \\
    --env OLLAMA_HOST="$OLLAMA_HOST" \\
    --env MARAL_VISION_MODEL="$VISION_MODEL" \\
    -- "$VENV_PY" "$SCRIPT_DIR/maral-vision/server.py"

claude mcp add maral-rag \\
    --env OLLAMA_HOST="$OLLAMA_HOST" \\
    --env MARAL_EMBED_MODEL="$EMBED_MODEL" \\
    -- "$VENV_PY" "$SCRIPT_DIR/maral-rag/server.py"

claude mcp add maral-review \\
    --env OLLAMA_HOST="$OLLAMA_HOST" \\
    -- "$VENV_PY" "$SCRIPT_DIR/maral-review/server.py"

claude mcp add maral-memory \\
    --env OLLAMA_HOST="$OLLAMA_HOST" \\
    -- "$VENV_PY" "$SCRIPT_DIR/maral-memory/server.py"

Verify with:  claude mcp list
============================================================
EOF
