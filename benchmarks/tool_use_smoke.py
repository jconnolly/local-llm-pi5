"""Smoke-test a model's tool-use compatibility with Claude Code.

Usage:
    python tool_use_smoke.py <model-name>

Hits Ollama's /v1/messages endpoint on Maral with one tool definition.
PASS criteria (all three required):
  1. content array contains a {"type": "tool_use"} block
  2. tool_use block has correct "name" matching the offered tool
  3. stop_reason == "tool_use"

FAIL modes documented from prior acts:
  - qwen2.5-coder: emits bare JSON inside a text block, no tool_use wrapper
  - any model returning stop_reason: "end_turn" with no tool_use block

Exits 0 on PASS, 1 on FAIL.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request

ENDPOINT = "http://maral.local:11434/v1/messages"
TOOL = {
    "name": "get_current_weather",
    "description": "Get the weather for a given city.",
    "input_schema": {
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"],
    },
}
PROMPT = "What's the weather in Paris right now? Use the tool."


def hit(model: str) -> dict:
    body = json.dumps({
        "model": model,
        "max_tokens": 300,
        "tools": [TOOL],
        "messages": [{"role": "user", "content": PROMPT}],
    }).encode()
    req = urllib.request.Request(
        ENDPOINT,
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-api-key": "ollama",
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read())
    data["_wall_s"] = round(time.time() - t0, 2)
    return data


def main(model: str) -> int:
    print(f"model: {model}")
    print(f"endpoint: {ENDPOINT}")
    try:
        r = hit(model)
    except Exception as e:
        print(f"FAIL: request error: {e}")
        return 1

    print(f"wall: {r['_wall_s']}s  stop_reason: {r.get('stop_reason')}  usage: {r.get('usage')}")
    print("content blocks:")
    for b in r.get("content", []):
        kind = b.get("type")
        if kind == "tool_use":
            print(f"  [tool_use] name={b.get('name')!r}  input={b.get('input')}")
        elif kind == "text":
            print(f"  [text] {b.get('text', '')[:200]}")
        elif kind == "thinking":
            print(f"  [thinking] {b.get('thinking', '')[:120]}...")
        else:
            print(f"  [{kind}] {json.dumps(b)[:200]}")

    has_tool_use = any(b.get("type") == "tool_use" for b in r.get("content", []))
    correct_name = any(
        b.get("type") == "tool_use" and b.get("name") == TOOL["name"]
        for b in r.get("content", [])
    )
    correct_stop = r.get("stop_reason") == "tool_use"

    print()
    print(f"  tool_use block present: {has_tool_use}")
    print(f"  tool name matches:      {correct_name}")
    print(f"  stop_reason == tool_use:{correct_stop}")
    ok = has_tool_use and correct_name and correct_stop
    print(f"\n{'PASS' if ok else 'FAIL'}: tool-use compatibility")
    return 0 if ok else 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python tool_use_smoke.py <model-name>", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
