@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title NBA 2K Jersey Modder Launcher

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

set "BASE_PY="
set "BUNDLED_PY=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%BUNDLED_PY%" set BASE_PY="%BUNDLED_PY%"

if not defined BASE_PY (
    where python >nul 2>nul
    if not errorlevel 1 set "BASE_PY=python"
)
if not defined BASE_PY (
    py -3 -c "import sys" >nul 2>nul
    if not errorlevel 1 set "BASE_PY=py -3"
)
if not defined BASE_PY (
    echo Python 3 was not found.
    echo Install Python 3 or open this project through Codex again so the bundled runtime is available.
    pause
    exit /b 1
)

%BASE_PY% "%~dp0tools\bootstrap_modern.py"
if errorlevel 1 (
    echo.
    echo The modern desktop components could not be prepared.
    pause
    exit /b 1
)

where dotnet >nul 2>nul
if errorlevel 1 (
    echo .NET 8 SDK was not found.
    echo Install the .NET 8 SDK to build and run the WPF application.
    pause
    exit /b 1
)

echo Preparing WPF workspace...
dotnet build "%~dp0wpf\JerseyModder.Wpf\JerseyModder.Wpf.csproj" -c Release --nologo --verbosity quiet
if errorlevel 1 (
    echo.
    echo The WPF application could not be built.
    pause
    exit /b 1
)

start "" "%~dp0wpf\JerseyModder.Wpf\bin\Release\net8.0-windows\NBA2KJerseyModder.exe"
exit /b 0
