@echo off
set "PROJECT_ROOT=%~dp0"
cd /d "%PROJECT_ROOT%"

if exist ".venv\Scripts\activate.bat" (
    echo [OK] Activating .venv...
    call .venv\Scripts\activate.bat
) else if exist "venv\Scripts\activate.bat" (
    echo [OK] Activating venv...
    call venv\Scripts\activate.bat
) else (
    echo [!] Virtual environment not found. Please create one with: python -m venv .venv
    pause
    exit /b
)

echo.
echo [INFO] Virtual environment activated!
echo [INFO] Use 'python app.py' to start the application.
cmd /k
