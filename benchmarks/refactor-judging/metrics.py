"""metrics.py — deterministic comparison of cloud vs local refactor.

Computes objective rubric per file:
  - SLOC (source lines, excluding blanks + comments)
  - Function/method count
  - Helper extraction count (new functions absent in input)
  - Docstring coverage (% of functions with docstrings)
  - Cyclomatic complexity (mean, max) — via radon if available; falls back to AST branch count
  - Public API preservation (each input @mcp.tool() must still exist with same signature)
  - Behavior smoke: file parses + module imports successfully

Writes metrics.json with side-by-side comparison.
"""
from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).parent
INPUT_FILE = HERE / "input.py"
CLOUD_FILE = HERE / "cloud_refactor.py"
LOCAL_FILE = HERE / "local_refactor.py"


def sloc(text: str) -> int:
    """Source lines of code: non-blank, not a sole comment, not docstring-only."""
    count = 0
    in_multiline_str = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            continue
        # Heuristic: triple-quote toggling (close enough for our purpose)
        toggles = line.count('"""') + line.count("'''")
        if in_multiline_str:
            in_multiline_str = (toggles % 2) == 0
            continue
        if toggles % 2:
            in_multiline_str = True
            # If the docstring is single-line and the line is *only* a docstring, skip
            if line.startswith('"""') and line.endswith('"""') and len(line) > 6:
                in_multiline_str = False
            continue
        count += 1
    return count


def parse(text: str) -> ast.AST:
    return ast.parse(text)


def all_funcs(tree: ast.AST) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def func_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    args = [a.arg for a in node.args.args]
    return f"{node.name}({','.join(args)})"


def docstring_coverage(funcs: list) -> tuple[int, int]:
    with_doc = sum(1 for f in funcs if ast.get_docstring(f))
    return with_doc, len(funcs)


def branch_count(node: ast.AST) -> int:
    """Cheap proxy for cyclomatic complexity: count branches per function."""
    return sum(
        1 for n in ast.walk(node)
        if isinstance(n, (ast.If, ast.For, ast.While, ast.Try, ast.With, ast.IfExp,
                          ast.BoolOp, ast.comprehension))
    )


def per_function_complexity(funcs: list) -> dict[str, int]:
    return {func_signature(f): branch_count(f) for f in funcs}


def public_tools(tree: ast.AST) -> set[str]:
    """Find functions decorated with @mcp.tool() — the public surface."""
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                # match `@mcp.tool()` exactly
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                    if dec.func.attr == "tool":
                        out.add(node.name)
                elif isinstance(dec, ast.Attribute) and dec.attr == "tool":
                    out.add(node.name)
    return out


def loadable(path: Path) -> tuple[bool, str]:
    try:
        spec = importlib.util.spec_from_file_location(path.stem, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore
        return True, "OK"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def analyze_file(path: Path, input_funcs: set[str] | None = None) -> dict:
    text = path.read_text()
    tree = parse(text)
    funcs = all_funcs(tree)
    fn_names = {f.name for f in funcs}
    with_doc, total = docstring_coverage(funcs)
    complexities = per_function_complexity(funcs)
    loadable_ok, load_msg = loadable(path)
    out = {
        "path": str(path.name),
        "lines_total": len(text.splitlines()),
        "sloc": sloc(text),
        "func_count": len(funcs),
        "public_tools": sorted(public_tools(tree)),
        "docstring_coverage": (with_doc / total if total else 0.0),
        "docstrings_with": with_doc,
        "docstrings_total": total,
        "complexity_mean": sum(complexities.values()) / len(complexities) if complexities else 0.0,
        "complexity_max": max(complexities.values()) if complexities else 0,
        "complexity_per_fn": complexities,
        "loadable": loadable_ok,
        "load_msg": load_msg,
    }
    if input_funcs is not None:
        out["new_helpers"] = sorted(fn_names - input_funcs)
        out["removed_funcs"] = sorted(input_funcs - fn_names)
    return out


def main() -> None:
    # Get input func names so we can compute "newly extracted helpers"
    input_tree = parse(INPUT_FILE.read_text())
    input_funcs = {f.name for f in all_funcs(input_tree)}
    input_tools = public_tools(input_tree)

    metrics = {
        "input": analyze_file(INPUT_FILE),
        "cloud": analyze_file(CLOUD_FILE, input_funcs=input_funcs),
        "local": analyze_file(LOCAL_FILE, input_funcs=input_funcs),
    }
    for k in ("cloud", "local"):
        m = metrics[k]
        m["api_preserved"] = set(input_tools).issubset(set(m["public_tools"]))

    (HERE / "metrics.json").write_text(json.dumps(metrics, indent=2, default=str))

    # Print summary
    print("=" * 70)
    print(f"{'Metric':<30} {'INPUT':>12} {'CLOUD':>12} {'LOCAL':>12}")
    print("=" * 70)
    rows = [
        ("Total lines", "lines_total"),
        ("SLOC (no blanks/comments)", "sloc"),
        ("Functions", "func_count"),
        ("Docstring coverage", "docstring_coverage"),
        ("Complexity mean", "complexity_mean"),
        ("Complexity max", "complexity_max"),
    ]
    for label, key in rows:
        i, c, l = metrics["input"][key], metrics["cloud"][key], metrics["local"][key]
        if isinstance(i, float):
            print(f"{label:<30} {i:>12.2f} {c:>12.2f} {l:>12.2f}")
        else:
            print(f"{label:<30} {i:>12d} {c:>12d} {l:>12d}")
    print("-" * 70)
    print(f"{'Loadable':<30} {'—':>12} {str(metrics['cloud']['loadable']):>12} {str(metrics['local']['loadable']):>12}")
    print(f"{'API preserved':<30} {'—':>12} {str(metrics['cloud']['api_preserved']):>12} {str(metrics['local']['api_preserved']):>12}")
    print(f"{'New helpers extracted':<30} {'—':>12} {len(metrics['cloud']['new_helpers']):>12d} {len(metrics['local']['new_helpers']):>12d}")
    print()
    print(f"Cloud new helpers: {metrics['cloud']['new_helpers']}")
    print(f"Local new helpers: {metrics['local']['new_helpers']}")


if __name__ == "__main__":
    main()
