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


def _encode_image_to_base64(file_path: Path) -> str:
    """Encode image file to base64 string."""
    return base64.b64encode(file_path.read_bytes()).decode()


async def _call_ollama_api(prompt: str, image_b64s: list[str]) -> str:
    """Call Ollama API with given prompt and base64-encoded images."""
    async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
        try:
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
        except httpx.HTTPError as e:
            return f"ERROR: vision call failed: {e}. Is Maral reachable at {OLLAMA_HOST}? Is {VISION_MODEL} pulled?"


def _validate_file(file_path: Path, allowed_extensions: set[str], max_size_bytes: int) -> str:
    """Validate file existence, format, and size. Return error message if invalid."""
    if not file_path.exists():
        return f"ERROR: file not found: {file_path}"
    if file_path.suffix.lower() not in allowed_extensions:
        return f"ERROR: unsupported file format: {file_path.suffix}"
    if file_path.stat().st_size > max_size_bytes:
        return f"ERROR: file too large: {file_path.stat().st_size} bytes (max {max_size_bytes} bytes)"
    return ""


def _build_error_message(error_type: str, file_path: Path) -> str:
    """Construct standardized error message for file validation failures."""
    return f"ERROR: {error_type}: {file_path}"


@mcp.tool()
async def describe_image(
    path: Annotated[str, "Absolute path to image file (PNG, JPG, JPEG, WEBP, GIF)"],
    prompt: Annotated[
        str,
        "What to look for in the image. Defaults to a general visual description.",
    ] = "Describe this image in detail. Identify any text, UI elements, charts, code, diagrams, or layout structure.",
) -> str:
    """Send an image to the local vision model and return a text description."""
    file_path = Path(path).expanduser().resolve()
    error = _validate_file(
        file_path,
        {".png", ".jpg", ".jpeg", ".webp", ".gif"},
        20 * 1024 * 1024,
    )
    if error:
        return error

    try:
        return await _call_ollama_api(prompt, [_encode_image_to_base64(file_path)])
    except Exception as e:
        return f"ERROR: unexpected error during vision call: {e}"


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
    file_path = Path(path).expanduser().resolve()
    error = _validate_file(file_path, {".pdf"}, 100 * 1024 * 1024)
    if error:
        return error

    try:
        from pypdf import PdfReader
    except ImportError:
        return "ERROR: pypdf not installed. Run: uv pip install pypdf"

    try:
        reader = PdfReader(str(file_path))
    except Exception as e:
        return f"ERROR: failed to parse PDF: {e}"

    total_pages = len(reader.pages)

    if page_range == "all":
        start_page, end_page = 0, total_pages
    else:
        try:
            start_str, end_str = page_range.split("-")
            start_page = max(0, int(start_str) - 1)
            end_page = min(total_pages, int(end_str))
        except (ValueError, AttributeError):
            return f"ERROR: invalid page_range: {page_range!r} (expected 'all' or 'N-M')"

    result_chunks = []
    for page_num in range(start_page, end_page):
        page = reader.pages[page_num]
        text = (page.extract_text() or "").strip()
        result_chunks.append(f"\n--- Page {page_num + 1}/{total_pages} ---\n{text}")

        if include_vision:
            try:
                from pdf2image import convert_from_path
                import io

                images = convert_from_path(
                    str(file_path), first_page=page_num + 1, last_page=page_num + 1, dpi=150
                )
                if images:
                    image_buffer = io.BytesIO()
                    images[0].save(image_buffer, format="PNG")
                    b64_image = base64.b64encode(image_buffer.getvalue()).decode()
                    vision_prompt = (
                        "Describe any figures, charts, diagrams, or visual layout on this PDF page "
                        "that are not captured by raw text extraction. Be concise."
                    )
                    vision_result = await _call_ollama_api(vision_prompt, [b64_image])
                    result_chunks.append(f"[vision] {vision_result}")
            except ImportError:
                result_chunks.append("[vision] SKIPPED — install pdf2image + pillow")
            except Exception as e:
                result_chunks.append(f"[vision] FAILED — {e}")

    return "\n".join(result_chunks)


def main() -> None:
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
