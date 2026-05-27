"""maral-review — Multi-pass code review backed by deterministic tools + Maral LLM pass.

Composes lint + type-check + LLM review into a single tool. Each deterministic
pass catches easy bugs; the LLM pass catches what the linters miss. Result is
denser than a pure single-model review.

Tools:
    review_file(path, language?) -> dict
    review_diff(diff_text or revision) -> dict
"""

from __future__ import annotations

import asyncio
import os
import shlex
import subprocess
from pathlib import Path
from typing import Annotated, Any

import httpx
from mcp.server.fastmcp import FastMCP

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://maral.local:11434")
REVIEW_MODEL = os.environ.get("MARAL_REVIEW_MODEL", "qwen3:14b")
TIMEOUT_S = float(os.environ.get("MARAL_REVIEW_TIMEOUT", "300"))

mcp = FastMCP("maral-review")


# Language -> [list of (label, command-template) tuples]
# Command receives {path} substitution. Should print findings on stdout.
LINTERS: dict[str, list[tuple[str, str]]] = {
    "python": [
        ("ruff", "ruff check {path}"),
        ("mypy", "mypy --no-error-summary {path}"),
    ],
    "typescript": [
        ("eslint", "npx --no-install eslint {path}"),
        ("tsc", "npx --no-install tsc --noEmit {path}"),
    ],
    "javascript": [
        ("eslint", "npx --no-install eslint {path}"),
    ],
    "rust": [
        ("clippy", "cargo clippy --message-format=short -- -A warnings"),
    ],
    "go": [
        ("vet", "go vet {path}"),
        ("staticcheck", "staticcheck {path}"),
    ],
    "shell": [
        ("shellcheck", "shellcheck {path}"),
    ],
}

LANG_BY_EXT = {
    ".py": "python", ".ts": "typescript", ".tsx": "typescript",
    ".js": "javascript", ".jsx": "javascript", ".rs": "rust", ".go": "go",
    ".sh": "shell", ".bash": "shell", ".zsh": "shell",
}


def _detect_language(path: Path) -> str | None:
    return LANG_BY_EXT.get(path.suffix.lower())


def _run_cmd(cmd: str, cwd: Path) -> tuple[int, str]:
    try:
        out = subprocess.run(
            shlex.split(cmd),
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        combined = out.stdout + ("\n" + out.stderr if out.stderr else "")
        return out.returncode, combined.strip()
    except FileNotFoundError:
        return -1, "TOOL_NOT_INSTALLED"
    except subprocess.TimeoutExpired:
        return -2, "TIMEOUT"
    except Exception as e:
        return -3, f"ERROR: {e}"


async def _llm_review(file_content: str, language: str, linter_findings: str) -> str:
    prompt = f"""You are reviewing a {language} file. Linter findings (already detected, do NOT repeat):

```
{linter_findings or "(none)"}
```

Now review the file for what static linters miss: logic bugs, race conditions,
incorrect error handling, security issues, API misuse, off-by-one errors,
incorrect assumptions about inputs. Be specific and cite line numbers.

File:
```{language}
{file_content[:30000]}
```

Return findings as: `LINE: severity: description. fix: suggested fix.`
One finding per line. If nothing found, return exactly: NO_ISSUES.
"""
    async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
        resp = await client.post(
            f"{OLLAMA_HOST}/api/generate",
            json={
                "model": REVIEW_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": 800, "temperature": 0.2},
            },
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()


@mcp.tool()
async def review_file(
    path: Annotated[str, "Absolute path to file to review"],
    language: Annotated[
        str,
        "Override language detection (python, typescript, javascript, rust, go, shell). Empty = auto-detect.",
    ] = "",
) -> dict[str, Any]:
    """Multi-pass review of a single file. Returns deterministic linter findings + LLM bug analysis."""
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return {"error": f"file not found: {p}"}

    lang = language or _detect_language(p)
    if not lang:
        return {"error": f"could not detect language for {p.suffix}. Specify language= explicitly."}

    findings: dict[str, Any] = {"file": str(p), "language": lang, "passes": {}}

    # Deterministic passes
    linter_summary = []
    for label, cmd_template in LINTERS.get(lang, []):
        cmd = cmd_template.format(path=shlex.quote(str(p)))
        rc, output = _run_cmd(cmd, p.parent)
        findings["passes"][label] = {"returncode": rc, "output": output[:5000]}
        if output and output != "TOOL_NOT_INSTALLED":
            linter_summary.append(f"# {label}\n{output}")

    # LLM pass
    try:
        content = p.read_text(encoding="utf-8", errors="ignore")
        llm_out = await _llm_review(content, lang, "\n\n".join(linter_summary))
        findings["passes"]["llm"] = {"output": llm_out}
    except Exception as e:
        findings["passes"]["llm"] = {"error": str(e)}

    return findings


@mcp.tool()
async def review_diff(
    diff_text: Annotated[
        str,
        "Unified-diff text to review. Use `git diff <ref>` output. If empty, attempts `git diff HEAD` in cwd.",
    ] = "",
    cwd: Annotated[str, "Working directory for git fallback"] = ".",
) -> dict[str, Any]:
    """Review a unified diff. Pulls from `git diff HEAD` if no diff_text passed."""
    diff = diff_text.strip()
    if not diff:
        rc, out = _run_cmd("git diff HEAD", Path(cwd).expanduser().resolve())
        if rc != 0:
            return {"error": f"git diff HEAD failed: {out}"}
        diff = out

    if not diff:
        return {"summary": "NO_CHANGES"}

    prompt = f"""Review this git diff for correctness bugs. Skip style nits. Cite file:line.
Output format: `path:line: <severity>: <problem>. <fix>.` One per line. If none, return NO_ISSUES.

Diff:
```diff
{diff[:30000]}
```
"""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            resp = await client.post(
                f"{OLLAMA_HOST}/api/generate",
                json={
                    "model": REVIEW_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"num_predict": 800, "temperature": 0.2},
                },
            )
            resp.raise_for_status()
            findings = resp.json().get("response", "").strip()
    except Exception as e:
        return {"error": f"LLM review failed: {e}"}

    return {
        "diff_size_bytes": len(diff),
        "findings": findings,
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
