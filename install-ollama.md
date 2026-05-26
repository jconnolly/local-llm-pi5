# Ollama install — Pi 5 (arm64, Debian 13 trixie)

Run on the Pi (`ssh <user>@<pi-ip>`).

## 1. Install

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Installs `/usr/local/bin/ollama` and systemd unit `ollama.service`. arm64 native binary.

Verify:
```bash
ollama --version
systemctl status ollama
```

## 2. Configure systemd unit for memory safety

```bash
sudo mkdir -p /etc/systemd/system/ollama.service.d
sudo tee /etc/systemd/system/ollama.service.d/override.conf <<'EOF'
[Service]
# Bind to LAN so Mac can reach it. Default is localhost only.
Environment="OLLAMA_HOST=0.0.0.0:11434"
# Only one model in RAM at a time
Environment="OLLAMA_MAX_LOADED_MODELS=1"
# No parallel inference (would balloon KV cache)
Environment="OLLAMA_NUM_PARALLEL=1"
# Unload after 5 min idle
Environment="OLLAMA_KEEP_ALIVE=5m"
# Cap context globally; per-request can be smaller
Environment="OLLAMA_CONTEXT_LENGTH=8192"
# Cap RAM to leave headroom (Pi has 16GB; leave 4GB for OS+sshd+claude-code)
MemoryHigh=11G
MemoryMax=12G
EOF

sudo systemctl daemon-reload
sudo systemctl restart ollama
```

## 3. Pull starter model (3B — smoke test)

```bash
ollama pull qwen2.5-coder:3b
ollama list
```

Should be ~2 GB download. Watch RAM during pull (`free -h` from another shell).

## 4. Smoke test

```bash
ollama run qwen2.5-coder:3b "write a python function that reverses a linked list"
```

Watch in second SSH:
```bash
vmstat 2 5    # si/so should stay 0 — non-zero means swap thrashing, kill model
```

If 3B is stable, pull 7B:

```bash
ollama pull qwen3-coder:7b
```

## 5. Test 7B with bounded context

```bash
ollama run qwen3-coder:7b --context-size 8192 "explain quicksort"
```

Watch RAM — expect peak ~7 GB.

## 6. Benchmark

```bash
ollama run --verbose qwen3-coder:7b "<some prompt>"
# Note: eval rate (tok/s), load duration, prompt eval rate
```

Or scripted:
```bash
curl -s http://localhost:11434/api/generate -d '{
  "model": "qwen3-coder:7b",
  "prompt": "write fizzbuzz in rust",
  "stream": false,
  "options": {"num_ctx": 8192}
}' | jq '{eval_count, eval_duration, prompt_eval_count, prompt_eval_duration}'
```

`tok/s = eval_count / (eval_duration / 1e9)`.

## 7. Wire Claude Code (on Mac)

```bash
export ANTHROPIC_BASE_URL=http://<pi-ip>:11434
export ANTHROPIC_AUTH_TOKEN=ollama
export ANTHROPIC_API_KEY=""
claude
```

Inside Claude Code, the model name will be ignored — Ollama serves whatever's loaded.

To force a specific model, set:
```bash
export ANTHROPIC_MODEL=qwen3-coder:7b
```

## Rollback

```bash
sudo systemctl stop ollama
sudo systemctl disable ollama
sudo rm /usr/local/bin/ollama
sudo rm -rf /usr/share/ollama
sudo userdel ollama
```
