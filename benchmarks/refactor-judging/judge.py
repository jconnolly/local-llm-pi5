"""judge.py — run multiple LLM judges on cloud vs local refactor, multiple rounds, with position swap.

Output: judge_runs.json — every (judge, round, ordering, winner, raw_text) record.
"""
from __future__ import annotations

import asyncio
import json
import random
import re
import time
from pathlib import Path

import httpx

HERE = Path(__file__).parent
OLLAMA = "http://maral.local:11434"

INPUT_SRC = (HERE / "input.py").read_text()
CLOUD_SRC = (HERE / "cloud_refactor.py").read_text()
LOCAL_SRC = (HERE / "local_refactor.py").read_text()

JUDGE_MODELS = ["qwen3:8b"]
ROUNDS_PER_ORDERING = 5  # 5 rounds × 2 orderings = 10 per judge


JUDGE_PROMPT_TEMPLATE = """/no_think

You are judging two refactorings of the same Python file. Output AT MOST 6 short bullet points then a single WINNER line. Do not show reasoning.

Goals of the refactoring (provided to both authors):
  1. Extract helpers where patterns repeat.
  2. Improve naming.
  3. Add missing docstrings.
  4. Preserve behavior exactly.
  5. Keep the public API the same.

Format your response EXACTLY like this:
  - readability: <which is better, one line>
  - maintainability: <one line>
  - correctness: <one line>
  - docstrings: <one line>
  - overall: <one sentence>
  WINNER: 1
(or `WINNER: 2` or `WINNER: TIE`)

=== ORIGINAL ===
```python
{original}
```

=== REFACTORING 1 ===
```python
{r1}
```

=== REFACTORING 2 ===
```python
{r2}
```

Now judge them. Be terse. End with WINNER: 1, WINNER: 2, or WINNER: TIE."""


async def _judge_call(judge_model: str, r1: str, r2: str) -> tuple[str, str, float]:
    """Run one judge round. Returns (raw_response, parsed_winner, wall_seconds)."""
    prompt = JUDGE_PROMPT_TEMPLATE.format(original=INPUT_SRC, r1=r1, r2=r2)
    t0 = time.time()
    async with httpx.AsyncClient(timeout=600) as c:
        resp = await c.post(
            f"{OLLAMA}/api/chat",
            json={
                "model": judge_model,
                "stream": False,
                "messages": [{"role": "user", "content": prompt}],
                "options": {"num_predict": 2000, "temperature": 0.3},
            },
        )
        resp.raise_for_status()
        body = resp.json()
    wall = time.time() - t0
    content = body["message"]["content"] or ""
    thinking = body["message"].get("thinking", "") or ""
    full = content + "\n" + thinking
    # Look for WINNER directive anywhere; take the LAST occurrence
    matches = re.findall(r"WINNER:\s*(1|2|TIE)", full, re.IGNORECASE)
    if matches:
        winner = matches[-1].upper()
    else:
        # Fallback: look for a sole "1", "2", or "TIE" near the end
        tail = full.strip().splitlines()[-3:] if full.strip() else []
        for line in reversed(tail):
            t = line.strip().upper()
            if t in ("1", "2", "TIE"):
                winner = t
                break
        else:
            winner = "UNPARSED"
    return content + ("\n--thinking--\n" + thinking if thinking else ""), winner, wall


async def main() -> None:
    rng = random.Random(42)
    records: list[dict] = []
    for judge in JUDGE_MODELS:
        print(f"\n=== judge: {judge} ===")
        for ordering in ("CLOUD_FIRST", "LOCAL_FIRST"):
            for round_idx in range(1, ROUNDS_PER_ORDERING + 1):
                if ordering == "CLOUD_FIRST":
                    r1, r2 = CLOUD_SRC, LOCAL_SRC
                    map_to_source = {"1": "CLOUD", "2": "LOCAL"}
                else:
                    r1, r2 = LOCAL_SRC, CLOUD_SRC
                    map_to_source = {"1": "LOCAL", "2": "CLOUD"}
                raw, winner_label, wall = await _judge_call(judge, r1, r2)
                winner_source = map_to_source.get(winner_label, "UNPARSED")
                print(
                    f"  {ordering:11s} round {round_idx}: winner_label={winner_label:>8s}  "
                    f"-> source={winner_source}  ({wall:.1f}s)"
                )
                records.append({
                    "judge": judge,
                    "ordering": ordering,
                    "round": round_idx,
                    "winner_label": winner_label,
                    "winner_source": winner_source,
                    "wall_s": wall,
                    "raw_excerpt": raw[-400:],
                })
                # Write incrementally so we have partial results if the run hangs
                (HERE / "judge_runs.json").write_text(json.dumps(records, indent=2))
    # Final write (no-op if loop finished cleanly)
    (HERE / "judge_runs.json").write_text(json.dumps(records, indent=2))
    print(f"\nWrote {len(records)} records to judge_runs.json")


if __name__ == "__main__":
    asyncio.run(main())
