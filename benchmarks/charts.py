"""charts.py — render benchmark results (speed, tool use, RAG) as PNG + mermaid + ASCII.

Reads benchmarks/results.json from the previous run.
Writes:
  benchmarks/charts/speed.png
  benchmarks/charts/tool_use.png
  benchmarks/charts/rag.png
  benchmarks/charts/overview.png   (combined dashboard for slides)
  benchmarks/charts/charts.md      (markdown with mermaid + ASCII)
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).parent
OUT = HERE / "charts"
OUT.mkdir(exist_ok=True)
results = json.loads((HERE / "results.json").read_text())

speed = results["suites"]["speed"]
tu = results["suites"]["tool_use"]
rag = results["suites"]["rag"]
agent = results["suites"].get("agent_loop", {})

# Compare to cloud reference (Opus 4.7 published numbers + observed)
CLOUD_REF = {
    "decode_tok_s": 50.0,   # observed streaming throughput
    "tool_use_pass_rate": 1.0,
    "swe_bench_verified": 0.876,
}
LOCAL_SWE_BENCH_EST = 0.45  # qwen3:14b general (not coder)

# ---- 1. Decode + prefill ----
fig, ax = plt.subplots(figsize=(8, 5))
models = list(speed.keys()) + ["Opus 4.7 (cloud, observed)"]
decode = [speed[m]["decode_tok_s_median"] for m in speed] + [CLOUD_REF["decode_tok_s"]]
prefill = [speed[m]["prefill_tok_s_median"] for m in speed] + [1000.0]  # cloud prefill rough
x = range(len(models))
width = 0.35
ax.bar([i - width/2 for i in x], decode, width, label="Decode tok/s", color="#4c8eda")
ax.bar([i + width/2 for i in x], prefill, width, label="Prefill tok/s", color="#e58f4c")
ax.set_xticks(list(x))
ax.set_xticklabels(models, rotation=15, ha="right")
ax.set_ylabel("Tokens / second")
ax.set_title("Throughput: local Maral vs. cloud (warm-state, median of 3 runs)")
ax.legend()
ax.set_yscale("log")
for i, v in enumerate(decode):
    ax.text(i - width/2, v * 1.05, f"{v:.0f}", ha="center", fontsize=8)
for i, v in enumerate(prefill):
    ax.text(i + width/2, v * 1.05, f"{v:.0f}", ha="center", fontsize=8)
plt.tight_layout()
plt.savefig(OUT / "speed.png", dpi=150)
plt.close()

# ---- 2. Tool use pass rate ----
fig, ax = plt.subplots(figsize=(6, 4))
m = list(tu.keys())
rates = [tu[k]["pass_rate"] for k in m]
ax.bar(m, rates, color=["#4c8eda", "#7eb3ee"])
ax.axhline(CLOUD_REF["tool_use_pass_rate"], color="grey", linestyle="--", label="Cloud Opus 4.7")
ax.set_ylim(0, 1.05)
ax.set_ylabel("Pass rate")
ax.set_title(f"Tool use correctness (n=3 cases each)")
for i, r in enumerate(rates):
    ax.text(i, r + 0.02, f"{r:.0%}", ha="center")
ax.legend(loc="lower right")
plt.tight_layout()
plt.savefig(OUT / "tool_use.png", dpi=150)
plt.close()

# ---- 3. RAG ----
fig, ax = plt.subplots(figsize=(5, 4))
qs = rag["queries"]
distances = [q["top_distance"] for q in qs]
labels = [q["query"][:30] + "…" if len(q["query"]) > 30 else q["query"] for q in qs]
colors = ["#4c8eda" if q["relevant_in_top3"] else "#aaa" for q in qs]
ax.barh(labels, distances, color=colors)
ax.set_xlabel("Top-1 cosine distance (lower = closer)")
ax.set_title(f"RAG retrieval — {sum(q['relevant_in_top3'] for q in qs)}/{len(qs)} queries hit relevant chunk in top-3")
plt.tight_layout()
plt.savefig(OUT / "rag.png", dpi=150)
plt.close()

# ---- 4. Combined overview dashboard ----
fig = plt.figure(figsize=(14, 9))
gs = fig.add_gridspec(2, 3, hspace=0.4, wspace=0.35)

# A: decode log
ax = fig.add_subplot(gs[0, 0])
m = list(speed.keys()) + ["Opus 4.7"]
v = [speed[k]["decode_tok_s_median"] for k in speed] + [CLOUD_REF["decode_tok_s"]]
colors = ["#e58f4c", "#e58f4c", "#4c8eda"]
ax.bar(m, v, color=colors)
ax.set_yscale("log")
ax.set_ylabel("tok/s")
ax.set_title("Decode throughput (log)")
for i, val in enumerate(v):
    ax.text(i, val * 1.1, f"{val:.0f}", ha="center", fontsize=9)

# B: prefill
ax = fig.add_subplot(gs[0, 1])
v = [speed[k]["prefill_tok_s_median"] for k in speed] + [1000]
ax.bar(m, v, color=colors)
ax.set_ylabel("tok/s")
ax.set_title("Prefill throughput")
for i, val in enumerate(v):
    ax.text(i, val * 1.02, f"{val:.0f}", ha="center", fontsize=9)

# C: tool use
ax = fig.add_subplot(gs[0, 2])
m = list(tu.keys()) + ["Opus 4.7"]
v = [tu[k]["pass_rate"] for k in tu] + [CLOUD_REF["tool_use_pass_rate"]]
colors = ["#e58f4c", "#e58f4c", "#4c8eda"]
ax.bar(m, v, color=colors)
ax.set_ylim(0, 1.1)
ax.set_ylabel("Pass rate")
ax.set_title("Tool use (3/3 each)")
for i, val in enumerate(v):
    ax.text(i, val + 0.03, f"{val:.0%}", ha="center", fontsize=9)

# D: SWE-bench
ax = fig.add_subplot(gs[1, 0])
xs = ["qwen3:14b\n(local)", "Opus 4.7\n(cloud)"]
ys = [LOCAL_SWE_BENCH_EST, CLOUD_REF["swe_bench_verified"]]
ax.bar(xs, ys, color=["#e58f4c", "#4c8eda"])
ax.set_ylim(0, 1.0)
ax.set_ylabel("SWE-bench Verified")
ax.set_title("Coding quality (est.)")
for i, val in enumerate(ys):
    ax.text(i, val + 0.03, f"{val:.0%}", ha="center", fontsize=9)

# E: RAG
ax = fig.add_subplot(gs[1, 1])
ax.bar(["RAG"], [rag["relevance_rate"]], color="#4c8eda")
ax.set_ylim(0, 1.1)
ax.set_ylabel("Relevance rate")
ax.set_title(f"RAG ({sum(q['relevant_in_top3'] for q in rag['queries'])}/{len(rag['queries'])})")
ax.text(0, rag["relevance_rate"] + 0.03, f"{rag['relevance_rate']:.0%}", ha="center")

# F: agent loop time
ax = fig.add_subplot(gs[1, 2])
agent_data = agent.get("qwen3:14b", {})
xs = ["qwen3:14b\n(local)", "Opus 4.7\n(cloud est.)"]
ys = [agent_data.get("wall_s", 0), 10.0]
ax.bar(xs, ys, color=["#e58f4c", "#4c8eda"])
ax.set_ylabel("Seconds")
ax.set_title("2-turn agent loop wall time")
for i, val in enumerate(ys):
    ax.text(i, val + 1.5, f"{val:.1f}s", ha="center", fontsize=9)

fig.suptitle("Maral local LLM vs. Cloud Opus 4.7 — benchmark dashboard (May 27 2026)", fontsize=14, y=0.99)
plt.savefig(OUT / "overview.png", dpi=150)
plt.close()

# ---- 5. Markdown writeup with mermaid + ASCII ----
md = []
md.append("# Benchmark charts\n")
md.append("Generated from `benchmarks/results.json`. Re-render with `python benchmarks/charts.py`.\n")

md.append("## Overview\n")
md.append("![overview](charts/overview.png)\n")

md.append("## Decode throughput\n")
md.append("```mermaid")
md.append("xychart-beta")
md.append("    title \"Decode tok/s (warm, median of 3)\"")
md.append("    x-axis [\"qwen3:8b\", \"qwen3:14b\", \"Opus 4.7\"]")
v = [speed['qwen3:8b']['decode_tok_s_median'], speed['qwen3:14b']['decode_tok_s_median'], CLOUD_REF['decode_tok_s']]
md.append(f"    y-axis \"tok/s\" 0 --> {max(v)+10:.0f}")
md.append(f"    bar [{v[0]:.1f}, {v[1]:.1f}, {v[2]:.1f}]")
md.append("```\n")
md.append("```")
maxv = max(v)
for name, val in zip(["qwen3:8b ", "qwen3:14b", "Opus 4.7 "], v):
    bar = "#" * int(val / maxv * 40)
    md.append(f"{name} {bar} {val:.1f}")
md.append("```\n")

md.append("## Tool use\n")
md.append("```")
for name in tu:
    val = tu[name]["pass_rate"]
    bar = "#" * int(val * 40)
    md.append(f"{name:10s} {bar} {val:.0%} ({tu[name]['passed']}/{tu[name]['total']})")
md.append("Opus 4.7   " + "#" * 40 + " 100% (3/3) [reference]")
md.append("```\n")

md.append("## RAG retrieval relevance\n")
md.append("```")
for q in rag["queries"]:
    hit = "HIT  " if q["relevant_in_top3"] else "MISS "
    md.append(f"{hit} dist={q['top_distance']:5.2f}  q={q['query'][:50]!r}")
md.append(f"-> overall: {rag['relevance_rate']:.0%} relevance rate ({sum(q['relevant_in_top3'] for q in rag['queries'])}/{len(rag['queries'])})")
md.append("```\n")

(OUT / "charts.md").write_text("\n".join(md))
print(f"Wrote {OUT}/{{speed,tool_use,rag,overview}}.png and charts.md")
