# Session State — local-llm

Running flight-recorder. Updated after each meaningful step. Newest info wins.

## Now
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
