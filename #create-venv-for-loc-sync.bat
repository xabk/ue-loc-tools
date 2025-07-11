@echo off
@echo Creating venv for loc-sync...
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

@echo `uv` is installed.
@echo You can ues `uv run loc-sync.py` or the batch files to run the script.
@echo.