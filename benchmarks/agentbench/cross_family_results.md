# Agentbench: cross-family agent-loop results (2026-06-23)

Same harness (`run.py`), same 5 hard multi-file bug-fix tasks (`tasks_hard`), same box
(Mac Studio M3 Ultra 96GB), `CLAUDE_CODE_DISABLE_THINKING=1`. Local backends only (cloud
row is the prior Opus 4.8 baseline). Model selected via `AGENTBENCH_LOCAL_MODEL=...`.

Motivation: the Boykis post + HN thread (news.ycombinator.com/item?id=48555993) flagged
that our `qwen3-coder:30b` was a stale model and that the agent-loop instability might be
a model artifact, not a property of local inference. This re-bench tests that.

| model | quant | pass | turns (range) | avg wall-clock | vs cloud |
|---|---|---|---|---|---|
| qwen3-coder:30b-a3b *(original deck baseline)* | q8 | 4/5 | 4–41 (wild) | 248 s | ~8× |
| qwen3.6:27b-mtp | q8 | 5/5 | 7–9 (stable) | 161 s | ~5× |
| **gpt-oss:20b** | mxfp4 | **5/5** | **7–9 (stable)** | **48.5 s** | **~1.5×** |
| gemma4:26b | (default) | 5/5 | 8–20 | 68.6 s | ~2× |
| Opus 4.8 (cloud baseline) | — | 5/5 | 5–9 (stable) | 31 s | 1× |

## Findings

1. **The instability was a stale-model artifact.** Every current model is 5/5 and stable
   (no 4→41 turn spiral). The `ttl_off_by_one` task that took coder-30b 41 turns / 584 s
   took 7–8 turns on every current model.
2. **gpt-oss:20b is the standout** — 5/5, tight 7–9 turns, 48 s avg (~1.5× cloud's 31 s),
   on a *20B* model. Most of the speed gap was also the model, not the hardware.
3. **gemma4:26b** passes 5/5 but is slightly wobblier (one 20-turn task) — mildly less
   stable than gpt-oss / Qwen 3.6 on agentic tool-use, consistent with HN reports.
4. coder-30b vs qwen3.6 are both q8 → the fix was the **model**, not the quant. The quant
   angle (q4 vs q6 on the 80B) is still untested and separate.

Per-task raw numbers in `/tmp/agentbench_{qwen36,gptoss,gemma4}.log` at run time
(agentbench_results.json is overwritten per run; this table is the durable record).
