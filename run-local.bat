@echo off
setlocal

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-local-launcher.ps1"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
  echo.
  echo Startup failed. Press any key to close this window.
  pause >nul
)

exit /b %EXIT_CODE%
