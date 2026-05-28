# Local LLMs at home: hiccups, dead ends, and what actually worked

*A real-time investigation log from May 26-27, 2026. Hardware: Raspberry Pi 5 16GB + AI HAT+ 2 (Hailo-10H), a spare MacBook Air M2 16GB, and a Mac running Claude Code on the LAN.*

Companion code + notes: https://github.com/jconnolly/local-llm-pi5

---

## TL;DR for the audience

> **"Just use the Mac you already have."**
>
> I spent a day trying to make a Raspberry Pi 5 with a 40-TOPS NPU into a usable local-LLM coding assistant. I built three Pi-side stacks, hit four dead ends, almost bought $80-1000 of hardware, then found a MacBook Air sitting downstairs that beat the Pi by 5x for $0. The Pi is still a great vision/Whisper experimentation platform. It is **not** an LLM appliance.
>
> The presentation is about the trip, not just the destination.

---

## Act 1 — The Pi 5 dream

### Starting state
- Raspberry Pi 5 16GB, Debian 13 trixie, kernel 6.12.75
- **Raspberry Pi AI HAT+ 2** with **Hailo-10H** NPU (40 TOPS, M.2 form factor, soldered)
- The pitch: "compiled HEFs run quantized LLMs at NPU speed, no GPU bill, sips power"

### Hiccup #1: Find the Pi
I didn't know its IP. Network was a Google Wifi mesh, ~30 devices.

What worked: `dns-sd -B _ssh._tcp local.` and `dns-sd -B _workstation._tcp local.` — but the Pi didn't advertise. So a `ping` sweep + ARP scan, then port-22 banner check on every reachable host, picked it up as the only Debian SSH responder.

What didn't:
- Standard Pi default hostname `raspberrypi.local` — user had renamed it `software2159`
- Pi OUI search (`b8:27:eb`, `dc:a6:32`, `d8:3a:dd`) — the on-board NIC's MAC didn't match common OUIs

### Hiccup #2: SSH password
User gave two family birthdates and said "the password is some combo." Brute-forced via `sshpass` against a 50-candidate list. **fail2ban kicked in after attempt #7** — all subsequent attempts got connection-reset before sshd even ran auth, so they looked like misses but were inconclusive. Backed off, retried single-stream. **Password was a 4-digit year. Plain.** Lesson: rate-limit yourself manually, *before* fail2ban does it for you, and treat connection-reset ≠ permission-denied.

### Lesson 1: SSH bruteforce on a fail2ban host is broken by design — connection resets look like auth failures and corrupt your "ruled out" list.

---

## Act 2 — Hailo-10H ambition

Plan was: install Hailo's HailoRT runtime, point Claude Code at a compiled LLM HEF on the NPU, claim victory.

### Research before installing (the right call)

Spent 15 minutes researching, before touching the system. Three findings killed the plan:

1. **Model ceiling is 2B parameters.** Hailo Model Zoo GenAI v5.3.0 [MODELS.rst](https://github.com/hailo-ai/hailo_model_zoo_genai/blob/main/docs/MODELS.rst) lists exactly these LLM HEFs for Hailo-10H:

   | Model | Params | Quant | Ctx | Decode tok/s | Tool use |
   |---|---|---|---|---|---|
   | Llama3.2-1B-Instruct | 1B | A8W4 | 2048 | 9.89 | No |
   | Qwen2.5-Coder-1.5B-Instruct | 1.5B | A8W4 | 2048 | 8.13 | No |
   | **Qwen2-1.5B-Function-Calling-v1** | **1.5B** | **A8W4** | **2048** | **6.69** | **Yes** |
   | Qwen3:1.7B | 1.7B | A8W4 | 2048 | 4.78 | No |
   | Qwen2-VL-2B / Qwen3-VL-2B | 2B | A8W4 | 2048 | ~5-7 | No |

   The *only* HEF with tool calling is a 1.5B fine-tune of Qwen2 (a 2024-era model). Too dumb for a real Claude Code agent loop.

2. **Context window is 2048 tokens.** Claude Code's official guidance is ≥64k. With 2k you cannot fit the CC system prompt + tool defs + a single small file read. Period.

3. **`hailo-ollama` 500s on `tools` payloads.** Open [Hailo Community thread Feb 2026](https://community.hailo.ai/t/hailo-ollama-tools-support/18624) — the shim that bridges Hailo's runtime to Ollama's API throws `TreeToObjectMapper::mapString(): Node is NOT a STRING` whenever the request contains a `tools` field. A community fork patches it; it is not upstream and won't survive HailoRT 5.3 upgrades.

### What I installed anyway

The Hailo stack is *fine* — just not for Claude Code. Installed it for vision / Whisper experimentation:

```bash
sudo tee /etc/apt/sources.list.d/hailo.sources <<'EOF'
Types: deb
URIs: https://hailo:chahy5Zo@extranet.raspberrypi.org/hailo
Suites: trixie
Components: main
Signed-By: /usr/share/keyrings/raspberrypi-archive-keyring.pgp
EOF
sudo apt update && sudo apt install -y dkms hailo-h10-all
git clone https://github.com/hailo-ai/hailo-apps.git ~/hailo-apps
sudo reboot
```

After reboot: `hailortcli fw-control identify` → firmware 5.1.1, device arch HAILO10H, PCIe 0001:01:00.0, `/dev/hailo0` present. Clean.

### Lesson 2: Don't pick the impressive hardware. Pick the matching software stack. Hailo-10H is a great NPU and a bad agent backend in May 2026.

---

## Act 3 — Ollama on Pi 5 CPU

Plan B: ignore the HAT, run llama.cpp via Ollama on the Pi 5's Cortex-A76 quad-core. Memory-bandwidth-bound but actually works.

### Memory safety guardrails (CRITICAL)

User had previously *bricked a 24GB MacBook* with Ollama. Pi 5 has 16GB RAM + a 2GB swap on the SD card. **SD swap is ~10x slower than NVMe — if Ollama swaps, the Pi will hang worse than the Mac did.**

Solution: systemd cgroup hard cap, so the kernel kills the model *before* swap thrash:

```ini
# /etc/systemd/system/ollama.service.d/override.conf
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
Environment="OLLAMA_MAX_LOADED_MODELS=1"
Environment="OLLAMA_NUM_PARALLEL=1"
Environment="OLLAMA_KEEP_ALIVE=5m"
Environment="OLLAMA_CONTEXT_LENGTH=8192"
MemoryHigh=11G
MemoryMax=12G
```

### Model selection journey (this is where the real lessons live)

**Attempt 1: `qwen3-coder:7b`** — doesn't exist on Ollama. Qwen3-Coder's smallest variant is the 30B-A3B MoE (too big for Pi). I had hallucinated the model name based on training data. **Lesson 3: always check `ollama list` for the actual model registry; don't trust your assumption.**

**Attempt 2: `qwen2.5-coder:7b`** — pulled, ran, decode 2.37 tok/s. Hit tool use with a `get_weather` function. Result:

```json
"content": [{"type":"text","text":"{\"name\": \"get_weather\", \"arguments\": {\"city\": \"Paris\"}}"}]
```

**Tool use is broken.** The model emitted bare JSON instead of the `<tool_call>` XML wrapper its own template expects. Ollama's parser doesn't find the tag, so it dumps the raw output into a `text` block. Claude Code can't dispatch a tool from a text block. **`tools` capability advertised ≠ tool use actually works.**

**Attempt 3: `qwen3:4b`** — pulled, ran, decode 4.05 tok/s. Same test:

```json
"content": [
  {"type":"thinking","thinking":"..."},
  {"type":"tool_use","id":"call_cdcrb8sm","name":"get_weather","input":{"city":"Paris"}}
],
"stop_reason": "tool_use"
```

Proper `tool_use` block. Proper `stop_reason`. Bonus: `thinking` reasoning trace included. **Native tool use works on Qwen3, not on Qwen2.5-Coder.**

**Attempt 4: `qwen3:8b`** — better quality, decode 1.92 tok/s warm. Tool use works. Realistic agent loop at 2 tok/s and ~300 tokens per assistant turn = **~25 minutes per 10-step loop**. Brutal but functional.

### Lesson 3: A model's `tools` capability advertisement is a *claim*, not a contract. Test end-to-end with a real request.

### Lesson 4: Qwen3 has trained-in tool-call formatting that Ollama's parser recognizes. Qwen2.5-Coder advertises tools but its outputs don't match its own template. Stick with model families designed for agentic use.

### Hiccup #3: I/O stall

Mid-investigation I tried to pull **`qwen2.5-coder:3b`** and **`qwen3:8b` concurrently** to save wall-time. Pi pinged but every TCP service (SSH, Ollama, HTTP) went dead. ~5 minutes of nothing.

Root cause: parallel 8GB SD-card writes saturated the I/O queue. Kernel stayed alive (ICMP responded), userspace blocked indefinitely on disk. **The SD card is the actual reliability ceiling, not RAM, not CPU.**

User opened a terminal locally on the Pi GUI, ran `sudo systemctl restart ollama` — that recovered. Lesson: **never run two `ollama pull` against an SD-rooted Pi at once.**

### Lesson 5: On an SD-card-rooted Pi 5, sustained parallel writes can lock all userspace services for minutes while the I/O queue drains. Kernel ICMP keeps responding so monitoring tools say "network is up."

---

## Act 4 — Buying my way out

Researched USB3 NVMe enclosures + drives, found the answer: NAND prices spiked in 2026 due to HBM/AI demand crowding out consumer flash. 1TB NVMe drives at retail: $200+. **Three-to-four-times normal.** Same SSD that was $50-70 in 2024 is $204+ today.

Pivoted toward **cheaper non-NVMe alternatives:**
- USB3 NVMe enclosure ($25) + 1TB NVMe ($200+) = $225+
- USB-SATA enclosure ($10) + Crucial MX500 1TB SATA ($70) = $80
- Pre-built [Crucial X9 Pro 1TB portable USB SSD](https://www.tomshardware.com/reviews/best-external-hard-drive-ssd,5987.html) = $80, no assembly

Critical realization: **Pi 5 USB3 is gen1 (5 Gbps) = ~500 MB/s real ceiling.** Any Gen3 NVMe (3000+ MB/s) saturates this. Buying Gen4 or Gen5 specs = paying for speed Pi physically cannot use. **Specifying past the bottleneck wastes money.**

### Lesson 6: Find the bottleneck *first*. Pi 5 USB3 caps at 500 MB/s; therefore any modern SSD is fine. Optimizing past the bottleneck is just markup.

---

## Act 5 — SWE-bench reality check

Realized the model selection question was actually a *budget* question. Pulled the live SWE-bench Verified leaderboard (May 27, 2026):

### Top 10 SWE-bench Verified (May 27 2026)

| Rank | Model | Score | Provider | Open? |
|---|---|---|---|---|
| 1 | Claude Mythos Preview | 93.9% | Anthropic | closed |
| 2 | **Claude Opus 4.7 Adaptive** | **87.6%** | Anthropic | closed |
| 3 | GPT-5.3 Codex | 85.0% | OpenAI | closed |
| 4 | Claude Opus 4.5 | 80.9% | Anthropic | closed |
| 6 | **DeepSeek V4 Pro Max** | **80.6%** | DeepSeek | **OPEN** |
| 8 | **Kimi K2.6** | **80.2%** | Moonshot | **OPEN** |
| 9 | GPT-5.2 | 80.0% | OpenAI | closed |
| 10 | Claude Sonnet 4.6 | 79.6% | Anthropic | closed |

### Top OPEN models worth running locally

| Model | Score | Params | Q4 RAM | Fits $1K hardware? |
|---|---|---|---|---|
| DeepSeek V4 Pro Max | 80.6% | ~671B MoE | ~340 GB | **No** |
| Kimi K2.6 | 80.2% | ~1T MoE | ~500+ GB | **No** |
| GLM-5 | 77.8% | ~335B | ~170 GB | **No** |
| Mistral Medium 3.5 | 77.6% | 128B | ~64 GB | Stretch ($1.5K Strix Halo 64GB) |
| **Qwen3.6-27B** | **77.2%** | 27B dense | **~18 GB** | **Yes — Mac Mini M4 24GB $999** |
| Qwen3-Coder-30B-A3B (MoE) | ~51.6% | 30B MoE | ~18 GB | Yes — same hw |
| Qwen3:14B (dense general) | ~40-50% est | 14B | ~9 GB | **Yes — MacBook Air M2 16GB ($0)** |
| Qwen3:8B (dense general) | ~30-40% est | 8B | ~5 GB | Yes — even Pi 5 |

### The verdict that came out of the leaderboard

**Top OPEN-source local model that fits a $1K appliance: Qwen3.6-27B at 77.2%.** Requires 24GB unified RAM. Real options:
- Mac Mini M4 24GB BTO = $999 (no same-day, 7-10 days BTO)
- Used Mac Studio M1 Max 32GB = $700-900 on eBay
- Used Mac Mini M2 Pro 32GB = $700-900 on eBay

Stretch to $1.5K: GMKtec EVO-X2 64GB (Strix Halo) at $1,499 → unlocks Mistral Medium 3.5 128B at 77.6%.

**The whole top tier (DeepSeek V4 Pro, GLM-5, Kimi K2.6) needs $5K+ hardware** to run at home. Not realistic for a one-day appliance build.

---

## Act 6 — "Wait, I have a MacBook downstairs"

After ~6 hours of Pi optimization and an aborted SSD shopping spree, the user mentioned a spare MacBook on the network.

### Finding it
Same `dns-sd` toolkit I used for the Pi, but Apple devices advertise **`_rfb._tcp` (Screen Sharing)** as a strong macOS signal:

```bash
dns-sd -B _rfb._tcp local.
# → "Maral" instance discovered
dns-sd -G v4 maral.local
# → maral.local
```

(MacBook was on a different subnet — 192.168.x.x vs my Mac's 192.168.x.x — Google Wifi mesh bridged them transparently. mDNS still propagated.)

### Probing
- ICMP blocked (macOS firewall default)
- TCP 22 (SSH) and 5900 (Screen Sharing) open
- SSH key auth worked under username `jconnolly` (I tried `john`, `john.connolly`, `johnconnolly`, `maral`, `jconnolly`; only the last succeeded)
- `system_profiler` → **MacBook Air 15", Apple M2, 16 GB RAM, 550 GB free, macOS 26.5**

### Installing Ollama headless on macOS

No Homebrew, no `.pkg` installer, no UI. The trick is the binary inside the official `.app` bundle:

```bash
curl -L -o /tmp/Ollama-darwin.zip https://ollama.com/download/Ollama-darwin.zip
unzip /tmp/Ollama-darwin.zip -d /tmp/ollama-extract
cp /tmp/ollama-extract/Ollama.app/Contents/Resources/ollama ~/bin/ollama
chmod +x ~/bin/ollama
```

Then a launchd user-agent plist to run `ollama serve` headless, bound to the LAN:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0"><dict>
  <key>Label</key><string>com.ollama.serve</string>
  <key>ProgramArguments</key>
  <array><string>/Users/jconnolly/bin/ollama</string><string>serve</string></array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>OLLAMA_HOST</key><string>0.0.0.0:11434</string>
    <key>OLLAMA_KEEP_ALIVE</key><string>10m</string>
    <key>OLLAMA_MAX_LOADED_MODELS</key><string>1</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
</dict></plist>
```

```bash
launchctl load ~/Library/LaunchAgents/com.ollama.serve.plist
```

Cross-subnet test from my Mac:
```bash
$ curl -s http://maral.local:11434/api/version
{"version":"0.24.0"}
```

### Keep-awake
Caffeinate as a launchd user agent (no sudo):

```xml
<key>ProgramArguments</key>
<array><string>/usr/bin/caffeinate</string><string>-dimsu</string></array>
```

(Full lid-closed sleep still requires `sudo pmset -a disablesleep 1`.)

---

## Act 7 — The actual numbers

### Benchmarks (May 27 2026)

| Device | Model | Tool use | Decode tok/s | Prefill tok/s | Warm load ms | Est SWE-bench Verified |
|---|---|---|---|---|---|---|
| Pi 5 16GB CPU | qwen2.5-coder:3b | **broken** (bare JSON) | 5.89 | 10.25 | ~3000 | ~25% |
| Pi 5 16GB CPU | qwen2.5-coder:7b | **broken** (bare JSON) | 2.37 | 4.45 | ~3000 | ~30% |
| Pi 5 16GB CPU | qwen3:4b | works | 4.05 | 7.81 | ~2000 | ~25-30% |
| Pi 5 16GB CPU | qwen3:8b | works | **1.92** | 4.34 | ~3000 | ~30-40% |
| Pi 5 + Hailo-10H | Qwen2-1.5B-FC | works but broken shim | ~6.69 | n/a | n/a | ~10-15% |
| **MacBook Air M2 16GB** | **qwen3:14b** | **works** | **10.13** | **64.19** | **118** | **~40-50%** |
| Mac Mini M4 24GB ($999, hypothetical) | Qwen3.6-27B | works | ~20-25 | ~120 | ~150 | **77.2%** |
| Claude Sonnet 4.6 (DSG default, cloud) | n/a | works | ~100 streaming | n/a | n/a | 79.6% |
| **Claude Opus 4.7 (current session, cloud)** | n/a | works | ~50 streaming | n/a | n/a | **87.6%** |

### Speedup vs Pi 5

| Comparison | Speedup |
|---|---|
| Pi 5 qwen3:8b → MacBook Air M2 qwen3:14b | **5.3x decode at a 2x bigger model** |
| Pi 5 qwen3:8b → MacBook Air M2 qwen3:8b (est) | ~10x decode at same model |
| Pi 5 qwen3:8b → Mac Mini M4 24GB Qwen3.6-27B | ~10-12x decode at a 3x bigger model |

### Quality drop vs cloud

| Path | SWE-bench Verified | Drop vs Opus 4.7 |
|---|---|---|
| Claude Opus 4.7 (current) | 87.6% | — |
| Cloud Sonnet 4.6 (DSG default) | 79.6% | -8 pts |
| Hypothetical Mac Mini M4 24GB + Qwen3.6-27B | 77.2% | -10.4 pts |
| **MacBook Air M2 + qwen3:14b** | **~40-50%** | **-37 to -47 pts** |
| Pi 5 qwen3:8b | ~30-40% | -47 to -57 pts |

**Going local on existing hardware buys back ~42 percentage points of accuracy. Going local on $999 of new hardware buys back ~10 pts.** Privacy and quota savings are real but coding accuracy halves.

---

## Act 8 — Wiring it into daily use without losing the cloud escape hatch

The whole point of this exercise is making the local LLM the *default* without losing access to cloud Claude when local falls short. The user requirement:

> "I want claude cloud only if I specifically invoke it. I don't want it for 'complex task' — I want my ollama to do memories and manage multiple sessions etc."

Tried two designs:

**Design A — auto-fallback on Maral down (rejected).**

```sh
claude() {
  if maral_up; then use_local
  else use_cloud   # silently
  fi
}
```

Rejected because "Maral momentarily unreachable" silently spends cloud quota. The user wants intent to be explicit.

**Design B — strict local, opt-in cloud (shipped).**

```sh
# ~/.zshrc — bounded marker block
LOCAL_LLM_HOST="maral.local:11434"
LOCAL_LLM_MODEL="qwen3:14b"
LOCAL_LLM_SMALL="qwen3:8b"

claude() {
  if [[ -n "$ANTHROPIC_FORCE_CLOUD" ]]; then
    env -u ANTHROPIC_BASE_URL -u ANTHROPIC_AUTH_TOKEN -u ANTHROPIC_API_KEY \
        -u ANTHROPIC_MODEL -u ANTHROPIC_SMALL_FAST_MODEL command claude "$@"
    return $?
  fi
  if ! curl -sf -m 1 "http://${LOCAL_LLM_HOST}/api/version" >/dev/null 2>&1; then
    echo "[claude] ERROR: Maral unreachable. Fix Maral, or use 'claude-cloud'." >&2
    return 1
  fi
  ANTHROPIC_BASE_URL="http://${LOCAL_LLM_HOST}" \
  ANTHROPIC_AUTH_TOKEN="ollama" \
  ANTHROPIC_API_KEY="" \
  ANTHROPIC_MODEL="${LOCAL_LLM_MODEL}" \
  ANTHROPIC_SMALL_FAST_MODEL="${LOCAL_LLM_SMALL}" \
    command claude "$@"
}
claude-cloud() { ANTHROPIC_FORCE_CLOUD=1 claude "$@"; }
claude-status() { ... }
```

`claude` → Maral or error. `claude-cloud` → explicit cloud. No silent cloud spend.

### Memories, sessions, skills — backend-agnostic

`~/.claude/` is filesystem storage owned by the Claude Code CLI, not the model:

| Directory | What | Affected by switching backend? |
|---|---|---|
| `~/.claude/memory/` | Auto-memory files + index | No — model reads/writes via standard tool calls |
| `~/.claude/projects/<hash>/messages/*.jsonl` | Per-project session transcripts | No — pure conversation log |
| `~/.claude/.credentials.json` | OAuth tokens | Only used when env vars NOT set (cloud path) |
| `~/.claude/sessions/` | Active session state | No |
| `~/.claude/plugins/` | Installed plugins/skills | No |
| `~/.claude/settings.json` | CLI settings | No |

So switching `claude` to Maral does **not** lose memories, session history, multi-project work, or skills. The model just answers the same conversation with different reasoning quality. *Quality of new auto-memory writes will be sloppier with qwen3:14b vs Opus 4.7* — that's a downstream cost worth accepting.

### Hot-swapping existing sessions

A running `claude` process locks its backend at launch — env vars don't hot-update. To migrate an in-flight session to Maral:

```
/exit                 # leave current session (transcript saved to .jsonl)
exec zsh              # reload shell with new router
claude --resume       # pick session from list — conversation continues on Maral
```

The transcript is replayed into qwen3:14b's context, so the resumed session retains every prior turn. Reasoning from this turn forward is qwen3:14b's, not Opus's.

### Loading the router into a current terminal

```
source ~/.zshrc       # in place
# or
exec zsh              # replace shell process (cleaner)
```

Verify:

```
claude-status
# Maral:  UP    (maral.local:11434, model=qwen3:14b)
# Routing: `claude` -> Maral ONLY | `claude-cloud` -> explicit cloud opt-in
```

### Lesson 11: Backend env vars are launch-time, not runtime. To migrate a session, exit + `--resume`. The on-disk transcript is the actual state; the model is interchangeable.

### Lesson 12: Make cloud opt-in, not auto-fallback. Silent fallback hides intent and burns quota. An explicit `claude-cloud` command makes the choice visible every time.

---

## Act 9 — How much SWE-bench am I actually trading away?

The router decision needs a calibration point. **What's the actual gap between my current LLM and the Maral local?**

### Current setup (this Mac, before Act 8)

- Claude Code points at Anthropic API via OAuth (`~/.claude/.credentials.json`, Claude Max subscription)
- This session is running on **Claude Opus 4.7** (1M context variant), released April 16 2026
- Daily-driver model when no override: whatever CC picks; typically Sonnet 4.6 for routine tasks, Opus 4.7 for harder ones, per Claude Max routing

### Target setup (Maral as primary)

- qwen3:14b Q4_K_M dense, Apache 2.0 (Alibaba Qwen)
- ~9 GB resident, 10 tok/s decode on M2 Air 16GB
- Estimated **40-50% SWE-bench Verified** (general-purpose model, not coder-specialized, Q4 quantization shaves 5-10 pts off FP16 baseline)

### The headline gap

| Path | SWE-bench Verified | Δ vs Opus 4.7 |
|---|---|---|
| Claude Opus 4.7 (current) | **87.6%** | baseline |
| Maral qwen3:14b (target) | **~45%** est | **-43 pts** |

**Switching local cuts measured coding-issue resolution by roughly half.** That's the price for privacy + zero quota + always-on.

### Where my current backend sits in Claude history

Anthropic shipped Claude Code-class models on a steep curve over 14 months. SWE-bench Verified score, in chronological order:

| Released | Model | SWE-bench Verified | Notes |
|---|---|---|---|
| Feb 25 2025 | Claude 3.7 Sonnet | 70.3% (scaffold) / 62.3% (no scaffold) | First with extended thinking |
| May 22 2025 | Claude Sonnet 4 | 72.7% | First "Claude 4" generation |
| May 2025 | Claude Opus 4 | ~72.5% | Released alongside Sonnet 4 |
| Aug 2025 | Claude Opus 4.1 | 74.5% | Incremental |
| Sep-Oct 2025 | Claude Sonnet 4.5 | 77.2% | "Highest-scoring Sonnet at release" |
| Dec 2025 | Claude Opus 4.5 | 80.9% | First crossed 80% mark |
| Dec 2025 | Claude Sonnet 4.6 | 79.6% | Sonnet catches Opus 4.5-class perf |
| Feb 5 2026 | Claude Opus 4.6 | 80.8% | Tiny regression; image res improvements |
| Apr 16 2026 | **Claude Opus 4.7** | **87.6%** | **Big jump; current default** |
| May 22 2026 | Claude Mythos Preview | 93.9% | Preview-only as of write date |

The cloud frontier moved from **70% → 88% in 14 months** — gained 18 pts. The leading open-weights model in the same window:

| Model | Released | SWE-bench Verified | Local-deployable? |
|---|---|---|---|
| Llama 3.3 70B | Dec 2024 | ~36% | needs ~40GB |
| DeepSeek-Coder-V2-Lite 16B | mid-2024 | ~37% | needs ~10GB |
| Qwen2.5-Coder 32B | Nov 2024 | ~47% | needs ~20GB |
| Qwen3:14B (general) | mid-2025 | **~45% est (Q4)** | **~9GB — fits Maral** |
| Qwen3-Coder-30B-A3B | Aug 2025 | 51.6% | needs ~18GB |
| GLM-4.5 | Sep 2025 | 64.2% | needs ~64GB+ |
| Qwen3.6-27B | Apr 22 2026 | **77.2%** | needs ~18GB — fits Mac Mini M4 24GB |
| GLM-5 | early 2026 | 77.8% | needs ~170GB |
| DeepSeek V4 Pro Max | May 2026 | 80.6% | needs ~340GB |

Putting them on the same axis (latest data, May 27 2026):

```
SWE-bench Verified score
100% |                                                  ██ Mythos
 95% |
 90% |
 85% |                                              ██ Opus 4.7  <-- I am here
 80% |                                  ██ Opus 4.5 ██ Sonnet 4.6  ██ Opus 4.6
 75% |                            ██ Sonnet 4.5                              ██ Qwen3.6-27B (local, $999 hw)
 70% |          ██ 3.7 Sonnet  ██ Sonnet 4   ██ Opus 4.1
 65% |                                          ██ GLM-4.5 (local, $1.5K hw)
 60% |
 55% |                                          ██ Qwen3-Coder-30B-A3B (local, $999 hw)
 50% |                                                  ██ Qwen2.5-Coder-32B (local, $999 hw)
 45% |                                          ██ qwen3:14b dense Q4   <-- Maral
 40% |          ██ Llama 3.3 70B   ██ DeepSeek-Coder-V2-Lite
       Feb'25   May'25   Aug'25   Oct'25   Dec'25   Feb'26   Apr'26   May'26
```

### Translation

Switching from Opus 4.7 to qwen3:14b on Maral is, roughly, **rolling back ~14 months of Anthropic's coding-agent progress** — landing approximately where Claude 3.5 Sonnet sat in mid-2024, or where open-weight 32B models sit at the time of writing.

That's not nothing — Claude 3.5 Sonnet shipped real production code for many people in 2024. But it is meaningfully *less capable* than current Opus, especially on multi-file refactors, subagent prompting, and subtle code review.

### What would close the gap

| Hardware (~price) | Model | Score | Δ vs Opus 4.7 |
|---|---|---|---|
| Maral (free, already owned) | qwen3:14b | ~45% | -43 pts |
| Mac Mini M4 24GB BTO ($999) | Qwen3.6-27B | **77.2%** | **-10 pts** |
| GMKtec EVO-X2 64GB ($1,499) | Mistral Medium 3.5 128B | 77.6% | -10 pts |
| Beelink GTR9 Pro 128GB ($1,985 Amazon) | GLM-5 / Kimi K2.6 Q4 | ~77-80% | -8 pts |
| Mac Studio M3 Ultra 256GB ($6K+) | DeepSeek V4 Pro Max Q4 | 80.6% | -7 pts |

To get within ~10 pts of cloud, **$999 buys back ~32 pts** (45% → 77%). Beyond that, hardware spend hits sharp diminishing returns: closing the *last* 8-10 pts to cloud parity requires hardware that doesn't exist at consumer prices yet (frontier closed-source models are months ahead of any local-deployable open weight).

### Lesson 13: Local-LLM coding parity tracks ~12-18 months behind the cloud frontier in 2025-2026. Maral on free hardware gets you to ~2024 Q3 frontier. $999 buys mid-2025 frontier. Closing the last 10 points takes $5K+ and isn't always possible.

### Lesson 14: When choosing between cloud and local, denominate in points of SWE-bench, not in dollars or principle. A 43-point gap is a 50% drop in real-world coding-issue resolution. A 10-point gap on $999 hardware is the actual sweet spot.

---

## Act 10 — Closing the hard breaks with MCP

The 43-point SWE-bench gap is mostly model capability — can't fix without bigger weights. But several other cloud-Claude features have nothing to do with model quality. They're *features Claude Code calls* on top of the model. Those, we can rebuild.

### What is and isn't fixable with infrastructure

| Cloud feature missing | Why missing | Infrastructure fix |
|---|---|---|
| Image / PDF understanding | qwen3:14b is text-only | ✅ Run a vision model (qwen2.5vl) and expose it as an MCP tool |
| Context window > 32k | qwen3:14b ceiling | ✅ Build a RAG MCP server — embed the repo, retrieve top-k chunks per query |
| Shallow code review | Single-pass LLM analysis | ✅ Compose deterministic linters + type checkers + LLM pass = denser findings |
| Sloppy memory writes | Smaller model = looser format adherence | ✅ Periodic cron: re-process memory entries with stricter prompt |
| Anthropic prompt cache | API-level feature | ✅ Local Ollama `OLLAMA_KEEP_ALIVE=24h` covers within-session; cross-machine is harder |
| Frontier reasoning depth | Model capability | ❌ Can't fix without bigger weights |
| Multi-file refactor coherence | Model context coherence | ❌ Partial — RAG helps but doesn't replace whole-repo reasoning |
| Subagent prompt quality | Model can't write tight prompts | ⚠️ Partial — templated prompt MCP could help |

### Architecture

```
Claude Code (your Mac)
  ├─ ANTHROPIC_BASE_URL → Maral Ollama (qwen3:14b primary)
  └─ MCP stdio subprocesses on your Mac:
       ├─ maral-vision   → calls qwen2.5vl on Maral over HTTP
       ├─ maral-rag      → calls nomic-embed-text on Maral, stores in sqlite-vec
       ├─ maral-review   → runs local linters + calls qwen3:14b on Maral
       └─ maral-memory   → reads ~/.claude/memory/, calls qwen3:14b for rewrites
```

Each server is ~150-300 lines of Python using `mcp.server.fastmcp.FastMCP`. They run as Claude Code stdio subprocesses. They don't need to live on Maral — they're thin clients to Ollama.

### The four servers

#### `maral-vision`
- `describe_image(path, prompt?)` — generic vision description
- `ocr_screenshot(path)` — verbatim text/code extraction from screenshots
- `extract_pdf(path, page_range?, include_vision?)` — text extraction with optional per-page vision augmentation

Closes: screenshots, mockups, PDFs with figures.

#### `maral-rag`
- `index_dir(path)` — chunks the directory (512 tokens per chunk, 80 overlap), embeds via nomic-embed-text, stores in sqlite-vec
- `search(query, root, k)` — returns top-k chunks
- `read_with_context(file, query)` — file body + related chunks elsewhere in the index

Closes: large-repo work that overflows 32k native context.

#### `maral-review`
- `review_file(path, language?)` — runs ruff/mypy/eslint/tsc/clippy/staticcheck/shellcheck (whichever fits the language) THEN sends file + linter findings to qwen3:14b with "find what linters missed" prompt
- `review_diff(diff_text?, cwd?)` — same idea for unified diffs (falls back to `git diff HEAD`)

Closes (partially): shallow single-model code review. Deterministic catches go up sharply; subtle bug catches still weaker than Opus.

#### `maral-memory`
- `audit_memory()` — reports malformed frontmatter, duplicates, oversized entries, missing **Why:** lines
- `cleanup_memory(dry_run=True)` — rewrites sloppy entries via qwen3:14b with strict format prompt
- `consolidate_index()` — rebuilds `MEMORY.md` from frontmatter

Closes: smaller-model auto-memory writes drifting from canonical format over time. Run weekly as cron.

### Install

```bash
cd ~/tmp-projects/local-llm/mcp-servers
./install.sh
# prints 4 `claude mcp add` commands at the end
```

The install script: bootstraps `uv`, creates `.venv`, installs deps, SSHes to Maral and pulls `qwen2.5vl:7b` (~5GB) + `nomic-embed-text` (~270MB), then prints registration commands.

### What this closes vs leaves open

After install, the **hard breaks** are gone:

- Screenshots / mockups / PDFs → usable (lower fidelity than Claude vision, but real)
- 32k context limit → effectively unbounded via RAG retrieval (loses cross-cutting reasoning vs huge ctx, but covers 95% of cases)
- Shallow review → multi-pass beats single-pass
- Memory drift → self-correcting

The **quality gaps from model size** stay:

- ~45% vs ~88% SWE-bench Verified
- Multi-file refactor coherence
- Subagent prompt quality
- Subtle bug catches

Net effect: from "can't do these tasks at all" to "can do them, just less precisely." That's the maximum useful work the infrastructure layer can do for you. Beyond this, you're paying for bigger weights (Mac Mini M4 24GB → Qwen3.6-27B).

### Lesson 15: Infrastructure can close *categorical* gaps (vision/long-context/multi-pass review) but cannot close *capability* gaps (reasoning depth, coherence). Build the MCP servers for the categorical wins; budget hardware for the capability gap.

---

## Act 11 — Bringing your past with you (settings + cloud export)

A coding agent is only as good as the context it walks into. Two pieces have to come along when you switch backends:

1. **Local Claude Code state** — `CLAUDE.md`, hooks, skills, plugins, memory, settings, shell router — should be available on every machine you run `claude` on, not just the primary Mac.
2. **Cloud-side history** — the conversations you've had on claude.ai, the auto-memories Anthropic has built up about you — should be queryable from the local LLM.

### Sync Mac → Maral

Maral has Claude Code installed (from Act 7) and now serves as both the Ollama backend AND a usable headless CC client over SSH. For the second role to work, it needs your settings.

Synced via rsync with path rewriting (`/Users/john.connolly` → `/Users/jconnolly`):

```bash
MARAL=youruser@maral.local

ssh $MARAL 'mkdir -p ~/.claude/hooks ~/.claude/skills ~/.claude/plugins ~/.claude/memory'

# CLAUDE.md + settings.json: pipe through sed for path rewrite
sed 's|/Users/john.connolly|/Users/jconnolly|g' ~/.claude/CLAUDE.md | ssh $MARAL 'cat > ~/.claude/CLAUDE.md'
sed 's|/Users/john.connolly|/Users/jconnolly|g' ~/.claude/settings.json | ssh $MARAL 'cat > ~/.claude/settings.json'

# bulk dirs: rsync (Node hook scripts, skills, plugins, existing memories)
rsync -aq ~/.claude/hooks/   $MARAL:~/.claude/hooks/
rsync -aq --exclude='.git' ~/.claude/skills/  $MARAL:~/.claude/skills/
rsync -aq --exclude='.git' --exclude='node_modules' ~/.claude/plugins/ $MARAL:~/.claude/plugins/
rsync -aq ~/.claude/memory/  $MARAL:~/.claude/memory/
```

The zsh router also goes on Maral, but pointing at `localhost:11434` (Maral runs Ollama locally) instead of the Mac IP:

```sh
# Maral's ~/.zshrc fragment (same structure, different LOCAL_LLM_HOST)
LOCAL_LLM_HOST="localhost:11434"
LOCAL_LLM_MODEL="qwen3:14b"
LOCAL_LLM_SMALL="qwen3:8b"
# ...same claude/claude-cloud/claude-status functions...
```

What was NOT synced:
- `~/.claude/.credentials.json` — OAuth tokens; re-login on Maral via `claude /login` if needed
- `~/.claude/projects/` — per-project session transcripts; large, sync selectively when continuity matters
- `~/.claude.json` — has cwd-keyed project entries with paths that won't translate; would need surgical merge

### Importing the cloud export

User triggered the claude.ai data export (Settings → Privacy → Export). Email arrived a few hours later, ZIP unpacks to `~/Downloads/data-<uuid>-batch-0000/` containing:

```
conversations.json        2.2 MB   — 8 conversations, 26 messages each on average
memories.json             1.8 KB   — Anthropic-side auto-memory profile of the user
projects/                 20 KB    — claude.ai project metadata
users.json                160 B    — minimal account info
```

The `memories.json` was the surprise: a hand-summarized profile of the user from cross-conversation memory. Worth keeping as a local memory file:

```bash
# ~/.claude/memory/cloud_export_user_profile.md
---
name: cloud-export-user-profile
description: User profile inferred from claude.ai conversations memory (exported May 2026)
metadata:
  type: user
---
# (content of memories.json[0].conversations_memory, lightly reformatted)
```

The `conversations.json` was converted to one markdown file per conversation, in a dedicated dir for RAG indexing:

```python
import json, re, pathlib
data = json.load(open(DATA + "/conversations.json"))
out = pathlib.Path("~/local-llm-data/cloud-conversations").expanduser()
out.mkdir(parents=True, exist_ok=True)
for conv in data:
    title = conv.get("name") or conv["uuid"]
    safe = re.sub(r"[^\w\-]", "_", title)[:80]
    fn = out / f"{conv['created_at'][:10]}__{safe}.md"
    lines = [f"# {title}", f"_uuid: {conv['uuid']}_", ""]
    for m in conv.get("chat_messages", []):
        lines.append(f"## {m['sender']} ({m['created_at']})\n\n{m['text']}\n")
    fn.write_text("\n".join(lines))
```

Then indexed via `maral-rag`:

```python
from server import index_dir
await index_dir("~/local-llm-data/cloud-conversations")
# → Indexed 7 files, 74 chunks
```

Smoke test query:

```python
await search("local LLM hardware Mac mini", "~/local-llm-data/cloud-conversations", k=3)
# → returns 3 chunks from "Secure Claude deployment for enterprise data" conversation,
#   covering Mac Mini M4 Pro pricing, MCP compatibility, cost analysis
```

The local model can now pull yesterday's cloud thinking into today's local session.

### Hiccup #4: macOS Python + sqlite extension loading

First `index_dir` attempt failed:

```
AttributeError: 'sqlite3.Connection' object has no attribute 'enable_load_extension'
```

macOS bundles a Python built without `--enable-loadable-sqlite-extensions`. `sqlite-vec` needs that flag. Fix was to use `uv` to install a python-build-standalone Python (which compiles sqlite3 with extensions on):

```bash
uv python install 3.12       # installs cpython-3.12.13-macos-aarch64-none
rm -rf .venv
uv venv --python 3.12
.venv/bin/python -c "import sqlite3; print(hasattr(sqlite3.connect(':memory:'), 'enable_load_extension'))"
# True
```

### Hiccup #5: sqlite-vec knn query syntax

After fixing Python, search threw:

```
sqlite3.OperationalError: A LIMIT or 'k = ?' constraint is required on vec0 knn queries.
```

sqlite-vec's knn syntax requires `AND k = ?` *in the WHERE clause*, not `LIMIT N` after `ORDER BY`. Wrong:

```sql
WHERE embedding MATCH ? ORDER BY distance LIMIT ?
```

Right:

```sql
WHERE embedding MATCH ? AND k = ? ORDER BY distance
```

One-line fix in `maral-rag/server.py`.

### Lesson 16: When you switch backends, you're not just switching the model — you're switching the *machine that knows your config, history, and skills*. Plan the sync explicitly. Path rewriting (`/Users/john.connolly` → `/Users/jconnolly`) is the boring step that breaks everything if you skip it.

### Lesson 17: Vendor-exported data has more than just chat logs. Claude's export ships an `conversations_memory` field that's effectively a hand-summarized you, written by their model. Drop it straight into `~/.claude/memory/` as a `type: user` entry — the cleanest one-line gain in the whole pivot.

### Lesson 18: macOS system Python's sqlite isn't built with extension loading. Use `uv python install` to get the python-build-standalone toolchain. This is the single most-frequent footgun for local-AI Python tooling on Macs.

---

## Lessons distilled

1. **SSH brute-force on a fail2ban host is broken by design** — connection resets ≠ permission denied, and your "ruled out" list lies. Rate-limit yourself.
2. **Pick software stack, not impressive hardware.** Hailo-10H is a great NPU. It is *not* a Claude Code backend in May 2026.
3. **A model's `tools` capability advertisement is a claim, not a contract.** Test end-to-end with a real `tool_use` round trip before committing.
4. **Model family matters more than parameter count for tool use.** Qwen3 has trained-in tool-call format; Qwen2.5-Coder doesn't reliably emit it.
5. **On SD-rooted Pi 5, sustained parallel disk writes lock all userspace services.** Never run two `ollama pull` at once. ICMP will lie to you.
6. **Find the bottleneck first.** Pi 5 USB3 = 500 MB/s ceiling. Buying past it is markup.
7. **The thing you already own may be 5x faster than the thing you're researching.** Inventory before purchase. Default to "use what's already running."
8. **SWE-bench Verified is the right axis for coding-agent comparisons** in May 2026. Top closed: Claude Mythos 93.9%, Opus 4.7 87.6%. Top open at $1K hardware: Qwen3.6-27B 77.2%. Realistic on free hardware: ~40-50%.
9. **NAND prices doubled in 2026 due to AI/HBM demand.** $80 1TB SSDs from 2024 are $200+ today. Plan for 2x premiums or shop SATA / used.
10. **macOS Ollama can be installed headless** by extracting the binary from the .app bundle and using a launchd plist. No GUI, no Homebrew, no .pkg required.

---

## What I actually shipped

| Artifact | Location |
|---|---|
| Pi setup notes (Ollama, Hailo, memory caps) | https://github.com/jconnolly/local-llm-pi5 |
| Maral (MacBook) headless install guide | `maral-mac-server.md` in the same repo |
| `qwen3:4b` + `qwen3:8b` on Pi (Ollama 0.24.0, systemd-capped) | Pi at `192.168.x.x` |
| `qwen3:14b` + `qwen3:8b` on Maral (Ollama 0.24.0, launchd, LAN-bound) | Mac at `maral.local` |
| Hailo-10H driver + runtime + `hailo-apps` cloned for vision experiments | Pi |
| Claude Code wired against either backend via `ANTHROPIC_BASE_URL` | env var, not committed to Mac |

### Final recommendation slide

> If you want a coding agent at home:
>
> - **You have an Apple Silicon Mac with ≥16GB unified?** Run Ollama on it. Done in 10 minutes. Free. ~50% SWE-bench.
> - **You have ≥24GB unified?** Use it. Qwen3.6-27B. ~77% SWE-bench.
> - **You have $999 + 10 days?** Mac Mini M4 24GB BTO. Same outcome as above.
> - **You have a Pi 5 + AI HAT?** Great for vision and Whisper. Don't use it for a coding agent. Use it for what it's good at.
>
> **And never, ever, run two `ollama pull` against an SD card at once.**

---

## References (live as of May 27 2026)

- [SWE-bench Verified official](https://www.swebench.com/verified.html)
- [SWE-bench Verified leaderboard (BenchLM live)](https://benchlm.ai/benchmarks/sweVerified)
- [SWE-bench Verified leaderboard (llm-stats live)](https://llm-stats.com/benchmarks/swe-bench-verified)
- [Qwen3.6-27B blog (Alibaba)](https://qwen.ai/blog?id=qwen3.6-27b)
- [Hailo GenAI Model Zoo MODELS.rst](https://github.com/hailo-ai/hailo_model_zoo_genai/blob/main/docs/MODELS.rst)
- [Hailo-Ollama tool-use bug thread](https://community.hailo.ai/t/hailo-ollama-tools-support/18624)
- [Raspberry Pi AI docs (Hailo install)](https://www.raspberrypi.com/documentation/computers/ai.html)
- [Ollama → Claude Code integration](https://docs.ollama.com/integrations/claude-code)
- [Tom's Hardware SSD price tracking 2026 (AI-driven crisis)](https://www.tomshardware.com/pc-components/ssds/ssd-price-tracking-2026-lowest-price-on-every-m-2-sata-and-portable-ssd)
- [Beelink GTR9 Pro at Amazon (pre-order $1985)](https://www.amazon.com/Beelink-GTR9-Crucial-Computer-DeepSeek/dp/B0FPQQYWQ1)
- [Framework Desktop review (Tom's Hardware)](https://www.tomshardware.com/desktops/gaming-pcs/framework-desktop-review)
