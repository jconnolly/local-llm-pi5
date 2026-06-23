"""Record each built game being *played* (Playwright video), then compose a labeled
side-by-side. Proves usability, not just "it loaded". Build-time + functional score are
burned into each pane's caption.

Pipeline per backend artifact (viz/appbench/<backend>/space_invaders/index.html):
  1. Playwright loads it, scripted-plays ~PLAY_SECS (move + shoot), records webm.
  2. ffmpeg: webm -> mp4, padded to uniform size, with a caption bar
     (model · built in Ns · k/7 playable).
  3. hstack all panes -> side_by_side.mp4  (+ a 2x gif for slides).

Metrics come from metrics.json (model label, build_secs, score) which merge.py writes.

Usage:  python record.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
REPO = HERE.parent.parent
VIZ = REPO / "viz" / "appbench"
PLAY_SECS = 14
W, H = 680, 760  # capture window
CAP_H = 96       # caption strip height

# fixed pane order if present
ORDER = ["local", "next80", "cloud"]
PRETTY = {"local": "qwen3-coder:30b  ·  LOCAL",
          "next80": "qwen3-next:80b  ·  LOCAL",
          "cloud": "Opus 4.8  ·  CLOUD"}
COLORS = {"local": (247, 129, 102), "next80": (63, 185, 80), "cloud": (88, 166, 255)}


def _font(sz):
    for f in ["/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Menlo.ttc"]:
        if Path(f).exists():
            try:
                return ImageFont.truetype(f, sz)
            except Exception:
                pass
    return ImageFont.load_default()


def record_play(html: Path, out_webm_dir: Path) -> Path:
    out_webm_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": W, "height": H},
                                  record_video_dir=str(out_webm_dir),
                                  record_video_size={"width": W, "height": H})
        page = ctx.new_page()
        page.goto(html.resolve().as_uri())
        page.wait_for_timeout(600)
        # dismiss any start screen / menu: press Enter+Space, click likely button spots
        try:
            for key in ["Enter", "Space"]:
                page.keyboard.press(key); page.wait_for_timeout(120)
            for fy in (0.40, 0.50, 0.62, 0.72):
                page.mouse.click(W // 2, int(H * fy)); page.wait_for_timeout(120)
            page.keyboard.press("Enter")
        except Exception:
            pass
        # scripted play: weave movement + shooting for PLAY_SECS
        import math
        steps = int(PLAY_SECS * 1000 / 90)
        for i in range(steps):
            if (i // 6) % 2 == 0:
                page.keyboard.down("ArrowRight")
            else:
                page.keyboard.down("ArrowLeft")
            page.keyboard.press("Space")
            page.wait_for_timeout(45)
            page.keyboard.up("ArrowRight"); page.keyboard.up("ArrowLeft")
            page.wait_for_timeout(45)
        vid = page.video
        path = Path(vid.path())
        ctx.close()
        browser.close()
    return path


def _caption_png(path: Path, title: str, sub: str, color):
    """Render a W x CAP_H caption strip (homebrew ffmpeg lacks drawtext, so we vstack a PNG)."""
    img = Image.new("RGB", (W, CAP_H), (17, 19, 23))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 4], fill=color)  # accent bar
    tf, sf = _font(30), _font(21)
    tw = d.textlength(title, font=tf)
    d.text(((W - tw) / 2, 20), title, font=tf, fill=(240, 240, 240))
    sw = d.textlength(sub, font=sf)
    d.text(((W - sw) / 2, 60), sub, font=sf, fill=(150, 158, 168))
    img.save(path)


def _duration(mp4: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(mp4)], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except Exception:
        return float(PLAY_SECS)


def caption(mp4_in: Path, mp4_out: Path, title: str, sub: str, color=(88, 166, 255)):
    png = mp4_in.parent / "_cap.png"
    _caption_png(png, title, sub, color)
    dur = _duration(mp4_in)
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(mp4_in), "-loop", "1", "-i", str(png),
         "-filter_complex", f"[1:v]scale={W}:{CAP_H}[c];[c][0:v]vstack=inputs=2:shortest=1[v]",
         "-map", "[v]", "-t", f"{dur:.2f}", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(mp4_out)],
        check=True, capture_output=True)


def main():
    metrics = json.loads((VIZ / "metrics.json").read_text()) if (VIZ / "metrics.json").exists() else {}
    panes = []
    for b in ORDER:
        html = VIZ / b / "space_invaders" / "index.html"
        if not html.exists():
            continue
        print(f"recording [{b}] ...", flush=True)
        webm = record_play(html, VIZ / b / "space_invaders" / "_rec")
        raw_mp4 = VIZ / b / "space_invaders" / "play_raw.mp4"
        subprocess.run(["ffmpeg", "-y", "-i", str(webm), "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", str(raw_mp4)], check=True, capture_output=True)
        m = metrics.get(b, {})
        secs = m.get("build_secs")
        score = m.get("score")
        sub = []
        if secs is not None:
            sub.append(f"built in {secs:.0f}s")
        if score is not None:
            sub.append(f"{score}/7 playable")
        capd = VIZ / b / "space_invaders" / "play_captioned.mp4"
        caption(raw_mp4, capd, PRETTY.get(b, b), "   ·   ".join(sub) or " ",
                COLORS.get(b, (88, 166, 255)))
        panes.append(capd)
        print(f"  [{b}] play captured -> {capd.name}", flush=True)

    if len(panes) >= 2:
        sbs = VIZ / "side_by_side.mp4"
        inputs = []
        for pth in panes:
            inputs += ["-i", str(pth)]
        n = len(panes)
        filt = "".join(f"[{i}:v]" for i in range(n)) + f"hstack=inputs={n}:shortest=1[v]"
        subprocess.run(["ffmpeg", "-y", *inputs, "-filter_complex", filt,
                        "-map", "[v]", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(sbs)],
                       check=True, capture_output=True)
        print(f"\nSIDE-BY-SIDE: {sbs}")
        # 2x-speed gif for slides
        gif = VIZ / "side_by_side_2x.gif"
        subprocess.run(["ffmpeg", "-y", "-i", str(sbs), "-vf",
                        "setpts=0.5*PTS,fps=14,scale=1280:-1:flags=lanczos", str(gif)],
                       check=True, capture_output=True)
        print(f"GIF (2x):     {gif}")
    else:
        print(f"only {len(panes)} pane(s) — need >=2 for side-by-side")


if __name__ == "__main__":
    main()
