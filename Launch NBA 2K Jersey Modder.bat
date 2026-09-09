@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title NBA 2K Jersey Modder Launcher

set "GIT_EXE="
where git >nul 2>nul && set "GIT_EXE=git"
if not defined GIT_EXE if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\cmd\git.exe" set "GIT_EXE=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\cmd\git.exe"
if not defined GIT_EXE if exist "C:\Program Files\Git\cmd\git.exe" set "GIT_EXE=C:\Program Files\Git\cmd\git.exe"
if not defined GIT_EXE if exist "%LOCALAPPDATA%\Programs\Git\cmd\git.exe" set "GIT_EXE=%LOCALAPPDATA%\Programs\Git\cmd\git.exe"
if /i "%GIT_EXE%"=="%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\cmd\git.exe" set "GIT_EXEC_PATH=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\mingw64\bin"

set "CURRENT_COMMIT="
if defined GIT_EXE (
    "!GIT_EXE!" -C "%~dp0" rev-parse --is-inside-work-tree >nul 2>nul
    if not errorlevel 1 (
        echo Checking GitHub for updates...
        "!GIT_EXE!" -C "%~dp0" pull --ff-only
        if errorlevel 1 echo Update could not be applied. Starting the installed version.
        for /f %%C in ('"!GIT_EXE!" -C "%~dp0" rev-parse HEAD 2^>nul') do set "CURRENT_COMMIT=%%C"
    )
)

set "BASE_PY="
if exist "%~dp0.venv\Scripts\python.exe" set "BASE_PY=%~dp0.venv\Scripts\python.exe"
if not defined BASE_PY if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" set "BASE_PY=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not defined BASE_PY where python >nul 2>nul && set "BASE_PY=python"
if not defined BASE_PY (
    echo Python 3 was not found.
    pause
    exit /b 1
)

"%BASE_PY%" "%~dp0tools\bootstrap_modern.py"
if errorlevel 1 goto :wpf_fallback

set "ELECTRON_EXE=%~dp0electron\out\NBA 2K Jersey Modder-win32-x64\NBA2KJerseyModder.exe"
set "BUILD_STAMP=%~dp0electron\out\.build-commit"
set "NEEDS_BUILD=0"
if not exist "%ELECTRON_EXE%" set "NEEDS_BUILD=1"
if defined CURRENT_COMMIT if exist "%BUILD_STAMP%" (
    set /p BUILT_COMMIT=<"%BUILD_STAMP%"
    if /i not "!BUILT_COMMIT!"=="!CURRENT_COMMIT!" set "NEEDS_BUILD=1"
)
if defined CURRENT_COMMIT if not exist "%BUILD_STAMP%" set "NEEDS_BUILD=1"

if "%NEEDS_BUILD%"=="1" (
    set "NODE_DIR="
    set "PNPM_EXE="
    if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe" set "NODE_DIR=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin"
    if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\fallback\pnpm.cmd" set "PNPM_EXE=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\fallback\pnpm.cmd"
    if not defined NODE_DIR for %%N in (node.exe) do set "NODE_DIR=%%~dp$PATH:N"
    if not defined PNPM_EXE for %%N in (pnpm.cmd) do set "PNPM_EXE=%%~$PATH:N"
    if not defined NODE_DIR goto :wpf_fallback
    if not defined PNPM_EXE goto :wpf_fallback
    set "PATH=!NODE_DIR!;!PATH!"
    echo Preparing Electron workspace...
    pushd "%~dp0electron"
    "!PNPM_EXE!" install --frozen-lockfile
    if errorlevel 1 (popd & goto :wpf_fallback)
    "!PNPM_EXE!" package
    if errorlevel 1 (popd & goto :wpf_fallback)
    popd
    if defined CURRENT_COMMIT (
        if not exist "%~dp0electron\out" mkdir "%~dp0electron\out"
        >"%BUILD_STAMP%" echo !CURRENT_COMMIT!
    )
)

if exist "%ELECTRON_EXE%" (
    start "" /d "%~dp0" "%ELECTRON_EXE%"
    exit /b 0
)

:wpf_fallback
echo The update could not be built.
if exist "%~dp0electron\out\NBA 2K Jersey Modder-win32-x64\NBA2KJerseyModder.exe" (
    echo Starting the last installed Electron version.
    start "" /d "%~dp0" "%~dp0electron\out\NBA 2K Jersey Modder-win32-x64\NBA2KJerseyModder.exe"
    exit /b 0
)
echo Install Python, Node.js and pnpm, then try again.
pause
exit /b 1
