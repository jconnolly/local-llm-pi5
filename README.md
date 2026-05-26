# Local LLM on Raspberry Pi 5 + Hailo-10H AI HAT+ 2

Goal: run a SOTA local LLM on the Pi, usable as a Claude Code backend over LAN.

Pi target: `<user>@<pi-ip>` (Pi 5, 16GB, Debian 13 trixie, kernel 6.12.75+rpt-rpi-2712, Hailo-10H on PCIe). Replace `<user>` and `<pi-ip>` with your own throughout.

## TL;DR verdict (May 2026)

**Use Pi 5 CPU + Ollama + Qwen3-Coder-7B for Claude Code. Don't use Hailo for Claude Code — yet.**

Three independent dealbreakers on Hailo-10H for agentic coding workloads:

1. **Model ceiling 2B params.** Largest HEF (Hailo-Executable-Format) compiled for Hailo-10H is ~2B. No Phi-4, no Qwen3-Coder, no Llama-3.3, no Gemma 7B+.
2. **Context window 2048 tokens.** Claude Code's official guidance is ≥64k. With 2k you cannot fit system prompt + tool defs + a single file read.
3. **`hailo-ollama` 500s on `tools` payload.** Open bug as of Feb 2026 — tool-call requests fail with `TreeToObjectMapper::mapString(): Node is NOT a STRING`. Community fork patches it; not upstream.

The only HEF that even advertises function calling is `Qwen2-1.5B-Instruct-Function-Calling-v1` — a 1.5B fine-tune of 2024-era Qwen2. Too dumb for a Claude Code tool-use loop.

Install Hailo anyway for vision / Whisper / chat-toy experiments — it's genuinely cool — just don't back Claude Code with it.

## Stack diagram (recommended)

```
Mac (Claude Code CLI)
  └─ ANTHROPIC_BASE_URL=http://<pi-ip>:11434
        └─ Ollama (arm64) on Pi 5 CPU
              └─ qwen3-coder:7b (Q4_K_M, 32k ctx, native tool use)
```

Realistic perf on Pi 5 16GB:
- 7B Q4_K_M: **3-5 tok/s decode**, ~5GB RAM resident
- 3B Q4_K_M: **6-8 tok/s decode**, ~2.5GB RAM resident
- Prompt prefill is the slow part on CPU. Long context = long TTFT.

## Memory safety plan (Pi swap is SD card — fatal if thrashed)

User reported Ollama bricked a 24GB MacBook. Pi has 16GB RAM + 2GB SD-card swap. SD swap is ~10x slower than NVMe — if Ollama starts swapping, the Pi will go unresponsive worse than the Mac did.

Guardrails:
- `OLLAMA_NUM_PARALLEL=1` — no concurrent inference
- `OLLAMA_MAX_LOADED_MODELS=1` — don't hold two models in RAM
- `OLLAMA_KEEP_ALIVE=5m` — unload on idle
- Cap context to 8192 initially via `OLLAMA_CONTEXT_LENGTH=8192` (KV cache scales linearly with ctx; full 32k on 7B Q4 ≈ +2GB KV)
- Start with 3B model to validate, only pull 7B after 3B is stable
- Watch `vmstat 2` during first run — if `si/so` columns go non-zero, kill the model immediately

Memory math for Qwen3-Coder-7B Q4_K_M:
- Model weights: ~4.5 GB
- KV cache @ 8k ctx: ~0.6 GB
- KV cache @ 32k ctx: ~2.4 GB
- Ollama runtime: ~0.5 GB
- Debian + sshd + idle: ~1.2 GB
- **Peak resident @ 8k**: ~7 GB → safe with 9 GB headroom
- **Peak resident @ 32k**: ~9 GB → safe but tighter

## Why Qwen3-Coder-7B specifically

- Only widely-deployed sub-10B model with **trained-in agentic tool use** (XML + JSON tool call formats both work)
- Trained on coding + tool-use traces; not a generalist with bolt-on function calling
- Ollama 2026 ships native Anthropic-API endpoint that maps tool blocks correctly for Qwen3-Coder template
- Alternatives considered and rejected:
  - Llama 3.1 8B: tool use OK but coding noticeably worse
  - DeepSeek-Coder-V2-Lite 16B: better code, too big for Pi RAM at usable ctx
  - Phi-4 14B: too big for usable speed on CPU
  - Qwen2.5-Coder-7B: predecessor, tool use less reliable

## Claude Code wiring

Ollama 2026 has a built-in Anthropic-compatible endpoint:

```bash
# on your dev machine
export ANTHROPIC_BASE_URL=http://<pi-ip>:11434
export ANTHROPIC_AUTH_TOKEN=ollama
export ANTHROPIC_API_KEY=""
claude   # the CLI now talks to the Pi
```

No proxy needed. If we later want task routing (cheap model for "background", cloud fallback for "thinking"), drop in `claude-code-router` (`npm i -g @musistudio/claude-code-router`).

## Hailo-10H (parallel/experimental track)

Even though Hailo isn't right for Claude Code, install the stack — it's useful for:
- Real-time object detection / pose / face on the camera
- Local Whisper STT (`hailo_model_zoo_genai` has Whisper HEFs)
- Toy chat with Qwen2-1.5B for non-agentic use

Install path (May 2026):
```bash
# Add Pi-hosted Hailo apt repo
sudo tee /etc/apt/sources.list.d/hailo.sources <<'EOF'
Types: deb
URIs: https://hailo:chahy5Zo@extranet.raspberrypi.org/hailo
Suites: trixie
Components: main
Signed-By: /usr/share/keyrings/raspberrypi-archive-keyring.pgp
EOF

sudo apt update && sudo apt full-upgrade -y && sudo reboot

# Driver + runtime + Python bindings (meta-pkg for Hailo-10H, NOT hailo-all which is Hailo-8)
sudo apt install dkms hailo-h10-all
sudo reboot

# Optional: upgrade to HailoRT 5.2.0 from Hailo Developer Zone for newer LLM HEFs
# (apt only ships 5.1.1 as of writing)

hailortcli fw-control identify   # verify
```

PCIe Gen3 override (`dtparam=pciex1_gen=3` in `/boot/firmware/config.txt`) is **not** required for AI HAT+ 2 — the device-tree overlay sets it automatically.

Examples repo: **`hailo-ai/hailo-apps`** (the older `hailo-rpi5-examples` is deprecated, Hailo-8 only).

## Sources

- Pi AI docs: https://www.raspberrypi.com/documentation/computers/ai.html
- HailoRT 5.2.0 upgrade thread: https://community.hailo.ai/t/upgrading-to-hailort-5-2-0-step-by-step-raspberry-pi-hailo-apps/19006
- Hailo GenAI Model Zoo: https://github.com/hailo-ai/hailo_model_zoo_genai
- Available HEF list: https://github.com/hailo-ai/hailo_model_zoo_genai/blob/main/docs/MODELS.rst
- Hailo Model Explorer (Hailo-10H): https://hailo.ai/products/hailo-software/model-explorer/generative-ai/devices/hailo-10h/
- `hailo-apps`: https://github.com/hailo-ai/hailo-apps
- hailo-ollama tool-use bug: https://community.hailo.ai/t/hailo-ollama-tools-support/18624
- Hailo-10H benchmarks (codesota): https://www.codesota.com/embedded-ai/hailo-10h-llms
- AI HAT+ 2 benchmarks (schwab.sh): https://www.schwab.sh/blog/hailo-ai-hat-benchmarks/
- Pi 5 LLM perf (Stratosphere Lab): https://www.stratosphereips.org/blog/2025/6/5/how-well-do-llms-perform-on-a-raspberry-pi-5
- Ollama → Claude Code: https://docs.ollama.com/integrations/claude-code
- claude-code-router: https://github.com/musistudio/claude-code-router
- Pudding tutorial: https://pudding-entertainment.medium.com/running-local-llms-on-raspberry-pi-5-and-hailo-ai-hat-2-b999fa240319
- ronstechhub Pi5 AI HAT+ 2 LLM: https://ronstechhub.com/run-local-llms-raspberry-pi-5-ai-hat-plus-2/
