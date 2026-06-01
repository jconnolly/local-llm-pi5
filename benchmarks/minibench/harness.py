"""Mini-bench harness — run a model over PROBLEMS, score by executing code.

Local model: hit Maral Ollama /api/chat with think:false.
Cloud baseline (Opus 4.8): solutions are provided as a JSON file (solved inline
by the Opus session) and scored by the identical test runner — fair head-to-head.

Usage:
    python harness.py local                 # run qwen3:8b on Maral, score, write local.json
    python harness.py score-file FILE.json   # score a {id: code} solutions file (cloud)

Scoring: each problem's code is exec'd in an isolated namespace; tests run with a
per-test timeout via signal alarm. A problem passes only if ALL its tests pass.
Score = problems_fully_passed / total_problems (SWE-bench-style: all-or-nothing).
"""
from __future__ import annotations

import json
import re
import signal
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from problems import PROBLEMS  # noqa: E402

HOST = "http://maral.local:11434/api/chat"
MODEL = "qwen3:8b"


class Timeout(Exception):
    pass


def _alarm(signum, frame):
    raise Timeout()


def run_with_timeout(fn, args, seconds=5):
    signal.signal(signal.SIGALRM, _alarm)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        return fn(*args)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


def extract_code(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    m = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.S)
    return m.group(1) if m else text


def score_problem(prob: dict, code: str) -> tuple[bool, str]:
    """Return (passed_all, note)."""
    ns: dict = {}
    try:
        exec(code, ns)
    except Exception as e:
        return False, f"exec-error: {str(e)[:60]}"

    # Special case: LRUCache stateful test
    if prob["entrypoint"] == "__LRUCACHE__":
        cls = ns.get("LRUCache")
        if not cls:
            return False, "no LRUCache class"
        try:
            c = cls(2)
            c.put(1, 1); c.put(2, 2)
            r1 = c.get(1)            # 1
            c.put(3, 3)              # evicts 2
            r2 = c.get(2)            # -1
            c.put(4, 4)              # evicts 1
            r3 = c.get(1)            # -1
            r4 = c.get(3)            # 3
            r5 = c.get(4)            # 4
            ok = [r1, r2, r3, r4, r5] == [1, -1, -1, 3, 4]
            return ok, "ok" if ok else f"got {[r1,r2,r3,r4,r5]}"
        except Exception as e:
            return False, f"runtime: {str(e)[:60]}"

    fn = ns.get(prob["entrypoint"])
    if not fn:
        return False, f"no {prob['entrypoint']} fn"
    for args, expected in prob["tests"]:
        try:
            got = run_with_timeout(fn, args, seconds=5)
        except Timeout:
            return False, f"timeout on {args}"
        except Exception as e:
            return False, f"runtime {args}: {str(e)[:40]}"
        # normalize: median returns float; allow int==float
        if got != expected:
            return False, f"{args} -> {repr(got)[:40]} != {repr(expected)[:40]}"
    return True, "ok"


def call_local(prompt: str) -> tuple[str, float, int]:
    body = json.dumps({
        "model": MODEL, "think": False, "stream": False,
        "messages": [{"role": "user", "content": prompt + " Output ONLY a python code block."}],
    }).encode()
    req = urllib.request.Request(HOST, data=body, headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=180) as r:
        d = json.loads(r.read())
    wall = time.time() - t0
    content = d.get("message", {}).get("content", "")
    toks = d.get("eval_count", 0)
    return content, wall, toks


def run_local() -> dict:
    results, solutions = [], {}
    total_wall, total_tok = 0.0, 0
    for prob in PROBLEMS:
        try:
            text, wall, toks = call_local(prob["prompt"])
        except Exception as e:
            results.append({"id": prob["id"], "passed": False, "note": f"call-fail: {str(e)[:50]}"})
            continue
        code = extract_code(text)
        solutions[prob["id"]] = code
        passed, note = score_problem(prob, code)
        total_wall += wall; total_tok += toks
        results.append({"id": prob["id"], "difficulty": prob["difficulty"],
                        "passed": passed, "note": note, "wall": round(wall, 1), "tok": toks})
        print(f"  {'PASS' if passed else 'FAIL'}  {prob['id']:<20} {prob['difficulty']:<7} {wall:>5.1f}s {note if not passed else ''}")
    n_pass = sum(1 for r in results if r["passed"])
    out = {
        "model": MODEL, "engine": "ollama-maral-think-false",
        "passed": n_pass, "total": len(PROBLEMS),
        "score": round(n_pass / len(PROBLEMS), 3),
        "total_wall_s": round(total_wall, 1),
        "decode_tps": round(total_tok / total_wall, 1) if total_wall else 0,
        "results": results,
    }
    return out, solutions


def score_file(path: str) -> dict:
    sols = json.loads(Path(path).read_text())
    results = []
    for prob in PROBLEMS:
        code = sols.get(prob["id"], "")
        passed, note = score_problem(prob, code)
        results.append({"id": prob["id"], "difficulty": prob["difficulty"],
                        "passed": passed, "note": note})
        print(f"  {'PASS' if passed else 'FAIL'}  {prob['id']:<20} {prob['difficulty']:<7} {note if not passed else ''}")
    n_pass = sum(1 for r in results if r["passed"])
    return {"source": path, "passed": n_pass, "total": len(PROBLEMS),
            "score": round(n_pass / len(PROBLEMS), 3), "results": results}


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "local"
    if mode == "local":
        print("Running local (qwen3:8b on Maral, think:false)...")
        out, sols = run_local()
        (HERE / "local.json").write_text(json.dumps(out, indent=2))
        (HERE / "local_solutions.json").write_text(json.dumps(sols, indent=2))
        print(f"\nLOCAL: {out['passed']}/{out['total']} = {out['score']*100:.0f}%  "
              f"({out['total_wall_s']}s, {out['decode_tps']} tok/s)")
    elif mode == "score-file":
        out = score_file(sys.argv[2])
        print(f"\nSCORE: {out['passed']}/{out['total']} = {out['score']*100:.0f}%")
        Path(sys.argv[2].replace(".json", "_scored.json")).write_text(json.dumps(out, indent=2))
    else:
        print("usage: harness.py local | score-file FILE.json")
