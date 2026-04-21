import os
import re
import json
import logging
import time
from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse
import uvicorn
from litellm import completion

# ── Kimi K2.5 token garbage filter ───────────────────────────────────────────
# Kimi sometimes leaks internal chain-of-thought as Python-repr content blocks.
# These patterns are NEVER valid response text and must be stripped.
# NOTE: "functions." is intentionally NOT in this global list — it caused false
# positives when models wrote Python code with "functions." in plain text.
# It is only checked inside the Kimi-specific buffer section.
_GARBAGE_PREFIXES = (
    "[{'type':", '[{"type":',   # Python repr of Anthropic content blocks
    "<|tool_call",              # raw Kimi special tokens
)

# Hard cap on Kimi buffer size to prevent unbounded memory growth.
# If a response exceeds this without emitting a clean flush, the buffer is
# force-flushed as plain text (minus any garbage prefix).
_KIMI_BUFFER_MAX_CHARS = 8192

def _is_garbage_text(text: str) -> bool:
    t = text.strip()
    return any(t.startswith(p) for p in _GARBAGE_PREFIXES)


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("arbiter_runtime.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("arbiter")

app = FastAPI(title="Arbiter Bridge")

# ── Model roster ──────────────────────────────────────────────────────────────
# Two-tier setup:
#   Elite        : Kimi K2.5 by default, overridable via NVIDIA_ELITE_MODEL env var
#   Speed/Fallback: Kimi K2 0905 — always fixed; never overridden by model selection
#
# NVIDIA_ELITE_MODEL is set by start_nvidia_brain.bat's model selection menu.
# It replaces the elite slot only — the speed/fallback chain is untouched.
# Strip "openai/" prefix if the user pasted a full LiteLLM string by mistake.
_env_elite = os.environ.get("NVIDIA_ELITE_MODEL", "").strip().removeprefix("openai/")
_elite_base = _env_elite if _env_elite else "moonshotai/kimi-k2.5"

ELITE_MODEL    = f"openai/{_elite_base}"
ELITE_FALLBACK = "openai/moonshotai/kimi-k2-instruct-0905"
SPEED_MODEL    = "openai/moonshotai/kimi-k2-instruct-0905"
UI_MODEL       = ELITE_MODEL  # GLM unavailable on NIM — elite model handles UI too

if _env_elite:
    logger.info(f"[*] Elite model overridden by env: {ELITE_MODEL}")

# ── Per-model tool cap ────────────────────────────────────────────────────────
# Some NIM models silently hang with Claude Code's full 59-tool payload.
# Kimi K2.5 is confirmed stable at 59 tools.
# Add entries here for any model that hangs: { "model-name-fragment": max_tools }
MAX_TOOLS_PER_MODEL: dict[str, int] = {}

# Request timeout — prevents silent hangs from consuming the fallback window.
REQUEST_TIMEOUT = 90

# ── Task-aware routing ────────────────────────────────────────────────────────
TASK_MODELS = {
    "coding":      ELITE_MODEL,
    "reasoning":   ELITE_MODEL,
    "longcontext": ELITE_MODEL,
    "ui_complex":  UI_MODEL,
    "ui_quick":    UI_MODEL,
    "vision":      ELITE_MODEL,
    "agentic":     ELITE_MODEL,
    "fast":        SPEED_MODEL,   # summarize/define/translate → speed tier
    "fallback":    ELITE_MODEL,
}

# Models where enable_thinking=True is wrong, slow, or unsupported.
# Kimi uses reasoning_content field, not a template kwarg.
# Add fragment strings here for any model that errors on enable_thinking.
_THINKING_OFF_FRAGMENTS = (
    "kimi-k2",     # K2.5 and K2 0905 — reasoning via reasoning_content field
    "mistral",     # Mistral Large 2 — no thinking support on NIM
    "llama",       # Llama models — no thinking template support
    "qwen3",       # Qwen3 Coder — uses its own reasoning, not enable_thinking
    "deepseek",    # DeepSeek R1 — reasoning built-in, enable_thinking unsupported
)

def _should_think(model: str) -> bool:
    """Return True only for models that support enable_thinking=True."""
    m = model.lower()
    return not any(frag in m for frag in _THINKING_OFF_FRAGMENTS)


# ── Task classification ───────────────────────────────────────────────────────
# Compiled patterns, ordered by priority in _TASK_PRIORITY below.
TASK_PATTERNS = {
    "coding": re.compile(
        r'\b(code|debug|implement|function|bug|error|script|class|refactor|syntax|compile|'
        r'api\s+endpoint|programming|typescript|javascript|python|rust|golang|'
        r'dockerfile|kubernetes|sql\s+query|unit\s+test|test\s+case|pull\s+request|'
        r'stack\s+trace|traceback|exception|linter|eslint|prettier)\b',
        re.IGNORECASE
    ),
    "ui_complex": re.compile(
        r'\b(design\s+system|component\s+library|architecture\s+for\s+(ui|ux|frontend)|'
        r'multi[\s\-]?step\s+(ui|interface|flow)|information\s+architecture|'
        r'wireframe\s+spec|accessibility\s+audit|design\s+token|figma\s+to\s+code|'
        r'responsive\s+layout\s+system|full\s+page\s+(design|layout)|'
        r'complex\s+(ui|ux|interface|component))\b',
        re.IGNORECASE
    ),
    "ui_quick": re.compile(
        r'\b(ui|ux|frontend|html|css|tailwind|react\s+component|vue\s+component|'
        r'navbar|button|card|modal|form|dropdown|sidebar|layout|landing\s+page|'
        r'color\s+palette|icon|figma|framer|shadcn|chakra|material\s+ui|'
        r'animate|transition|hover|flex|grid\s+layout)\b',
        re.IGNORECASE
    ),
    "reasoning": re.compile(
        r'\b(calculate|prove|analyze|plan|strategy|architecture|optimize|algorithm|'
        r'math|logic|theorem|hypothesis|proof|statistical|probability|'
        r'system\s+design|tradeoff|compare\s+approaches|why\s+does|'
        r'explain\s+how|break\s+down|step[\s\-]?by[\s\-]?step\s+plan)\b',
        re.IGNORECASE
    ),
    "longcontext": re.compile(
        r'\b(entire\s+(codebase|repository|repo)|all\s+files|'
        r'read\s+everything|full\s+context|summarize\s+(this\s+)?repo|'
        r'across\s+(all|multiple)\s+files|large\s+document|'
        r'1\s*million\s*token|very\s+long|extensive\s+context)\b',
        re.IGNORECASE
    ),
    "fast": re.compile(
        r'\b(what\s+is|define|summarize|translate|list\s+(the\s+)?\d+|'
        r'quick\s+(question|answer)|simple\s+(question|task)|'
        r'one[\s\-]?liner|tl;?dr|spell\s+check|fix\s+grammar|'
        r'convert\s+(this\s+)?(to|from))\b',
        re.IGNORECASE
    ),
}

# Priority order — first match wins.
# ui_complex before ui_quick so architecture requests aren't cheapened.
# ui_quick before coding so "Create a React component" routes to UI model.
_TASK_PRIORITY = ["ui_complex", "ui_quick", "coding", "reasoning", "longcontext", "fast"]

def classify_task(messages: list) -> str | None:
    """
    Scan the last 2 user messages and return a task key, or None.
    Priority: ui_complex > ui_quick > coding > reasoning > longcontext > fast.
    """
    user_texts = []
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, list):
                content = " ".join(
                    c.get("text", "") for c in content
                    if isinstance(c, dict) and c.get("type") == "text"
                )
            user_texts.append(content)
            if len(user_texts) == 2:
                break
    combined = " ".join(user_texts)
    if not combined.strip():
        return None
    for task in _TASK_PRIORITY:
        if TASK_PATTERNS[task].search(combined):
            return task
    return None


MODEL_MAX_TOKENS = {
    "openai/moonshotai/kimi-k2.5":             32768,
    "openai/moonshotai/kimi-k2-instruct-0905": 32768,
    # Custom/unknown models fall back to 32768 (safe default)
}
# Ensure the selected elite model always has a max_tokens entry
MODEL_MAX_TOKENS.setdefault(ELITE_MODEL, 32768)

# Maps Claude model aliases (what CC sends) → NVIDIA NIM model strings.
# Add new aliases here as needed.
MODEL_MAP = {
    "claude-haiku-4-5-20251001":  SPEED_MODEL,
    "claude-3-5-sonnet-20241022": ELITE_MODEL,
    "claude-3-5-sonnet":          ELITE_MODEL,
    "claude-sonnet-4-6":          ELITE_MODEL,
}

# Models that are never overridden by task routing (pinned to exact target).
_PINNED_MODELS: set[str] = set()

# ── Helpers ───────────────────────────────────────────────────────────────────
def clean_tools(tools):
    """Normalise Anthropic-format tool definitions to OpenAI function format."""
    if not tools:
        return None
    cleaned = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        name   = tool.get("name")
        desc   = tool.get("description", "")
        params = tool.get("parameters") or tool.get("input_schema")
        if name and params:
            cleaned.append({"type": "function", "function": {"name": name, "description": desc, "parameters": params}})
        elif "function" in tool:
            f = tool["function"]
            cleaned.append({"type": "function", "function": {
                "name":        f.get("name"),
                "description": f.get("description", ""),
                "parameters":  f.get("parameters") or f.get("input_schema"),
            }})
        else:
            cleaned.append(tool)
    return cleaned


def normalize_messages(messages):
    """
    Convert Anthropic message format to OpenAI format.
    Handles: system, assistant (text + tool_use), user (text + tool_result).
    """
    normalized = []
    for msg in messages:
        role    = msg.get("role")
        content = msg.get("content")

        if role == "system":
            if isinstance(content, list):
                content = "".join(c.get("text", "") for c in content if isinstance(c, dict))
            normalized.append({"role": "system", "content": content})

        elif role == "assistant":
            if isinstance(content, list):
                text_content = ""
                tool_calls   = []
                for block in content:
                    if block.get("type") == "text":
                        t = block.get("text", "")
                        if not _is_garbage_text(t):
                            text_content += t
                    elif block.get("type") == "tool_use":
                        tool_calls.append({
                            "id":   block.get("id"),
                            "type": "function",
                            "function": {
                                "name":      block.get("name"),
                                "arguments": json.dumps(block.get("input", {})),
                            },
                        })
                new_msg = {"role": "assistant", "content": text_content or None}
                if tool_calls:
                    new_msg["tool_calls"] = tool_calls
                normalized.append(new_msg)
            else:
                normalized.append(msg)

        elif role == "user":
            if isinstance(content, list):
                tool_results = [c for c in content if isinstance(c, dict) and c.get("type") == "tool_result"]
                if tool_results:
                    for res in tool_results:
                        rc = res.get("content")
                        if isinstance(rc, list):
                            rc = "".join(c.get("text", "") for c in rc if isinstance(c, dict))
                        normalized.append({
                            "role":         "tool",
                            "tool_call_id": res.get("tool_use_id"),
                            "content":      str(rc) if rc is not None else "",
                        })
                    text_parts = "".join(c.get("text", "") for c in content
                                         if isinstance(c, dict) and c.get("type") == "text")
                    if text_parts:
                        normalized.append({"role": "user", "content": text_parts})
                else:
                    text_parts = "".join(c.get("text", "") for c in content if isinstance(c, dict))
                    normalized.append({"role": "user", "content": text_parts})
            else:
                normalized.append(msg)

        else:
            normalized.append(msg)

    return normalized


def trim_tools(tools: list | None, model: str) -> list | None:
    """
    Cap tool list to MAX_TOOLS_PER_MODEL[model] if a limit is configured.
    Tools are sorted by name for a deterministic, reproducible subset.
    """
    if not tools:
        return tools
    model_key = model.removeprefix("openai/")
    cap = None
    for fragment, limit in MAX_TOOLS_PER_MODEL.items():
        if fragment in model_key:
            cap = limit
            break
    if cap is None or len(tools) <= cap:
        return tools
    trimmed = sorted(tools, key=lambda t: (
        t.get("function", t).get("name", "") if isinstance(t, dict) else ""
    ))[:cap]
    logger.warning(
        f"[!] Tool cap: {model_key} limit={cap}, "
        f"trimmed {len(tools)} → {len(trimmed)} tools"
    )
    return trimmed


def safe_json(obj) -> str:
    """json.dumps with a fallback for non-serialisable values."""
    try:
        return json.dumps(obj)
    except (TypeError, ValueError):
        return json.dumps(obj, default=str)


def _estimate_input_tokens(messages: list, tools: list) -> int:
    """
    Fast token estimator: ~4 chars per token.
    Pre-fills message_start so CC never sees a placeholder '1' for input_tokens,
    avoiding the 'undefined is not an object (evaluating $.input_tokens)' crash.
    """
    total_chars = 0
    for m in (messages or []):
        content = m.get("content", "")
        if isinstance(content, str):
            total_chars += len(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    total_chars += len(block.get("text", "") or block.get("content", ""))
    if tools:
        total_chars += len(tools) * 800  # ~200 tokens per tool schema
    return max(1, total_chars // 4)


def _call(model, messages, tools, body):
    extra_body = {}
    if _should_think(model):
        extra_body = {"chat_template_kwargs": {"enable_thinking": True, "clear_thinking": False}}

    capped_tools = trim_tools(tools, model)

    return completion(
        model=model,
        messages=messages,
        tools=capped_tools,
        tool_choice=body.get("tool_choice"),
        temperature=0.2,
        max_tokens=MODEL_MAX_TOKENS.get(model, 32768),
        stream=True,
        api_base="https://integrate.api.nvidia.com/v1",
        api_key=os.environ.get("NVIDIA_API_KEY"),
        drop_params=True,
        timeout=REQUEST_TIMEOUT,
        extra_headers={"X-NVIDIA-Source": "Claude-Code-Bridge"},
        extra_body=extra_body,
    )


def call_with_fallback(nvidia_model, messages, tools, body):
    """
    Three-tier cascade: target → ELITE_FALLBACK → SPEED_MODEL.
    Retriable errors (429/DEGRADED/502/503) step to the next tier with a
    short back-off. Non-retriable errors fail fast.
    Each tier is tried at most once.
    """
    def _is_retriable(err: str) -> bool:
        return any(code in err for code in ("429", "DEGRADED", "503", "502"))

    chain = list(dict.fromkeys([nvidia_model, ELITE_FALLBACK, SPEED_MODEL]))

    last_exc = None
    for idx, model in enumerate(chain):
        try:
            if idx > 0:
                sleep_s = 2 * idx
                logger.warning(f"[!] Falling back to {model} (sleeping {sleep_s}s)...")
                time.sleep(sleep_s)
            return _call(model, messages, tools, body)
        except Exception as e:
            last_exc = e
            if not _is_retriable(str(e)):
                raise
            logger.warning(f"[!] {model} failed: {str(e)[:80]}")

    raise last_exc


# ── Routes ────────────────────────────────────────────────────────────────────
@app.get("/")
@app.head("/")
async def health():
    return {
        "status":        "online",
        "engine":        "Arbiter",
        "elite_model":   ELITE_MODEL,
        "speed_model":   SPEED_MODEL,
    }


@app.get("/v1/models")
async def list_models():
    """CC may probe this endpoint; return the supported model roster."""
    models = [
        {
            "id": alias, "object": "model", "created": 1700000000,
            "owned_by": "arbiter", "context_window": 131072,
        }
        for alias in MODEL_MAP
    ]
    return {"object": "list", "data": models}


@app.post("/v1/messages/count_tokens")
async def count_tokens(request: Request):
    """CC 2.1.114+ calls this for context budget management before agentic loops.

    CC accesses the result as both response.input_tokens AND response.usage.input_tokens
    depending on version. We return both shapes to avoid the
    'undefined is not an object (evaluating $.input_tokens)' crash.
    """
    try:
        body       = await request.json()
        messages   = list(body.get("messages", []))
        system_msg = body.get("system")
        if system_msg:
            if isinstance(system_msg, str):
                messages.insert(0, {"role": "system", "content": system_msg})
            elif isinstance(system_msg, list):
                content = "".join(m.get("text", "") for m in system_msg if isinstance(m, dict))
                messages.insert(0, {"role": "system", "content": content})

        total_chars = sum(len(str(m.get("content", ""))) for m in messages)
        tool_chars  = sum(len(str(t)) for t in (body.get("tools") or []))
        estimated   = max(1, (total_chars + tool_chars) // 4)
        # Return both top-level and nested under "usage" — CC versions differ on which they read.
        return {"input_tokens": estimated, "usage": {"input_tokens": estimated}}
    except Exception as e:
        logger.error(f"[!] count_tokens error: {e}")
        return {"input_tokens": 1000, "usage": {"input_tokens": 1000}}


@app.post("/v1/messages")
@app.post("/v1/chat/completions")
async def handle_request(request: Request):
    body = None
    try:
        body         = await request.json()
        model_name   = body.get("model", "claude-haiku-4-5-20251001")
        nvidia_model = MODEL_MAP.get(model_name, model_name)
        if not nvidia_model.startswith("openai/"):
            nvidia_model = "openai/" + nvidia_model

        messages   = list(body.get("messages", []))
        system_msg = body.get("system")
        if system_msg:
            if isinstance(system_msg, str):
                messages.insert(0, {"role": "system", "content": system_msg})
            elif isinstance(system_msg, list):
                content = "".join(m.get("text", "") for m in system_msg if isinstance(m, dict))
                messages.insert(0, {"role": "system", "content": content})

        messages = normalize_messages(messages)
        tools    = clean_tools(body.get("tools"))

        # ── Task-aware routing ─────────────────────────────────────────────────
        # Classifies the last 2 user messages and upgrades to ELITE_MODEL for
        # heavy tasks (coding, UI, reasoning, long-context), even when CC
        # dispatches via the Haiku (speed-tier) alias.
        task = None
        if model_name not in _PINNED_MODELS:
            task = classify_task(messages)
            HEAVY_TASKS = {"coding", "ui_complex", "ui_quick", "reasoning", "longcontext"}
            if task and task in HEAVY_TASKS:
                nvidia_model = TASK_MODELS.get(task, ELITE_MODEL)
                logger.info(f"[*] Task router: '{task}' → {nvidia_model} (upgraded from {model_name})")
            elif nvidia_model == ELITE_MODEL:
                logger.info("[*] Task router: no specific task → Kimi K2.5 (agentic default)")
            else:
                logger.info(f"[*] Task router: no task detected, speed tier → {nvidia_model}")

        for field in ["thinking", "metadata", "context_management", "edits"]:
            body.pop(field, None)

        logger.info(
            f"[*] Dispatching {model_name} -> {nvidia_model} "
            f"(task={task or 'agentic'}, tools: {len(tools) if tools else 0})"
        )
        response = call_with_fallback(nvidia_model, messages, tools, body)

        # is_kimi_raw: True ONLY for Kimi K2.5 which leaks raw <|tool_call_argument_begin|> tokens.
        # K2 Instruct (0905) uses standard OpenAI function calling — no buffering needed.
        # Applying the K2.5 buffer to K2 Instruct causes two bugs:
        #   1. Any response containing "functions." (e.g. Python code) holds the entire
        #      response until the 8192-char cap, turning streaming into a single burst.
        #   2. Unnecessary overhead on every text chunk.
        is_kimi_raw = "k2.5" in nvidia_model.lower()

        def stream_generator():
            msg_id = f"msg_{int(time.time())}"

            estimated_input_tokens = _estimate_input_tokens(messages, tools)
            yield "event: message_start\ndata: " + safe_json({
                "type": "message_start",
                "message": {
                    "id": msg_id, "type": "message", "role": "assistant",
                    "content": [], "model": model_name,
                    "stop_reason": None, "stop_sequence": None,
                    "usage": {
                        "input_tokens":               estimated_input_tokens,
                        "output_tokens":              0,
                        "cache_creation_input_tokens": 0,
                        "cache_read_input_tokens":     0,
                    },
                },
            }) + "\n\n"

            text_block_open     = False
            in_thinking         = False
            active_tool_indices = set()
            real_input_tokens   = 1
            real_output_tokens  = 1
            kimi_content_buffer = ""
            KIMI_TOKEN          = "<|tool_call_argument_begin|>"

            try:
                for chunk in response:
                    try:
                        data = chunk.model_dump() if hasattr(chunk, "model_dump") else chunk.dict()
                    except Exception:
                        continue

                    chunk_usage = data.get("usage") or {}
                    if chunk_usage.get("prompt_tokens"):
                        real_input_tokens = chunk_usage["prompt_tokens"]
                    elif chunk_usage.get("input_tokens"):
                        real_input_tokens = chunk_usage["input_tokens"]
                    if chunk_usage.get("completion_tokens"):
                        real_output_tokens = chunk_usage["completion_tokens"]
                    elif chunk_usage.get("output_tokens"):
                        real_output_tokens = chunk_usage["output_tokens"]

                    if not data.get("choices"):
                        continue

                    delta = data["choices"][0].get("delta", {})

                    # ── Reasoning / thinking content ───────────────────────────
                    reasoning = delta.get("reasoning_content")
                    if reasoning:
                        if not text_block_open:
                            yield "event: content_block_start\ndata: " + safe_json({
                                "type": "content_block_start", "index": 0,
                                "content_block": {"type": "text", "text": ""},
                            }) + "\n\n"
                            text_block_open = True
                        if not in_thinking:
                            yield "event: content_block_delta\ndata: " + safe_json({
                                "type": "content_block_delta", "index": 0,
                                "delta": {"type": "text_delta", "text": "<thinking>\n"},
                            }) + "\n\n"
                            in_thinking = True
                        yield "event: content_block_delta\ndata: " + safe_json({
                            "type": "content_block_delta", "index": 0,
                            "delta": {"type": "text_delta", "text": reasoning},
                        }) + "\n\n"

                    # ── Regular text content ───────────────────────────────────
                    content_text = delta.get("content")
                    if content_text and content_text != "None":
                        if is_kimi_raw:
                            kimi_content_buffer += content_text
                            # Force-flush if buffer exceeds hard cap
                            buffer_full = len(kimi_content_buffer) >= _KIMI_BUFFER_MAX_CHARS
                            has_token   = KIMI_TOKEN in kimi_content_buffer or "functions." in kimi_content_buffer
                            if not has_token or buffer_full:
                                if buffer_full:
                                    logger.warning("[!] Kimi buffer cap hit — force-flushing as plain text")
                                flush_text = kimi_content_buffer
                                kimi_content_buffer = ""
                                if flush_text and not _is_garbage_text(flush_text):
                                    if in_thinking:
                                        yield "event: content_block_delta\ndata: " + safe_json({
                                            "type": "content_block_delta", "index": 0,
                                            "delta": {"type": "text_delta", "text": "\n</thinking>\n\n"},
                                        }) + "\n\n"
                                        in_thinking = False
                                    if not text_block_open:
                                        yield "event: content_block_start\ndata: " + safe_json({
                                            "type": "content_block_start", "index": 0,
                                            "content_block": {"type": "text", "text": ""},
                                        }) + "\n\n"
                                        text_block_open = True
                                    yield "event: content_block_delta\ndata: " + safe_json({
                                        "type": "content_block_delta", "index": 0,
                                        "delta": {"type": "text_delta", "text": flush_text},
                                    }) + "\n\n"
                        else:
                            if not _is_garbage_text(content_text):
                                if in_thinking:
                                    yield "event: content_block_delta\ndata: " + safe_json({
                                        "type": "content_block_delta", "index": 0,
                                        "delta": {"type": "text_delta", "text": "\n</thinking>\n\n"},
                                    }) + "\n\n"
                                    in_thinking = False
                                if not text_block_open:
                                    yield "event: content_block_start\ndata: " + safe_json({
                                        "type": "content_block_start", "index": 0,
                                        "content_block": {"type": "text", "text": ""},
                                    }) + "\n\n"
                                    text_block_open = True
                                yield "event: content_block_delta\ndata: " + safe_json({
                                    "type": "content_block_delta", "index": 0,
                                    "delta": {"type": "text_delta", "text": content_text},
                                }) + "\n\n"

                    # ── Tool calls ─────────────────────────────────────────────
                    tool_calls = delta.get("tool_calls")
                    if tool_calls:
                        if in_thinking:
                            yield "event: content_block_delta\ndata: " + safe_json({
                                "type": "content_block_delta", "index": 0,
                                "delta": {"type": "text_delta", "text": "\n</thinking>\n\n"},
                            }) + "\n\n"
                            in_thinking = False

                        for tc in tool_calls:
                            raw_index = tc.get("index")
                            tc_index  = (raw_index if isinstance(raw_index, int) else 0) + 1

                            if "function" in tc:
                                f_data = tc["function"]
                                if f_data.get("name"):
                                    active_tool_indices.add(tc_index)
                                    yield "event: content_block_start\ndata: " + safe_json({
                                        "type": "content_block_start", "index": tc_index,
                                        "content_block": {
                                            "type": "tool_use",
                                            "id":   tc.get("id") or f"call_{int(time.time())}_{tc_index}",
                                            "name": f_data["name"],
                                            "input": {},
                                        },
                                    }) + "\n\n"
                                if f_data.get("arguments"):
                                    args = f_data["arguments"]
                                    if not isinstance(args, str):
                                        args = json.dumps(args)
                                    yield "event: content_block_delta\ndata: " + safe_json({
                                        "type": "content_block_delta", "index": tc_index,
                                        "delta": {"type": "input_json_delta", "partial_json": args},
                                    }) + "\n\n"

            except Exception as stream_err:
                logger.error(f"[!] Stream processing error: {stream_err}")

            # ── Parse any buffered Kimi raw tool-call tokens ───────────────────
            if is_kimi_raw and kimi_content_buffer:
                kimi_tool_re = re.compile(
                    r'functions\.(\w+):(\d+)\s*<\|tool_call_argument_begin\|>(.*?)<\|tool_call_end\|>',
                    re.DOTALL
                )
                first_match = kimi_tool_re.search(kimi_content_buffer)
                if first_match:
                    pre_text = kimi_content_buffer[:first_match.start()].strip()
                    if pre_text and not _is_garbage_text(pre_text) and not text_block_open:
                        yield "event: content_block_start\ndata: " + safe_json({
                            "type": "content_block_start", "index": 0,
                            "content_block": {"type": "text", "text": ""},
                        }) + "\n\n"
                        text_block_open = True
                        yield "event: content_block_delta\ndata: " + safe_json({
                            "type": "content_block_delta", "index": 0,
                            "delta": {"type": "text_delta", "text": pre_text},
                        }) + "\n\n"
                    for m in kimi_tool_re.finditer(kimi_content_buffer):
                        tool_name = m.group(1)
                        tc_index  = int(m.group(2)) + 1
                        args_raw  = m.group(3).strip()
                        try:
                            json.loads(args_raw)
                        except Exception:
                            args_raw = "{}"
                        call_id = f"call_{int(time.time())}_{tc_index}"
                        active_tool_indices.add(tc_index)
                        yield "event: content_block_start\ndata: " + safe_json({
                            "type": "content_block_start", "index": tc_index,
                            "content_block": {
                                "type": "tool_use",
                                "id":    call_id,
                                "name":  tool_name,
                                "input": {},
                            },
                        }) + "\n\n"
                        yield "event: content_block_delta\ndata: " + safe_json({
                            "type": "content_block_delta", "index": tc_index,
                            "delta": {"type": "input_json_delta", "partial_json": args_raw},
                        }) + "\n\n"
                    logger.info(f"[*] Kimi buffer: converted {len(active_tool_indices)} tool call(s) from raw tokens")
                else:
                    if not text_block_open and not _is_garbage_text(kimi_content_buffer):
                        yield "event: content_block_start\ndata: " + safe_json({
                            "type": "content_block_start", "index": 0,
                            "content_block": {"type": "text", "text": ""},
                        }) + "\n\n"
                        text_block_open = True
                        yield "event: content_block_delta\ndata: " + safe_json({
                            "type": "content_block_delta", "index": 0,
                            "delta": {"type": "text_delta", "text": kimi_content_buffer},
                        }) + "\n\n"

            # ── Close thinking if stream ended mid-thought ─────────────────────
            if in_thinking:
                yield "event: content_block_delta\ndata: " + safe_json({
                    "type": "content_block_delta", "index": 0,
                    "delta": {"type": "text_delta", "text": "\n</thinking>\n\n"},
                }) + "\n\n"

            # ── Safety fallback: ensure at least one content block ─────────────
            if not text_block_open and not active_tool_indices:
                yield "event: content_block_start\ndata: " + safe_json({
                    "type": "content_block_start", "index": 0,
                    "content_block": {"type": "text", "text": ""},
                }) + "\n\n"
                yield "event: content_block_delta\ndata: " + safe_json({
                    "type": "content_block_delta", "index": 0,
                    "delta": {"type": "text_delta", "text": " "},
                }) + "\n\n"
                text_block_open = True

            # ── Close all open content blocks ──────────────────────────────────
            if text_block_open:
                yield "event: content_block_stop\ndata: " + safe_json({
                    "type": "content_block_stop", "index": 0,
                }) + "\n\n"
            for idx in active_tool_indices:
                yield "event: content_block_stop\ndata: " + safe_json({
                    "type": "content_block_stop", "index": idx,
                }) + "\n\n"

            stop_reason = "tool_use" if active_tool_indices else "end_turn"

            # ── message_delta ──────────────────────────────────────────────────
            # Send all 4 fields matching message_start's usage shape.
            # Some CC versions read input_tokens from message_delta too —
            # sending 0 here is safe since the real value is already in message_start.
            yield "event: message_delta\ndata: " + safe_json({
                "type": "message_delta",
                "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                "usage": {
                    "input_tokens":                0,
                    "output_tokens":               real_output_tokens,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens":     0,
                },
            }) + "\n\n"

            yield "event: message_stop\ndata: " + safe_json({"type": "message_stop"}) + "\n\n"

        return StreamingResponse(
            stream_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control":     "no-cache",
                "X-Accel-Buffering": "no",
                "Connection":        "keep-alive",
            },
        )

    except Exception as e:
        logger.error(f"[!] Bridge Error: {e}")
        if body:
            # Strip conversation content before dumping — messages/system can
            # contain sensitive user data. Keep only the structural fields
            # needed to reproduce the routing/format issue.
            safe_dump = {
                k: v for k, v in body.items()
                if k not in ("messages", "system")
            }
            safe_dump["messages_count"] = len(body.get("messages", []))
            safe_dump["system_present"] = bool(body.get("system"))
            with open("failed_request_body.json", "w") as f:
                json.dump(safe_dump, f, indent=2)
        return Response(
            content=json.dumps({"error": {"message": str(e), "type": "bridge_error", "param": None, "code": "500"}}),
            status_code=500, media_type="application/json",
        )


if __name__ == "__main__":
    # FIX: bind to 127.0.0.1, not 0.0.0.0.
    # 0.0.0.0 exposes the bridge (which has no auth) to every device on the
    # local network. Local-only binding is correct for Claude Code use.
    host = os.environ.get("BRIDGE_HOST", "127.0.0.1")
    port = int(os.environ.get("BRIDGE_PORT", "4005"))
    try:
        uvicorn.run(app, host=host, port=port, log_level="info")
    except Exception as e:
        with open("arbiter_crash.log", "a") as f:
            f.write(f"\nCRASH at {time.ctime()}: {str(e)}\n")
        raise e
