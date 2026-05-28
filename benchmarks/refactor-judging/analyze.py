"""analyze.py — read judge_runs.json, compute robust stats, render summary.

Outputs:
  - judge_analysis.json  (machine-readable)
  - judge_analysis.md    (human writeup with charts)
  - judge_chart.png      (matplotlib bar chart)
"""
from __future__ import annotations

import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

import matplotlib

matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt

HERE = Path(__file__).parent
runs = json.loads((HERE / "judge_runs.json").read_text())


def wilson_ci(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score 95% confidence interval for a binomial proportion."""
    if n == 0:
        return (0.0, 0.0)
    p = wins / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    radius = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, centre - radius), min(1.0, centre + radius))


def cohens_kappa(rater_a: list[str], rater_b: list[str]) -> float:
    """Cohen's kappa for two raters on the same items. -1..1 (1 = perfect agreement)."""
    assert len(rater_a) == len(rater_b)
    n = len(rater_a)
    if n == 0:
        return 0.0
    categories = set(rater_a) | set(rater_b)
    po = sum(1 for a, b in zip(rater_a, rater_b) if a == b) / n
    pe = sum(
        (rater_a.count(c) / n) * (rater_b.count(c) / n) for c in categories
    )
    return (po - pe) / (1 - pe) if pe != 1 else 1.0


# --- Per-source totals ---
total_votes = len(runs)
parsed = [r for r in runs if r["winner_source"] != "UNPARSED"]
unparsed_n = total_votes - len(parsed)

source_counts = Counter(r["winner_source"] for r in parsed)
cloud_wins = source_counts.get("CLOUD", 0)
local_wins = source_counts.get("LOCAL", 0)
ties = source_counts.get("TIE", 0)
decisive = cloud_wins + local_wins  # exclude ties for win-rate
cloud_rate = cloud_wins / decisive if decisive else 0.0
local_rate = local_wins / decisive if decisive else 0.0
cloud_ci = wilson_ci(cloud_wins, decisive)
local_ci = wilson_ci(local_wins, decisive)

# --- Per-judge breakdown ---
per_judge: dict[str, dict] = {}
for judge in sorted({r["judge"] for r in parsed}):
    j_rows = [r for r in parsed if r["judge"] == judge]
    jc = Counter(r["winner_source"] for r in j_rows)
    j_decisive = jc.get("CLOUD", 0) + jc.get("LOCAL", 0)
    per_judge[judge] = {
        "votes": len(j_rows),
        "cloud_wins": jc.get("CLOUD", 0),
        "local_wins": jc.get("LOCAL", 0),
        "ties": jc.get("TIE", 0),
        "cloud_rate": jc.get("CLOUD", 0) / j_decisive if j_decisive else 0.0,
        "cloud_ci": wilson_ci(jc.get("CLOUD", 0), j_decisive),
    }

# --- Position bias check ---
# Within each ordering, what fraction of votes went to "position 1"?
# If unbiased we'd see ~50%. Skew indicates bias.
position_bias: dict[str, dict] = {}
for ordering in ("CLOUD_FIRST", "LOCAL_FIRST"):
    o_rows = [r for r in parsed if r["ordering"] == ordering]
    pos1 = sum(1 for r in o_rows if r["winner_label"] == "1")
    pos2 = sum(1 for r in o_rows if r["winner_label"] == "2")
    n = pos1 + pos2  # exclude ties
    position_bias[ordering] = {
        "n": n,
        "pos1_wins": pos1,
        "pos2_wins": pos2,
        "pos1_rate": pos1 / n if n else 0.0,
        "pos1_ci": wilson_ci(pos1, n),
    }

# Combined position bias across orderings
total_pos1 = sum(b["pos1_wins"] for b in position_bias.values())
total_pos_n = sum(b["n"] for b in position_bias.values())
combined_pos_bias = {
    "n": total_pos_n,
    "pos1_rate": total_pos1 / total_pos_n if total_pos_n else 0.0,
    "pos1_ci": wilson_ci(total_pos1, total_pos_n),
}

# --- Inter-judge agreement ---
judges = sorted({r["judge"] for r in parsed})
if len(judges) >= 2:
    j1, j2 = judges[0], judges[1]
    # Pair votes by (ordering, round) — both judges saw same comparison
    by_key_j1 = {(r["ordering"], r["round"]): r["winner_source"] for r in parsed if r["judge"] == j1}
    by_key_j2 = {(r["ordering"], r["round"]): r["winner_source"] for r in parsed if r["judge"] == j2}
    common_keys = sorted(set(by_key_j1) & set(by_key_j2))
    rater_a = [by_key_j1[k] for k in common_keys]
    rater_b = [by_key_j2[k] for k in common_keys]
    kappa = cohens_kappa(rater_a, rater_b)
    agreement = sum(1 for a, b in zip(rater_a, rater_b) if a == b) / len(rater_a) if rater_a else 0.0
    inter_judge = {"judges": [j1, j2], "kappa": kappa, "raw_agreement": agreement, "n": len(rater_a)}
else:
    inter_judge = {"note": "fewer than 2 judges, can't compute kappa"}

# --- Latency ---
mean_latency = mean(r["wall_s"] for r in runs) if runs else 0.0

# --- Aggregate ---
analysis = {
    "total_votes": total_votes,
    "unparsed": unparsed_n,
    "decisive_votes": decisive,
    "cloud_wins": cloud_wins,
    "local_wins": local_wins,
    "ties": ties,
    "cloud_win_rate": cloud_rate,
    "cloud_win_ci_95": cloud_ci,
    "local_win_rate": local_rate,
    "local_win_ci_95": local_ci,
    "per_judge": per_judge,
    "position_bias_by_ordering": position_bias,
    "combined_position_bias": combined_pos_bias,
    "inter_judge_agreement": inter_judge,
    "mean_judge_latency_s": mean_latency,
}
(HERE / "judge_analysis.json").write_text(json.dumps(analysis, indent=2))

# --- Render PNG chart ---
fig, axes = plt.subplots(1, 3, figsize=(15, 5))

# Chart 1: win counts
ax = axes[0]
labels = ["Cloud (Opus 4.7)", "Local (qwen3:14b)", "Tie"]
values = [cloud_wins, local_wins, ties]
colors = ["#4c8eda", "#e58f4c", "#888"]
bars = ax.bar(labels, values, color=colors)
ax.set_title(f"Refactor judging — total votes (n={total_votes})", fontsize=12)
ax.set_ylabel("Wins")
for bar, v in zip(bars, values):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.1, str(v), ha="center")
ax.set_ylim(0, max(values) + 3 if values else 5)

# Chart 2: win rate with Wilson CI
ax = axes[1]
y = [cloud_rate, local_rate]
yerr_low = [cloud_rate - cloud_ci[0], local_rate - local_ci[0]]
yerr_high = [cloud_ci[1] - cloud_rate, local_ci[1] - local_rate]
xs = ["Cloud", "Local"]
ax.bar(xs, y, color=["#4c8eda", "#e58f4c"], yerr=[yerr_low, yerr_high], capsize=10)
ax.set_title("Win rate (excl. ties) ±95% Wilson CI", fontsize=12)
ax.set_ylabel("Win rate")
ax.set_ylim(0, 1.0)
ax.axhline(0.5, color="grey", linestyle="--", linewidth=0.7)
for i, (rate, ci) in enumerate(zip(y, [cloud_ci, local_ci])):
    ax.text(i, rate + 0.05, f"{rate:.0%}\n[{ci[0]:.0%}, {ci[1]:.0%}]", ha="center", fontsize=9)

# Chart 3: per-judge
ax = axes[2]
judge_names = list(per_judge.keys())
cloud_per = [per_judge[j]["cloud_wins"] for j in judge_names]
local_per = [per_judge[j]["local_wins"] for j in judge_names]
ties_per = [per_judge[j]["ties"] for j in judge_names]
x = range(len(judge_names))
width = 0.25
ax.bar([i - width for i in x], cloud_per, width, label="Cloud", color="#4c8eda")
ax.bar([i for i in x], local_per, width, label="Local", color="#e58f4c")
ax.bar([i + width for i in x], ties_per, width, label="Tie", color="#888")
ax.set_xticks(list(x))
ax.set_xticklabels(judge_names)
ax.set_title("Wins per judge", fontsize=12)
ax.set_ylabel("Wins")
ax.legend()

plt.tight_layout()
plt.savefig(HERE / "judge_chart.png", dpi=150)
print(f"Wrote judge_chart.png")

# --- Render markdown writeup ---
md = []
md.append("# Refactor judging analysis\n")
md.append(f"Task: refactor `mcp-servers/maral-vision/server.py` (158 lines).")
md.append(f"Contestants: **CLOUD** = Claude Opus 4.7, **LOCAL** = Maral qwen3:14b.")
md.append(f"Judges: {', '.join(judges)} (Maral-hosted, different from contestants).")
md.append(f"Protocol: each judge sees the original + two refactorings (anonymized as 'Refactoring 1' and '2'), votes one as winner. Position swapped each round to control for position bias. {ROUNDS_PER_ORDERING := 5} rounds × 2 orderings × {len(judges)} judges = {total_votes} total votes.\n")

md.append("## Headline\n")
md.append(f"| Source | Wins | Win rate (decisive) | 95% Wilson CI |")
md.append(f"|---|---|---|---|")
md.append(f"| Cloud (Opus 4.7)  | {cloud_wins} | {cloud_rate:.1%} | [{cloud_ci[0]:.1%}, {cloud_ci[1]:.1%}] |")
md.append(f"| Local (qwen3:14b) | {local_wins} | {local_rate:.1%} | [{local_ci[0]:.1%}, {local_ci[1]:.1%}] |")
md.append(f"| Tie               | {ties}        | —                  | — |")
md.append(f"| Unparsed          | {unparsed_n}  | —                  | — |\n")

md.append("## Per-judge breakdown\n")
md.append("| Judge | Cloud wins | Local wins | Tie | Cloud rate | Cloud 95% CI |")
md.append("|---|---|---|---|---|---|")
for jname, d in per_judge.items():
    md.append(f"| {jname} | {d['cloud_wins']} | {d['local_wins']} | {d['ties']} | {d['cloud_rate']:.0%} | [{d['cloud_ci'][0]:.0%}, {d['cloud_ci'][1]:.0%}] |")
md.append("")

md.append("## Position bias check\n")
md.append("If judges are unbiased, position-1 win rate should be ~50% within each ordering.")
md.append("Strong skew = judge prefers position 1 (or 2) regardless of content.\n")
md.append("| Ordering | n | Position-1 wins | Pos-1 rate | 95% CI |")
md.append("|---|---|---|---|---|")
for ord_name, d in position_bias.items():
    md.append(f"| {ord_name} | {d['n']} | {d['pos1_wins']} | {d['pos1_rate']:.0%} | [{d['pos1_ci'][0]:.0%}, {d['pos1_ci'][1]:.0%}] |")
md.append(f"| **Combined** | **{combined_pos_bias['n']}** | **{total_pos1}** | **{combined_pos_bias['pos1_rate']:.0%}** | **[{combined_pos_bias['pos1_ci'][0]:.0%}, {combined_pos_bias['pos1_ci'][1]:.0%}]** |")
md.append("")

md.append("## Inter-judge agreement\n")
if "kappa" in inter_judge:
    md.append(f"Cohen's κ between {inter_judge['judges'][0]} and {inter_judge['judges'][1]} on {inter_judge['n']} paired comparisons: **κ = {inter_judge['kappa']:.3f}** (raw agreement {inter_judge['raw_agreement']:.0%}).\n")
    md.append("κ interpretation: <0 = worse than chance, 0–0.20 = slight, 0.21–0.40 = fair, 0.41–0.60 = moderate, 0.61–0.80 = substantial, 0.81–1.00 = almost perfect.")
else:
    md.append(inter_judge.get("note", ""))
md.append("")

md.append("## Latency\n")
md.append(f"Mean judge call wall time: **{mean_latency:.1f}s** per round.\n")

md.append("## Chart\n")
md.append("![Judge chart](judge_chart.png)\n")

md.append("## Method notes / threats to validity\n")
md.append("- Judges run on the same Maral box as the local contestant. Not on cloud. (No \"true\" external judge.)")
md.append("- qwen3:8b and qwen3:4b are smaller than the local contestant (qwen3:14b), so they may be biased toward simpler / shorter refactorings.")
md.append("- Single refactoring task, single source file. Generalization to other tasks is not implied.")
md.append("- Judge prompt asks for free-form score then a `WINNER:` directive. Free-form portion can drift; we only parse the final directive.")
md.append("- Position-swap is applied but only 2 orderings. A full Latin-square would scale combinatorially.")
md.append("- Temperature 0.3 on judge — some run-to-run variance is expected even with same inputs.")
md.append("")

(HERE / "judge_analysis.md").write_text("\n".join(md))
print(f"Wrote judge_analysis.md ({sum(len(l) for l in md)} chars)")
print(f"Wrote judge_analysis.json")
