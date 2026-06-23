"""agentbench — measure the real Claude Code agent experience: LOCAL vs Opus 4.8.

For each task: spin up a temp repo with buggy files + a visible test, then run the
*actual Claude Code agent loop* (`claude -p ... --output-format json`) against it —
once on the local Studio model, once on cloud Opus 4.8. The agent reads, edits, and
iterates until the test passes (or it gives up). We capture, per run:

  - success         did the hidden test end up passing
  - duration_ms     total wall-clock  ("time waiting")
  - ttft_ms         time to first token
  - num_turns       agent loop iterations
  - input/output    tokens (+ cache reads)
  - cost_usd        (cloud only; local is $0)

Then a side-by-side table with deltas. This is the agent experience, not raw model
capability — the tokens/latency/turns comparison you actually feel in daily use.

Tasks are the repobench hard set (multi-file, subtle bugs).

Usage:
    python run.py                 # all tasks, both backends
    python run.py --task ttl_off_by_one
    python run.py --backends local           # local only (skip cloud cost)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).parent
REPOBENCH = HERE.parent / "repobench"
sys.path.insert(0, str(REPOBENCH))
import importlib
TASKS = importlib.import_module("tasks_hard").TASKS

import os as _os
CLAUDE = "/Users/john.connolly/.local/bin/claude"
STUDIO = "studio.local:11434"
LOCAL_MODEL = _os.environ.get("AGENTBENCH_LOCAL_MODEL", "qwen3-coder:30b-a3b-q8_0")

# Backends: env overlay for the claude binary. Cloud = stored OAuth (strip overrides).
BACKENDS = {
    "local": {
        "ANTHROPIC_BASE_URL": f"http://{STUDIO}",
        "ANTHROPIC_AUTH_TOKEN": "ollama",
        "ANTHROPIC_API_KEY": "",
        "ANTHROPIC_MODEL": LOCAL_MODEL,
        "ANTHROPIC_SMALL_FAST_MODEL": LOCAL_MODEL,
        "CLAUDE_CODE_DISABLE_THINKING": "1",
    },
    "cloud": {"__strip__": ["ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN",
                            "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL", "ANTHROPIC_SMALL_FAST_MODEL"]},
}


def agent_prompt(task: dict) -> str:
    return (
        f"This repository has a bug. {task['prompt']}\n\n"
        "Edit the files in this directory to fix it. A test file `test_task.py` is "
        "present — run `python -m pytest -q test_task.py` and iterate until ALL tests "
        "pass. Do not edit the test file."
    )


def run_one(task: dict, backend: str) -> dict:
    import os
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        for rel, content in task["files"].items():
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
        (root / "test_task.py").write_text(task["test"])

        env = dict(os.environ)
        cfg = BACKENDS[backend]
        for k in cfg.get("__strip__", []):
            env.pop(k, None)
        for k, v in cfg.items():
            if k != "__strip__":
                env[k] = v
        env["CLAUDE_PROJECT_DIR"] = str(root)

        t0 = time.time()
        try:
            r = subprocess.run(
                [CLAUDE, "-p", agent_prompt(task), "--output-format", "json",
                 "--dangerously-skip-permissions"],
                cwd=root, env=env, capture_output=True, text=True, timeout=600,
            )
        except subprocess.TimeoutExpired:
            return {"backend": backend, "success": False, "note": "timeout(600s)",
                    "duration_ms": 600000}
        wall = (time.time() - t0) * 1000

        # parse the result event
        res = {}
        try:
            data = json.loads(r.stdout)
            res = (data[-1] if isinstance(data, list) else data) or {}
        except Exception:
            res = {}

        # score with the hidden test (same file; re-run to be sure of final state)
        try:
            tr = subprocess.run([sys.executable, "-m", "pytest", "-q", "test_task.py"],
                                cwd=root, capture_output=True, text=True, timeout=60)
            passed = tr.returncode == 0
        except subprocess.TimeoutExpired:
            passed = False

        u = res.get("usage", {}) or {}
        return {
            "backend": backend,
            "success": passed,
            "duration_ms": res.get("duration_ms", round(wall)),
            "ttft_ms": res.get("ttft_ms"),
            "num_turns": res.get("num_turns"),
            "in_tokens": u.get("input_tokens"),
            "out_tokens": u.get("output_tokens"),
            "cache_read": u.get("cache_read_input_tokens"),
            "cost_usd": res.get("total_cost_usd"),
            "is_error": res.get("is_error"),
        }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task")
    ap.add_argument("--backends", default="local,cloud")
    args = ap.parse_args()
    tasks = [t for t in TASKS if not args.task or t["id"] == args.task]
    backends = args.backends.split(",")

    rows = []
    for t in tasks:
        for b in backends:
            print(f"running {t['id']:<26} [{b}] ...", flush=True)
            row = run_one(t, b)
            row["task"] = t["id"]
            rows.append(row)
            sec = (row["duration_ms"] or 0) / 1000
            print(f"  {'PASS' if row['success'] else 'FAIL'}  {sec:6.1f}s  "
                  f"turns={row.get('num_turns')}  in={row.get('in_tokens')} "
                  f"out={row.get('out_tokens')}  ${row.get('cost_usd') or 0:.3f}")

    (HERE / "agentbench_results.json").write_text(json.dumps(rows, indent=2))

    # summary table
    print("\n=== SUMMARY: local vs cloud ===")
    print(f"{'task':<26}{'backend':<8}{'ok':<4}{'sec':>7}{'ttft':>7}{'turns':>6}{'in':>8}{'out':>7}{'$':>8}")
    for r in rows:
        print(f"{r['task']:<26}{r['backend']:<8}{('Y' if r['success'] else 'N'):<4}"
              f"{(r['duration_ms'] or 0)/1000:>7.1f}{(r.get('ttft_ms') or 0)/1000:>7.1f}"
              f"{str(r.get('num_turns') or '-'):>6}{str(r.get('in_tokens') or '-'):>8}"
              f"{str(r.get('out_tokens') or '-'):>7}{r.get('cost_usd') or 0:>8.3f}")

    for b in backends:
        br = [r for r in rows if r["backend"] == b]
        if not br:
            continue
        npass = sum(1 for r in br if r["success"])
        avg_s = sum((r["duration_ms"] or 0) for r in br) / len(br) / 1000
        tot_out = sum((r.get("out_tokens") or 0) for r in br)
        tot_cost = sum((r.get("cost_usd") or 0) for r in br)
        print(f"\n{b:8} pass {npass}/{len(br)}  avg {avg_s:.1f}s/task  "
              f"out_tokens {tot_out}  cost ${tot_cost:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
