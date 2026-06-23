---
marp: true
theme: default
paginate: true
header: "Local LLM at Home — June 2026"
---

<!-- Render: `npx @marp-team/marp-cli slides.md -o slides.pdf` (or .html). VS Code: Marp extension preview. -->

# Can a local LLM replace cloud Claude Code?

### A 3-week investigation: Pi 5 → MacBook Air → $4,676 Mac Studio

**TL;DR:** On self-contained coding, **yes — local ties the frontier, free, fast.**
On open-ended repo work, **no — and no hardware closes that.**

John Connolly · June 2026

---

## The question

> Can I run a "SOTA" local LLM at home, usable as my Claude Code backend,
> and stop paying for cloud?

Two things to find out:
1. **Is it possible** — and at what hardware/cost?
2. **Is it good enough** — measured, not vibes?

---

## The trip (the lessons are in the trip, not just the destination)

| Stop | Hardware | Verdict |
|---|---|---|
| 1 | **Raspberry Pi 5 + Hailo NPU** | Dead end — 2B model ceiling, 2k context, broken tool-use |
| 2 | **Spare MacBook Air M2 16GB ("Maral")** | Carried the project — qwen3:14b @ ~10 tok/s, taught every lesson |
| 3 | **The tuning wall** | `think:false` = ~3× speedup; quant sweep; prompt slim |
| 4 | **The reckoning** | Frontier parity is *not purchasable locally at any price* |
| 5 | **Mac Studio M3 Ultra 96GB ($4,676 used)** | Ties Opus on coding @ 68 tok/s, $0/mo |

---

## Dead end #1: the Pi was the wrong tool

- 40-TOPS NPU sounded great; reality killed it:
  - Largest LLM that runs: **2B params**
  - Context window: **2,048 tokens** (Claude Code needs ≥64k)
  - Tool-use shim **500s** on every `tools` payload
- **Lesson:** don't buy the impressive hardware — buy the matching *software stack*.
  The Pi is a great vision/Whisper box. It is not an agent backend.

---

## The Maral era: a 16GB Air did the real work

- qwen3:8b / :14b via Ollama's Anthropic-compatible endpoint — wired into Claude Code with one env block
- **Surprises:**
  - Tool-use was already at *parity* with cloud — the worry was misplaced
  - The real pain wasn't model quality, it was **memory bandwidth** (speed) and **WiFi-driver crashes** under load
- 16GB is the *floor* of viability, not a stable platform

---

## The single best tuning knob: kill the thinking tax

Qwen3 emits a `<think>` trace before every answer.
A coding answer needing **80 tokens** cost **600** — 8× the work.

```
CLAUDE_CODE_DISABLE_THINKING=1     # or {"think": false}
```

**~3× effective speedup for one env var.** Everything else (KV-cache quant,
context tuning, quant choice) was secondary to this.

---

## The reckoning: you cannot buy frontier parity

| Tier | Best model | SWE-bench | Gap to Opus 4.8 |
|---|---|---|---|
| 96GB Mac | qwen3-coder:30b | ~77% | −12 |
| 192GB | qwen3-235b Q4 | ~86% | −3 |
| **512GB ($11.5K)** | DeepSeek-V3 Q4 | **~88%** | **−4 (still short!)** |
| Cloud | **Opus 4.8** | **88.6%** | 0 |

> Open weights trail the closed frontier by 6–12 months.
> **The only thing that gives you Opus quality is Opus.**

---

## So the decision is about *how close*, not *parity*

- Don't chase a number that isn't for sale
- **Buy hardware for the 80%; keep an explicit `claude-cloud` for the 20%**
- Denominate the choice in your **actual task mix**, not dollars or principle

The honest sweet spot for one developer: **~$4–5K, one Mac Studio, 96GB.**

---

## The buy: $4,676 for a used M3 Ultra 96GB

- Apple-direct was **4 months backordered** (M3 Ultra was EOL'd)
- Every reseller went dry within days — only the grey market left
- Verified a sealed eBay unit (buyer protection, 99.3% seller); $4,299 + tax
- **Lesson:** a just-discontinued machine vanishes from every channel at once.
  Buy the current-gen config *before* the refresh rumor lands.

---

## The verdict: local ties cloud on coding

**Mini-bench (24 algorithmic problems, easy → LeetCode-hard, deterministic scoring):**

| Model | Score | Speed |
|---|---|---|
| **qwen3-coder:30b (local)** | **24 / 24** | **68 tok/s** |
| Opus 4.8 (cloud) | 24 / 24 | — |
| qwen3:32b dense | 16 / 18 | 20 tok/s (skip) |

**It tied Opus on every problem, at 4× the old box's speed.**

---

## What the tie means (precisely)

✅ **Local owns:** self-contained coding — functions, scripts, algorithms,
single-file and moderate multi-file work.

❌ **Cloud still wins:** open-ended, multi-file, sprawling-context repo work
(vague bug reports across large codebases — real SWE-bench).

> The gap is real but lives on a *different axis* than most benchmarks test.
> A bench your best model can't lose on has stopped measuring.

---

## Why the Studio is fast: bandwidth, not parameters

| Box | Memory bandwidth | coder-30b speed |
|---|---|---|
| MacBook Air M2 16GB | ~100 GB/s | 16 tok/s |
| **Mac Studio M3 Ultra 96GB** | **~800 GB/s** | **68 tok/s** |

- Same model, **4× faster — entirely the memory bus**
- **MoE beats dense** on a bandwidth-bound box: 3B-active MoE ran 3× faster
  than dense 32B *and* scored higher. Pay RAM for the weights, only active
  experts hit the bottleneck.

---

## Bonus: one box = a full local AI server

With `OLLAMA_MAX_LOADED_MODELS=3`, all resident simultaneously (~38GB, 50GB free):

- 🧑‍💻 **coder-30b** — the coding agent
- 👁 **qwen2.5-VL** — vision / OCR
- 🔎 **nomic-embed** — RAG embeddings

Plus **qwen3-next:80b** (80B, 64 tok/s — bigger brain for hard tasks, same speed).

---

## But the *agent loop* tells a harder truth

5 multi-file bug-fix tasks, measured through the **real Claude Code agent loop**,
local model vs cloud Opus:

| | pass | avg wall-clock | turns (range) |
|---|---|---|---|
| **Cloud (Opus)** | **5 / 5** | **31 s** | 5–9 (stable) |
| **Local (coder-30b)** | 4 / 5 | **248 s** | **4–41 (wild)** |

**Local averaged 8× slower — and a one-line `>`→`>=` fix took it 41 turns / 584 s.**

---

## It's not caching — it's *convergence*

The investigation disproved the obvious culprits:
- ✅ Ollama **does** prefix-cache (the big local token counts are CC's *accounting*,
  not the box re-computing)
- ❌ The real cost is **turn-count instability**: the 30B model fumbles in the loop,
  sometimes spiraling to 41 turns, sometimes giving up at 4

> Cloud converges in 5 turns *every time*. Local swings 4–41.
> The one-shot "68 tok/s, ties Opus" number was single-turn — it hid all of this.

---

## The honest reconciliation

| Workload | Local verdict |
|---|---|
| One-shot bounded coding | **Ties Opus** — fast, free |
| Multi-turn agent loops | **Works (4/5) but ~8× slower, unstable** |
| Open-ended multi-file repos | **Loses on capability too** |

Local is genuinely capable *and* the daily agent experience is far less reliable
than the raw speed implied. Both true. **Measure the agent loop, not just tok/s.**

---

## The economics

- **Cloud:** ~$200/mo → ~$2,400/yr, indefinitely
- **Local:** $4,676 once → **$0/mo** after
- **Breakeven: ~2 years**, then pure savings — *for the work local handles well*
- Privacy bonus: code never leaves the LAN

The catch: it's a **supplement**, not a full replacement. Hard repo work still
routes to cloud.

---

## Recommendation

**Hybrid, not either/or:**

- `claude`  → local Studio (the 80%: daily coding, free, private, fast)
- `claude-cloud` → Opus 4.8 (the 20%: hard cross-file repo work)

One toggle, per task. Denominated in your real workload.

**Single-dev sweet spot:** Mac Studio, **64–96GB**, MoE coder model, ~$4–5K.

---

## Honest caveats (the asterisk is load-bearing)

- "Local SOTA at home" is real in 2026 — **narrowly**, on bounded coding
- On open-ended engineering it is **not**, and no honest setup pretends otherwise
- 16GB is too small; >96GB is overkill for one person
- Benchmarks saturate — measure *your* task mix, not a leaderboard

---

## What's next (this is being measured)

1. **Cut my agents fully over to local**
2. **Measure local vs Opus 4.8** head-to-head on real tasks:
   - token usage · wall-clock latency · time-to-first-token · task success
3. Add **verification-loop scaffolding** (guardrails took an 8B from 53%→99% on
   agentic workflows) — the software lever, not a bigger model

---

# Thank you

**The win is real. The asterisk is load-bearing.**

Repo + full write-up (19 acts, 41 lessons): `github.com/jconnolly/local-llm-pi5`
Benchmarks: `benchmarks/minibench/` · `benchmarks/repobench/`
