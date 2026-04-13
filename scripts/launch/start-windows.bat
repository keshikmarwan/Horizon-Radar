@echo off
setlocal EnableExtensions EnableDelayedExpansion
set "HOLD_OPEN=1"
if /I "%~1"=="--no-pause" set "HOLD_OPEN=0"

set "ROOT_DIR=%~dp0..\.."
for %%I in ("%ROOT_DIR%") do set "ROOT_DIR=%%~fI"
set "BACKEND_DIR=%ROOT_DIR%\backend"
set "FRONTEND_DIR=%ROOT_DIR%\frontend"
set "RUNTIME_DIR=%ROOT_DIR%\runtime"
set "BACKEND_HOST=127.0.0.1"
set "BACKEND_PORT=8000"
set "FRONTEND_PORT=3000"
set "API_URL=http://%BACKEND_HOST%:%BACKEND_PORT%"

where npm >nul 2>&1
if errorlevel 1 (
  echo npm non trovato. Installa Node.js e riprova.
  goto :exit_err
)

set "PY_BIN="
for %%P in (py.exe python.exe) do (
  where %%P >nul 2>&1
  if not errorlevel 1 (
    set "PY_BIN=%%P"
    goto :py_found
  )
)

echo Python non trovato. Installa Python 3.10+ e riprova.
goto :exit_err

:py_found
if /I "%PY_BIN%"=="py.exe" (
  set "PY_CMD=py -3"
) else (
  set "PY_CMD=python"
)

if not exist "%RUNTIME_DIR%" mkdir "%RUNTIME_DIR%"
if not exist "%RUNTIME_DIR%\logs" mkdir "%RUNTIME_DIR%\logs"
if not exist "%RUNTIME_DIR%\snapshots" mkdir "%RUNTIME_DIR%\snapshots"
if not exist "%BACKEND_DIR%\data\horizon_matcher" mkdir "%BACKEND_DIR%\data\horizon_matcher"

(
  echo APP_BASE_URL=http://localhost:%FRONTEND_PORT%
) > "%BACKEND_DIR%\.env"

(
  echo NEXT_PUBLIC_API_URL=%API_URL%
  echo NEXT_PUBLIC_DEMO_USER_ID=demo-user
  echo AUTH_SECRET=devsecret
  echo AUTH_URL=http://localhost:%FRONTEND_PORT%
  echo ADMIN_USERNAME=admin
  echo ADMIN_PASSWORD=admin123
) > "%FRONTEND_DIR%\.env.local"

if not exist "%BACKEND_DIR%\.venv\Scripts\python.exe" (
  echo Creo virtualenv backend...
  pushd "%BACKEND_DIR%"
  call %PY_CMD% -m venv .venv
  if errorlevel 1 (
    popd
    echo Errore creazione virtualenv.
    goto :exit_err
  )
  popd
)

echo Installo dipendenze backend...
pushd "%BACKEND_DIR%"
call .venv\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 (
  popd
  echo Errore aggiornamento pip.
  goto :exit_err
)
call .venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
  popd
  echo Errore installazione dipendenze backend.
  goto :exit_err
)
popd

if not exist "%FRONTEND_DIR%\node_modules" (
  echo Installo dipendenze frontend...
  pushd "%FRONTEND_DIR%"
  call npm install
  if errorlevel 1 (
    popd
    echo Errore installazione dipendenze frontend.
    goto :exit_err
  )
  popd
)

for /f "tokens=5" %%a in ('netstat -ano ^| findstr :%BACKEND_PORT% ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :%FRONTEND_PORT% ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>&1

start "Horizon Backend" cmd /k "cd /d %BACKEND_DIR% && set PYTHONPATH=%BACKEND_DIR% && call .venv\Scripts\activate.bat && python -m uvicorn app.main:app --host %BACKEND_HOST% --port %BACKEND_PORT% --reload"
start "Horizon Frontend" cmd /k "cd /d %FRONTEND_DIR% && npm run dev -- -H 0.0.0.0 -p %FRONTEND_PORT%"

echo.
echo Avvio completato.
echo Frontend: http://localhost:%FRONTEND_PORT%
echo Backend docs: http://localhost:%BACKEND_PORT%/docs
goto :exit_ok

:exit_err
echo.
echo Avvio non completato.
if "%HOLD_OPEN%"=="1" pause
exit /b 1

:exit_ok
if "%HOLD_OPEN%"=="1" pause
exit /b 0
