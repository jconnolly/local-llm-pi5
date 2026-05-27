"""maral-memory — Audit + normalize ~/.claude/memory/ entries written by a local LLM.

The local LLM tends to produce sloppier memory entries than cloud Claude — verbose,
inconsistent format, no `[[wikilinks]]`, missing Why/How fields. This server runs
a normalization pass that:
  - Reads every memory file
  - Checks frontmatter conformance
  - Identifies stale, duplicated, or malformed entries
  - Optionally rewrites them via the LLM with strict format requirements

Tools:
    audit_memory() -> dict   (report only, no writes)
    cleanup_memory(dry_run=True) -> dict   (rewrite sloppy entries; dry_run shows diffs)
    consolidate_index() -> str   (rebuild MEMORY.md from headers of memory/*.md)
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Annotated, Any

import httpx
from mcp.server.fastmcp import FastMCP

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://maral.local:11434")
MEMORY_MODEL = os.environ.get("MARAL_MEMORY_MODEL", "qwen3:14b")
MEMORY_DIR_DEFAULT = Path(os.environ.get("MARAL_MEMORY_DIR", "~/.claude/memory")).expanduser()

mcp = FastMCP("maral-memory")


FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)", re.DOTALL)


def _find_memory_dirs() -> list[Path]:
    """Find all memory dirs (global + per-project)."""
    out: list[Path] = []
    if MEMORY_DIR_DEFAULT.is_dir():
        out.append(MEMORY_DIR_DEFAULT)
    # Per-project memory dirs at ~/.claude/projects/*/memory/
    projects = Path.home() / ".claude" / "projects"
    if projects.is_dir():
        for p in projects.iterdir():
            mem = p / "memory"
            if mem.is_dir():
                out.append(mem)
    return out


def _parse_memory_file(p: Path) -> dict[str, Any]:
    content = p.read_text(encoding="utf-8", errors="ignore")
    m = FRONTMATTER_RE.match(content)
    if not m:
        return {"path": str(p), "valid": False, "error": "no frontmatter"}
    fm_text, body = m.group(1), m.group(2)
    fm: dict[str, str] = {}
    for line in fm_text.splitlines():
        if ":" in line and not line.startswith(" "):
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    return {
        "path": str(p),
        "valid": True,
        "name": fm.get("name", ""),
        "description": fm.get("description", ""),
        "type": fm.get("type", "unknown"),
        "body": body.strip(),
        "body_chars": len(body),
        "wikilinks": re.findall(r"\[\[([^\]]+)\]\]", body),
    }


@mcp.tool()
def audit_memory(
    memory_dir: Annotated[
        str,
        "Override memory directory. Empty = scan all known dirs (~/.claude/memory and per-project).",
    ] = "",
) -> dict[str, Any]:
    """Read every memory file and report on health: malformed frontmatter, duplicates, oversized, missing wikilinks."""
    dirs = [Path(memory_dir).expanduser()] if memory_dir else _find_memory_dirs()
    if not dirs:
        return {"error": "no memory directories found"}

    findings: dict[str, Any] = {"dirs_scanned": [str(d) for d in dirs], "files": [], "issues": []}
    seen_descriptions: dict[str, list[str]] = {}

    for d in dirs:
        for fp in d.glob("*.md"):
            if fp.name == "MEMORY.md":
                continue
            parsed = _parse_memory_file(fp)
            findings["files"].append(parsed)

            if not parsed["valid"]:
                findings["issues"].append({"file": str(fp), "issue": parsed.get("error")})
                continue

            if parsed["body_chars"] > 4000:
                findings["issues"].append({"file": str(fp), "issue": f"oversized ({parsed['body_chars']} chars; soft cap 4k)"})

            if parsed["type"] in ("feedback", "project") and "**Why:**" not in parsed["body"]:
                findings["issues"].append({"file": str(fp), "issue": f"missing **Why:** line (type={parsed['type']})"})

            if not parsed["name"]:
                findings["issues"].append({"file": str(fp), "issue": "missing name in frontmatter"})

            if parsed["description"]:
                seen_descriptions.setdefault(parsed["description"], []).append(str(fp))

    for desc, files in seen_descriptions.items():
        if len(files) > 1:
            findings["issues"].append({"issue": "duplicate description", "description": desc, "files": files})

    findings["summary"] = {
        "total_files": len(findings["files"]),
        "issues_count": len(findings["issues"]),
    }
    return findings


@mcp.tool()
async def cleanup_memory(
    dry_run: Annotated[bool, "If True, show what would change without writing."] = True,
    memory_dir: Annotated[str, "Override memory directory."] = "",
) -> dict[str, Any]:
    """Rewrite sloppy memory entries via the LLM. Adds missing Why/How lines, fixes frontmatter, trims oversized body."""
    audit = audit_memory(memory_dir=memory_dir)
    if "error" in audit:
        return audit

    rewrites: list[dict[str, Any]] = []

    for parsed in audit["files"]:
        if not parsed["valid"]:
            continue
        needs_rewrite = (
            parsed["body_chars"] > 4000
            or (parsed["type"] in ("feedback", "project") and "**Why:**" not in parsed["body"])
        )
        if not needs_rewrite:
            continue

        prompt = f"""You are rewriting a memory file to fit a strict format.

Type: {parsed["type"]}
Name: {parsed["name"]}
Description: {parsed["description"]}

Current body (sloppy):
{parsed["body"]}

Rewrite the body. Requirements:
- For type=feedback or type=project: include **Why:** <one-sentence reason> and **How to apply:** <one-sentence rule>
- Trim to under 400 words
- Preserve all technical facts (file paths, function names, error messages)
- Keep [[wikilinks]] if present
- Output ONLY the body, no frontmatter, no commentary
"""
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    f"{OLLAMA_HOST}/api/generate",
                    json={"model": MEMORY_MODEL, "prompt": prompt, "stream": False, "options": {"temperature": 0.2}},
                )
                resp.raise_for_status()
                new_body = resp.json().get("response", "").strip()
        except Exception as e:
            rewrites.append({"file": parsed["path"], "error": str(e)})
            continue

        new_content = (
            f"---\n"
            f"name: {parsed['name']}\n"
            f"description: {parsed['description']}\n"
            f"metadata:\n  type: {parsed['type']}\n"
            f"---\n\n"
            f"{new_body}\n"
        )

        rewrites.append({
            "file": parsed["path"],
            "before_chars": parsed["body_chars"],
            "after_chars": len(new_body),
            "preview": new_body[:300],
        })

        if not dry_run:
            Path(parsed["path"]).write_text(new_content, encoding="utf-8")
            rewrites[-1]["written"] = True

    return {"dry_run": dry_run, "rewrites": rewrites, "count": len(rewrites)}


@mcp.tool()
def consolidate_index(
    memory_dir: Annotated[str, "Memory directory containing the .md files"] = "",
) -> str:
    """Rebuild MEMORY.md from the name+description of each memory file in the dir."""
    d = Path(memory_dir).expanduser() if memory_dir else MEMORY_DIR_DEFAULT
    if not d.is_dir():
        return f"ERROR: not a directory: {d}"

    entries: list[str] = []
    for fp in sorted(d.glob("*.md")):
        if fp.name == "MEMORY.md":
            continue
        parsed = _parse_memory_file(fp)
        if not parsed["valid"]:
            continue
        name = parsed["name"] or fp.stem
        desc = parsed["description"] or ""
        title = name.replace("-", " ").title()
        entries.append(f"- [{title}]({fp.name}) — {desc}")

    new_index = "\n".join(entries) + "\n"
    (d / "MEMORY.md").write_text(new_index, encoding="utf-8")
    return f"Wrote MEMORY.md with {len(entries)} entries to {d}"


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
