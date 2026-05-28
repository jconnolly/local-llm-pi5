"""Drive Maral qwen3:14b to produce local_refactor.py."""
import asyncio, httpx, json, re, pathlib

HERE = pathlib.Path(__file__).parent
prompt_text = (HERE / "REFACTOR_PROMPT.txt").read_text()
src = (HERE / "input.py").read_text()
full_prompt = f"{prompt_text}\n\nFile to refactor:\n```python\n{src}\n```\n"

async def main():
    async with httpx.AsyncClient(timeout=900) as c:
        r = await c.post("http://maral.local:11434/api/chat", json={
            "model": "qwen3:14b",
            "stream": False,
            "messages": [{"role": "user", "content": full_prompt}],
            "options": {"num_predict": 6000, "temperature": 0.2},
        })
        r.raise_for_status()
        d = r.json()
    content = d["message"]["content"]
    thinking = d["message"].get("thinking", "")
    ec = d.get("eval_count", 0)
    ed = d.get("eval_duration", 1) / 1e9
    print(f"[meta] thinking_chars={len(thinking)} eval_tokens={ec} eval_s={ed:.1f} tok_s={ec/ed:.2f}")
    # Strip markdown fences
    m = re.search(r"```(?:python)?\s*\n(.*?)\n```", content, re.DOTALL)
    if m:
        content = m.group(1)
    content = content.strip()
    (HERE / "local_refactor.py").write_text(content + "\n")
    line_count = sum(1 for _ in content.splitlines())
    print(f"[output] wrote local_refactor.py: {line_count} lines, {len(content)} chars")

asyncio.run(main())
