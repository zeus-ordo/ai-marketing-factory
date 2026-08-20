@echo off
setlocal

cd /d "%~dp0"

echo.
echo [AI Marketing Factory] Bootstrap starting...
echo.

where npm >nul 2>nul
if errorlevel 1 (
  echo [ERROR] npm not found. Please install Node.js 20+ first.
  goto :fail
)

npm run dev:bootstrap:win
if errorlevel 1 goto :fail

goto :end

:fail
echo.
echo Bootstrap failed. Please check the error messages above.
pause
exit /b 1

:end
echo.
echo Bootstrap finished.
pause
exit /b 0
