@echo off
@echo Creating venv for loc-sync...
@echo.
@echo ------------------------------------------------------------
@echo Trying to create a virtual environment...
@echo Replace `projectname` with the prefix you want for the virtual environment
@echo Command: python -m venv .venv --prompt projectname
python -m venv .venv --prompt projectname
if %errorlevel% neq 0 (
  echo Command failed with exit code %errorlevel%.
  echo Please create a virtual environment manually under .venv and install the dependencies.
  pause
  exit /b %errorlevel%
)
@echo Virtual environment created.
@echo.
@echo.

@echo ------------------------------------------------------------
@echo Trying to activate the virtual environment...
@echo Command: call .venv\Scripts\activate.bat
call .venv\Scripts\activate.bat
if %errorlevel% neq 0 (
  echo Command failed with exit code %errorlevel%.
  echo Please create a virtual environment under manually .venv and install the dependencies.
  pause
  exit /b %errorlevel%
)
@echo Virtual environment activated.
@echo.
@echo.

@echo ------------------------------------------------------------
@echo Trying to install dependencies...
@echo Command: pip install -r requirements.txt
pip install -r requirements.txt
if %errorlevel% neq 0 (
  echo Command failed with exit code %errorlevel%.
  echo Please create a virtual environment under manually .venv and install the dependencies.
  pause
  exit /b %errorlevel%
)
@echo Virtual environment activated.
@echo.
@echo.
@echo on

pause