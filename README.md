# Arbiter

A local proxy that lets **Claude Code** use NVIDIA NIM models instead of Anthropic's API, with zero changes to your Claude Code workflow.

```
Claude Code → localhost:4005 → arbiter_bridge.py → NVIDIA NIM (Kimi K2.5 / K2 0905)
```

---

## Features

| Feature | Detail |
|---|---|
| **Task-aware routing** | Classifies each request (coding / UI / reasoning / fast) and routes to the best model tier |
| **Three-tier fallback** | On 429/503/DEGRADED: target → ELITE_FALLBACK → SPEED_MODEL |
| **Kimi token cleanup** | Strips raw `<\|tool_call...\|>` leakage from Kimi K2.5 streaming responses |
| **Per-model tool cap** | Prevents silent hangs on models that choke on Claude Code's 59-tool payload |
| **CC crash fix** | Correct SSE field placement (input_tokens in message_start only) prevents the `$.input_tokens` undefined crash in CC 2.1.114+ |

---

## Quick Start

### 1. Prerequisites

```bash
pip install fastapi uvicorn litellm openai
```

### 2. Set your NVIDIA API key

**Windows (permanent):**
```cmd
setx NVIDIA_API_KEY nvapi-your-key-here
```
Then open a **new** terminal — `setx` only takes effect in new sessions.

**Or per-session:**
```cmd
set NVIDIA_API_KEY=nvapi-your-key-here
```

### 3. Launch

```cmd
start_nvidia_brain.bat
```

This will:
1. Verify dependencies
2. Start the bridge on `127.0.0.1:4005`
3. Set `ANTHROPIC_BASE_URL=http://127.0.0.1:4005` so Claude Code routes through it
4. Launch Claude Code in your project folder

---

## Configuration

### Changing the target project folder

Set `TARGET_DIR` before running:
```cmd
set TARGET_DIR=C:\path\to\your\project
start_nvidia_brain.bat
```

### Overriding the Python executable

```cmd
set PYTHON_EXE=C:\path\to\python.exe
start_nvidia_brain.bat
```

### Bridge host/port

```cmd
set BRIDGE_HOST=127.0.0.1
set BRIDGE_PORT=4005
```

---

## Model Selection

On first launch you'll see a menu to pick your elite model:

```
[?] Select the elite model for this session:
    (K2 0905 is always kept as speed/fallback — this replaces the elite slot only)

    1. Kimi K2.5                (elite — best coding/agentic, confirmed)
    2. Kimi K2 0905             (fast — good for most tasks, confirmed)
    3. Qwen3-Coder 480B         (coding-focused, very large) (*)
    4. Llama 3.3 70B Instruct   (general purpose, fast) (*)
    5. DeepSeek R1 0528         (strong reasoning) (*)
    6. Custom                   (enter any NIM model string manually)

    Choice [1-6, default=1]:
```

Your choice replaces the **elite slot only** — K2 0905 stays fixed as the speed tier and fallback. If the elite model hits a 429 or 503, the bridge automatically steps down to K2 0905.

Save your choice to skip the menu on future launches. To reset it:
```cmd
setx NVIDIA_ELITE_MODEL ""
```

To add models to the list, edit the `MODEL ROSTER` block at the top of `start_nvidia_brain.bat`.

> `(*)` = not confirmed available on all NIM tiers. If a model returns 404, the fallback chain will catch it and step down to K2 0905.

---

### Tiers

| Tier | Model | When |
|---|---|---|
| Elite | `kimi-k2.5` | coding, UI, reasoning, long-context, agentic default |
| Speed | `kimi-k2-instruct-0905` | fast tasks (define/summarize/translate), 429 fallback |

### Task classifier

The bridge scans the last 2 user messages and pattern-matches to one of:

`ui_complex` → `ui_quick` → `coding` → `reasoning` → `longcontext` → `fast`

Heavy tasks (`coding`, `ui_*`, `reasoning`, `longcontext`) always upgrade to Kimi K2.5, even when Claude Code dispatches via the Haiku alias.

### Adding a new model

1. Add it to `MODEL_MAP` in `arbiter_bridge.py`
2. Add its `max_tokens` to `MODEL_MAX_TOKENS`
3. If it hangs with many tools, add it to `MAX_TOOLS_PER_MODEL`

---

## Known NIM Model Status

| Model | Status |
|---|---|
| `moonshotai/kimi-k2.5` | ✅ Available |
| `moonshotai/kimi-k2-instruct-0905` | ✅ Available |
| `mistral-large-2-instruct` | ❌ 404 (may require tier upgrade) |
| `GLM 4.7 / GLM 5.1` | ❌ 404 (may require tier upgrade) |

---

## Files

| File | Purpose |
|---|---|
| `arbiter_bridge.py` | Main FastAPI proxy server |
| `start_nvidia_brain.bat` | Windows launcher |
| `check_arbiter.py` | Dependency audit + optional functional test (`--test`) |
| `orjson.py` / `mock_orjson/` | stdlib-only orjson shim (no Rust dependency needed) |
| `requirements.txt` | Python dependencies |
| `.env.example` | Environment variable template |

---

## Security

- The bridge binds to `127.0.0.1` only — not reachable from other devices on your network
- **Never commit your NVIDIA API key** — use environment variables or a `.env` file (already in `.gitignore`)
- `bridge_runtime.log` and `failed_request_body.json` are gitignored — they can contain request data

---

## License

MIT
