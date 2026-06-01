"""mlx-server — Anthropic /v1/messages wrapper around mlx_lm.generate.

Bypasses the broken mlx_lm.server (hangs on 14B load per Act 14). Uses the
working in-process `mlx_lm.load + generate` path.

v0.5 scope (this file):
  - POST /v1/messages[?beta=true]   text + tool_use + KV-cache reuse
  - GET  /api/version               returns "0.24.0" so the zshrc healthcheck passes
  - GET  /v1/models                 returns the single loaded model
  - HEAD /                          returns 200 (Claude Code probe)
  - --kv-bits / --kv-group-size     forwarded to mlx_lm.generate_step; quantizes
                                    KV cache for 2-4x memory reduction
  - --prefill-step-size             chunks the prefill pass; reduces peak Metal
                                    command buffer memory on long prompts.
                                    Default 2048. Lower to 512 if 16GB OOMs.
  - --quantized-kv-start            tokens to keep at fp16 before switching to
                                    quantized KV. Default 0 (quantize from start).

Prompt-cache reuse:
  Across requests we keep one (cache, cached_token_ids) pair. On each new
  request we (a) tokenize, (b) compute the longest common prefix vs the last
  cached tokens, (c) trim the cache back to that prefix length, (d) feed only
  the delta tokens as prefill, (e) generate. For Claude Code's pattern
  (system + history + new turn), this turns a 29k-token re-prefill on every
  tool call into a small delta.

Streaming is v0.4. Speculative decoding via draft model is v0.5.

Run on Maral:
    cd ~/mlx
    ./.venv/bin/python ~/mlx/server.py \
        --model mlx-community/Qwen3-8B-4bit \
        --host 0.0.0.0 --port 11435

Default port 11435 (not 11434) so this can coexist with Ollama for A/B
benching.

Cross-subnet rDNS hang (Act 14 / Act 15) is mitigated by overriding
BaseHTTPRequestHandler.address_string — Python stdlib's default does a reverse
DNS lookup on every client, which hangs ~10s on cross-subnet WiFi clients.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mlx-server")

MODEL_NAME: str | None = None
MODEL = None
TOKENIZER = None

# Single mutable cache shared across requests. mlx_lm caches are stateful and
# not safe to use concurrently — serialize requests via GEN_LOCK.
CACHE: Any = None
CACHED_TOKENS: list[int] = []
GEN_LOCK = threading.Lock()

# Reuse the cache only when prefix is "worth it" — short prefixes have no
# meaningful prefill cost saved.
CACHE_MIN_PREFIX = 256

# Quantized KV cache + prefill chunking. Forwarded to mlx_lm.generate_step.
KV_BITS: int | None = None        # None = fp16; 4 or 8 enables quantized KV
KV_GROUP_SIZE: int = 64
QUANTIZED_KV_START: int = 0       # tokens of fp16 KV before switching to quantized
PREFILL_STEP_SIZE: int = 2048     # chunked prefill; lower to ~512 if OOM on long prompts
NUM_LAYERS: int = 0               # populated after model load

# Qwen3 emits these literal tags. Compile once.
THINK_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL)
TOOL_CALL_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)


def load_model(model_id: str) -> None:
    global MODEL, TOKENIZER, MODEL_NAME, NUM_LAYERS
    from mlx_lm import load

    t0 = time.time()
    log.info("loading model %s", model_id)
    MODEL, TOKENIZER = load(model_id)
    MODEL_NAME = model_id
    NUM_LAYERS = len(MODEL.layers) if hasattr(MODEL, "layers") else (
        MODEL.args.num_hidden_layers if hasattr(MODEL, "args") else 0
    )
    log.info("loaded in %.2fs num_layers=%d", time.time() - t0, NUM_LAYERS)


def _new_cache() -> list:
    """Build a fresh fp16 prompt cache. mlx_lm.generate handles quantization
    internally when kv_bits is forwarded — pre-quantizing here triggers OOM
    during prefill chunks on 16GB hardware (the prefill compute is the issue,
    not steady-state KV storage)."""
    from mlx_lm.models.cache import make_prompt_cache
    return make_prompt_cache(MODEL)


# ---- Anthropic -> Qwen3 prompt rendering --------------------------------------

def _text_of(content: Any) -> str:
    """Best-effort flatten Anthropic content (string or list of blocks) to text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict):
                t = b.get("type")
                if t == "text":
                    parts.append(b.get("text", ""))
                elif t == "tool_use":
                    parts.append(
                        f'<tool_call>{json.dumps({"name": b.get("name"), "arguments": b.get("input", {})})}</tool_call>'
                    )
                elif t == "tool_result":
                    inner = b.get("content", "")
                    if isinstance(inner, list):
                        inner = "\n".join(x.get("text", "") for x in inner if isinstance(x, dict))
                    parts.append(str(inner))
            elif isinstance(b, str):
                parts.append(b)
        return "\n".join(parts)
    return str(content)


def _to_qwen3_messages(messages: list[dict]) -> list[dict]:
    out = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "user" and isinstance(content, list):
            tool_results = [b for b in content if isinstance(b, dict) and b.get("type") == "tool_result"]
            other = [b for b in content if not (isinstance(b, dict) and b.get("type") == "tool_result")]
            for tr in tool_results:
                out.append({"role": "tool", "content": _text_of(tr.get("content", ""))})
            if other:
                out.append({"role": "user", "content": _text_of(other)})
            continue
        out.append({"role": role, "content": _text_of(content)})
    return out


def _render_prompt(messages: list[dict], tools: list[dict] | None) -> str:
    qwen_msgs = _to_qwen3_messages(messages)
    kw: dict[str, Any] = {"tokenize": False, "add_generation_prompt": True}
    if tools:
        kw["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": t.get("name"),
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema", {"type": "object"}),
                },
            }
            for t in tools
        ]
    try:
        return TOKENIZER.apply_chat_template(qwen_msgs, **kw)
    except Exception as e:
        log.warning("apply_chat_template failed (%s); falling back to plain concat", e)
        return "\n".join(f"{m['role']}: {m['content']}" for m in qwen_msgs)


# ---- Qwen3 output -> Anthropic content blocks --------------------------------

def _parse_qwen3_output(text: str) -> tuple[list[dict], bool]:
    spans: list[tuple[int, int, str, Any]] = []
    for m in THINK_RE.finditer(text):
        spans.append((m.start(), m.end(), "thinking", m.group(1).strip()))
    for m in TOOL_CALL_RE.finditer(text):
        body = m.group(1)
        try:
            obj = json.loads(body)
        except json.JSONDecodeError:
            log.warning("malformed tool_call JSON; emitting as text: %s", body[:80])
            continue
        spans.append((m.start(), m.end(), "tool_use", obj))
    spans.sort(key=lambda s: s[0])

    blocks: list[dict] = []
    cursor = 0
    tool_use_present = False
    for start, end, kind, payload in spans:
        if start > cursor:
            txt = text[cursor:start].strip()
            if txt:
                blocks.append({"type": "text", "text": txt})
        if kind == "thinking":
            blocks.append({"type": "thinking", "thinking": payload})
        elif kind == "tool_use":
            tool_use_present = True
            blocks.append({
                "type": "tool_use",
                "id": f"toolu_{uuid.uuid4().hex[:24]}",
                "name": payload.get("name", ""),
                "input": payload.get("arguments", payload.get("input", {})),
            })
        cursor = end
    if cursor < len(text):
        tail = text[cursor:].strip()
        if tail:
            blocks.append({"type": "text", "text": tail})
    if not blocks:
        blocks.append({"type": "text", "text": text})
    return blocks, tool_use_present


# ---- Cache helpers -----------------------------------------------------------

def _lcp(a: list[int], b: list[int]) -> int:
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            return i
    return n


def _reset_cache() -> None:
    global CACHE, CACHED_TOKENS
    CACHE = _new_cache()
    CACHED_TOKENS = []


# ---- Generation --------------------------------------------------------------

def generate_once(messages: list[dict], tools: list[dict] | None, max_tokens: int) -> dict:
    global CACHE, CACHED_TOKENS
    from mlx_lm import generate
    from mlx_lm.models.cache import trim_prompt_cache
    from mlx_lm.sample_utils import make_sampler

    prompt_text = _render_prompt(messages, tools)
    new_tokens = TOKENIZER.encode(prompt_text)

    with GEN_LOCK:
        if CACHE is None:
            CACHE = _new_cache()
            CACHED_TOKENS = []

        common = _lcp(CACHED_TOKENS, new_tokens)
        prefix_tokens_reused = common
        discarded = len(CACHED_TOKENS) - common
        rebuilt = False

        if common < CACHE_MIN_PREFIX:
            # Not worth it; rebuild from scratch.
            CACHE = _new_cache()
            common = 0
            discarded = 0
            rebuilt = True
        elif discarded > 0:
            # trim_prompt_cache MUTATES in place and returns the int count;
            # do not reassign CACHE.
            actually_trimmed = trim_prompt_cache(CACHE, discarded)
            if actually_trimmed != discarded:
                # Some KVCache layers refused to trim (e.g., not enough offset).
                # Cache state is inconsistent — rebuild from scratch.
                log.warning(
                    "trim mismatch: asked=%d trimmed=%d; rebuilding cache",
                    discarded, actually_trimmed,
                )
                CACHE = _new_cache()
                common = 0
                discarded = 0
                rebuilt = True

        prefill = new_tokens[common:]

        # Edge case: full prompt is already in cache (CC sent identical prompt
        # twice, e.g. on retry). mlx_lm refuses an empty prompt. Roll back one
        # token from the cache so we have a 1-token prefill to feed it.
        if not prefill and common > 0:
            extra = trim_prompt_cache(CACHE, 1)
            if extra == 1:
                common -= 1
                discarded += 1
                prefill = new_tokens[common:]
                log.info("empty-prefill rollback: re-prefilling last token")

        log.info(
            "cache: reused=%d prefill_new=%d discarded=%d rebuilt=%s",
            prefix_tokens_reused if not rebuilt else 0, len(prefill), discarded, rebuilt,
        )

        sampler = make_sampler(temp=0.6, top_p=0.95)
        gen_kwargs: dict = {
            "prompt_cache": CACHE,
            "prefill_step_size": PREFILL_STEP_SIZE,
        }
        if KV_BITS is not None:
            gen_kwargs["kv_bits"] = KV_BITS
            gen_kwargs["kv_group_size"] = KV_GROUP_SIZE
            gen_kwargs["quantized_kv_start"] = QUANTIZED_KV_START
        t0 = time.time()
        try:
            text = generate(
                MODEL, TOKENIZER,
                prompt=prefill,
                max_tokens=max_tokens,
                sampler=sampler,
                **gen_kwargs,
            )
        except Exception as e:
            # On error (commonly Metal OOM) reset cache to avoid keeping a
            # half-corrupt state. Re-raise so the caller returns HTTP 500.
            log.exception("generate failed; resetting cache")
            _reset_cache()
            raise
        wall = time.time() - t0
        output_tokens_list = TOKENIZER.encode(text)
        # After generate, cache state = prefix + prefill + output tokens.
        CACHED_TOKENS = new_tokens + output_tokens_list

    output_tokens = len(output_tokens_list)
    input_tokens = len(new_tokens)
    decode_tps = output_tokens / wall if wall else 0
    log.info(
        "generate: in=%d out=%d wall=%.2fs decode=%.2f tok/s tools=%s",
        input_tokens, output_tokens, wall, decode_tps, bool(tools),
    )

    blocks, tool_use_present = _parse_qwen3_output(text)
    if tool_use_present:
        stop_reason = "tool_use"
    elif output_tokens >= max_tokens:
        stop_reason = "max_tokens"
    else:
        stop_reason = "end_turn"

    return {
        "id": f"msg_{uuid.uuid4().hex[:24]}",
        "type": "message",
        "role": "assistant",
        "model": MODEL_NAME,
        "content": blocks,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
    }


# ---- HTTP --------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    def address_string(self) -> str:
        return self.client_address[0] if self.client_address else "-"

    def log_message(self, fmt: str, *args) -> None:
        log.info("%s - %s", self.address_string(), fmt % args)

    def _send_json(self, status: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_HEAD(self) -> None:
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/version":
            self._send_json(200, {"version": "0.24.0"})
            return
        if path == "/v1/models":
            self._send_json(200, {
                "object": "list",
                "data": [{"id": MODEL_NAME, "object": "model"}],
            })
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError as e:
            self._send_json(400, {"error": f"bad json: {e}"})
            return

        path = urlparse(self.path).path
        if path.rstrip("/").endswith("/v1/messages"):
            try:
                resp = generate_once(
                    payload.get("messages", []),
                    payload.get("tools"),
                    int(payload.get("max_tokens", 256)),
                )
            except Exception as e:
                log.exception("generate failed")
                self._send_json(500, {"error": str(e)})
                return
            self._send_json(200, resp)
            return

        self._send_json(404, {"error": "not found"})


def main() -> int:
    global KV_BITS, KV_GROUP_SIZE, QUANTIZED_KV_START, PREFILL_STEP_SIZE
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True, help="HF model id or local path")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=11435)
    p.add_argument("--kv-bits", type=int, choices=[4, 8], default=None,
                   help="Quantize KV cache to 4 or 8 bits via mlx_lm. Omit for FP16.")
    p.add_argument("--kv-group-size", type=int, default=64)
    p.add_argument("--quantized-kv-start", type=int, default=0,
                   help="Tokens to keep at fp16 before switching to quantized KV.")
    p.add_argument("--prefill-step-size", type=int, default=2048,
                   help="Chunk size for prefill; lower (512/256) reduces Metal OOM risk on long prompts.")
    args = p.parse_args()

    KV_BITS = args.kv_bits
    KV_GROUP_SIZE = args.kv_group_size
    QUANTIZED_KV_START = args.quantized_kv_start
    PREFILL_STEP_SIZE = args.prefill_step_size
    load_model(args.model)
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    log.info(
        "listening on http://%s:%d (model=%s, kv_bits=%s, prefill_step=%d)",
        args.host, args.port, args.model,
        "fp16" if KV_BITS is None else str(KV_BITS), PREFILL_STEP_SIZE,
    )
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        log.info("shutting down")
    return 0


if __name__ == "__main__":
    sys.exit(main())
