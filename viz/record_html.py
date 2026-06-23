"""Record a self-contained HTML animation to mp4 + looping gif (for slide embedding).

Usage: python record_html.py <input.html> <out_prefix> <seconds> <width> <height>
e.g.   python record_html.py agent-race.html agent-race 18 1280 720
Produces <out_prefix>.mp4 and <out_prefix>.gif next to the html.
"""
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    html = Path(sys.argv[1]).resolve()
    prefix = sys.argv[2]
    secs = float(sys.argv[3])
    W, H = int(sys.argv[4]), int(sys.argv[5])
    outdir = html.parent

    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": W, "height": H},
                            record_video_dir=str(outdir / "_rec"),
                            record_video_size={"width": W, "height": H},
                            device_scale_factor=1)
        page = ctx.new_page()
        page.goto(html.as_uri())
        page.wait_for_timeout(int(secs * 1000))
        webm = Path(page.video.path())
        ctx.close(); b.close()

    mp4 = outdir / f"{prefix}.mp4"
    gif = outdir / f"{prefix}.gif"
    subprocess.run(["ffmpeg", "-y", "-i", str(webm), "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-t", f"{secs:.2f}", str(mp4)],
                   check=True, capture_output=True)
    subprocess.run(["ffmpeg", "-y", "-i", str(mp4), "-vf",
                    "fps=15,scale=1100:-1:flags=lanczos", str(gif)],
                   check=True, capture_output=True)
    # clean intermediate
    subprocess.run(["rm", "-rf", str(outdir / "_rec")], check=False)
    print(f"mp4: {mp4}\ngif: {gif}")


if __name__ == "__main__":
    main()
