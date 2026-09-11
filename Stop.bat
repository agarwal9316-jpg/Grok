@echo off
echo Stopping Grok Org OS on port 8000 (if running)...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
  echo Killing PID %%a
  taskkill /F /PID %%a >nul 2>&1
)
echo Done.
pause
