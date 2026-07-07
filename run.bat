@echo off
setlocal
cd /d "%~dp0"

python -c "import sys" >nul 2>nul
if not errorlevel 1 (
    python main.py
    exit /b %ERRORLEVEL%
)

py -3 -c "import sys" >nul 2>nul
if not errorlevel 1 (
    py -3 main.py
    exit /b %ERRORLEVEL%
)

if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" (
    "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" main.py
    exit /b %ERRORLEVEL%
)

echo Python 3 was not found. Install Python 3, then run this file again.
pause
