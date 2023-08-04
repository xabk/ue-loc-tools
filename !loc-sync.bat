@echo off
@echo Running the loc-sync script in interactive mode.
@echo.
@echo See logs/locsync.log for logs.
@echo.
@echo ------------------------------------------------------------
@echo Trying to activate the virtual environment...
@echo Command: call .venv\Scripts\activate.bat
call .venv\Scripts\activate.bat
if %errorlevel% neq 0 (
  echo Command failed with exit code %errorlevel%.
  echo Please create a virtual environment under .venv and install the dependencies.
  pause
  exit /b %errorlevel%
)
@echo Virtual environment activated.
@echo.
@echo.

@echo ------------------------------------------------------------
@echo @echo Running the loc-sync script in interactive mode...
@echo Command: python loc-sync.py
python loc-sync.py
@echo.
@echo.
pause