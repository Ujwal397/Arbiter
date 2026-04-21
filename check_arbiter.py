import sys
import os
import importlib
import subprocess

REQUIRED = [
    ("litellm",   "litellm"),
    ("fastapi",   "fastapi"),
    ("uvicorn",   "uvicorn[standard]"),
    ("openai",    "openai"),
    ("requests",  "requests"),   # used by --test flag
]

def check_module(import_name):
    try:
        importlib.import_module(import_name)
        return True
    except ImportError:
        return False

def install_package(pip_name):
    print(f"  Installing {pip_name}...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", pip_name, "--quiet"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"  [!] Failed:\n{result.stderr.strip()}")
        return False
    return True

print("\n=== ARBITER: SYSTEM AUDIT ===")
print(f"Python : {sys.version.split()[0]}  ({sys.executable})")
print(f"API Key: {'SET' if os.environ.get('NVIDIA_API_KEY') else 'NOT SET'}")
print("-" * 45)

auto_install = "--install" in sys.argv
missing = []

for import_name, pip_name in REQUIRED:
    ok = check_module(import_name)
    status = "OK" if ok else "MISSING"
    print(f"  {'[+]' if ok else '[!]'} {import_name:<20} {status}")
    if not ok:
        missing.append((import_name, pip_name))

if missing and auto_install:
    print()
    print(f"[*] Installing {len(missing)} missing package(s)...")
    failed = []
    for import_name, pip_name in missing:
        if install_package(pip_name):
            # Verify it actually works after install
            if check_module(import_name):
                print(f"  [+] {import_name} installed OK")
            else:
                print(f"  [!] {import_name} installed but still can't import")
                failed.append(pip_name)
        else:
            failed.append(pip_name)
    if failed:
        print()
        print(f"[!] Could not install: {', '.join(failed)}")
        print(f"[!] Try manually:  pip install {' '.join(failed)}")
        sys.exit(1)
elif missing:
    print()
    print(f"[!] {len(missing)} missing package(s). Run with --install to fix automatically.")
    print(f"[!] Or:  pip install {' '.join(p for _, p in missing)}")
    sys.exit(1)

print()
print("[+] All dependencies present.")

# Optional functional test
if "--test" in sys.argv:
    print("\n=== FUNCTIONAL BRIDGE TEST ===")
    import requests, json
    url     = "http://127.0.0.1:4005/v1/chat/completions"
    headers = {"Content-Type": "application/json", "Authorization": "Bearer sk-test-123"}
    data    = {
        "model": "claude-sonnet-4-6",
        "messages": [{"role": "user", "content": "List the files in this directory."}],
        "tools": [{"type": "function", "function": {
            "name": "Bash", "description": "Run a bash command",
            "parameters": {"type": "object",
                           "properties": {"command": {"type": "string"}},
                           "required": ["command"]},
        }}],
        "tool_choice": "auto",
    }
    try:
        r = requests.post(url, headers=headers, json=data, timeout=30)
        if r.status_code == 200:
            choice = r.json()["choices"][0]["message"]
            if "tool_calls" in choice:
                tc = choice["tool_calls"][0]["function"]
                print(f"[+] Tool call returned: {tc['name']}({tc['arguments']})")
            else:
                print(f"[!] No tool call: {choice.get('content','')}")
        else:
            print(f"[!] HTTP {r.status_code}: {r.text}")
    except Exception as e:
        print(f"[!] Could not reach bridge: {e}")

print("===========================================\n")
