@echo off
setlocal
cd /d "%~dp0"

where git >nul 2>nul
if errorlevel 1 (
    echo Git was not found on PATH.
    echo Install Git for Windows or GitHub Desktop, then run this again.
    pause
    exit /b 1
)

git remote get-url origin >nul 2>nul
if errorlevel 1 (
    echo Paste the empty GitHub repository URL.
    echo Example: https://github.com/your-name/nba2k-jersey-modder.git
    set /p REPO_URL=GitHub URL: 
    if "%REPO_URL%"=="" (
        echo No URL entered.
        pause
        exit /b 1
    )
    git remote add origin "%REPO_URL%"
)

git branch -M main
git push -u origin main
pause
