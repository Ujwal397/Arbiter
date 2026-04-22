@echo off
SETLOCAL EnableDelayedExpansion

:: ===========================================================================
:: MODEL ROSTER -- Edit this block to add / remove / update models.
:: To add a model: increment MODEL_COUNT, add a NAME and ID pair.
:: MODEL_ID must be the exact NIM model string (without "openai/" prefix).
:: The last entry must always be the Custom option (ID=CUSTOM).
::
:: To open this file for editing from the startup menu, choose option E.
:: ===========================================================================
set "MODEL_COUNT=7"
set "MODEL_NAME_1=Kimi K2 0905              (DEFAULT - fast + capable)"
set "MODEL_ID_1=moonshotai/kimi-k2-instruct-0905"
set "MODEL_NAME_2=Kimi K2.5                 (elite - best coding/agentic)"
set "MODEL_ID_2=moonshotai/kimi-k2.5"
set "MODEL_NAME_3=Mistral Large 3           (fallback default - strong general purpose)"
set "MODEL_ID_3=mistralai/mistral-large-3-675b-instruct-2512"
set "MODEL_NAME_4=Qwen3-Coder 480B          (coding-focused, very large)"
set "MODEL_ID_4=qwen/qwen3-coder-480b-a22b"
set "MODEL_NAME_5=Llama 3.3 70B Instruct    (general purpose, fast)"
set "MODEL_ID_5=meta/llama-3.3-70b-instruct"
set "MODEL_NAME_6=DeepSeek R1 0528          (strong reasoning)"
set "MODEL_ID_6=deepseek/deepseek-r1-0528"
set "MODEL_NAME_7=Custom                    (enter any NIM model string manually)"
set "MODEL_ID_7=CUSTOM"

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
    SETLOCAL DisableDelayedExpansion
    echo [!] ERROR: No working Python found.
    ENDLOCAL
    echo     Tried: py, python, python3 - all failed.
    echo.
    echo     Fix options:
    echo       1. Install Python from https://python.org
    echo          Tick "Add python.exe to PATH" during install.
    echo       2. Disable the Windows Store alias:
    echo          Settings ^> Apps ^> Advanced app settings ^> App execution aliases
    echo          then turn OFF python / python3.
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
    SETLOCAL DisableDelayedExpansion
    echo [!] Dependency install failed. See output above.
    ENDLOCAL
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
    echo [?]   Sign in ^> click your avatar ^> API Key
    echo.
    set /p NVIDIA_API_KEY="    Paste key (nvapi-...): "
    echo.
    if "!NVIDIA_API_KEY!"=="" (
        SETLOCAL DisableDelayedExpansion
        echo [!] No key entered. Exiting.
        ENDLOCAL
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
    SETLOCAL DisableDelayedExpansion
    echo [!] Folder not found: %TARGET_DIR%
    echo [!] Check the path or reset it with:  setx TARGET_DIR ""
    ENDLOCAL
    pause
    exit /b 1
)

:: ===========================================================================
:: STEP 5 - Model Selection
:: ===========================================================================
echo.
if not "%NVIDIA_ELITE_MODEL%"=="" goto :model_done

:: ---------------------------------------------------------------------------
:: NIM Availability Check
:: Probes each model with a lightweight POST (max_tokens=1) in parallel.
:: Uses only Python stdlib — no pip deps required — so it runs before
:: check_arbiter.py installs anything.
:: Set SKIP_NIM_CHECK=1 to bypass and show ???? badges instead.
:: ---------------------------------------------------------------------------
if "%SKIP_NIM_CHECK%"=="1" goto :skip_nim_check

:: Clean up any stale tmp file from a previous crashed run.
del "%~dp0nim_status.tmp.bat" >nul 2>&1

echo [*] Checking NIM model availability (8 s timeout, all models in parallel)...
echo.

"%PYTHON_EXE%" "%~dp0verify_nim_models.py"
if exist "%~dp0nim_status.tmp.bat" (
    call "%~dp0nim_status.tmp.bat"
    del "%~dp0nim_status.tmp.bat" >nul 2>&1
)

:skip_nim_check

:: Map each raw status to a 4-char display badge via the :set_badge subroutine.
call :set_badge MODEL_STATUS_1 BADGE_1
call :set_badge MODEL_STATUS_2 BADGE_2
call :set_badge MODEL_STATUS_3 BADGE_3
call :set_badge MODEL_STATUS_4 BADGE_4
call :set_badge MODEL_STATUS_5 BADGE_5
call :set_badge MODEL_STATUS_6 BADGE_6
call :set_badge MODEL_STATUS_7 BADGE_7

echo [?] Select the elite model for this session:
echo     K2 0905 is the default and is always kept as the speed ^/ last-resort model.
echo     Mistral Large 3 is the automatic fallback when the elite model is unavailable.
echo.
SETLOCAL DisableDelayedExpansion
echo [!] Not all NIM models support the tool-calling required by Claude Code.
echo [!] FAIL = not available on your NIM tier or deprecated. Arbiter falls back automatically.
echo [!] Check https://build.nvidia.com for the current model catalogue.
ENDLOCAL
echo.
echo     Status   [OK  ] Live and responding on your key
echo              [FAIL] Not available on NIM (4xx / deprecated)
echo              [TIME] Timed out (NIM overloaded or network issue)
echo              [????] Skipped (no API key yet, or SKIP_NIM_CHECK=1)
echo              [SKIP] Not applicable (Custom slot)
echo.
echo     1. [%BADGE_1%] %MODEL_NAME_1%
echo     2. [%BADGE_2%] %MODEL_NAME_2%
echo     3. [%BADGE_3%] %MODEL_NAME_3%
echo     4. [%BADGE_4%] %MODEL_NAME_4%
echo     5. [%BADGE_5%] %MODEL_NAME_5%
echo     6. [%BADGE_6%] %MODEL_NAME_6%
echo     7. [%BADGE_7%] %MODEL_NAME_7%
echo     E. Edit model list (opens this file in Notepad, then restart)
echo.
choice /C 1234567E /N /M "    Choice [1-7 / E, default=1]: "
set "SEL=%errorlevel%"

:: choice /C returns errorlevel position: 1=1, 2=2 ... 7=7, 8=E
if "%SEL%"=="8" goto :edit_model_list
if "%SEL%"=="7" set "NVIDIA_ELITE_MODEL=%MODEL_ID_7%"
if "%SEL%"=="6" set "NVIDIA_ELITE_MODEL=%MODEL_ID_6%"
if "%SEL%"=="5" set "NVIDIA_ELITE_MODEL=%MODEL_ID_5%"
if "%SEL%"=="4" set "NVIDIA_ELITE_MODEL=%MODEL_ID_4%"
if "%SEL%"=="3" set "NVIDIA_ELITE_MODEL=%MODEL_ID_3%"
if "%SEL%"=="2" set "NVIDIA_ELITE_MODEL=%MODEL_ID_2%"
if "%SEL%"=="1" set "NVIDIA_ELITE_MODEL=%MODEL_ID_1%"

if "!NVIDIA_ELITE_MODEL!"=="CUSTOM" (
    echo.
    echo [?] Enter the NIM model string.
    echo [?] You can paste the model ID or the full build.nvidia.com URL - both work.
    echo [?] Example ID : mistralai/mistral-large-3-675b-instruct-2512
    echo [?] Example URL: https://build.nvidia.com/mistralai/mistral-large-3-675b-instruct-2512
    echo.
    set /p NVIDIA_ELITE_MODEL="    Model: "
    if "!NVIDIA_ELITE_MODEL!"=="" (
        SETLOCAL DisableDelayedExpansion
        echo [!] No model entered. Using default Kimi K2 0905.
        ENDLOCAL
        set "NVIDIA_ELITE_MODEL=%MODEL_ID_1%"
    )
    set "NVIDIA_ELITE_MODEL=!NVIDIA_ELITE_MODEL:https://build.nvidia.com/=!"
    set "NVIDIA_ELITE_MODEL=!NVIDIA_ELITE_MODEL:http://build.nvidia.com/=!"
    echo [*] Using model ID: !NVIDIA_ELITE_MODEL!
)

echo.
echo [*] Elite model : %NVIDIA_ELITE_MODEL%
echo.
choice /C YN /M "Save this as your default model (skip menu next time)"
if !errorlevel! equ 1 (
    setx NVIDIA_ELITE_MODEL "!NVIDIA_ELITE_MODEL!" >nul
    echo [+] Saved.
)
echo.
goto :model_done

:: ---------------------------------------------------------------------------
:edit_model_list
:: ---------------------------------------------------------------------------
echo.
echo [*] Opening start_arbiter.bat in Notepad...
echo [*] Edit the MODEL ROSTER block at the very top of the file.
echo [*] Increment MODEL_COUNT when adding entries, decrement when removing.
echo [*] Save and close Notepad, then re-run start_arbiter.bat to apply.
echo.
start "" notepad "%~f0"
echo [*] Notepad launched. Arbiter setup will now exit - re-run after saving.
echo.
pause
exit /b 0

:model_done
echo [*] Elite model : %NVIDIA_ELITE_MODEL%

:: ===========================================================================
:: STEP 6 - Launch
:: ===========================================================================

:: Arbiter intercepts all Anthropic API calls for this session.
:: ANTHROPIC_BASE_URL redirects Claude Code to the local bridge.
:: ANTHROPIC_API_KEY must be non-empty or Claude Code refuses to start -
::   the bridge never forwards this value to NVIDIA; "sk-test-123" is intentionally fake.
:: ANTHROPIC_AUTH_TOKEN is cleared so Claude Code uses ANTHROPIC_API_KEY instead.
if not "%ANTHROPIC_AUTH_TOKEN%"=="" (
    echo [*] Clearing ANTHROPIC_AUTH_TOKEN for this session ^(Arbiter handles auth^)
    set ANTHROPIC_AUTH_TOKEN=
)
set ANTHROPIC_BASE_URL=http://127.0.0.1:4005
set ANTHROPIC_API_KEY=sk-test-123
set PYTHONIOENCODING=utf-8

:: Kill any stale process already on port 4005.
:: Uses exact port match " :4005 " (with surrounding spaces) to avoid
:: accidentally matching ports like :40050 or :140005.
echo [*] Cleaning up port 4005...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr "LISTENING" ^| findstr " :4005 "') do (
    taskkill /f /pid %%a >nul 2>&1
)

if "%PYTHONPATH%"=="" (
    set "PYTHONPATH=%~dp0"
) else (
    set "PYTHONPATH=%PYTHONPATH%;%~dp0"
)

echo [*] Starting Arbiter on 127.0.0.1:4005...
start "ARBITER BRIDGE" "%PYTHON_EXE%" "%~dp0arbiter_bridge.py"

:: --wait polls http://127.0.0.1:4005/ every 0.5s until the bridge responds
:: (up to 15 seconds). Exits 1 if the bridge never comes up.
"%PYTHON_EXE%" "%~dp0check_arbiter.py" --wait
if %errorlevel% neq 0 (
    echo.
    SETLOCAL DisableDelayedExpansion
    echo [!] Bridge failed to start. See the log excerpt above.
    echo [!] Full log: %~dp0arbiter_runtime.log
    ENDLOCAL
    pause
    exit /b 1
)

:: -- Check Claude Code is installed -----------------------------------------
where claude >nul 2>&1
if %errorlevel% equ 0 goto :claude_found

echo.
echo [^^!] Claude Code is not installed on this machine.
echo [^^!] Arbiter needs Claude Code to work.
echo.
echo     Claude Code is installed via npm (Node.js package manager).
echo.
where npm >nul 2>&1
if %errorlevel% neq 0 goto :no_npm

echo [+] npm is available. Offering automatic install...
echo.
choice /C YN /M "    Install Claude Code now? (npm install -g @anthropic-ai/claude-code)"
if %errorlevel% neq 1 goto :manual_install

echo.
echo [*] Installing Claude Code - this may take a minute...
npm install -g @anthropic-ai/claude-code
if %errorlevel% equ 0 (
    echo.
    echo [+] Claude Code installed successfully.
    echo [+] Launching now...
    echo.
    goto :claude_found
)
echo.
echo [^^!] npm install failed. Try running this script as Administrator,
echo [^^!] or install manually: npm install -g @anthropic-ai/claude-code
pause
exit /b 1

:manual_install
echo.
echo     To install manually:
echo       npm install -g @anthropic-ai/claude-code
echo     Then re-run start_arbiter.bat.
pause
exit /b 1

:no_npm
echo [^^!] npm is not installed either. You need Node.js first.
echo.
echo     Step 1: Download and install Node.js from https://nodejs.org
echo             Choose the LTS version. Tick "Add to PATH" during install.
echo.
echo     Step 2: Open a NEW terminal window (PATH won't update until you do).
echo.
echo     Step 3: Run:  npm install -g @anthropic-ai/claude-code
echo.
echo     Step 4: Re-run start_arbiter.bat
echo.
pause
exit /b 1

:claude_found
echo.
echo ======================================================
echo  Arbiter running. Launching Claude Code...
echo ======================================================
echo.
cd /d "%TARGET_DIR%"

:: Run claude in an isolated cmd so a crash cannot kill this window.
:: Stderr is captured to claude_stderr.log for crash diagnosis.
set "STDERR_LOG=%~dp0claude_stderr.log"
cmd /c claude 2>"%STDERR_LOG%"
set CC_EXIT=%errorlevel%

echo.
echo ======================================================
if %CC_EXIT% equ 0 (
    echo  Claude Code exited normally.
) else (
    echo  Claude Code exited with error code: %CC_EXIT%
    echo.
    echo  --- stderr output: ---
    if exist "%STDERR_LOG%" (
        type "%STDERR_LOG%"
    ) else (
        echo  [no stderr captured]
    )
    echo  ----------------------
    echo.
    echo  Also check:
    echo    - Arbiter Bridge window for [REQ] request logs
    echo    - %~dp0arbiter_runtime.log
)
echo ======================================================
echo.
pause
goto :eof


:: ===========================================================================
:: SUBROUTINE: set_badge
:: Usage:  call :set_badge  STATUS_VAR_NAME  BADGE_VAR_NAME
:: Reads MODEL_STATUS_N (via indirect delayed expansion) and maps it to a
:: fixed-width 4-char display badge stored in BADGE_N.
:: ===========================================================================
:set_badge
set "_raw=!%~1!"
set "%~2=????"
if "!_raw!"=="OK"      set "%~2=OK  "
if "!_raw!"=="NOKEY"   set "%~2=????"
if "!_raw!"=="SKIP"    set "%~2=SKIP"
if "!_raw!"=="TIMEOUT" set "%~2=TIME"
:: Match FAIL:NNN — guard against empty _raw to avoid spurious "ECHO is off." output.
if not "!_raw!"=="" (
    echo !_raw! | findstr /b "FAIL" >nul 2>&1
    if !errorlevel! equ 0 set "%~2=FAIL"
)
goto :eof
