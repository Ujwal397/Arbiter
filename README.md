<div align="center">

# ⚖️ Arbiter

### Run Claude Code on NVIDIA's free cloud models — zero cost, no hardware needed.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Platform](https://img.shields.io/badge/Launcher-Windows-0078D6?logo=windows&logoColor=white)](https://github.com/Ujwal397/Arbiter)

<br>

```
Claude Code  ──▶  Arbiter (localhost:4005)  ──▶  NVIDIA NIM Cloud  ──▶  Free Models
```

Claude Code only works with Anthropic's paid API by default. Arbiter breaks that lock —
it sits between Claude Code and NVIDIA's free cloud API, transparently routing every request
to models like **Kimi K2 0905**, **Mistral Large 3**, and **Llama 3.3 70B** at **zero cost**.

[**Get started →**](#-quick-start) · [Model availability](#-known-model-availability) · [Configuration](#️-configuration)

</div>

---

## ✦ Why Arbiter?

| Without Arbiter | With Arbiter |
|:---|:---|
| Claude Code only works with Anthropic's paid API | Routes through NVIDIA's free cloud models |
| You pay per token — costs stack up fast | Completely free with an NVIDIA API key |
| Limited to models Anthropic offers | Access models like Kimi K2, Mistral Large 3, Llama 3.3 |
| Large models require enterprise hardware locally | Runs in the cloud — nothing to install beyond Python |

> **NVIDIA NIM is free.** Get an API key at [build.nvidia.com](https://build.nvidia.com) — no credit card, no per-token charges.

---

## ✦ Features

<details open>
<summary><strong>🧭 Task-aware model routing</strong></summary>

<br>

Arbiter reads your last two messages and classifies the task before dispatching. Heavy work goes to the most capable model; quick questions go to the fastest one — automatically.

| Task type | Triggers on | Model tier |
|:---|:---|:---|
| `coding` | debug, implement, refactor, traceback, unit test… | Elite |
| `reasoning` | analyze, algorithm, system design, optimize, prove… | Elite |
| `longcontext` | entire codebase, across all files, large document… | Elite |
| `ui_complex` | design system, component library, responsive layout system… | Elite |
| `ui_quick` | react component, tailwind, navbar, modal, landing page… | Elite |
| `fast` | what is, summarize, define, translate, tl;dr… | Speed |

If no task is detected, requests default to the Elite model for agentic sessions.

</details>

<details open>
<summary><strong>🔁 Three-tier automatic fallback</strong></summary>

<br>

If your chosen model is rate-limited, degraded, or unavailable, Arbiter silently steps down the chain with a short back-off — no interruptions, no errors shown to Claude Code.

```
Your chosen model  ──▶  Mistral Large 3  ──▶  Kimi K2 Instruct 0905
        ↑                      ↑                        ↑
   (primary)          (elite fallback)          (last resort / speed)
```

Retriable errors: `429`, `503`, `502`, `DEGRADED`. Non-retriable errors fail fast.

</details>

<details open>
<summary><strong>🛡️ Claude Code crash prevention</strong></summary>

<br>

Claude Code has a silent crash bug when used with non-Anthropic backends — your session stops working with no error message. Arbiter prevents this with:

- **`/v1/messages/count_tokens` endpoint** — Claude Code calls this before agentic loops for context budget management. Without it, the session crashes silently.
- **Input token tracking** — Populates accurate token counts in both `message_start` and `message_delta` events, preventing crashes from undefined or zero `input_tokens` fields.
- **Request logging middleware** — Every inbound request is logged with method, path, and status code for easy debugging.

</details>

<details open>
<summary><strong>🧹 Kimi K2.5 stream sanitisation</strong></summary>

<br>

Kimi K2.5 occasionally leaks internal tokens into the response stream — raw `<|tool_call_argument_begin|>` markers and Python-repr content blocks that would corrupt Claude Code's parser. Arbiter buffers and sanitises these before they reach Claude Code, then reconstructs clean tool calls from the raw format.

K2 Instruct (0905) uses standard OpenAI function calling and doesn't need this — the buffer is only applied to K2.5.

> **Note:** K2.5 is currently unstable on NIM. K2 0905 is the recommended default.

</details>

<details open>
<summary><strong>🔍 NIM availability probing</strong></summary>

<br>

On startup, Arbiter probes every model in the roster with a lightweight 1-token request to NVIDIA NIM — all probes run in parallel with an 8-second timeout. The model selection menu shows live status badges so you can see which models are available before choosing.

```
Status   [OK  ] Live and responding on your key
         [FAIL] Not available on NIM (4xx / deprecated)
         [TIME] Timed out (NIM overloaded or network issue)
         [????] Skipped (no API key yet, or SKIP_NIM_CHECK=1)
         [SKIP] Not applicable (Custom slot)
```

Set `SKIP_NIM_CHECK=1` to bypass probing if you want to skip the startup delay.

</details>

<details open>
<summary><strong>⚙️ Add any NIM model in two lines</strong></summary>

<br>

The model roster lives in `start_arbiter.bat`. Add a new `MODEL_NAME_N` / `MODEL_ID_N` pair, increment `MODEL_COUNT`, and it appears in the selection menu automatically. The Custom option also accepts any NIM model string or full URL directly.

For task routing, add the model to `MODEL_MAP` and `TASK_MODELS` in `arbiter_bridge.py`.

</details>

---

## ✦ Quick Start

### 1 — Get a free NVIDIA API key

Go to [build.nvidia.com](https://build.nvidia.com), sign up, and copy your API key. It starts with `nvapi-`.

### 2 — Install dependencies

```cmd
pip install fastapi uvicorn litellm openai httpx[http2] orjson requests
```

### 3 — Launch

**Windows:**
```cmd
start_arbiter.bat
```

**Linux / Mac** (manual launch — no `.bat` required):
```bash
export NVIDIA_API_KEY=nvapi-your-key-here
export ANTHROPIC_API_KEY=sk-test-123
export ANTHROPIC_BASE_URL=http://127.0.0.1:4005
python arbiter_bridge.py &
claude
```

On first Windows run, you'll be prompted for your API key and which model you want. Claude Code opens automatically after that. Your choice is saved — you won't see the menu again unless you reset it.

**To reset and see the menu again:**
```cmd
setx NVIDIA_ELITE_MODEL ""
```

---

## ✦ Model Selection Menu

```
[?] Select the elite model for this session:

    1. [OK  ] Kimi K2 0905              (DEFAULT - fast + capable)
    2. [    ] Kimi K2.5                 (elite - best coding/agentic)
    3. [OK  ] Mistral Large 3           (fallback default - strong general purpose)
    4. [FAIL] Qwen3-Coder 480B          (coding-focused, very large)
    5. [OK  ] Llama 3.3 70B Instruct    (general purpose, fast)
    6. [FAIL] DeepSeek R1 0528          (strong reasoning)
    7. [SKIP] Custom                    (enter any NIM model string manually)
    E. Edit model list (opens this file in Notepad, then restart)

    Choice [1-7 / E, default=1]:
```

Your selected model becomes the **Elite tier**. Mistral Large 3 is the automatic **fallback** when the elite model is unavailable. Kimi K2 0905 is the **last resort / speed** model.

> Live status badges are shown at launch based on real-time NIM availability probes. Models marked `[FAIL]` are unavailable on your NIM tier or have been deprecated. The fallback chain handles failures silently.

---

## ✦ Known Model Availability

*Last verified: April 2026*

| Model | NIM ID | Status |
|:---|:---|:---|
| Kimi K2 0905 | `moonshotai/kimi-k2-instruct-0905` | ✅ Working — recommended default |
| Mistral Large 3 | `mistralai/mistral-large-3-675b-instruct-2512` | ✅ Working — automatic fallback |
| Llama 3.3 70B Instruct | `meta/llama-3.3-70b-instruct` | ✅ Working |
| Kimi K2.5 | `moonshotai/kimi-k2.5` | ⚠️ Unstable — probe returns no status |
| Qwen3-Coder 480B | `qwen/qwen3-coder-480b-a22b` | ❌ Unavailable on NIM |
| DeepSeek R1 0528 | `deepseek/deepseek-r1-0528` | ❌ Unavailable on NIM |

Not all NIM models support the tool-calling protocol that Claude Code requires. If a model doesn't support it, the fallback chain handles it automatically. Check [build.nvidia.com](https://build.nvidia.com) for the current model catalogue.

---

## ⚙️ Configuration

Most things work without touching any config. These environment variables are available if you need them:

```cmd
:: Change which folder Claude Code opens in
set TARGET_DIR=C:\path\to\your\project

:: Change the Python executable if needed
set PYTHON_EXE=C:\path\to\python.exe

:: Change the local port (default: 4005)
set BRIDGE_PORT=4005

:: Skip NIM availability probing at startup
set SKIP_NIM_CHECK=1
```

Your API key can also be stored in a `.env` file instead of system environment variables — see `.env.example` for the format.

---

## ✦ File Reference

| File | Purpose |
|:---|:---|
| `arbiter_bridge.py` | The proxy server — routing, translation, streaming, fallback |
| `start_arbiter.bat` | Windows launcher — model selection, NIM probing, starts everything |
| `check_arbiter.py` | Dependency checker and bridge readiness poller |
| `verify_nim_models.py` | Parallel NIM availability prober (stdlib only, no pip deps) |
| `requirements.txt` | Python dependencies |
| `.env.example` | API key storage template |

---

## ✦ Security

- Arbiter binds to `127.0.0.1` only — not accessible from other devices on your network
- Your NVIDIA API key is never written to disk by default — stored in environment variables only
- Log files are excluded from git via `.gitignore`
- On errors, request bodies are sanitised before logging — message content is never written to disk

---

## ✦ License

MIT — free to use, modify, and distribute.
