"""maral-vision — MCP server exposing image and PDF understanding via Ollama-hosted vision model.

Tools:
    describe_image(path, prompt?) -> str
    extract_pdf(path, page_range?, include_vision?) -> str
    ocr_screenshot(path) -> str  (vision-based OCR, useful for code screenshots)
"""

from __future__ import annotations

import base64
import io
import os
from pathlib import Path
from typing import Annotated

import httpx
from mcp.server.fastmcp import FastMCP

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://maral.local:11434")
VISION_MODEL = os.environ.get("MARAL_VISION_MODEL", "qwen2.5vl:7b")
TIMEOUT_S = float(os.environ.get("MARAL_VISION_TIMEOUT", "180"))

SUPPORTED_IMAGE_EXTS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif"})
MAX_IMAGE_BYTES = 20 * 1024 * 1024  # 20 MB

OCR_PROMPT = (
    "This is a screenshot. Extract ALL text verbatim, preserving exact formatting. "
    "If the screenshot contains code, return it as a fenced code block. "
    "If it contains a terminal or log output, return as plain text. "
    "Do not summarize or interpret — just transcribe."
)
PDF_PAGE_VISION_PROMPT = (
    "Describe any figures, charts, diagrams, or visual layout on this PDF page that are not captured "
    "by raw text extraction. Be concise."
)

mcp = FastMCP("maral-vision")


def _resolve_path(path: str) -> Path:
    """Expand ~ and resolve relative segments, returning a normalized absolute Path."""
    return Path(path).expanduser().resolve()


def _validate_image_file(p: Path) -> str | None:
    """Return None if the path is a usable image file, else an `ERROR: ...` message string."""
    if not p.exists():
        return f"ERROR: file not found: {p}"
    if p.suffix.lower() not in SUPPORTED_IMAGE_EXTS:
        return (
            f"ERROR: unsupported image format: {p.suffix} "
            f"(supported: {', '.join(sorted(e.lstrip('.') for e in SUPPORTED_IMAGE_EXTS))})"
        )
    if p.stat().st_size > MAX_IMAGE_BYTES:
        return f"ERROR: file too large: {p.stat().st_size} bytes (max {MAX_IMAGE_BYTES})"
    return None


def _encode_image_b64(path: Path) -> str:
    """Read a file from disk and return its base64-encoded contents as a UTF-8 string."""
    return base64.b64encode(path.read_bytes()).decode()


def _encode_pil_image_b64(image) -> str:
    """Encode a PIL Image as base64 PNG bytes (used for PDF-page rasterization)."""
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


async def _vision_call(prompt: str, image_b64s: list[str]) -> str:
    """POST to Ollama's `/api/generate` with one or more base64 images and return the response text."""
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


def _vision_error(exc: Exception) -> str:
    """Build a uniform error message for failed vision calls."""
    return f"ERROR: vision call failed: {exc}. Is Maral reachable at {OLLAMA_HOST}? Is {VISION_MODEL} pulled?"


def _parse_page_range(page_range: str, total_pages: int) -> tuple[int, int] | str:
    """Parse an inclusive `'N-M'` or `'all'` string into a `(start, end)` slice over 0-indexed pages.

    Returns a `(start, end)` tuple suitable for `range(start, end)`, or an error message string.
    """
    if page_range == "all":
        return 0, total_pages
    try:
        s, e = page_range.split("-")
        return max(0, int(s) - 1), min(total_pages, int(e))
    except (ValueError, AttributeError):
        return f"ERROR: invalid page_range: {page_range!r} (expected 'all' or 'N-M')"


async def _describe_pdf_page_visually(pdf_path: Path, page_index: int) -> str:
    """Rasterize a single PDF page and run the vision model on it.

    Returns a `[vision] ...` annotated string. Falls back to a `[vision] SKIPPED/FAILED ...` line on error
    so the caller can keep extracting text without the whole call failing.
    """
    try:
        from pdf2image import convert_from_path
    except ImportError:
        return "[vision] SKIPPED — install pdf2image + pillow"
    try:
        images = convert_from_path(
            str(pdf_path), first_page=page_index + 1, last_page=page_index + 1, dpi=150
        )
        if not images:
            return "[vision] FAILED — no image rendered"
        b64 = _encode_pil_image_b64(images[0])
        return f"[vision] {await _vision_call(PDF_PAGE_VISION_PROMPT, [b64])}"
    except Exception as exc:
        return f"[vision] FAILED — {exc}"


@mcp.tool()
async def describe_image(
    path: Annotated[str, "Absolute path to image file (PNG, JPG, JPEG, WEBP, GIF)"],
    prompt: Annotated[
        str,
        "What to look for in the image. Defaults to a general visual description.",
    ] = "Describe this image in detail. Identify any text, UI elements, charts, code, diagrams, or layout structure.",
) -> str:
    """Send an image to the local vision model and return a text description."""
    p = _resolve_path(path)
    if (err := _validate_image_file(p)) is not None:
        return err
    try:
        return await _vision_call(prompt, [_encode_image_b64(p)])
    except httpx.HTTPError as exc:
        return _vision_error(exc)


@mcp.tool()
async def ocr_screenshot(
    path: Annotated[str, "Absolute path to screenshot file"],
) -> str:
    """Vision-based OCR optimized for code screenshots. Returns extracted text/code verbatim."""
    return await describe_image(path, prompt=OCR_PROMPT)


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

    p = _resolve_path(path)
    if not p.exists():
        return f"ERROR: file not found: {p}"
    if p.suffix.lower() != ".pdf":
        return f"ERROR: not a PDF: {p.suffix}"

    try:
        reader = PdfReader(str(p))
    except Exception as exc:
        return f"ERROR: failed to parse PDF: {exc}"

    total = len(reader.pages)
    parsed = _parse_page_range(page_range, total)
    if isinstance(parsed, str):
        return parsed
    start, end = parsed

    chunks: list[str] = []
    for i in range(start, end):
        text = (reader.pages[i].extract_text() or "").strip()
        chunks.append(f"\n--- Page {i+1}/{total} ---\n{text}")
        if include_vision:
            chunks.append(await _describe_pdf_page_visually(p, i))

    return "\n".join(chunks)


def main() -> None:
    """Entrypoint: start the FastMCP stdio server."""
    mcp.run()


if __name__ == "__main__":
    main()
