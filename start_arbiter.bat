@echo off
SETLOCAL EnableDelayedExpansion
set "BANG=!"

:: ===========================================================================
:: MODEL ROSTER -- Edit this block to add / remove / update models.
:: To add a model: increment MODEL_COUNT, add a NAME and ID pair.
:: MODEL_ID must be the exact NIM model string (without "openai/" prefix).
:: The last entry should always be the Custom option (ID=CUSTOM).
:: Confirmed available models listed first; unconfirmed marked with (*).
:: ===========================================================================
set "MODEL_COUNT=6"
set "MODEL_NAME_1=Kimi K2.5                (elite - best coding/agentic, confirmed)"
set "MODEL_ID_1=moonshotai/kimi-k2.5"
set "MODEL_NAME_2=Kimi K2 0905             (fast - good for most tasks, confirmed)"
set "MODEL_ID_2=moonshotai/kimi-k2-instruct-0905"
set "MODEL_NAME_3=Qwen3-Coder 480B         (coding-focused, very large) (*)"
set "MODEL_ID_3=qwen/qwen3-coder-480b-a22b"
set "MODEL_NAME_4=Llama 3.3 70B Instruct   (general purpose, fast) (*)"
set "MODEL_ID_4=meta/llama-3.3-70b-instruct"
set "MODEL_NAME_5=DeepSeek R1 0528         (strong reasoning) (*)"
set "MODEL_ID_5=deepseek/deepseek-r1-0528"
set "MODEL_NAME_6=Custom                   (enter any NIM model string manually)"
set "MODEL_ID_6=CUSTOM"

cls
echo.
echo     _    ____  ____ ___ _____ _____ ____  
echo    / \  ^|  _ \^| __ )_ _^|_   _^| ____^|  _ \ 
echo   / _ \ ^| ^|_) ^|  _ \^| ^|  ^| ^| ^|  _^| ^| ^|_) ^|
echo  / ___ \^|  _ ^<^| ^|_) ^| ^|  ^| ^| ^| ^|___^|  _ ^< 
echo /_/   \_\_^| \_\____/___^| ^|_^| ^|_____^|_^| \_\
echo.

:: ===========================================================================
:: STEP 1 - Find Python
:: ===========================================================================
:: We run --version to confirm execution, not just "where".
:: The Windows Store creates a fake python stub that passes "where" but
:: opens the Store instead of running Python.
:: No goto-inside-parentheses here - that silently crashes CMD.

if "%PYTHON_EXE%"=="" (
    py --version >nul 2>&1
    if !errorlevel! equ 0 set "PYTHON_EXE=py"
)
if "%PYTHON_EXE%"=="" (
    python --version >nul 2>&1
    if !errorlevel! equ 0 set "PYTHON_EXE=python"
)
if "%PYTHON_EXE%"=="" (
    python3 --version >nul 2>&1
    if !errorlevel! equ 0 set "PYTHON_EXE=python3"
)
if "%PYTHON_EXE%"=="" (
    echo.
    echo [!BANG!] ERROR: No working Python found.
    echo     Tried: py, python, python3 - all failed.
    echo.
    echo     Fix options:
    echo       1. Install Python from https://python.org
    echo          Tick "Add python.exe to PATH" during install.
    echo       2. Disable the Windows Store alias:
    echo          Settings ^> Apps ^> Advanced app settings
    echo          ^> App execution aliases ^> turn OFF python/python3
    echo       3. Set PYTHON_EXE before running this script:
    echo          set PYTHON_EXE=C:\path\to\python.exe
    echo.
    pause
    exit /b 1
)
echo [*] Python    : %PYTHON_EXE%

:: ===========================================================================
:: STEP 2 - Install missing dependencies
:: ===========================================================================
echo [*] Checking dependencies...
"%PYTHON_EXE%" "%~dp0check_arbiter.py" --install
if %errorlevel% neq 0 (
    echo.
    echo [!BANG!] Dependency install failed. See output above.
    pause
    exit /b 1
)

:: ===========================================================================
:: STEP 3 - NVIDIA API Key
:: ===========================================================================
echo.
if not "%NVIDIA_API_KEY%"=="" goto :key_done
    echo [?] No NVIDIA API key found.
    echo [?] Get one free at: https://build.nvidia.com
    echo [?]   Sign in, then click your avatar ^> API Key
    echo.
    set /p NVIDIA_API_KEY="    Paste key (nvapi-...): "
    echo.
    if "!NVIDIA_API_KEY!"=="" (
        echo [!BANG!] No key entered. Exiting.
        pause
        exit /b 1
    )
    echo [+] Key accepted for this session.
    echo.
    choice /C YN /M "Save this key permanently so you are not asked again"
    if !errorlevel! equ 1 (
        setx NVIDIA_API_KEY "!NVIDIA_API_KEY!" >nul
        echo [+] Key saved. Will load automatically next time.
    )
    echo.
:key_done
echo [*] NVIDIA key : set
set NVIDIA_NIM_API_KEY=%NVIDIA_API_KEY%

:: ===========================================================================
:: STEP 4 - Project Folder
:: ===========================================================================
echo.
if not "%TARGET_DIR%"=="" goto :dir_done
    echo [?] Where should Claude Code open?
    echo [?] Enter the full path to your project folder.
    echo [?] Example: C:\Users\YourName\Projects\my-app
    echo [?] Press Enter to use the current directory.
    echo.
    set /p TARGET_DIR="    Project path: "
    echo.
    if "!TARGET_DIR!"=="" (
        set "TARGET_DIR=%CD%"
        echo [*] Using current directory.
    )
    choice /C YN /M "Save this as your default project folder"
    if !errorlevel! equ 1 (
        setx TARGET_DIR "!TARGET_DIR!" >nul
        echo [+] Saved. Will load automatically next time.
    )
    echo.
:dir_done
echo [*] Project    : %TARGET_DIR%

if not exist "%TARGET_DIR%" (
    echo.
    echo [!BANG!] Folder not found: %TARGET_DIR%
    echo [!BANG!] Check the path or reset it with:  setx TARGET_DIR ""
    pause
    exit /b 1
)

:: ===========================================================================
:: STEP 5 - Model Selection
:: ===========================================================================
:: Only ask once - if NVIDIA_ELITE_MODEL is already saved, skip the menu.
:: The selected model fills the elite slot only.
:: K2 0905 is always kept as the speed/fallback tier regardless of choice.
:: ===========================================================================
echo.
if not "%NVIDIA_ELITE_MODEL%"=="" goto :model_done

echo [?] Select the elite model for this session:
echo     (K2 0905 is always kept as speed/fallback - this replaces the elite slot only)
echo.
echo [!BANG!] NOTE: Not all NIM models work with Claude Code.
echo [!BANG!] A model can fail for two reasons:
echo [!BANG!]   1. Not available on your NIM tier/deprecated (returns 404 - Arbiter will fall back to K2 0905)
echo [!BANG!]   2. Does not support function/tool calling (causes silent failures or broken output)
echo [!BANG!] Models may go deprecated anytime so please watch https://build.nvidia.com to check for latest models.
echo     (*) = not confirmed available on all NIM tiers
echo.
echo     1. %MODEL_NAME_1%
echo     2. %MODEL_NAME_2%
echo     3. %MODEL_NAME_3%
echo     4. %MODEL_NAME_4%
echo     5. %MODEL_NAME_5%
echo     6. %MODEL_NAME_6%
echo.
choice /C 123456 /N /M "    Choice [1-6, default=1]: "
set "SEL=!errorlevel!"

:: Map choice number to model ID
if "!SEL!"=="6" set "NVIDIA_ELITE_MODEL=!MODEL_ID_6!"
if "!SEL!"=="5" set "NVIDIA_ELITE_MODEL=!MODEL_ID_5!"
if "!SEL!"=="4" set "NVIDIA_ELITE_MODEL=!MODEL_ID_4!"
if "!SEL!"=="3" set "NVIDIA_ELITE_MODEL=!MODEL_ID_3!"
if "!SEL!"=="2" set "NVIDIA_ELITE_MODEL=!MODEL_ID_2!"
if "!SEL!"=="1" set "NVIDIA_ELITE_MODEL=!MODEL_ID_1!"

:: Custom path -- ask for manual model string
if "!NVIDIA_ELITE_MODEL!"=="CUSTOM" (
    echo.
    echo [?] Enter the NIM model string.
    echo [?] You can paste the model ID or the full build.nvidia.com URL - both work.
    echo [?] Example ID : mistralai/mistral-large-3-675b-instruct-2512
    echo [?] Example URL: https://build.nvidia.com/mistralai/mistral-large-3-675b-instruct-2512
    echo.
    set /p NVIDIA_ELITE_MODEL="    Model: "
    if "!NVIDIA_ELITE_MODEL!"=="" (
        echo [!BANG!] No model entered. Using default Kimi K2.5.
        set "NVIDIA_ELITE_MODEL=!MODEL_ID_1!"
    )
    :: Strip build.nvidia.com URL prefix if user pasted the browser URL.
    :: CMD string substitution: replaces the prefix with nothing, leaving only the model path.
    set "NVIDIA_ELITE_MODEL=!NVIDIA_ELITE_MODEL:https://build.nvidia.com/=!"
    set "NVIDIA_ELITE_MODEL=!NVIDIA_ELITE_MODEL:http://build.nvidia.com/=!"
    echo [*] Using model ID: !NVIDIA_ELITE_MODEL!
)

echo.
echo [*] Elite model : !NVIDIA_ELITE_MODEL!
echo.
choice /C YN /M "Save this as your default model (skip menu next time)"
if !errorlevel! equ 1 (
    setx NVIDIA_ELITE_MODEL "!NVIDIA_ELITE_MODEL!" >nul
    echo [+] Saved.
)
echo.

:model_done
echo [*] Elite model : %NVIDIA_ELITE_MODEL%

:: ===========================================================================
:: STEP 6 - Launch
:: ===========================================================================
set ANTHROPIC_AUTH_TOKEN=
set ANTHROPIC_BASE_URL=http://127.0.0.1:4005
:: Claude Code requires ANTHROPIC_API_KEY to be set or it refuses to start.
:: The bridge never forwards this value to NVIDIA - your real key is NVIDIA_API_KEY.
:: Any non-empty string works here; "sk-test-123" is intentionally fake.
set ANTHROPIC_API_KEY=sk-test-123
set PYTHONIOENCODING=utf-8

echo [*] Cleaning up port 4005...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :4005') do (
    taskkill /f /pid %%a >nul 2>&1
)

set PYTHONPATH=%PYTHONPATH%;%~dp0
echo [*] Starting Arbiter on 127.0.0.1:4005...
start "ARBITER BRIDGE" /min "%PYTHON_EXE%" "%~dp0arbiter_bridge.py"
echo [*] Waiting for bridge to start...
timeout /t 5 /nobreak >nul

echo.
echo ======================================================
echo  Arbiter running. Launching Claude Code...
echo ======================================================
echo.
cd /d "%TARGET_DIR%"
claude
