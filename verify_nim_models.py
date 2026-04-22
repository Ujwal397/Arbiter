"""
verify_nim_models.py  —  Arbiter NIM availability probe
========================================================
Reads MODEL_COUNT + MODEL_ID_N environment variables set by start_arbiter.bat,
fires a lightweight POST to NVIDIA NIM for each model in parallel (8s timeout),
then writes a small batch file (nim_status.tmp.bat) containing:

    set "MODEL_STATUS_1=OK"
    set "MODEL_STATUS_2=FAIL:404"
    ...

start_arbiter.bat calls that file to load the status variables, then
maps them to display badges via the :set_badge subroutine.

Status values written to the tmp file:
    OK           - HTTP 200 received; model is live
    FAIL:<code>  - HTTP error (4xx/5xx); unavailable or not on your tier
    TIMEOUT      - No response within 8 seconds
    NOKEY        - NVIDIA_API_KEY is not set; probe skipped
    SKIP         - Model ID is CUSTOM or empty; probe not applicable

Environment variables consumed:
    NVIDIA_API_KEY   - NIM bearer token
    MODEL_COUNT      - Number of models in the roster
    MODEL_ID_N       - NIM model string for slot N
"""

import os
import sys
import urllib.request
import urllib.error
import json
import threading

NIM_URL   = "https://integrate.api.nvidia.com/v1/chat/completions"
TIMEOUT_S = 8   # per-model request timeout


def _probe(model_id: str, api_key: str) -> str:
    """
    Send a minimal 1-token request to NIM.
    Returns "OK", "FAIL:<http_status>", or "TIMEOUT".
    Uses only stdlib so it works before pip deps are installed.
    """
    payload = json.dumps({
        "model":    model_id,
        "messages": [{"role": "user", "content": "Hi"}],
        "max_tokens": 1,
        "stream": False,
    }).encode("utf-8")

    req = urllib.request.Request(
        NIM_URL,
        data=payload,
        headers={
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            return "OK" if resp.status == 200 else f"FAIL:{resp.status}"
    except urllib.error.HTTPError as e:
        return f"FAIL:{e.code}"
    except Exception:
        # Covers URLError, TimeoutError, ConnectionRefusedError, socket errors, etc.
        return "TIMEOUT"


def _write_tmp(script_dir: str, statuses: dict[int, str]) -> None:
    """Write nim_status.tmp.bat with set commands for each slot."""
    tmp_bat = os.path.join(script_dir, "nim_status.tmp.bat")
    with open(tmp_bat, "w", newline="\r\n") as f:
        for n, status in sorted(statuses.items()):
            f.write(f'set "MODEL_STATUS_{n}={status}"\n')


def main() -> None:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    api_key    = os.environ.get("NVIDIA_API_KEY", "").strip()

    # --- Parse MODEL_COUNT --------------------------------------------------
    try:
        count = int(os.environ.get("MODEL_COUNT", "0"))
    except ValueError:
        count = 0

    if count <= 0:
        _write_tmp(script_dir, {1: "SKIP"})
        return

    # --- No API key — mark every slot NOKEY so badges show ???? -------------
    if not api_key:
        _write_tmp(script_dir, {n: "NOKEY" for n in range(1, count + 1)})
        return

    # --- Collect model IDs --------------------------------------------------
    slots: list[tuple[int, str]] = []
    for n in range(1, count + 1):
        mid = os.environ.get(f"MODEL_ID_{n}", "").strip()
        slots.append((n, mid))

    # --- Probe all models in parallel ---------------------------------------
    results: dict[int, str] = {}
    lock = threading.Lock()

    def check(n: int, model_id: str) -> None:
        if not model_id or model_id.upper() == "CUSTOM":
            status = "SKIP"
        else:
            status = _probe(model_id, api_key)
        with lock:
            results[n] = status

    threads = [
        threading.Thread(target=check, args=(n, mid), daemon=True)
        for n, mid in slots
    ]
    for t in threads:
        t.start()
    for t in threads:
        # Give each thread TIMEOUT_S + 2 s to finish cleanly.
        t.join(timeout=TIMEOUT_S + 2)

    # Fill in TIMEOUT for any thread that didn't finish in time.
    final: dict[int, str] = {n: results.get(n, "TIMEOUT") for n, _ in slots}
    _write_tmp(script_dir, final)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Last-resort: if anything goes wrong, write SKIP so the bat
        # can still continue without hanging on a missing tmp file.
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            count_raw  = os.environ.get("MODEL_COUNT", "0")
            count      = int(count_raw) if count_raw.isdigit() else 0
            _write_tmp(script_dir, {n: "SKIP" for n in range(1, max(count, 1) + 1)})
        except Exception:
            pass
        sys.exit(0)   # Don't surface errors to the bat — just proceed
