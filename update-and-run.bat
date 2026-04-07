@echo off
setlocal

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0update-and-run.ps1"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
  echo.
  echo Update or startup failed. Press any key to close this window.
  pause >nul
)

exit /b %EXIT_CODE%
