# Maral MCP servers — closing cloud-Claude feature gaps for local LLM

Four MCP servers that backfill features lost when you switch Claude Code from
cloud Anthropic to a local Ollama backend (qwen3:14b on Maral).

Each server runs as a stdio MCP subprocess of Claude Code on **your Mac**, and
makes HTTP calls to **Ollama on Maral** (`maral.local:11434`). They do not
need to run on Maral itself.

| Server | What it solves | Backing model on Maral |
|---|---|---|
| `maral-vision` | Local LLM is text-only; can't read screenshots/PDFs | `qwen2.5vl:7b` |
| `maral-rag` | Local LLM has 32k context max; can't load big repos | `nomic-embed-text` (embeddings only) |
| `maral-review` | Local LLM review is shallow; misses subtle bugs | `qwen3:14b` + ruff/mypy/eslint/tsc |
| `maral-memory` | Local LLM writes sloppy auto-memory entries | `qwen3:14b` for rewrites |

## Quickstart

```bash
cd /Users/john.connolly/tmp-projects/local-llm/mcp-servers
./install.sh
```

This will:
1. Install `uv` (Python package manager) if missing
2. Create `.venv` with all required deps
3. SSH to Maral and pull `qwen2.5vl:7b` + `nomic-embed-text`
4. Print the four `claude mcp add` commands to register the servers

Run those four registration commands in a normal shell (not inside an active
Claude Code session). Then `claude mcp list` to verify.

## Tools each server exposes

### `maral-vision`
- `describe_image(path, prompt?)` — generic image description
- `ocr_screenshot(path)` — verbatim text/code extraction from screenshots
- `extract_pdf(path, page_range?, include_vision?)` — text from PDF, optionally augmented with per-page vision-model description

### `maral-rag`
- `index_dir(path, glob?)` — build/refresh a semantic index over a code directory
- `search(query, root, k?)` — top-k chunks from the index
- `read_with_context(file, query?)` — file body + related chunks from the index
- `list_indexes()` — show all built indexes

### `maral-review`
- `review_file(path, language?)` — run linter + type-checker + LLM pass on one file; returns structured findings
- `review_diff(diff_text?, cwd?)` — review a unified diff (falls back to `git diff HEAD`)

### `maral-memory`
- `audit_memory(memory_dir?)` — report sloppy/duplicate/oversized entries
- `cleanup_memory(dry_run=True)` — rewrite sloppy entries via the LLM with strict format
- `consolidate_index(memory_dir?)` — rebuild `MEMORY.md` from frontmatter

## Manual install (no script)

```bash
# uv + deps
curl -LsSf https://astral.sh/uv/install.sh | sh
cd /Users/john.connolly/tmp-projects/local-llm/mcp-servers
uv venv --python 3.12
uv pip install mcp httpx pypdf pillow sqlite-vec pdf2image watchdog

# Models on Maral
ssh youruser@maral.local '~/bin/ollama pull qwen2.5vl:7b'
ssh youruser@maral.local '~/bin/ollama pull nomic-embed-text'

# Register with Claude Code
VENV_PY=$PWD/.venv/bin/python
claude mcp add maral-vision -- "$VENV_PY" "$PWD/maral-vision/server.py"
claude mcp add maral-rag    -- "$VENV_PY" "$PWD/maral-rag/server.py"
claude mcp add maral-review -- "$VENV_PY" "$PWD/maral-review/server.py"
claude mcp add maral-memory -- "$VENV_PY" "$PWD/maral-memory/server.py"

claude mcp list
```

## Configuration via environment

| Var | Default | Used by |
|---|---|---|
| `OLLAMA_HOST` | `http://maral.local:11434` | all |
| `MARAL_VISION_MODEL` | `qwen2.5vl:7b` | vision |
| `MARAL_EMBED_MODEL` | `nomic-embed-text` | rag |
| `MARAL_REVIEW_MODEL` | `qwen3:14b` | review |
| `MARAL_MEMORY_MODEL` | `qwen3:14b` | memory |
| `MARAL_INDEX_DIR` | `~/.local/share/maral-rag` | rag (sqlite DB location) |
| `MARAL_MEMORY_DIR` | `~/.claude/memory` | memory (audit target) |

## Troubleshooting

**`vision call failed: ConnectError` →** Maral isn't reachable. Run `claude-status` from your shell. If Maral is up, check that Ollama is listening on `0.0.0.0:11434` (not just localhost).

**`embedding failed: model not found` →** Run `ssh youruser@maral.local '~/bin/ollama pull nomic-embed-text'`.

**`sqlite_vec` import error →** `uv pip install sqlite-vec` inside `.venv`.

**`pdf2image` errors →** Needs `poppler` installed (`brew install poppler` on Mac). Without it, PDF extraction works for text-only PDFs; `include_vision=True` will fail.

**Server crashes silently →** Claude Code suppresses MCP stderr. Run the server manually to see errors: `.venv/bin/python maral-vision/server.py` then type a JSON-RPC request like `{"jsonrpc":"2.0","id":1,"method":"tools/list"}` — should print tool list.

## What's still broken after install

These remain weak even with all 4 servers:

- **Frontier reasoning depth** — qwen3:14b is qwen3:14b; smarter prompts don't make it Opus.
- **Subagent prompt quality** — local model writes worse Task tool prompts. Could be partly mitigated by adding a `maral-prompt-template` MCP later.
- **Long-horizon agentic loops** — even with RAG, the 14B model derails on 50-step tasks.

These are model-capability ceilings. Closing them needs bigger hardware (Mac Mini M4 24GB → Qwen3.6-27B, see `presentation.md` Act 9).
