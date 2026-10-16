@echo off
:: ============================================================
:: start_workers.bat
:: Starts Redis + Celery workers for the Court Scraper system.
:: Run this BEFORE starting app.py / main.py.
::
:: Requirements: Redis binary in .\bin\redis\  (set up by setup_redis.bat)
:: ============================================================

setlocal

set REDIS_EXE=bin\redis\redis-server.exe
set REDIS_CONF=bin\redis\redis.windows.conf
set VENV=.venv\Scripts

:: ── 1. Start Redis (background) ──────────────────────────────────────────────
echo [1/3] Starting Redis...
tasklist /FI "IMAGENAME eq redis-server.exe" 2>NUL | find /I "redis-server.exe" >NUL
if %ERRORLEVEL% == 0 (
    echo      Redis already running. Skipping.
) else (
    start "Redis" /B %REDIS_EXE% %REDIS_CONF%
    timeout /t 2 /nobreak > NUL
    echo      Redis started on 127.0.0.1:6379
)

:: ── 2. Start Deed workers (4 threads) ────────────────────────────────────────
echo [2/3] Starting Deed workers (4 threads)...
start "Celery-Deed" %VENV%\celery -A tasks.celery_app worker ^
    -Q deed ^
    --concurrency=4 ^
    --pool=threads ^
    --loglevel=info ^
    -n deed@%%COMPUTERNAME%%

:: ── 3. Start Obituary workers (8 prefork) ────────────────────────────────────
echo [3/3] Starting Obituary workers (8 processes)...
start "Celery-Obituary" %VENV%\celery -A tasks.celery_app worker ^
    -Q obituary ^
    --concurrency=8 ^
    --pool=prefork ^
    --loglevel=info ^
    -n obituary@%%COMPUTERNAME%%

echo.
echo All workers started.
echo Flower dashboard: run  .venv\Scripts\celery -A tasks.celery_app flower --port=5555
echo Then open:  http://localhost:5555
echo.
echo Press any key to open the Flower dashboard now, or Ctrl+C to skip.
pause > NUL
start "Flower" %VENV%\celery -A tasks.celery_app flower --port=5555
start http://localhost:5555
