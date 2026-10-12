@echo off
setlocal
cd /d "%~dp0"
if not defined CHATBOT_INTERNAL_API_KEY (
  >&2 echo CHATBOT_INTERNAL_API_KEY must be set before starting campaign-service.
  exit /b 1
)
if not defined CHAT_AUDIT_API_KEY (
  >&2 echo CHAT_AUDIT_API_KEY must be set before starting campaign-service.
  exit /b 1
)
set CAMPAIGN_REQUIRE_POSTGRES=false
set CHAT_AUDIT_REQUIRE_PERSISTENCE=false
"C:\Program Files\Python311\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8080
