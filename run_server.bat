@echo off
rem ---------------------------------------------------------------
rem  datagokr-mcp server launcher (web chat + API + /mcp)
rem  usage : run_server.bat [port] [host]
rem          default port 9001, host 0.0.0.0
rem  ASCII only - do not add non-ASCII characters to this file.
rem ---------------------------------------------------------------
setlocal

cd /d "%~dp0"

set "PORT=%~1"
if "%PORT%"=="" set "PORT=9001"
set "HOST=%~2"
if "%HOST%"=="" set "HOST=0.0.0.0"

set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" (
    echo [ERROR] venv not found: %PY%
    echo         python -m venv .venv  then  .venv\Scripts\pip install -e .
    pause
    exit /b 1
)

set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

echo [INFO] starting server on http://%HOST%:%PORT%  (Ctrl+C to stop)
"%PY%" -m pds serve --host %HOST% --port %PORT%

echo [INFO] server exited with code %ERRORLEVEL%
pause
endlocal
