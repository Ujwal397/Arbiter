# Arbiter

> **Run Claude Code with massive AI models — completely free, no local hardware required.**

Claude Code normally only works with Anthropic's own models, which cost money per token. Arbiter breaks that lock. It sits between Claude Code and NVIDIA's free cloud API, letting you use models like **Kimi K2.5** — a 1 trillion parameter model that would be physically impossible to run on your own machine — at zero cost.

```
Claude Code  →  Arbiter (localhost)  →  NVIDIA NIM Cloud  →  Kimi K2.5 (1T params)
```

**NVIDIA NIM models are free** to use with an API key from [build.nvidia.com](https://build.nvidia.com). No credit card, no per-token charges.

---

## Why Arbiter?

| Without Arbiter | With Arbiter |
|---|---|
| Claude Code only works with Anthropic's paid API | Use NVIDIA's free cloud models instead |
| You pay per token, costs add up fast | Completely free |
| Limited to models Anthropic offers | Access 1T+ parameter models like Kimi K2.5 |
| Would need enterprise hardware to run large models locally | Runs in the cloud, nothing to install beyond Python |

---

## Features

**Smart model routing** — Arbiter reads what you're asking Claude Code to do and automatically picks the right model for the job. Asking it to build a complex UI? It routes to the most powerful model. Just asking it to summarize something? It picks the fastest one. You never have to think about this.

**Automatic fallback** — If a model is busy or unavailable, Arbiter silently steps down to the next best option and keeps working. You won't see errors or interruptions.

**Works out of the box** — No changes to how you use Claude Code. Install, run the launcher, and everything routes through Arbiter automatically.

**Supports any NIM model** — The model list is editable. If NVIDIA releases something new, you add two lines and it's available in the menu.

**Crash prevention** — Fixes a known Claude Code bug that causes a silent crash when using non-Anthropic backends. You would never see an error message — your session would just silently stop working. Arbiter prevents this.

---

## Quick Start

### Step 1 — Get a free NVIDIA API key

Go to [build.nvidia.com](https://build.nvidia.com), sign up, and copy your API key. It starts with `nvapi-`.

### Step 2 — Install Python dependencies

```cmd
pip install fastapi uvicorn litellm openai
```

### Step 3 — Save your API key

```cmd
setx NVIDIA_API_KEY nvapi-your-key-here
```

Then open a **new terminal window** — the key won't be visible in your current one.

### Step 4 — Launch

```cmd
start_arbiter.bat
```

That's it. Claude Code will open automatically, already pointed at Arbiter. You'll be asked to pick a model on first run — just hit Enter to go with Kimi K2.5 (the best option).

---

## Model Selection

When you launch for the first time, you'll see this menu:

```
[?] Select the elite model for this session:

    1. Kimi K2.5                (best — 1T params, top coding & reasoning)
    2. Kimi K2 0905             (fast — great for most tasks)
    3. Qwen3-Coder 480B         (coding-focused, very large) (*)
    4. Llama 3.3 70B Instruct   (general purpose, fast) (*)
    5. DeepSeek R1 0528         (strong reasoning) (*)
    6. Custom                   (enter any NIM model string manually)

    Choice [1-6, default=1]:
```

Your pick becomes the primary model. **Kimi K2 0905 is always kept as a backup** — if your chosen model is unavailable, Arbiter automatically falls back to it with no interruption.

You can also paste a full URL from build.nvidia.com directly into the Custom field — Arbiter strips it down to the right format automatically.

> **Note:** Models marked `(*)` are not confirmed available on all NVIDIA account tiers. If one returns a "not found" error, Arbiter falls back to K2 0905 silently.

To reset your saved choice and see the menu again:
```cmd
setx NVIDIA_ELITE_MODEL ""
```

---

## Configuration

Most things work without touching any config. These are available if you need them:

```cmd
:: Change which folder Claude Code opens in
set TARGET_DIR=C:\path\to\your\project

:: Change the Python executable if needed
set PYTHON_EXE=C:\path\to\python.exe

:: Change the local port (default: 4005)
set BRIDGE_PORT=4005
```

---

## Known Model Availability

| Model | Status |
|---|---|
| Kimi K2.5 (`moonshotai/kimi-k2.5`) | ✅ Confirmed working |
| Kimi K2 0905 (`moonshotai/kimi-k2-instruct-0905`) | ✅ Confirmed working |
| Mistral Large 2 | ❌ Not available on free tier |
| GLM 4.7 / 5.1 | ❌ Not available on free tier |

Not all models on [build.nvidia.com](https://build.nvidia.com) support the tool-calling that Claude Code requires. If a model doesn't work, the fallback chain will catch it. Check the site for the latest available models.

---

## Files

| File | What it does |
|---|---|
| `arbiter_bridge.py` | The proxy server — handles all routing and translation |
| `start_arbiter.bat` | Windows launcher — run this to start everything |
| `check_arbiter.py` | Checks your setup is correct (`--test` runs a live request) |
| `requirements.txt` | Python packages needed |
| `.env.example` | Template for storing your API key in a file instead of system env |

---

## Security

- Arbiter only listens on `127.0.0.1` — it's not accessible from other devices on your network
- Your NVIDIA API key is never written to any file by default — it stays in your environment variables
- Log files are excluded from git automatically

---

## License

MIT
