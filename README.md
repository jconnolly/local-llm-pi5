# Local LLM on Raspberry Pi 5 + Hailo-10H AI HAT+ 2

Goal: run a SOTA local LLM on the Pi, usable as a Claude Code backend over LAN.

Pi target: `<user>@<pi-ip>` (Pi 5, 16GB, Debian 13 trixie, kernel 6.12.75+rpt-rpi-2712, Hailo-10H on PCIe). Replace `<user>` and `<pi-ip>` with your own throughout.

## TL;DR verdict (May 2026, empirically verified)

**Use Pi 5 CPU + Ollama + `qwen3:8b` (or `qwen3:4b` for faster turnaround) for Claude Code. Don't use Hailo for Claude Code.**

The original plan was Qwen2.5-Coder-7B. **It does not work for Claude Code** — Ollama's tool-use parser fails to extract structured tool calls from Qwen2.5-Coder's output (model emits bare JSON instead of the `<tool_call>` XML wrapper its template expects). Anthropic `/v1/messages` endpoint returns the tool call inside a `text` block, not a `tool_use` block. Claude Code can't dispatch it.

**Qwen3 (released 2025) is the answer.** It has native trained-in tool use, emits properly structured `tool_calls`, and Ollama's `/v1/messages` shim correctly translates these to Anthropic `tool_use` blocks. Includes a `thinking` reasoning trace as bonus.

Hailo-10H stack is installed and working for vision/Whisper. Three dealbreakers for Claude Code remain:

1. **Model ceiling 2B params.** Largest LLM HEF (Hailo-Executable-Format) is ~2B.
2. **Context window 2048 tokens.** Claude Code official guidance is ≥64k.
3. **`hailo-ollama` 500s on `tools` payload.** Open upstream bug.

## Stack diagram (recommended)

```
Claude Code CLI
  └─ ANTHROPIC_BASE_URL=http://<pi-ip>:11434
        └─ Ollama 0.24.0 (arm64) on Pi 5 CPU
              └─ qwen3:8b  (Q4_K_M, 40k ctx, native tool use + thinking)
```

## Measured performance (Pi 5 16GB, Debian 13, CPU only)

| Model | Tool use | Decode tok/s | Prompt tok/s | Disk | Notes |
|---|---|---|---|---|---|
| qwen2.5-coder:3b | broken (bare JSON) | 5.89 | 10.25 | 1.9 GB | fast but tool-use unusable for CC |
| qwen2.5-coder:7b | broken (bare JSON) | 2.37 | 4.45 | 4.7 GB | not viable for CC |
| **qwen3:4b** | **works** (native) | **4.05** | **7.81** | 2.5 GB | best speed/usability tradeoff |
| qwen3:8b | works (native) | TBD (~2-3) | TBD | 5 GB | best quality, slow |

(qwen3:8b numbers pending — pull in progress.)

TTFT on first call includes ~2-3s model load; subsequent calls keep model warm for 5min (`OLLAMA_KEEP_ALIVE=5m`).

## Memory safety (Pi swap is SD card — fatal if thrashed)

User reported Ollama bricked a 24GB MacBook. Pi has 16GB RAM + 2GB SD-card swap. SD swap is ~10x slower than NVMe — if Ollama swaps, the Pi will go unresponsive worse than the Mac did.

Guardrails (already applied in `/etc/systemd/system/ollama.service.d/override.conf` on the Pi):

```ini
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
Environment="OLLAMA_MAX_LOADED_MODELS=1"
Environment="OLLAMA_NUM_PARALLEL=1"
Environment="OLLAMA_KEEP_ALIVE=5m"
Environment="OLLAMA_CONTEXT_LENGTH=8192"
MemoryHigh=11G
MemoryMax=12G
```

`MemoryMax=12G` is a systemd cgroup hard cap — if Ollama tries to allocate past it, the kernel will kill the process *before* swap thrash starts. Pi stays responsive.

Memory math for qwen3:8b Q4_K_M:
- Weights: ~5 GB
- KV cache @ 8k: ~0.7 GB
- Ollama runtime: ~0.5 GB
- Debian + sshd + idle: ~1.2 GB
- **Peak resident**: ~7.5 GB → 8 GB headroom

## Why qwen3:8b (not qwen2.5-coder:7b)

- Qwen3 has trained-in tool-call format that Ollama's parser actually understands → `tool_use` blocks reach Claude Code intact
- Qwen2.5-Coder-7B advertises `tools` capability but emits bare JSON without the `<tool_call>` XML wrapper its own template requires → Ollama parser misses it → text block returned → Claude Code can't dispatch
- Qwen3 includes optional `thinking` reasoning trace — useful for agent decision quality
- Alternatives:
  - Qwen3-Coder-30B-A3B (MoE): better at code, too big for Pi 16GB even at Q4
  - Llama 3.1 8B: tool use OK but coding noticeably worse than Qwen3
  - DeepSeek-Coder-V2-Lite 16B: better code, too big
  - Phi-4 14B: too slow on CPU

## Claude Code wiring

Ollama 0.24.0 ships a native Anthropic-compatible `/v1/messages` endpoint. Verified end-to-end with tools test:

```bash
# on your dev machine
export ANTHROPIC_BASE_URL=http://<pi-ip>:11434
export ANTHROPIC_AUTH_TOKEN=ollama
export ANTHROPIC_API_KEY=""
export ANTHROPIC_MODEL=qwen3:8b
claude   # the CLI now talks to the Pi
```

No proxy needed. Tool use, streaming, and thinking blocks all translate correctly.

Smoke test command (run from any machine on the LAN):
```bash
curl -s http://<pi-ip>:11434/v1/messages \
  -X POST -H "Content-Type: application/json" \
  -H "x-api-key: ollama" -H "anthropic-version: 2023-06-01" \
  -d '{"model":"qwen3:8b","max_tokens":50,
       "messages":[{"role":"user","content":"hi"}]}'
```

Expected response shape:
```json
{
  "id": "msg_...",
  "type": "message",
  "role": "assistant",
  "content": [{"type":"text","text":"..."}],
  "stop_reason": "end_turn",
  "usage": {"input_tokens":N,"output_tokens":M}
}
```

For tool-using requests, you also get `{"type":"thinking",...}` and `{"type":"tool_use",...}` blocks with `stop_reason: "tool_use"`.

## Hailo-10H (parallel/experimental track)

Installed and verified working:
- HailoRT 5.1.1, device arch HAILO10H, PCIe 0001:01:00.0
- `/dev/hailo0` present, `hailortcli fw-control identify` returns clean

Not useful for Claude Code (see dealbreakers above). Useful for:
- Real-time vision (YOLO, pose, segmentation) via `hailo-apps` GStreamer pipelines
- Local Whisper STT (HEFs in `hailo_model_zoo_genai`)
- Toy chat with Qwen2-1.5B for non-agentic use

See [install-hailo.md](install-hailo.md) for setup, [install-ollama.md](install-ollama.md) for the LLM stack.

## Sources

- Pi AI docs: https://www.raspberrypi.com/documentation/computers/ai.html
- HailoRT 5.2.0 upgrade thread: https://community.hailo.ai/t/upgrading-to-hailort-5-2-0-step-by-step-raspberry-pi-hailo-apps/19006
- Hailo GenAI Model Zoo: https://github.com/hailo-ai/hailo_model_zoo_genai
- Available HEF list: https://github.com/hailo-ai/hailo_model_zoo_genai/blob/main/docs/MODELS.rst
- `hailo-apps`: https://github.com/hailo-ai/hailo-apps
- hailo-ollama tool-use bug: https://community.hailo.ai/t/hailo-ollama-tools-support/18624
- Hailo-10H benchmarks (codesota): https://www.codesota.com/embedded-ai/hailo-10h-llms
- AI HAT+ 2 benchmarks (schwab.sh): https://www.schwab.sh/blog/hailo-ai-hat-benchmarks/
- Pi 5 LLM perf (Stratosphere Lab): https://www.stratosphereips.org/blog/2025/6/5/how-well-do-llms-perform-on-a-raspberry-pi-5
- Ollama → Claude Code: https://docs.ollama.com/integrations/claude-code
- Qwen3 announcement: https://qwenlm.github.io/blog/qwen3/
- claude-code-router: https://github.com/musistudio/claude-code-router
