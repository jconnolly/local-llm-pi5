# Session State — local-llm

Running flight-recorder. Updated after each meaningful step. Newest info wins.

## Now
- **2026-06-23 (cont): CROSS-FAMILY AGENT-LOOP BENCH — instability was a STALE-MODEL artifact.**
  - Prompted by Boykis/HN: re-ran agentbench (5 hard tasks, same box) across current models.
    Added `AGENTBENCH_LOCAL_MODEL` env override to run.py. Results (durable record:
    `benchmarks/agentbench/cross_family_results.md`):
    - coder-30b q8 (old deck baseline): 4/5, **4-41 turns (wild)**, 248s, ~8x cloud
    - qwen3.6:27b-mtp q8: 5/5, 7-9 stable, 161s, ~5x
    - **gpt-oss:20b: 5/5, 7-9 stable, 48s, ~1.5x cloud** <- STANDOUT
    - gemma4:26b: 5/5, 8-20, 69s, ~2x
    - Opus cloud: 5/5, 5-9, 31s
  - FINDING: every current model is stable + 5/5. The 41-turn ttl spiral was the MODEL, not
    local inference (coder vs qwen3.6 both q8 -> it's the model, not quant). gpt-oss 20b nearly
    catches cloud. Our deck's "8x slower, unstable" headline was a stale-model artifact.
  - Deck UPDATED (both, 32 slides): new "Tested it: the instability was the model" slide (full
    cross-family table) + reconciliation + PS now reflect this. Committed 2f5e7aa.
  - Quant angle (q6 vs q4 on the 80B) still untested + separate.

- **2026-06-23 (cont): PRESENTATION DECK built (DS-branded) + Boykis/HN reality-check.**
  - Two decks, 31 slides each, content-synced: `local-llm-datasociety.pptx` (native Data Society
    template via `build_pptx.py` + python-pptx) and `slides.html`/`slides.pdf` (Marp, brand-themed,
    gifs animate). Both: purple ACT dividers + white content, DS logo every slide, TL;DR callout,
    Mac Studio photo (stock; eBay swap pending), full talk-script presenter notes (~1min/slide).
  - Editorial passes: de-Claude'd (no arrows/em-dashes/emoji), gen-z + dry humor, hyperbole cut
    ("Maral era"->"doing the most"), acronyms trimmed (kept niche, cut LLM/SOTA/OCR/CPU/RAM).
  - **HARDWARE ACCURACY FIX:** the Pi accelerator is the **AI HAT+ 2 (Hailo-10H, 40 TOPS, 8GB
    on-board)** = Adafruit #6451, a real gen-AI accelerator, NOT the old vision AI HAT+. Real
    dead-end reason = **integration (c)**: no Anthropic/Ollama endpoint, Claude Code couldn't connect.
    Rewrote dead-end + "show the work" slides honestly (napkin-math caveat; dropped false CNN/CPU claim).
  - **Boykis "Running local models is good now" (Jun 15) + 1,589pt HN thread** analyzed. Corroborates
    our axis (context=wall, ~30B MoE sweet spot, agentic local model-dependent). TWO updates: (1) our
    models stale — community on **Qwen 3.6** (27b/35b-a3b) + **Gemma 4** + gpt-oss; (2) **q4 quant
    weakens tool-calling, q6 = agentic sweet spot** — our 80B ran q4, may explain the instability.
    Added a **PS slide** citing both. NEXT: re-bench Qwen3.6/Gemma4/gpt-oss + agent loop at q6.
  - Assets in viz/: agent-race.gif, appbench/side_by_side_2x.gif, mac-studio.jpg, ds-logo-{dark,white}.png.

- **2026-06-23: APPBENCH (build playable Space Invaders) — NEW long-horizon bench + gameplay videos.**
  - New harness `benchmarks/appbench/`: agent builds a single self-contained index.html via the REAL
    `claude -p` loop; scored by a Playwright 7-check rubric (load/canvas/animation/controls/no-crash/
    render/game-logic). Rubric validated on a ref game = 7/7. `record.py` plays each game ~14s, records
    video, ffmpeg captions (model · built Ns · k/7) + hstacks -> viz/appbench/side_by_side.mp4 + .gif.
  - RESULTS (all built playable in 2 turns): cloud Opus 7/7 @ 50s · **next80 qwen3-next:80b 7/7 @ 98s**
    · local coder-30b 6/7 @ 166s (only miss = idle-animation; game static until keypress).
  - **KEY FINDING: the 8x agent-loop gap COLLAPSES on a clean build task.** No failing-test to spiral on
    -> local 80B ties cloud on quality, within 2x on speed. The 80B beat coder-30b on BOTH speed+score
    (98s/7 vs 166s/6) and used HALF the output tokens (1844 vs 3482) = bigger local model converges
    better even here. The 8x/41-turn gap was specific to the DEBUG-spiral case, not open-ended building.
  - Deck assets: 3 playable index.html + screenshots + side-by-side gameplay video under viz/appbench/.

- **2026-06-09 (cont): MULTI-MODEL SERVER LIVE + qwen3-next:80b added.**
  - #3 DONE: OLLAMA_MAX_LOADED_MODELS=3. coder-30b + qwen2.5vl:7b (vision) + nomic-embed-text
    all resident simultaneously (~38GB, ~50GB free). Box = full local AI server (code+vision+RAG).
    NOTE: `ollama ps` shows empty in 0.30.7 (display bug); confirm via `ps aux | grep llama-server`.
  - qwen3-next:80b-a3b-instruct-q4 (50GB) pulled. Runs **63.8 tok/s** (80B MoE, 3B active = ~same
    speed as the 30B coder). = free quality upgrade for hard/open-ended work. Runs on llama.cpp.
  - SPEC-DECODE finding: NOT achievable via Ollama GGUF path. Ollama 0.30.7 MTP = MLX-runner +
    MLX-format models only; `ollama pull` GGUF runs llama.cpp (no MTP). Skipped — already 63-68 tok/s.
  - Models pulled: qwen2.5vl:7b, nomic-embed-text, qwen3-next:80b-a3b-instruct-q4_K_M.
  - Beefier-model survey (fit 96GB, beat 30B coder): qwen3.5:122b-a10b (~65GB, newest+strongest),
    gpt-oss:120b (~63GB), llama4:17b-scout (~60GB, 10M ctx). glm-4.6=cloud-only; 480b/235b/v3 too big.
  - Team-of-24 analysis: 1 box = ~2-4 concurrent CC sessions OK; 24 bursty = viable supplement w/
    vllm-mlx batching + LiteLLM gateway (auth/quota); all-24-heavy overwhelms it. Cluster or cloud for spikes.

- **2026-06-09: M3 ULTRA LIVE + FIRST BENCH = MILESTONE.** qwen3-coder:30b-a3b-q8 on the Studio
  scored **18/18 = 100%** on the expanded minibench (12 bounded + 6 expert: regex/N-queens/calculator/
  LIS/min-path/decode) at **68.4 tok/s** — **TIES Opus 4.8 (18/18)** AND aces the expert tier, at 4x
  Maral's decode speed. The hardware delivered: local now matches cloud on these problems, fast.
  - **Bootstrap bug found+fixed:** setup-newbox.sh copied only the `ollama` binary; Ollama 0.30+ needs
    the full Resources/ (llama-server + ggml/MLX dylibs) or it 500s "llama-server not found". Fixed in
    the committed script (cp -R Resources/*).
  - **Gotcha:** restarting the ollama launchd agent KILLS in-flight `ollama pull`. Don't restart mid-pull.
  - qwen3:32b + qwen3:8b re-pulling (~/repull.log; the llama-server-fix restart had killed them).
  - **BENCH DONE (full 24, incl 6 brutal LeetCode-hard):** coder-30b-a3b = **24/24 @ 64 tok/s** (ties
    Opus, aced Dijkstra/calc-parens/LIS-palindrome/max-profit-k/word-ladder/RPN). qwen3:8b=16/18@64.5,
    qwen3:32b=16/18@20.5 (skip, slow+no edge). FINDING: bench saturated — local coder = cloud on ALL
    self-contained/algorithmic coding; the local<-cloud gap is purely open-ended multi-file repo work
    (needs SWE-bench-style harness, not harder algos). **coder-30b-a3b = THE model.** Committed e076f5c.
  - `claude` verified end-to-end -> Studio. Router labels fixed (Studio not Maral). claude-status READY.
  - **Spec decoding finding:** Ollama 0.30.7 spec-decode = MLX runner + models w/ native MTP/nextn heads
    (Qwen3-Next, Qwen3.5-MoE, DeepSeek-V3). GGUF coder on llama.cpp does NOT use it. Pulling
    qwen3-next:80b-a3b-instruct-q4 (50GB, MTP model) to measure spec-decode tok/s + as a possible
    bigger-model upgrade (~/nextpull.log, slow ~40min).
  - **Research (what beefy-Studio people run beyond coding agents):** local fine-tuning (mlx-tune:
    SFT/DPO/GRPO/vision/OCR), private RAG over docs, fully-local voice agents (OpenClaw+TTS+STT),
    vision/OCR pipelines, faster serving (vllm-mlx ~113 tok/s on 30B MoE = 1.6x our Ollama 68),
    LM Studio 0.4 headless "llmster". Top adds for John: vllm-mlx for speed + fine-tune on own codebase.
- **(prior) 2026-06-09: M3 ULTRA ARRIVED + SETUP.** Box on network as
  `studio.local` (user jconnolly, passwordless SSH set up). Confirmed M3 Ultra/96GB/873GB
  free. Ran setup-newbox.sh: **Ollama 0.30.7** (has MLX backend) + tuned launchd (KV q8, flash-attn,
  32k ctx) + caffeinate — all up. Models pulling fresh (~/modelpull.log, ~30MB/s): qwen3-coder:30b-a3b-q8
  then qwen3:32b then qwen3:8b. Laptop ~/.zshrc router REPOINTED: LOCAL_LLM_HOST=studio.local,
  LOCAL_LLM_MODEL=qwen3-coder:30b-a3b-q8_0, SMALL=qwen3:8b. (Maral offline during setup; demoted to fallback.)
  - **Next once models land:** `exec zsh` + `claude-status` (verify Studio READY), smoke-test tool use,
    re-run benchmarks/minibench/harness.py on the Studio vs the 12/12 qwen3:8b baseline + Opus. Then tune.
- **(prior) Now**
- **HARDWARE PURCHASED (2026-06-03):** Bought eBay M3 Ultra 96GB/1TB SEALED, item 398020186804,
  $4,299.99 + $376.25 tax = **$4,676.24 all-in.** Verified sealed, free returns, 99.3% seller,
  eBay buyer protection. (Apple-direct was Oct 13 / 4mo out; this ships ~Jun 9.)
  - **AWAITING DELIVERY (~Jun 9).** On arrival: headless-server setup like Maral, pull models,
    swap router, re-bench.
- **SETUP PLAN when it lands (the new box becomes the primary LLM server, replacing Maral):**
  1. Headless server: install Ollama, launchd agent (OLLAMA_HOST=0.0.0.0:11434, KEEP_ALIVE,
     FLASH_ATTENTION=1, KV_CACHE_TYPE=q8_0, CONTEXT_LENGTH=16384), caffeinate agent. Mirror the
     Maral setup in maral-mac-server.md / setup-maral-services.sh.
  2. MODELS (CORRECTED — qwen3:72b does NOT exist; that was a Qwen2.5 number). Best for 96GB:
     `qwen3:32b` (~20GB, largest dense, ~76%) + `qwen3-coder:30b-a3b-q8_0` (~32GB, coder MoE,
     ~77%, fast, already verified working) + `qwen3:8b` (small/fast). 235b-a22b needs 128GB, won't
     fit. Realistic ceiling on this box: ~76-77% SWE-bench (not the ~80% earlier 72b guess).
     PRE-STAGING NOW on Maral (~/prestage.log) so arrival = LAN rsync not internet pull.
  3. Swap `LOCAL_LLM_HOST` in ~/.zshrc to the new box's hostname (use mDNS .local, NOT LAN IP).
     Keep think:false, tool-search auto:5, 120s timeout. Maral demoted to fallback/experiments.
  4. Re-run benchmarks/minibench/harness.py on qwen3:72b vs the 12/12 qwen3:8b baseline + vs Opus.
  5. Hybrid routing = effective parity: new box 72b for daily ~80-83%, `claude-cloud` for hard repo tasks.
- (superseded) prior plan was Apple-direct $3,999:
- **HARDWARE DECISION (2026-06-03, superseded by purchase above):** Apple-direct M3 Ultra 96GB/1TB $3,999.
  John chose quick + Apple Card (3% Daily Cash ~$120 + 0% financing + full warranty + 14-day
  return) over the parity-class 256GB ($9,499, 1-3wk BTO, still only ~87%).
  KEY REALITY ESTABLISHED: **full Opus-4.8 parity (92%) is NOT purchasable locally at any price** —
  best open model (DeepSeek-V3, 512GB/$11.5K) = ~88%, still -4pt. So paying $9.5K + waiting weeks
  for -5pt was the worse deal. 96GB = qwen3:72b ~80% (+10pt over Maral), runs qwen3-coder:30b-a3b
  Q8 too. PARITY PATH = HYBRID: local 96GB for 80% daily grind + `claude-cloud` for hard repo tasks.
  - **Buy path:** apple.com/shop/buy-mac/mac-studio -> M3 Ultra 28C/60C -> 96GB/1TB (standard
    config, $3,999, pickup-able). Cart -> Pick up -> zip 11747 -> check Walt Whitman (Huntington
    Station, closest), Roosevelt Field, Americana Manhasset. Pay Apple Card.
  - **Couldn't confirm live store stock** (Apple gates the fulfillment API behind bot wall +
    correct part#); the in-cart pickup check with zip is the real-time authoritative source.
- **Post-purchase migration:** drop-in. Swap `LOCAL_LLM_HOST` in ~/.zshrc to new box,
  `ollama pull qwen3:72b` (Q8 ~75GB fits 96GB) + `qwen3-coder:30b`. Same router/commands.
- **Next action:** John executes the Apple buy. Then: pull qwen3:72b, re-run minibench on new
  hardware vs the 12/12 baseline; tune; set up hybrid local+cloud routing for hard tasks.
- **Other deferred:** speculative decoding (MLX, +50-100% decode); test-time verification Stop
  hook (+10-20pt); Act 16 writeup (today's tuning + 12/12 parity result).

## Recent (newest first)
- 2026-06-03: Wrote + pushed Acts 16-17 + lessons 31-36 (commit 6b435f5). Act 16 = tuning ladder +
  the 12/12 minibench TIE vs Opus 4.8. Act 17 = parity-not-purchasable + the hardware hunt/buy.
  Committed setup-newbox.sh + SESSION_STATE (8b9da92). Disk cleanup: freed ~72GB (Docker 56G +
  stale Ollama 18G), MacBook now 75% / 108GB free. Pre-pull of qwen3:32b + coder-30b-a3b-q8 still
  running on Maral (~/prestage.log).
- 2026-06-03: **VERIFIED BUY FOUND.** Apple-direct M3 Ultra 96GB = Oct 13 (EOL/backordered, all
  11 NY/CT stores). Pivoted to resale, full due-diligence sweep (resellers + marketplaces, no
  false positives). WINNER: eBay itm/398020186804 — $4,299.99, SEALED, M3 Ultra 96GB/1TB (A3389),
  99.3% seller, free returns, BIN in-stock, verified live. +$300 over MSRP but Apple is 4mo out.
  Runner-ups: $4,899 verified ships-today (318381669124); $3,999 auction (127899684822, unverified/
  bot-blocked, could climb). Dead: MicroCenter/Newegg/B&H/Best Buy/Expercom/Apple all no-stock.
- 2026-06-02: Built session-state hook + global rule. This file created.
- 2026-06-01/02: Committed + pushed 5 commits (a16fbeb..6148baf): config, mlx-server v0.6,
  benchmarks/minibench, maral infra, Act 15. Repo public: github.com/jconnolly/local-llm-pi5.
- Mini-bench head-to-head: **tuned qwen3:8b TIED Opus 4.8 at 12/12 = 100%** on
  algorithmic problems (deterministic test scoring, no LLM-judge). Parity for bounded
  coding; gap remains on open-ended multi-file repo work.
- Tuning wins (all $0): `think:false` (CLAUDE_CODE_DISABLE_THINKING=1 in all local
  routes — killed ~3x thinking-token tax, biggest speed win); KV cache q8_0 + context
  4k→16k; quant sweep (qwen3:8b Q4 wins, 17.7 tok/s); slim CC prompt 28k→9.7k.
- mlx-server v0.6: Anthropic /v1/messages wrapper, tool-use translation, prompt-cache
  reuse, quantized KV, chunked prefill. Bypasses broken mlx_lm.server.

## Open threads (deferred)
- **Speculative decoding** — not built. Needs qwen3:0.6b MLX draft model + `--draft-model`.
- **Test-time verification Stop hook** — documented not built. Mechanism: Stop hook script
  runs project test cmd; if fail, emit `{"decision":"block","reason":"..."}` (exit 0) to
  force CC to iterate until green. ~8 consecutive-block limit. +10-20pt SWE-bench proxy.
- **Act 16 writeup** — code/data committed, narrative not written.
- **Hardware** — best live deal was eBay $3,999 M3 Ultra 96GB auction (2d left as of 5/29).
  Melville LI Craigslist $4,000 SOLD. Declined $2,400 Mac mini ripoff (new = $1,999-2,199).
  M3 Ultra 96GB ($800GB/s bandwidth) = real SOTA-class unlock; fits qwen3:235b-a22b Q3.

## Key facts
- **Maral** = MacBook Air M2 16GB LLM server. Reach via `maral.local` (NOT the LAN IP
  maral.local — dies on WiFi-driver crashes; mDNS/awdl0 survives). SSH `youruser@maral.local`.
- **This Mac** = MacBook Pro M4 Pro 24GB (daily driver — do NOT run Ollama here full-time;
  WindowServer crashed when 30b model starved RAM).
- **Routing** (`~/.zshrc` bounded marker block): `claude`→Maral Ollama qwen3:8b |
  `claude-mlx`→Maral MLX :11435 | `claude-laptop`→this Mac (on-demand) | `claude-cloud`→Opus (explicit opt-in only).
  `claude-status` shows all 4. All local routes: think disabled, tool-search auto:5, 120s timeout.
- **Hard rules (memories):** NEVER Groq. NEVER cloud unless explicitly invoked. Always stream output.
- **Empirical ceilings:** 16GB = floor not ceiling (WiFi crashes 3x); 24GB laptop too small to
  serve; 30B MoE loads on 16GB but <1 tok/s (CPU/GPU split). Real CC use is prefill-bound on 16GB.
- **Repo:** github.com/jconnolly/local-llm-pi5 (PUBLIC). presentation.md = the journey (15 acts,
  30 lessons). benchmarks/minibench/ = the parity harness.
