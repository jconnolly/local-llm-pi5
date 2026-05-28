"""render_charts.py — metrics dashboard + ASCII for Act 13."""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).parent
m = json.loads((HERE / "metrics.json").read_text())

labels = ["Input", "Cloud (Opus 4.7)", "Local (qwen3:14b)"]
keys = ["input", "cloud", "local"]
colors = ["#888", "#4c8eda", "#e58f4c"]

fig, axes = plt.subplots(2, 3, figsize=(14, 8))

# A. SLOC
ax = axes[0, 0]
vals = [m[k]["sloc"] for k in keys]
ax.bar(labels, vals, color=colors)
ax.set_title("SLOC (source lines)")
for i, v in enumerate(vals):
    ax.text(i, v + 1, str(v), ha="center")

# B. Function count
ax = axes[0, 1]
vals = [m[k]["func_count"] for k in keys]
ax.bar(labels, vals, color=colors)
ax.set_title("Function count")
for i, v in enumerate(vals):
    ax.text(i, v + 0.1, str(v), ha="center")

# C. Docstring coverage
ax = axes[0, 2]
vals = [m[k]["docstring_coverage"] for k in keys]
ax.bar(labels, vals, color=colors)
ax.set_ylim(0, 1.1)
ax.set_title("Docstring coverage")
for i, v in enumerate(vals):
    ax.text(i, v + 0.02, f"{v:.0%}", ha="center")

# D. Complexity mean
ax = axes[1, 0]
vals = [m[k]["complexity_mean"] for k in keys]
ax.bar(labels, vals, color=colors)
ax.set_title("Cyclomatic-proxy mean per fn")
for i, v in enumerate(vals):
    ax.text(i, v + 0.05, f"{v:.2f}", ha="center")

# E. Complexity max
ax = axes[1, 1]
vals = [m[k]["complexity_max"] for k in keys]
ax.bar(labels, vals, color=colors)
ax.set_title("Cyclomatic-proxy max per fn")
for i, v in enumerate(vals):
    ax.text(i, v + 0.1, str(v), ha="center")

# F. New helpers extracted
ax = axes[1, 2]
xs = ["Cloud", "Local"]
vals = [len(m["cloud"]["new_helpers"]), len(m["local"]["new_helpers"])]
ax.bar(xs, vals, color=["#4c8eda", "#e58f4c"])
ax.set_title("New helper functions extracted")
for i, v in enumerate(vals):
    ax.text(i, v + 0.1, str(v), ha="center")

fig.suptitle("Refactor comparison — deterministic metrics", fontsize=14)
plt.tight_layout()
plt.savefig(HERE / "metrics_chart.png", dpi=150)
print("Wrote metrics_chart.png")
