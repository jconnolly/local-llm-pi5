"""Playwright functional rubric for a built game artifact (index.html).

7 deterministic checks — the failure modes a weak local model actually hits:
throws on load, blank canvas, dead animation loop, missing controls, crash on input,
no game logic. Returns score k/7 + reason per check + two screenshots (initial, post-input).

Usage:
    python score.py /path/to/index.html /path/to/out_dir
"""
from __future__ import annotations

import base64
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


def _canvas_png(page):
    """Base64 PNG of the first canvas, or None."""
    return page.evaluate(
        "() => { const c = document.querySelector('canvas');"
        " return c ? c.toDataURL('image/png') : null; }"
    )


def _decode(data_url):
    if not data_url:
        return b""
    return base64.b64decode(data_url.split(",", 1)[1])


def _byte_diff_ratio(a: bytes, b: bytes) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    if n == 0:
        return 0.0
    diff = sum(1 for i in range(0, n, 7) if a[i] != b[i])  # sample every 7th byte
    return diff / (n / 7)


def score(html_path: Path, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    src = html_path.read_text(errors="ignore")
    checks: dict[str, bool] = {}
    notes: dict[str, str] = {}

    # static-source checks (cheap, robust)
    checks["controls_wired"] = bool(
        re.search(r"keydown|onkeydown", src, re.I)
        and re.search(r"ArrowLeft|ArrowRight", src)
        and re.search(r"' '|\"\s\"|Space|keyCode\s*===?\s*32|32", src)
    )
    checks["game_logic_present"] = bool(
        re.search(r"score", src, re.I)
        and re.search(r"game\s*over|gameover|you\s*win|game_over|win", src, re.I)
    )

    errors: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 900, "height": 900})
        page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}")
                if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))

        page.goto(html_path.resolve().as_uri())
        page.wait_for_timeout(800)

        checks["no_load_errors"] = len(errors) == 0
        notes["no_load_errors"] = "; ".join(errors[:3])

        dims = page.evaluate(
            "() => { const c=document.querySelector('canvas');"
            " return c ? [c.width, c.height] : [0,0]; }"
        )
        checks["canvas_min_size"] = dims[0] >= 600 and dims[1] >= 600
        notes["canvas_min_size"] = f"{dims[0]}x{dims[1]}"

        # animation running: raf in source AND canvas pixels change over ~1s
        frame0 = _decode(_canvas_png(page))
        page.wait_for_timeout(1100)
        frame1 = _decode(_canvas_png(page))
        moved = _byte_diff_ratio(frame0, frame1)
        checks["animation_running"] = bool(
            re.search(r"requestAnimationFrame", src) and moved > 0.005
        )
        notes["animation_running"] = f"raf={'Y' if 'requestAnimationFrame' in src else 'N'} pixel_delta={moved:.3f}"

        # non-blank render: canvas has meaningful content (frame differs a lot from a 1-color blank)
        # approximate: PNG of a real scene compresses larger than a flat fill
        checks["canvas_rendered"] = len(frame1) > 1500
        notes["canvas_rendered"] = f"png_bytes={len(frame1)}"

        page.screenshot(path=str(out_dir / "shot_initial.png"))

        # input crash test: drive arrows + space for ~1.5s, expect no NEW errors
        err_before = len(errors)
        for _ in range(6):
            page.keyboard.down("ArrowRight"); page.wait_for_timeout(80); page.keyboard.up("ArrowRight")
            page.keyboard.press("Space"); page.wait_for_timeout(80)
            page.keyboard.down("ArrowLeft"); page.wait_for_timeout(80); page.keyboard.up("ArrowLeft")
        page.wait_for_timeout(300)
        checks["no_errors_on_input"] = len(errors) == err_before
        notes["no_errors_on_input"] = "; ".join(errors[err_before:err_before + 3])

        page.screenshot(path=str(out_dir / "shot_played.png"))
        browser.close()

    passed = sum(1 for v in checks.values() if v)
    return {
        "artifact": str(html_path),
        "score": passed,
        "max": len(checks),
        "checks": checks,
        "notes": notes,
    }


if __name__ == "__main__":
    res = score(Path(sys.argv[1]), Path(sys.argv[2]))
    print(f"\n  {res['score']}/{res['max']} functional checks passed")
    for k, v in res["checks"].items():
        n = res["notes"].get(k, "")
        print(f"    {'PASS' if v else 'FAIL'}  {k:<22} {n}")
