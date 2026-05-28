"""maral-vision — MCP server exposing image and PDF understanding via Ollama-hosted vision model.

Tools:
    describe_image(path, prompt?) -> str
    extract_pdf(path, page_range?, include_vision?) -> str
    ocr_screenshot(path) -> str  (vision-based OCR, useful for code screenshots)
"""

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Annotated

import httpx
from mcp.server.fastmcp import FastMCP

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://maral.local:11434")
VISION_MODEL = os.environ.get("MARAL_VISION_MODEL", "qwen2.5vl:7b")
TIMEOUT_S = float(os.environ.get("MARAL_VISION_TIMEOUT", "180"))

mcp = FastMCP("maral-vision")


def _b64_image(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode()


async def _vision_call(prompt: str, image_b64s: list[str]) -> str:
    async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
        resp = await client.post(
            f"{OLLAMA_HOST}/api/generate",
            json={
                "model": VISION_MODEL,
                "prompt": prompt,
                "images": image_b64s,
                "stream": False,
            },
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()


@mcp.tool()
async def describe_image(
    path: Annotated[str, "Absolute path to image file (PNG, JPG, JPEG, WEBP, GIF)"],
    prompt: Annotated[
        str,
        "What to look for in the image. Defaults to a general visual description.",
    ] = "Describe this image in detail. Identify any text, UI elements, charts, code, diagrams, or layout structure.",
) -> str:
    """Send an image to the local vision model and return a text description."""
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return f"ERROR: file not found: {p}"
    if p.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        return f"ERROR: unsupported image format: {p.suffix} (supported: png, jpg, jpeg, webp, gif)"
    if p.stat().st_size > 20 * 1024 * 1024:
        return f"ERROR: file too large: {p.stat().st_size} bytes (max 20MB)"

    try:
        return await _vision_call(prompt, [_b64_image(p)])
    except httpx.HTTPError as e:
        return f"ERROR: vision call failed: {e}. Is Maral reachable at {OLLAMA_HOST}? Is {VISION_MODEL} pulled?"


@mcp.tool()
async def ocr_screenshot(
    path: Annotated[str, "Absolute path to screenshot file"],
) -> str:
    """Vision-based OCR optimized for code screenshots. Returns extracted text/code verbatim."""
    return await describe_image(
        path,
        prompt=(
            "This is a screenshot. Extract ALL text verbatim, preserving exact formatting. "
            "If the screenshot contains code, return it as a fenced code block. "
            "If it contains a terminal or log output, return as plain text. "
            "Do not summarize or interpret — just transcribe."
        ),
    )


@mcp.tool()
async def extract_pdf(
    path: Annotated[str, "Absolute path to PDF file"],
    page_range: Annotated[
        str,
        "Page range like '1-5' or 'all'. Pages are 1-indexed.",
    ] = "all",
    include_vision: Annotated[
        bool,
        "If True, also send each page as image to vision model and merge with extracted text. Slow but catches embedded figures.",
    ] = False,
) -> str:
    """Extract text from a PDF. Optionally augment with vision-model description of each page."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return "ERROR: pypdf not installed. Run: uv pip install pypdf"

    p = Path(path).expanduser().resolve()
    if not p.exists():
        return f"ERROR: file not found: {p}"
    if p.suffix.lower() != ".pdf":
        return f"ERROR: not a PDF: {p.suffix}"

    try:
        reader = PdfReader(str(p))
    except Exception as e:
        return f"ERROR: failed to parse PDF: {e}"

    total = len(reader.pages)

    if page_range == "all":
        start, end = 0, total
    else:
        try:
            s, e = page_range.split("-")
            start, end = max(0, int(s) - 1), min(total, int(e))
        except (ValueError, AttributeError):
            return f"ERROR: invalid page_range: {page_range!r} (expected 'all' or 'N-M')"

    chunks: list[str] = []
    for i in range(start, end):
        page = reader.pages[i]
        text = (page.extract_text() or "").strip()
        chunks.append(f"\n--- Page {i+1}/{total} ---\n{text}")

        if include_vision:
            try:
                import io
                from pdf2image import convert_from_path

                images = convert_from_path(str(p), first_page=i + 1, last_page=i + 1, dpi=150)
                if images:
                    buf = io.BytesIO()
                    images[0].save(buf, format="PNG")
                    b64 = base64.b64encode(buf.getvalue()).decode()
                    desc = await _vision_call(
                        "Describe any figures, charts, diagrams, or visual layout on this PDF page that are not captured by raw text extraction. Be concise.",
                        [b64],
                    )
                    chunks.append(f"[vision] {desc}")
            except ImportError:
                chunks.append("[vision] SKIPPED — install pdf2image + pillow")
            except Exception as e:
                chunks.append(f"[vision] FAILED — {e}")

    return "\n".join(chunks)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
