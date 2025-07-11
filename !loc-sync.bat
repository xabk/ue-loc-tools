@echo off
@echo Running the loc-sync script in interactive mode.
@echo.
@echo See logs/locsync.log for logs.
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
@echo @echo Running the loc-sync script in interactive mode...
@echo Command: python loc-sync.py
uv run loc-sync.py %*
@echo.
@echo.
pause