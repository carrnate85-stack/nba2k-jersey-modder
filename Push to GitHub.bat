@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

set "GIT_EXE=git"
where git >nul 2>nul
if not errorlevel 1 goto :git_found

set "GIT_EXE=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\cmd\git.exe"
if exist "%GIT_EXE%" goto :git_found

set "GIT_EXE=C:\Program Files\Git\cmd\git.exe"
if exist "%GIT_EXE%" goto :git_found

set "GIT_EXE=%LOCALAPPDATA%\GitHubDesktop\app\git\cmd\git.exe"
if exist "%GIT_EXE%" goto :git_found

echo Git was not found.
echo Install Git for Windows or GitHub Desktop, then run this again.
pause
exit /b 1

:git_found
echo Using Git: %GIT_EXE%

"%GIT_EXE%" remote get-url origin >nul 2>nul
if errorlevel 1 (
    echo Paste the empty GitHub repository URL.
    echo Example: https://github.com/your-name/nba2k-jersey-modder.git
    set /p REPO_URL=GitHub URL: 
    if "!REPO_URL!"=="" (
        echo No URL entered.
        pause
        exit /b 1
    )
    "%GIT_EXE%" remote add origin "!REPO_URL!"
)

"%GIT_EXE%" branch -M main
"%GIT_EXE%" push -u origin main
pause
