"""maral-rag — Semantic search over a code directory, hosted on Maral.

Backs an embedding index using nomic-embed-text via Ollama + sqlite-vec for storage.
Lets the local model retrieve relevant chunks from large codebases without loading
them into its 32k context.

Tools:
    index_dir(path, glob?) -> str
    search(query, k?) -> list[dict]
    read_with_context(file, query?) -> str
    list_indexes() -> list[str]
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Annotated, Any

import httpx
from mcp.server.fastmcp import FastMCP

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://maral.local:11434")
EMBED_MODEL = os.environ.get("MARAL_EMBED_MODEL", "nomic-embed-text")
INDEX_DIR = Path(os.environ.get("MARAL_INDEX_DIR", "~/.local/share/maral-rag")).expanduser()
INDEX_DIR.mkdir(parents=True, exist_ok=True)

CHUNK_SIZE_TOKENS = 512  # rough token target per chunk
CHUNK_CHARS = CHUNK_SIZE_TOKENS * 4  # ~4 chars per token
CHUNK_OVERLAP = 80
EMBED_DIM = 768

# File globs we'll index by default
DEFAULT_INCLUDES = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".kt", ".rb",
    ".sh", ".zsh", ".bash", ".sql", ".md", ".mdx", ".txt", ".yaml", ".yml",
    ".toml", ".json", ".html", ".css", ".scss", ".vue", ".svelte",
    ".c", ".cpp", ".h", ".hpp", ".swift", ".m", ".mm",
}
DEFAULT_EXCLUDES = {
    "node_modules", ".git", ".venv", "venv", "__pycache__", "dist", "build",
    ".next", ".turbo", "target", ".cache", ".terraform", "vendor",
}

mcp = FastMCP("maral-rag")


def _index_path(root: str) -> Path:
    digest = hashlib.sha256(str(Path(root).expanduser().resolve()).encode()).hexdigest()[:16]
    return INDEX_DIR / f"{digest}.db"


def _connect(db_path: Path) -> sqlite3.Connection:
    import sqlite_vec

    conn = sqlite3.connect(str(db_path))
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.execute("CREATE TABLE IF NOT EXISTS meta (root TEXT PRIMARY KEY, indexed_at INTEGER)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chunks (
            rowid INTEGER PRIMARY KEY,
            file_path TEXT,
            start_byte INTEGER,
            end_byte INTEGER,
            content TEXT
        )
    """)
    conn.execute(
        f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0(embedding float[{EMBED_DIM}])"
    )
    return conn


async def _embed(text: str) -> list[float]:
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{OLLAMA_HOST}/api/embeddings",
            json={"model": EMBED_MODEL, "prompt": text},
        )
        resp.raise_for_status()
        return resp.json()["embedding"]


def _chunk(text: str) -> list[tuple[int, int, str]]:
    """Return list of (start_byte, end_byte, chunk_text)."""
    if len(text) <= CHUNK_CHARS:
        return [(0, len(text), text)]
    out = []
    i = 0
    while i < len(text):
        end = min(i + CHUNK_CHARS, len(text))
        out.append((i, end, text[i:end]))
        i += CHUNK_CHARS - CHUNK_OVERLAP
    return out


def _iter_files(root: Path, glob: str | None) -> list[Path]:
    if glob:
        return [p for p in root.rglob(glob) if p.is_file()]
    out = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if any(part in DEFAULT_EXCLUDES for part in p.parts):
            continue
        if p.suffix.lower() in DEFAULT_INCLUDES:
            out.append(p)
    return out


@mcp.tool()
async def index_dir(
    path: Annotated[str, "Absolute path to directory to index"],
    glob: Annotated[
        str,
        "Optional glob to restrict files (e.g. '**/*.py'). If empty, uses default include/exclude rules.",
    ] = "",
) -> str:
    """Build or rebuild a semantic search index over the given directory.

    Returns a summary string with file/chunk counts."""
    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        return f"ERROR: not a directory: {root}"

    db_path = _index_path(str(root))
    conn = _connect(db_path)

    # Wipe existing
    conn.execute("DELETE FROM chunks")
    conn.execute("DELETE FROM vec_chunks")

    files = _iter_files(root, glob or None)
    file_count = 0
    chunk_count = 0

    for fp in files:
        try:
            content = fp.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if not content.strip():
            continue
        for start, end, body in _chunk(content):
            try:
                emb = await _embed(body)
            except Exception as e:
                return f"ERROR: embedding failed on {fp}: {e}. Is {EMBED_MODEL} pulled on Ollama?"
            cur = conn.execute(
                "INSERT INTO chunks (file_path, start_byte, end_byte, content) VALUES (?, ?, ?, ?)",
                (str(fp), start, end, body),
            )
            rowid = cur.lastrowid
            conn.execute(
                "INSERT INTO vec_chunks (rowid, embedding) VALUES (?, ?)",
                (rowid, json.dumps(emb)),
            )
            chunk_count += 1
        file_count += 1

    import time as _t
    conn.execute(
        "INSERT OR REPLACE INTO meta (root, indexed_at) VALUES (?, ?)",
        (str(root), int(_t.time())),
    )
    conn.commit()
    conn.close()

    return (
        f"Indexed {file_count} files, {chunk_count} chunks from {root}\n"
        f"Index stored at {db_path}\n"
        f"Use search(query) to query."
    )


@mcp.tool()
async def search(
    query: Annotated[str, "Natural-language query"],
    root: Annotated[str, "Absolute path to the directory previously indexed"],
    k: Annotated[int, "Number of top results to return"] = 5,
) -> list[dict[str, Any]]:
    """Return the top-k most relevant chunks from the index for the given query."""
    db_path = _index_path(str(Path(root).expanduser().resolve()))
    if not db_path.exists():
        return [{"error": f"no index found at {db_path}; run index_dir({root!r}) first"}]

    conn = _connect(db_path)
    try:
        query_emb = await _embed(query)
    except Exception as e:
        return [{"error": f"embedding failed: {e}"}]

    rows = conn.execute(
        """
        SELECT chunks.file_path, chunks.start_byte, chunks.end_byte, chunks.content, vec_chunks.distance
        FROM vec_chunks
        JOIN chunks ON chunks.rowid = vec_chunks.rowid
        WHERE vec_chunks.embedding MATCH ?
        ORDER BY vec_chunks.distance
        LIMIT ?
        """,
        (json.dumps(query_emb), k),
    ).fetchall()
    conn.close()

    return [
        {
            "file": fp,
            "byte_range": f"{sb}-{eb}",
            "distance": dist,
            "preview": content[:300],
            "full_content": content,
        }
        for (fp, sb, eb, content, dist) in rows
    ]


@mcp.tool()
async def read_with_context(
    file: Annotated[str, "Absolute path to the file to read"],
    query: Annotated[
        str,
        "Optional query. If provided, also returns top-3 related chunks from elsewhere in the same index.",
    ] = "",
) -> str:
    """Read a file and optionally include related chunks from the rest of the index."""
    p = Path(file).expanduser().resolve()
    if not p.exists():
        return f"ERROR: file not found: {p}"

    body = p.read_text(encoding="utf-8", errors="ignore")
    out = [f"=== {p} ===\n{body}"]

    if query:
        # try to find an index covering this file
        for db_path in INDEX_DIR.glob("*.db"):
            conn = _connect(db_path)
            roots = [r for (r,) in conn.execute("SELECT root FROM meta").fetchall()]
            covering = next((r for r in roots if str(p).startswith(r)), None)
            if not covering:
                conn.close()
                continue
            try:
                query_emb = await _embed(query)
            except Exception:
                conn.close()
                continue
            rows = conn.execute(
                """
                SELECT chunks.file_path, chunks.content, vec_chunks.distance
                FROM vec_chunks
                JOIN chunks ON chunks.rowid = vec_chunks.rowid
                WHERE vec_chunks.embedding MATCH ? AND chunks.file_path != ?
                ORDER BY vec_chunks.distance
                LIMIT 3
                """,
                (json.dumps(query_emb), str(p)),
            ).fetchall()
            conn.close()
            if rows:
                out.append("\n=== Related chunks ===")
                for fp, content, dist in rows:
                    out.append(f"\n--- {fp} (distance={dist:.3f}) ---\n{content[:500]}")
            break

    return "\n".join(out)


@mcp.tool()
def list_indexes() -> list[dict[str, Any]]:
    """List all indexes built so far."""
    import sqlite_vec

    results = []
    for db_path in INDEX_DIR.glob("*.db"):
        conn = sqlite3.connect(str(db_path))
        try:
            for (root, indexed_at) in conn.execute("SELECT root, indexed_at FROM meta").fetchall():
                count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
                results.append(
                    {
                        "root": root,
                        "indexed_at": indexed_at,
                        "chunks": count,
                        "db": str(db_path),
                    }
                )
        finally:
            conn.close()
    return results


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
