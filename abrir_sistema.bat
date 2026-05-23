@echo off
cd /d "%~dp0"
echo Iniciando sistema de gestion...
echo.
echo Cuando veas "Running on http://127.0.0.1:5000", entra desde el navegador a:
echo http://127.0.0.1:5000
echo.
"C:\Users\frang\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" run_server.py
pause
