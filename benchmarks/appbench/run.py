"""appbench — long-horizon app-build benchmark through the REAL Claude Code agent loop.

For each task (e.g. "build playable Space Invaders as index.html"), run the actual
`claude -p` agent loop once per backend, then score the produced artifact with a
Playwright functional rubric (score.py). Captures the agent metrics you feel in daily
use (wall-clock, turns, tokens, cost) AND whether the thing actually works.

Artifacts (the playable index.html + screenshots) land in viz/appbench/<backend>/<task>/
so they drop straight into the slide deck.

Usage:
    python run.py --backends local                 # local only (free; the interesting one)
    python run.py --backends local,cloud           # head-to-head (cloud costs $)
    python run.py --backends next80                # the 80B (does bigger converge better?)
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))
from spec import TASKS  # noqa: E402
from score import score  # noqa: E402

CLAUDE = "/Users/john.connolly/.local/bin/claude"
STUDIO = "studio.local:11434"
VIZ = REPO / "viz" / "appbench"

LOCAL_OVERLAY = {
    "ANTHROPIC_BASE_URL": f"http://{STUDIO}",
    "ANTHROPIC_AUTH_TOKEN": "ollama",
    "ANTHROPIC_API_KEY": "",
    "CLAUDE_CODE_DISABLE_THINKING": "1",
}
BACKENDS = {
    "local": {**LOCAL_OVERLAY,
              "ANTHROPIC_MODEL": "qwen3-coder:30b-a3b-q8_0",
              "ANTHROPIC_SMALL_FAST_MODEL": "qwen3-coder:30b-a3b-q8_0"},
    "next80": {**LOCAL_OVERLAY,
               "ANTHROPIC_MODEL": "qwen3-next:80b-a3b-instruct-q4_K_M",
               "ANTHROPIC_SMALL_FAST_MODEL": "qwen3-next:80b-a3b-instruct-q4_K_M"},
    "cloud": {"__strip__": ["ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY",
                            "ANTHROPIC_MODEL", "ANTHROPIC_SMALL_FAST_MODEL"]},
}

TIMEOUT = 1500  # 25 min — a long build; local may grind


def agent_prompt(task: dict) -> str:
    return (
        task["prompt"]
        + "\n\nWork in the current directory. When you believe the game is complete and "
        "correct, stop."
    )


def run_one(task: dict, backend: str) -> dict:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        env = dict(os.environ)
        cfg = BACKENDS[backend]
        for k in cfg.get("__strip__", []):
            env.pop(k, None)
        for k, v in cfg.items():
            if k != "__strip__":
                env[k] = v
        env["CLAUDE_PROJECT_DIR"] = str(root)

        print(f"  [{backend}] agent building '{task['id']}' (timeout {TIMEOUT}s) ...", flush=True)
        t0 = time.time()
        try:
            r = subprocess.run(
                [CLAUDE, "-p", agent_prompt(task), "--output-format", "json",
                 "--dangerously-skip-permissions"],
                cwd=root, env=env, capture_output=True, text=True, timeout=TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return {"backend": backend, "task": task["id"], "success": False,
                    "note": f"timeout({TIMEOUT}s)", "duration_ms": TIMEOUT * 1000, "score": 0, "max": 7}
        wall = (time.time() - t0) * 1000

        res = {}
        try:
            data = json.loads(r.stdout)
            res = (data[-1] if isinstance(data, list) else data) or {}
        except Exception:
            res = {}

        # locate artifact
        art = root / task["artifact"]
        if not art.exists():
            htmls = list(root.rglob("*.html"))
            art = htmls[0] if htmls else None

        out_dir = VIZ / backend / task["id"]
        sc = {"score": 0, "max": 7, "checks": {}, "notes": {}}
        if art and art.exists():
            out_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy(art, out_dir / "index.html")
            try:
                sc = score(out_dir / "index.html", out_dir)
            except Exception as e:
                sc["notes"] = {"score_error": str(e)[:200]}

        u = res.get("usage", {}) or {}
        row = {
            "backend": backend, "task": task["id"],
            "built": bool(art and art.exists()),
            "score": sc["score"], "max": sc["max"], "checks": sc.get("checks", {}),
            "check_notes": sc.get("notes", {}),
            "duration_ms": res.get("duration_ms", round(wall)),
            "num_turns": res.get("num_turns"),
            "in_tokens": u.get("input_tokens"), "out_tokens": u.get("output_tokens"),
            "cost_usd": res.get("total_cost_usd"),
            "artifact_dir": str(out_dir),
        }
        sec = (row["duration_ms"] or 0) / 1000
        print(f"  [{backend}] {'BUILT' if row['built'] else 'NO ARTIFACT'}  "
              f"score {row['score']}/{row['max']}  {sec:.0f}s  turns={row['num_turns']}  "
              f"out={row['out_tokens']}  ${row.get('cost_usd') or 0:.2f}", flush=True)
        return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backends", default="local")
    ap.add_argument("--task")
    args = ap.parse_args()
    tasks = [t for t in TASKS if not args.task or t["id"] == args.task]
    backends = args.backends.split(",")

    rows = []
    for t in tasks:
        for b in backends:
            rows.append(run_one(t, b))

    (HERE / "appbench_results.json").write_text(json.dumps(rows, indent=2))

    print("\n=== APPBENCH SUMMARY ===")
    print(f"{'task':<16}{'backend':<8}{'built':<7}{'score':<7}{'sec':>7}{'turns':>7}{'out':>8}{'$':>8}")
    for r in rows:
        print(f"{r['task']:<16}{r['backend']:<8}{('Y' if r['built'] else 'N'):<7}"
              f"{str(r['score'])+'/'+str(r['max']):<7}{(r['duration_ms'] or 0)/1000:>7.0f}"
              f"{str(r.get('num_turns') or '-'):>7}{str(r.get('out_tokens') or '-'):>8}"
              f"{r.get('cost_usd') or 0:>8.2f}")
    print(f"\nartifacts + screenshots: {VIZ}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
