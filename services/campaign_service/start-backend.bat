@echo off
cd /d "C:\Users\User\Desktop\MF\ai-marketing-factory\services\campaign_service"
set CHATBOT_INTERNAL_API_KEY=change_me_internal_key
set CHAT_AUDIT_API_KEY=change_me_audit_key
set CAMPAIGN_REQUIRE_POSTGRES=false
set CHAT_AUDIT_REQUIRE_PERSISTENCE=false
"C:\Program Files\Python311\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8080