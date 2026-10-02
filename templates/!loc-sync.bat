@echo off
cd /d "%~dp0"
@echo Running the loc-sync script in interactive mode.
@echo.
@echo The log for this run goes to the logs folder: its path is printed below.
@echo.
@echo ------------------------------------------------------------
@echo Checking if `uv` is installed...
uv --version >nul 2>&1
if %errorlevel% neq 0 (
  echo `uv` does not seem to be installed.
  echo Please install `uv`: https://docs.astral.sh/uv/getting-started/installation/
  echo Press any key to exit...
  pause >nul
  exit /b %errorlevel%
)

@echo.
@echo ------------------------------------------------------------
@echo Command: uv run --project loctools loctools/loc-sync.py
uv run --project loctools loctools/loc-sync.py %*
@echo.
@echo.
pause
