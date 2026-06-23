"""repobench harness — run multi-file tasks against a model, score by hidden tests.

Each task: give the model ALL its files + the prompt, ask it to return the complete
content of any files it changes (fenced as ```python path=<path>). Apply those into
a fresh temp copy of the repo, run the hidden test with pytest, score pass/fail
(all tests in a task must pass). No LLM judge — deterministic.

Validate mode runs the REFERENCE solution (must pass) and the untouched BUGGY repo
(must fail) for every task, proving the fixtures are sound before any model is scored.

Usage:
    python harness.py validate                       # check tasks are well-formed
    MINIBENCH_HOST=studio.local:11434 \
      MINIBENCH_MODEL=qwen3-coder:30b-a3b-q8_0 \
      python harness.py run                          # score a model
    python harness.py score-file cloud.json          # score a {task_id: {path: content}} file
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from tasks import TASKS  # noqa: E402

HOST = f"http://{os.environ.get('MINIBENCH_HOST', 'studio.local:11434')}/api/chat"
MODEL = os.environ.get("MINIBENCH_MODEL", "qwen3-coder:30b-a3b-q8_0")


# ---- repo build + test run ---------------------------------------------------

def write_repo(root: Path, files: dict) -> None:
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)


def run_test(base_files: dict, overlay: dict, test_src: str) -> tuple[bool, str]:
    """Build base_files, apply overlay (model/reference edits), run the test."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        write_repo(root, base_files)
        write_repo(root, overlay or {})
        (root / "test_hidden.py").write_text(test_src)
        try:
            r = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "test_hidden.py"],
                cwd=root, capture_output=True, text=True, timeout=60,
            )
        except subprocess.TimeoutExpired:
            return False, "timeout"
        ok = r.returncode == 0
        tail = (r.stdout + r.stderr).strip().splitlines()
        return ok, " | ".join(tail[-3:])[:200]


# ---- model call + parse ------------------------------------------------------

def build_prompt(task: dict) -> str:
    parts = [task["prompt"], "\n\nThe repository files:\n"]
    for path, content in task["files"].items():
        parts.append(f"\n--- {path} ---\n```python\n{content}```\n")
    parts.append(
        "\n\nOutput ONLY the complete content of every file you create or change, each "
        "in this EXACT format with no markdown fences:\n\n"
        "<<<FILE path/to/file.py>>>\n"
        "<full file content here>\n"
        "<<<END>>>\n\n"
        "Repeat the block for each changed file. Change only what's needed. Do not "
        "include explanation outside the blocks."
    )
    return "".join(parts)


def call_model(prompt: str) -> tuple[str, float]:
    body = json.dumps({
        "model": MODEL, "think": False, "stream": False,
        "options": {"temperature": 0, "num_ctx": 8192},
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(HOST, data=body, headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=300) as r:
        d = json.loads(r.read())
    return d.get("message", {}).get("content", ""), time.time() - t0


_PY_PATH = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_./-]*\.py")

def parse_files(text: str) -> dict:
    """Extract {path: content}. Primary: explicit <<<FILE path>>> ... <<<END>>> blocks
    (what the prompt demands). Fallback: markdown fences with the nearest .py path
    mentioned just before the fence — for models that ignore the delimiter format."""
    out = {}
    # Primary: explicit delimiters. Strip ``` fences if the model wrapped content anyway.
    for m in re.finditer(r"<<<FILE\s+([^\n>]+?)>>>\s*\n(.*?)<<<END>>>", text, re.S):
        path = m.group(1).strip()
        body = m.group(2)
        fence = re.match(r"\s*```[^\n]*\n(.*?)```\s*$", body, re.S)
        if fence:
            body = fence.group(1)
        out[path] = body
    if out:
        return out
    # Fallback: markdown fences + nearest preceding .py path token
    for m in re.finditer(r"```[^\n]*\n(.*?)```", text, re.S):
        body = m.group(1)
        hm = re.match(r"\s*#\s*(?:path:|file:)?\s*([\w./-]+\.py)\s*\n", body)
        inline = None
        if hm:
            inline, body = hm.group(1), body[hm.end():]
        info_end = text[m.start():].find("\n")
        cands = _PY_PATH.findall(text[max(0, m.start() - 120):m.start()]) + \
                _PY_PATH.findall(text[m.start():m.start() + info_end])
        path = (cands[-1] if cands else None) or inline
        if path:
            out[path.strip()] = body
    return out


# ---- modes -------------------------------------------------------------------

def validate() -> int:
    bad = 0
    print(f"{'task':<22}{'ref_pass':>9}{'buggy_fail':>12}  note")
    print("-" * 60)
    for t in TASKS:
        ref_ok, _ = run_test(t["files"], t["reference"], t["test"])
        buggy_ok, bnote = run_test(t["files"], {}, t["test"])
        sound = ref_ok and not buggy_ok
        if not sound:
            bad += 1
        print(f"{t['id']:<22}{str(ref_ok):>9}{str(not buggy_ok):>12}  "
              f"{'' if sound else 'FIXTURE BROKEN: ' + bnote}")
    print(f"\n{'ALL FIXTURES SOUND' if not bad else str(bad) + ' BROKEN'}")
    return 0 if not bad else 1


def run() -> int:
    results, sols = [], {}
    print(f"Running {MODEL} @ {HOST} on {len(TASKS)} multi-file tasks...\n")
    for t in TASKS:
        try:
            text, wall = call_model(build_prompt(t))
        except Exception as e:
            results.append({"id": t["id"], "passed": False, "note": f"call-fail: {str(e)[:50]}"})
            print(f"  FAIL  {t['id']:<22} call error")
            continue
        overlay = parse_files(text)
        sols[t["id"]] = overlay
        if not overlay:
            results.append({"id": t["id"], "passed": False, "note": "no files parsed"})
            print(f"  FAIL  {t['id']:<22} (no parseable files in output)")
            continue
        ok, note = run_test(t["files"], overlay, t["test"])
        results.append({"id": t["id"], "passed": ok, "note": note, "wall": round(wall, 1),
                        "files_changed": list(overlay.keys())})
        print(f"  {'PASS' if ok else 'FAIL'}  {t['id']:<22} {wall:>5.1f}s  "
              f"{'' if ok else note}")
    n = sum(1 for r in results if r["passed"])
    out = {"model": MODEL, "passed": n, "total": len(TASKS),
           "score": round(n / len(TASKS), 3), "results": results}
    slug = MODEL.replace(":", "_").replace("/", "_")
    (HERE / f"result_{slug}.json").write_text(json.dumps(out, indent=2))
    (HERE / f"solutions_{slug}.json").write_text(json.dumps(sols, indent=2))
    print(f"\n{MODEL}: {n}/{len(TASKS)} = {out['score']*100:.0f}%  -> result_{slug}.json")
    return 0


def score_file(path: str) -> int:
    sols = json.loads(Path(path).read_text())
    n = 0
    for t in TASKS:
        overlay = sols.get(t["id"], {})
        ok, note = run_test(t["files"], overlay, t["test"])
        n += ok
        print(f"  {'PASS' if ok else 'FAIL'}  {t['id']:<22} {'' if ok else note}")
    print(f"\n{n}/{len(TASKS)} = {n/len(TASKS)*100:.0f}%")
    return 0


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "validate"
    sys.exit({"validate": validate, "run": run}.get(mode, lambda: score_file(sys.argv[2]))())
