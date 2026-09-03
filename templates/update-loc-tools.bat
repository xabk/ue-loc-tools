@echo off
setlocal enabledelayedexpansion

rem Everything resolves against the working directory.
cd /d "%~dp0"

rem This script always installs something, so it would always hit the
rem cross-drive hardlink warning otherwise.
set UV_LINK_MODE=copy

set FAILED=0

rem A tool installed by an earlier run is on the user PATH but not on this
rem process's, so pick it up before checking whether anything is missing.
call :refresh_path

@echo ============================================================
@echo  Loc tools: install, update and verify
@echo ============================================================
@echo.

@echo [1/6] Checking for uv...
where uv >nul 2>&1
if %errorlevel% neq 0 (
  @echo   uv was not found on PATH. Installing it with winget...
  where winget >nul 2>&1
  if !errorlevel! neq 0 (
    @echo   winget is not available on this machine either.
    @echo   Install uv by hand: https://docs.astral.sh/uv/getting-started/
    @echo.
    pause
    exit /b 1
  )
  winget install --id astral-sh.uv -e --accept-source-agreements --accept-package-agreements
  where uv >nul 2>&1
  if !errorlevel! neq 0 (
    @echo.
    @echo   uv was installed but is not on PATH yet.
    @echo   Open a NEW terminal and run this again.
    @echo.
    pause
    exit /b 1
  )
  call :refresh_path
  @echo   uv installed.
) else (
  @echo   uv found.
)
@echo.

@echo [2/6] Updating the loc tools...
if exist ".git" (
  git submodule update --remote --merge loctools
  if !errorlevel! neq 0 (
    @echo   Could not update the tools. Check your network and git access.
    set FAILED=1
  ) else (
    git diff --quiet --ignore-submodules=dirty -- loctools
    if !errorlevel! neq 0 (
      @echo.
      @echo   The tools were updated. Remember to commit the new version:
      @echo     git commit -am "Bump loctools"
    ) else (
      @echo   Already up to date.
    )
  )
) else (
  @echo   Not a git checkout, so this is a Perforce copy of the tools.
  @echo   Skipping the update and just verifying. Sync in Perforce to update.
)
@echo.

@echo [3/6] Installing dependencies...
uv sync --project loctools --locked --extra test
if %errorlevel% neq 0 (
  @echo   Dependencies failed to install.
  @echo   If uv.lock is out of date with pyproject.toml, run: uv lock
  set FAILED=1
)
@echo.

@echo [4/6] Checking the Crowdin CLI...
uv run --project loctools --no-sync loctools/loc-project.py --ensure-crowdin
if %errorlevel% neq 0 (
  @echo   The Crowdin CLI needs attention. See the messages above.
  set FAILED=1
)
call :refresh_path
@echo.

@echo [5/6] Checking the project configuration...
uv run --project loctools --no-sync loctools/loc-project.py --check
if %errorlevel% neq 0 (
  @echo   The configuration has problems. See the messages above.
  set FAILED=1
)
@echo.

@echo [6/6] Running the tool's own tests...
uv run --directory loctools --extra test python -m pytest -q
if %errorlevel% neq 0 (
  @echo   Tests failed. The tools may not work correctly.
  set FAILED=1
)
@echo.

@echo ============================================================
if %FAILED% neq 0 (
  @echo  SOMETHING NEEDS ATTENTION - see the messages above.
  @echo  Do not run a loc sync until it is resolved.
) else (
  @echo  ALL GOOD - the loc tools are ready to use.
  @echo  Run ^^!loc-sync.bat to start a sync.
)
@echo ============================================================
@echo.
pause
exit /b %FAILED%

rem winget adds new tool directories to the user PATH in the registry.
rem This process inherited PATH at launch and cannot see that, so pull
rem the current value in rather than asking for a terminal restart.
:refresh_path
for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('Path','User')"`) do set "PATH=%PATH%;%%P"
exit /b 0
