@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title NBA 2K Mod Tools Launcher

set "GIT_EXE="
where git >nul 2>nul
if not errorlevel 1 set "GIT_EXE=git"

if not defined GIT_EXE (
    set "CANDIDATE=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\cmd\git.exe"
    if exist "!CANDIDATE!" set "GIT_EXE=!CANDIDATE!"
)
if not defined GIT_EXE (
    set "CANDIDATE=C:\Program Files\Git\cmd\git.exe"
    if exist "!CANDIDATE!" set "GIT_EXE=!CANDIDATE!"
)
if not defined GIT_EXE (
    set "CANDIDATE=%LOCALAPPDATA%\Programs\Git\cmd\git.exe"
    if exist "!CANDIDATE!" set "GIT_EXE=!CANDIDATE!"
)
if not defined GIT_EXE (
    for /d %%D in ("%LOCALAPPDATA%\GitHubDesktop\app-*") do (
        if exist "%%D\resources\app\git\cmd\git.exe" (
            set "GIT_EXE=%%D\resources\app\git\cmd\git.exe"
        )
    )
)

if defined GIT_EXE (
    "!GIT_EXE!" -C "%~dp0" rev-parse --is-inside-work-tree >nul 2>nul
    if not errorlevel 1 (
        echo Checking GitHub for updates...
        "!GIT_EXE!" -C "%~dp0" pull --rebase --autostash
        if errorlevel 1 (
            echo Update could not be applied. Starting the installed version.
        )
    )
) else (
    echo Git was not found. Starting without checking for updates.
)

set "BUNDLED_PY=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

if exist "%BUNDLED_PY%" (
    "%BUNDLED_PY%" "%~dp0main.py"
    exit /b %ERRORLEVEL%
)

python -c "import sys" >nul 2>nul
if not errorlevel 1 (
    python "%~dp0main.py"
    exit /b %ERRORLEVEL%
)

py -3 -c "import sys" >nul 2>nul
if not errorlevel 1 (
    py -3 "%~dp0main.py"
    exit /b %ERRORLEVEL%
)

echo Python 3 was not found.
echo Install Python 3 or open this project through Codex again so the bundled runtime is available.
pause
