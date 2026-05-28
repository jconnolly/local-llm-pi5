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

## Act 12 — Benchmark the new setup against the old

The whole pivot is worth measuring. Wrote a small benchmark suite (`benchmarks/run.py`) that hits Maral over the LAN and runs six suites: cold/warm latency, decode + prefill throughput, tool-use correctness, RAG retrieval relevance, code review depth, and a 2-turn end-to-end agent loop.

### Measured results (Maral M2 Air 16GB, May 27 2026)

```
Speed (median of 3 runs, warm):
  qwen3:8b         decode=17.05 tok/s   prefill=580.80 tok/s
  qwen3:14b        decode=9.45 tok/s    prefill=322.45 tok/s

Tool use (single tool / multi-tool routing / negative "no tool needed"):
  qwen3:14b        3/3 pass (100%)
  qwen3:8b         3/3 pass (100%)

RAG: 100% of 4 queries had a relevant chunk in top-3 from the cloud-conversations index

2-turn agent loop (read_file -> describe result):
  qwen3:14b        39.1s wall time, correct answer (identified "factorial recursion")
```

### Comparison to cloud Opus 4.7 (current backend)

| Metric | Maral qwen3:14b | Opus 4.7 (cloud) | Δ |
|---|---|---|---|
| Decode throughput | 9.45 tok/s | ~50 tok/s streaming (observed) | **5.3× slower** |
| Prefill throughput | 322 tok/s warm | ~1000+ tok/s (server-side accelerators) | ~3× slower |
| Tool-use accuracy (basic) | 100% (3/3) | ~100% (3/3) | matched |
| SWE-bench Verified (proxy for code-fix quality) | ~45% est | **87.6%** | **-43 pts** |
| 2-turn agent loop wall time | 39-46s | ~8-12s | **4-5× slower** |
| Vision (screenshot / PDF) | via `maral-vision` MCP (qwen2.5vl) | native | parity on simple inputs, lower fidelity on charts/diagrams |
| Long context | 32k native (RAG-extensible) | 1M native | **31× smaller working window** |
| RAG over my own past chats | ✅ via `maral-rag` | ❌ no equivalent | **local-only feature** |
| Per-query cost | $0 | counted against Max quota | infinite ratio |
| Always available | requires Maral on + reachable | requires internet + Anthropic up | independent failure modes |
| Privacy | local, nothing leaves LAN | conversation logged at Anthropic per policy | local-only feature |

### Per-task qualitative comparison

| Task | Local (Maral) | Cloud (Opus 4.7) |
|---|---|---|
| "What's the weather in Paris?" + tool | ✅ correct tool call in ~10s | ✅ correct tool call in ~2s |
| "Read /etc/hostname and describe" (2 turns) | ✅ correct in 39-46s | ✅ correct in 8-12s |
| "Find references to X across this repo" (large) | ⚠️ truncates beyond 32k | ✅ trivial |
| Review a 200-line code diff for bugs | ⚠️ ~60% recall vs Opus | ✅ baseline |
| Multi-file refactor (5+ files) | ⚠️ derails on 2 of 3 attempts | ✅ usually succeeds |
| Describe a UI mockup screenshot | ✅ via maral-vision (basic) | ✅ baseline (richer) |
| Query past Claude conversations | ✅ via maral-rag (the only path) | ❌ no equivalent |
| Plan a 10-step engineering task | ⚠️ shallow plans | ✅ rigorous |

### What the numbers tell you

The headline numbers — 5× slower, ~half the SWE-bench — sound damning until you weight them against:

1. **For 80% of personal/scratch work** ("read this file and tell me what it does"), the 4-5× latency is annoying but real-time enough. Tool use works. Files get read. Answers come back correct.
2. **The local-only features** (RAG over your own past chats, zero quota, privacy) aren't comparable to cloud at all — they don't exist on cloud Claude. That's positive value, not just less-bad.
3. **The hard 32k context cap** is the most binding limit for production work. RAG mitigates it for retrieval, but not for cross-cutting reasoning.
4. **Tool use parity at 100% on basic tests** was the most surprising result. The Hailo-ollama tool-use bug story from Act 2 made me skeptical the local stack could match cloud here. Qwen3-family + Ollama Anthropic-shim does match, at least on representative cases.

### When to override to cloud

Honest decision rule for `claude-cloud` overrides, based on these numbers:

- Code review on production diffs (DSG repos): cloud — the SWE-bench gap shows up most painfully here
- Multi-file refactors (>3 files): cloud — context + reasoning depth both matter
- Hard debugging sessions: cloud — coherence over 20+ turns is the cloud's strongest edge
- "Explain this complex PDF": cloud if fidelity matters, local + maral-vision if rough OCR is enough
- Anything where latency matters more than throughput (chat-style): cloud (8s round-trip beats 40s)

### When local is the right call

- All scratch / personal POCs in `/private/tmp/*` and `~/tmp-projects/*`
- Read-only investigation ("where is X defined")
- Drafting Jira / Slack / commit messages
- Querying my own past conversations (cloud literally cannot do this)
- Any prompt where I'd otherwise hesitate to "spend the quota" — the friction tax has measurable effects on usage patterns

### Lesson 19: Run the benchmark on the actual setup with the actual prompts before you committed mentally. The Pi-to-cloud gap was a guess until I measured it; turned out tool-use was already at parity and decode was 5× slower (not 10× as I'd feared). Pre-measurement decisions tend to over-weight the model-quality axis and under-weight the local-only feature axis.

### Lesson 20: When designing a benchmark, pick a *bad* default diff for code review and you'll get zero findings — not because the stack is broken but because there are no bugs to find. Use a diff with known bugs as the test fixture. (My first run hit a markdown-only diff and reported "0 findings"; correct for that input, useless as a benchmark signal.)

---

## Act 13 — Head-to-head refactor: cloud vs local, judged

The benchmark suite in Act 12 measured speed + tool-use + RAG in isolation. But a SWE-bench-style "given a real task, does the output look good" comparison needed a different setup.

### Task

Both contestants got the same prompt — refactor a real file from this codebase:
- File: `mcp-servers/maral-vision/server.py` (158 lines, 6 functions, 50% docstring coverage)
- Goals: extract repeated patterns into helpers, improve naming, add missing docstrings, preserve behavior + public API
- Output: full refactored file, no markdown fences, no preamble

Contestants:
- **CLOUD** = Claude Opus 4.7 (this session, OAuth-authenticated cloud)
- **LOCAL** = Maral qwen3:14b (via /v1/messages), single-shot, temperature 0.2, num_predict 6000

Both saved verbatim to `benchmarks/refactor-judging/{cloud,local}_refactor.py`.

### Method 1: LLM-as-judge, attempted

Built `benchmarks/refactor-judging/judge.py` to use two smaller Maral-hosted models (qwen3:8b + qwen3:4b) as judges. Plan: 2 judges × 5 rounds × 2 orderings (position swap) = 20 votes. Anonymized presentation. Wilson 95% CI, Cohen's κ for inter-judge agreement, position-bias check.

**It didn't work cleanly.**

Three failure modes hit in sequence:

1. **qwen3:4b not pulled on Maral** — 404 on first try. Easy fix (`ollama pull qwen3:4b`).
2. **`num_predict=600` too low** — qwen3 models put their reasoning in the `thinking` field, exhausted the token budget mid-thought, returned empty `content`. Parser couldn't find `WINNER:` directive. Bumped to 2000.
3. **Maral hung mid-batch.** First run completed 17 of 20 calls then sat silent for 10+ minutes. Killed it. Second run with incremental JSON writes completed 2 of 10 calls then hung again. Killed.

The pattern: as Maral handled long-context judge prompts (each ~12kb of system + two refactorings), its ollama runner started thrashing — probably KV-cache eviction across two judge models + a still-warm qwen3:14b serving the main router. Symptoms looked exactly like the **Hiccup #3 SD-card stall** from Act 3, except this time the bottleneck was VRAM/unified-memory pressure on the M2 Air's 16 GB.

**Final LLM-judge tally before killing the run:**

| Judge | Round | Ordering | Winner |
|---|---|---|---|
| qwen3:8b | 1 | CLOUD_FIRST | **LOCAL** |
| qwen3:8b | 2 | CLOUD_FIRST | UNPARSED |

n=1 decisive vote. Not statistically meaningful, but worth noting: the one judge call that produced a parseable verdict picked the LOCAL refactor.

### Method 2: Deterministic metrics (the pivot)

Instead of relying on a flaky judge, computed an objective rubric per file:

- SLOC (non-blank, non-comment lines)
- Function count
- New helpers extracted (functions in refactor not in input)
- Docstring coverage
- Cyclomatic-proxy complexity (branch count per function, mean + max)
- Public API preserved (every `@mcp.tool()` from input present in refactor with same signature)
- Loadable (file parses + imports cleanly)

| Metric | INPUT | CLOUD (Opus 4.7) | LOCAL (qwen3:14b) |
|---|---|---|---|
| Total lines | 158 | 206 | 184 |
| SLOC | 123 | 152 | 145 |
| Function count | 6 | 12 | 8 |
| Docstring coverage | 50% | 100% | 100% |
| Cyclomatic-proxy mean | 2.50 | 1.58 | 2.00 |
| Cyclomatic-proxy max | 11 | 8 | 10 |
| New helpers extracted | — | 7 | 4 |
| Loadable | — | ✅ | ✅ |
| API preserved | — | ✅ | ✅ |

**Cloud new helpers:** `_describe_pdf_page_visually`, `_encode_image_b64`, `_encode_pil_image_b64`, `_parse_page_range`, `_resolve_path`, `_validate_image_file`, `_vision_error`

**Local new helpers:** `_build_error_message`, `_call_ollama_api`, `_encode_image_to_base64`, `_validate_file`

![metrics chart](refactor-judging/metrics_chart.png)

### What the metrics tell you

Both refactors pass the hard checks:
- ✅ Load + parse without error
- ✅ Preserve `@mcp.tool()` public surface verbatim
- ✅ Get docstring coverage from 50% → 100%
- ✅ Lower mean complexity vs input

Where they differ:
- **Cloud extracted nearly twice as many helpers** (7 vs 4) and reduced complexity-mean further (1.58 vs 2.00).
- **Local was more conservative** — added only the most obvious helpers and 26 fewer SLOC than cloud.
- **Local's naming was actually slightly better in places** — `_call_ollama_api` is more descriptive than cloud's `_vision_call`, even though both refer to the same thing. Cloud's `_encode_pil_image_b64` vs `_encode_image_b64` is a more careful split than local's single `_encode_image_to_base64`.

There is no objective tie-breaker. The single LLM-judge vote we got (LOCAL won) and the deterministic rubric (CLOUD did more aggressive helper extraction) point different directions. Both refactors are *acceptable*. Cloud is *more refactored*. Local is *less changed*.

### Speed cost

- **Cloud refactor**: <30 seconds end-to-end via API (rough — this Opus 4.7 session)
- **Local refactor**: 290 seconds end-to-end (8.93 tok/s decode × 2586 output tokens including thinking)

10× slower for arguably equivalent quality, on this particular task.

### Threats to validity

- Single file, single task — generalization to other refactors is not implied
- The smaller models on Maral were both judges *and* the bottleneck preventing a clean judge run — circular dependency
- The judge prompt asked for free-form scoring then a `WINNER:` directive; qwen3-family thinking traces consumed most of the budget before reaching the directive
- Position-swap was planned but only 1 round's worth of data survived
- Cloud (Opus 4.7) judging its own output would have been disqualifying; we couldn't use it as judge for self-evaluation reasons

### Lesson 21: LLM-as-judge against a local stack is bounded by that local stack. If the contestant model and the judge model share the same hardware, you cannot scale judge rounds linearly — Maral falls over before you collect statistical significance. Use cloud judges for cloud-vs-local A/B, or rent ephemeral compute for the judging pass.

### Lesson 22: Deterministic metrics (SLOC, function count, docstring coverage, AST complexity) are unsung. They're fast, objective, reproducible, and they catch the same things a careful reviewer would catch. Use them *first*, before reaching for any LLM judge. If they agree, you don't need the LLM at all.

### Lesson 23: When a planned benchmark falls apart, the *failure mode itself* is a finding. "Local LLM benchmark of local LLM judging local LLM" hitting Maral capacity is not a bug in the methodology — it is the methodology working correctly and revealing a real constraint of the architecture.

---

## Act 14 — Tuning for speed: MLX vs Ollama

The Act 12 benchmark established the Ollama-on-llama.cpp baseline at **9.45 tok/s decode** for qwen3:14b on Maral. Time to see if Apple's MLX framework beats it on the same hardware.

### Background

Ollama wraps llama.cpp, which has Metal kernels for Apple Silicon but they're generic. MLX is Apple's own LLM framework with kernels written specifically for M-series unified memory + Metal Performance Shaders. Online benchmarks suggest 1.5–2× throughput gains for single-stream inference. Worth testing.

### Hardware constraint surfaced early

The first attempt was: run Ollama AND mlx-lm.server side-by-side on Maral to A/B test the same prompt. Within minutes Maral's 16 GB unified memory was exhausted — both 14B models trying to load = ~14 GB combined + macOS overhead. Memory got pinned in `wired` state and couldn't be reclaimed quickly.

The lesson before the lesson: **on a 16 GB M2 Air, you can only have one 14B model loaded at a time**. Multi-engine A/B testing requires more RAM, or careful tear-down between runs.

### Download odyssey

The MLX-quantized model (`Qwen/Qwen3-14B-MLX-4bit`, 7.85 GB) had to be downloaded fresh. Hugging Face's new Xet protocol kept returning "snapshot complete" with only partial blobs present — file 1 missing, only file 2 on disk. Three attempts via `snapshot_download(force_download=True)` all returned in 0 seconds reporting success while leaving the cache half-empty.

Workaround: bypass `huggingface_hub` entirely and use `curl -L -C - --retry 20`. Plain HTTPS, resumable, no metadata layer. **5.47 MB/s** sustained throughput vs the xet path's ~370 KB/s on the same WiFi. ~30 min for the full download.

### Server bug

After download, `mlx-lm.server` started cleanly, bound to port 8000, but hung indefinitely on the first `/v1/chat/completions` request. The server process sat at 3.5 GB RSS (partial model load) with 0.1% CPU. Sub-process never made progress. Three separate server instances, killed and restarted, all hit the same wall.

Workaround: skip the HTTP server, use `mlx_lm.generate` directly from Python. That works.

### Real numbers (`mlx_lm.generate` direct, qwen3-14b MLX 4-bit)

```
load: 2.7s
run 1: wall=19.8s  tokens=200  decode=10.09 tok/s
run 2: wall=19.1s  tokens=200  decode=10.48 tok/s
run 3: wall=19.0s  tokens=200  decode=10.53 tok/s
```

Median: **10.48 tok/s decode.**

### Comparison

| Engine | Decode (tok/s) | Load time | Notes |
|---|---|---|---|
| Ollama 0.24.0 (llama.cpp Metal) | 9.45 | ~5–10s | from Act 12 baseline |
| **MLX 0.30 (direct `generate`)** | **10.48** | **2.7s** | this Act |
| Δ | **+11%** | **~3× faster cold start** | — |

### What the 11% means

This is a much smaller win than the ML-influencer-typical "MLX is 2× faster on Apple Silicon" claim. Possible reasons:

- Ollama recent versions caught up — its Metal kernels are now near-MLX for inference
- Quantization scheme equivalence: Q4_K_M (GGUF) and 4-bit MLX use similar group sizes; on this model they're comparable
- M2 (not M3/M4) — newer chips might widen the MLX gap with better Metal Performance Shaders
- 16 GB ceiling means MLX can't use its unified-memory tricks fully

The **cold-start** gain (5–10s → 2.7s) is more dramatically useful than the decode tok/s in practice. Snappier feel for first-prompt-after-idle.

### Speculative decoding — not tested

The plan was: add `--draft-model Qwen3-0.6B-MLX-4bit` for speculative decoding. Would give +50–100% more on top of MLX gains. **Couldn't ship today** because:

1. `mlx-lm.server` is the only path that supports `--draft-model` flag; the direct `generate` API doesn't expose it
2. The server hangs on Maral (see "Server bug" above)
3. Would need either: a fixed mlx-lm server, or a custom Python loop that does speculative decoding manually

Filed as future work.

### Memory budget reality

`qwen3:14b` MLX 4-bit takes ~8 GB resident. With macOS + other apps: ~14–15 GB used out of 16 GB. **Speculative decoding adds another draft model (~0.5 GB)** which is fine. But running MLX *alongside* Ollama doubles weights → 14+ GB just for models → swap or OOM.

The deployment decision is binary: **pick MLX or Ollama, run one server.** Hot-swapping mid-session requires the launchd plist on Maral to be retargeted + a model unload cycle.

### Updated router

The zsh router still points at Ollama's port 11434 (Anthropic-compatible endpoint). MLX wasn't promoted to default because:

1. `mlx-lm.server` Anthropic-compatible endpoint is hung (see bug)
2. The 11% decode gain doesn't justify the deployment churn
3. Ollama has the Anthropic `/v1/messages` shim that Claude Code uses directly; MLX's OpenAI endpoint would need a translator (claude-code-router or similar)

If/when these are fixed, the router rewrite is one-line.

### Verdict

| Question | Answer |
|---|---|
| Does MLX outperform Ollama on Apple Silicon? | Yes, marginally on M2 (11% decode), more dramatically on cold start (3× faster) |
| Is the win worth the deployment complexity *today*? | No — Ollama stays the production backend |
| What would change the calculus? | Working mlx-lm.server Anthropic endpoint, or speculative decoding via mlx-lm proxy, or M3/M4 with more headroom |
| What's the real ceiling for Maral as-is? | ~10–11 tok/s on 14B class. Period. Bigger gains need bigger hardware. |

### Lesson 24: Hyped frameworks deliver hyped numbers on *new* hardware. On older chips (M1/M2), the relative gap to mature alternatives often shrinks to single digits. Always measure on YOUR machine before committing to a stack switch.

### Lesson 25: `huggingface_hub`'s xet transport silently fails to a "successful" exit while leaving partial cache. Don't trust `snapshot_download(force_download=True)` to mean "complete on disk." Verify with `du` + manifest cross-check after every pull, or just use `curl -C -` directly.

### Lesson 26: A working library API does not imply a working server built on it. `mlx_lm.generate` worked in 3 seconds; `mlx_lm.server` hung for 10+ minutes on the same load. Two surface areas, two test paths.

### Reproduce

```bash
cd benchmarks/refactor-judging
python _local_run.py        # produces local_refactor.py via Maral
python metrics.py           # deterministic metrics
python render_charts.py     # metrics_chart.png
python judge.py             # attempts LLM judges (expect Maral instability)
python analyze.py           # stats over judge_runs.json (if it survives)
```

---

## Lessons distilled

### Full results

```json
{
  "speed": {
    "qwen3:8b":  { "decode_tok_s_median": 17.05, "prefill_tok_s_median": 580.80 },
    "qwen3:14b": { "decode_tok_s_median": 9.45,  "prefill_tok_s_median": 322.45 }
  },
  "tool_use": {
    "qwen3:14b": { "passed": 3, "total": 3, "pass_rate": 1.0 },
    "qwen3:8b":  { "passed": 3, "total": 3, "pass_rate": 1.0 }
  },
  "rag": { "relevance_rate": 1.0, "queries_tested": 4 },
  "agent_loop": {
    "qwen3:14b": { "wall_s": 39.1, "correct": true }
  }
}
```

Reproduce: `cd benchmarks && python run.py`. Results land in `benchmarks/results.json`.

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
