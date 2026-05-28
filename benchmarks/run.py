#!/usr/bin/env python3
"""benchmarks/run.py — measure Maral local-LLM stack on speed + correctness.

Runs 6 benchmark suites against Maral via Anthropic-compatible /v1/messages:
  1. Cold/warm latency on qwen3:14b and qwen3:8b
  2. Decode + prefill throughput
  3. Tool-use correctness (single tool, multi-tool)
  4. RAG retrieval relevance
  5. Code review depth on a real diff
  6. End-to-end mini agent loop (read file -> describe content)

Cloud comparison: published SWE-bench Verified scores from May 2026 leaderboards.
Writes results to benchmarks/results.json + summary table to stdout.
"""

from __future__ import annotations

import asyncio
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx

MARAL = "http://maral.local:11434"
RESULTS_DIR = Path(__file__).parent
RESULTS_FILE = RESULTS_DIR / "results.json"

results: dict[str, Any] = {"ts": time.time(), "suites": {}}


def section(name: str) -> None:
    print(f"\n{'='*60}\n{name}\n{'='*60}")


async def call_chat(model: str, prompt: str, num_predict: int = 128, tools: list | None = None) -> dict:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"num_predict": num_predict, "temperature": 0.2},
    }
    if tools is not None:
        payload["tools"] = tools
    t0 = time.time()
    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(f"{MARAL}/api/chat", json=payload)
        resp.raise_for_status()
        body = resp.json()
    body["_wall_s"] = time.time() - t0
    return body


async def call_anthropic(model: str, messages: list, tools: list | None = None, max_tokens: int = 256) -> dict:
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    if tools is not None:
        payload["tools"] = tools
    t0 = time.time()
    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(
            f"{MARAL}/v1/messages",
            json=payload,
            headers={"x-api-key": "ollama", "anthropic-version": "2023-06-01"},
        )
        resp.raise_for_status()
        body = resp.json()
    body["_wall_s"] = time.time() - t0
    return body


def tok_metrics(body: dict) -> dict:
    ec = body.get("eval_count", 0)
    ed = body.get("eval_duration", 1)
    pc = body.get("prompt_eval_count", 0)
    pd = body.get("prompt_eval_duration", 1)
    return {
        "decode_tok_s": ec / (ed / 1e9) if ed > 0 else 0,
        "prefill_tok_s": pc / (pd / 1e9) if pd > 0 else 0,
        "tokens_out": ec,
        "tokens_in": pc,
        "wall_s": body.get("_wall_s", 0),
    }


# -----------------------------
# Suite 1+2: Speed
# -----------------------------
async def suite_speed() -> None:
    section("Suite 1 + 2 — Speed (cold + warm)")
    out: dict[str, Any] = {}
    prompt = "Write a Python function `binary_search(arr, target)` with type hints. Return the index or -1. No explanation."
    for model in ("qwen3:8b", "qwen3:14b"):
        # cold (after small warm-up of unrelated model to evict)
        runs = []
        for i in range(3):
            body = await call_chat(model, prompt, num_predict=200)
            m = tok_metrics(body)
            runs.append(m)
            print(f"  {model} run {i+1}: decode={m['decode_tok_s']:.2f} prefill={m['prefill_tok_s']:.2f} wall={m['wall_s']:.1f}s")
        out[model] = {
            "decode_tok_s_median": statistics.median([r["decode_tok_s"] for r in runs]),
            "prefill_tok_s_median": statistics.median([r["prefill_tok_s"] for r in runs]),
            "wall_s_median": statistics.median([r["wall_s"] for r in runs]),
            "runs": runs,
        }
    results["suites"]["speed"] = out


# -----------------------------
# Suite 3: Tool use
# -----------------------------
async def suite_tools() -> None:
    section("Suite 3 — Tool use correctness")
    tests = [
        {
            "name": "single_tool_basic",
            "tools": [{
                "name": "get_weather",
                "description": "Get current weather for a city",
                "input_schema": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            }],
            "prompt": "What's the weather in Paris?",
            "expect_tool": "get_weather",
            "expect_arg": {"city": "Paris"},
        },
        {
            "name": "multi_tool_routing",
            "tools": [
                {
                    "name": "read_file",
                    "description": "Read contents of a file",
                    "input_schema": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                },
                {
                    "name": "write_file",
                    "description": "Write content to a file",
                    "input_schema": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                        "required": ["path", "content"],
                    },
                },
                {
                    "name": "list_dir",
                    "description": "List entries in a directory",
                    "input_schema": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                },
            ],
            "prompt": "Read the file /etc/hostname and tell me its contents.",
            "expect_tool": "read_file",
            "expect_arg": {"path": "/etc/hostname"},
        },
        {
            "name": "negative_no_tool_needed",
            "tools": [{
                "name": "get_weather",
                "description": "Get current weather",
                "input_schema": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            }],
            "prompt": "What is 2 + 2?",
            "expect_tool": None,  # Should NOT call the tool
        },
    ]

    out: dict[str, Any] = {}
    for model in ("qwen3:14b", "qwen3:8b"):
        results_for_model: list[dict] = []
        for t in tests:
            body = await call_anthropic(
                model,
                [{"role": "user", "content": t["prompt"]}],
                tools=t["tools"],
                max_tokens=400,
            )
            tool_uses = [b for b in body.get("content", []) if b.get("type") == "tool_use"]
            called_name = tool_uses[0]["name"] if tool_uses else None
            called_input = tool_uses[0].get("input", {}) if tool_uses else {}

            correct = False
            if t["expect_tool"] is None:
                correct = called_name is None
            else:
                correct = called_name == t["expect_tool"] and all(
                    called_input.get(k) == v for k, v in t["expect_arg"].items()
                )

            print(
                f"  {model} {t['name']}: called={called_name}({called_input})  "
                f"expected={t['expect_tool']}({t.get('expect_arg',{})})  "
                f"{'PASS' if correct else 'FAIL'}  ({body['_wall_s']:.1f}s)"
            )
            results_for_model.append({
                "name": t["name"],
                "expected_tool": t["expect_tool"],
                "expected_arg": t.get("expect_arg"),
                "called_tool": called_name,
                "called_input": called_input,
                "correct": correct,
                "wall_s": body["_wall_s"],
            })
        passed = sum(1 for r in results_for_model if r["correct"])
        out[model] = {
            "pass_rate": passed / len(results_for_model),
            "passed": passed,
            "total": len(results_for_model),
            "tests": results_for_model,
        }
        print(f"  → {model}: {passed}/{len(results_for_model)} pass")
    results["suites"]["tool_use"] = out


# -----------------------------
# Suite 4: RAG retrieval
# -----------------------------
def _load_module(name: str, path: str):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


async def suite_rag() -> None:
    section("Suite 4 — RAG retrieval (cloud-conversations index)")
    rag_server = _load_module("rag_server", str(RESULTS_DIR.parent / "mcp-servers" / "maral-rag" / "server.py"))

    queries = [
        ("Mac mini hardware cost analysis", "Mac mini"),
        ("MCP architecture for local deployment", "MCP"),
        ("local model running on Raspberry Pi", "Pi"),
        ("compound interest formula", "compound"),
    ]
    out: list[dict] = []
    for q, must_contain in queries:
        hits = await rag_server.search(
            q, "/Users/john.connolly/local-llm-data/cloud-conversations", 3
        )
        has_match = any(must_contain.lower() in (h.get("full_content", "") + " " + h.get("preview", "")).lower() for h in hits)
        top_distance = hits[0].get("distance", float("inf")) if hits else float("inf")
        print(f"  {q!r:50s}  hits={len(hits)}  top_dist={top_distance:.2f}  relevant={'YES' if has_match else 'no'}")
        out.append({
            "query": q,
            "must_contain": must_contain,
            "hits": len(hits),
            "top_distance": top_distance,
            "relevant_in_top3": has_match,
        })
    results["suites"]["rag"] = {
        "relevance_rate": sum(1 for r in out if r["relevant_in_top3"]) / len(out),
        "queries": out,
    }


# -----------------------------
# Suite 5: Code review depth
# -----------------------------
async def suite_review() -> None:
    section("Suite 5 — Code review depth on a real diff")
    # Use a recent diff from this repo's history
    repo = RESULTS_DIR.parent
    try:
        diff = subprocess.check_output(
            ["git", "log", "-p", "-n", "1", "--no-merges"],
            cwd=str(repo),
            text=True,
        )[:8000]
    except Exception as e:
        diff = f"(could not get git diff: {e})"

    if not diff or len(diff) < 100:
        print("  no diff available, skipping")
        results["suites"]["review"] = {"skipped": True}
        return

    review_server = _load_module("review_server", str(RESULTS_DIR.parent / "mcp-servers" / "maral-review" / "server.py"))
    res = await review_server.review_diff(diff_text=diff, cwd=str(repo))
    findings = res.get("findings", "")
    findings_count = sum(1 for l in findings.splitlines() if ":" in l and "severity" not in l.lower()[:20])
    print(f"  diff bytes: {res.get('diff_size_bytes', 0)}")
    print(f"  findings (first 300 chars): {findings[:300]}")
    print(f"  finding line count: {findings_count}")
    results["suites"]["review"] = {
        "diff_size_bytes": res.get("diff_size_bytes", 0),
        "findings": findings,
        "finding_lines": findings_count,
    }


# -----------------------------
# Suite 6: Mini agent loop
# -----------------------------
async def suite_agent_loop() -> None:
    section("Suite 6 — Mini agent loop (read file → describe)")
    test_file = "/tmp/maral-bench-test.py"
    Path(test_file).write_text(
        "def factorial(n: int) -> int:\n    if n <= 1:\n        return 1\n    return n * factorial(n - 1)\n"
    )
    tools = [
        {
            "name": "read_file",
            "description": "Read contents of a file",
            "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        },
    ]
    out: dict[str, Any] = {}
    for model in ("qwen3:14b",):
        t0 = time.time()
        # Turn 1: ask model to read
        body = await call_anthropic(
            model,
            [{"role": "user", "content": f"Read {test_file} and tell me what the function does in one sentence."}],
            tools=tools,
            max_tokens=300,
        )
        tool_calls = [b for b in body.get("content", []) if b.get("type") == "tool_use"]
        if not tool_calls:
            print(f"  {model}: model didn't call read_file (FAIL)")
            out[model] = {"correct": False, "reason": "no tool call"}
            continue
        # Turn 2: provide the file content + ask to describe
        file_content = Path(test_file).read_text()
        history = [
            {"role": "user", "content": f"Read {test_file} and tell me what the function does in one sentence."},
            {"role": "assistant", "content": body["content"]},
            {"role": "user", "content": [{
                "type": "tool_result",
                "tool_use_id": tool_calls[0]["id"],
                "content": file_content,
            }]},
        ]
        body2 = await call_anthropic(model, history, tools=tools, max_tokens=200)
        final = " ".join(b.get("text", "") for b in body2.get("content", []) if b.get("type") == "text").strip()
        t1 = time.time()
        # Correctness: contains "factorial" or "recursive" or similar
        correct = any(kw in final.lower() for kw in ("factorial", "recursive", "n!", "multiply"))
        print(f"  {model}: 2-turn agent loop took {t1-t0:.1f}s")
        print(f"  {model}: final answer: {final[:200]}")
        print(f"  {model}: correct={'YES' if correct else 'no'}")
        out[model] = {
            "wall_s": t1 - t0,
            "final_answer": final,
            "correct": correct,
        }
    results["suites"]["agent_loop"] = out


# -----------------------------
# Print summary + save
# -----------------------------
def print_summary() -> None:
    section("SUMMARY")

    sp = results["suites"].get("speed", {})
    print("\nSpeed (median of 3 runs):")
    for model, d in sp.items():
        print(f"  {model:15s}  decode={d['decode_tok_s_median']:.2f} tok/s  prefill={d['prefill_tok_s_median']:.2f} tok/s")

    tu = results["suites"].get("tool_use", {})
    print("\nTool use:")
    for model, d in tu.items():
        print(f"  {model:15s}  {d['passed']}/{d['total']} pass  ({d['pass_rate']*100:.0f}%)")

    rag = results["suites"].get("rag", {})
    if rag:
        print(f"\nRAG: {rag['relevance_rate']*100:.0f}% queries had relevant chunk in top-3")

    rv = results["suites"].get("review", {})
    if rv and not rv.get("skipped"):
        print(f"\nCode review: {rv['finding_lines']} findings on {rv['diff_size_bytes']}-byte diff")

    al = results["suites"].get("agent_loop", {})
    print("\nAgent loop (2 turns):")
    for model, d in al.items():
        print(f"  {model:15s}  wall={d.get('wall_s', 0):.1f}s  correct={d.get('correct', False)}")

    print(f"\nFull results: {RESULTS_FILE}")


async def main() -> None:
    await suite_speed()
    await suite_tools()
    await suite_rag()
    await suite_review()
    await suite_agent_loop()
    RESULTS_FILE.write_text(json.dumps(results, indent=2, default=str))
    print_summary()


if __name__ == "__main__":
    asyncio.run(main())
