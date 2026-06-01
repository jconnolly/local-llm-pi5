# mlx-server

Minimal Anthropic `/v1/messages` HTTP wrapper around `mlx_lm.generate`.

Built because `mlx-lm.server` (the stock MLX HTTP server) hangs on Maral when
loading qwen3:14b (see Act 14 / Act 15). Direct `mlx_lm.generate` works; this
file exposes that as a stable HTTP server.

## Scope

- **v0.1** (this commit): text-only, no tools, no streaming. Bench-grade.
- **v0.2** (next): Qwen3 `<tool_call>` parsing → Anthropic `tool_use` blocks.
- **v0.3**: SSE streaming.
- **v0.4**: speculative decoding via MLX `--draft-model`.

## Run (on Maral)

```bash
cd ~/mlx
./.venv/bin/python /path/to/server.py \
    --model mlx-community/Qwen3-14B-4bit \
    --host 0.0.0.0 --port 11435
```

Port `11435` so this can A/B alongside Ollama on `11434`.

## Bench

Once running:

```bash
curl -s http://maral.local:11435/v1/messages \
  -H 'content-type: application/json' \
  -d '{"model":"qwen3:14b","max_tokens":200,
       "messages":[{"role":"user","content":"hi"}]}'
```

## Known issues

- v0.1 returns HTTP 400 for any request with `tools` — deliberate; this keeps
  Claude Code from silently degrading on a tool-use prompt.
- Single-stream only. `ThreadingHTTPServer` is used, but the model itself is
  single-instance; concurrent requests serialize.
- No keep-alive eviction. Model stays loaded until process killed.
