@echo off
chcp 65001 > nul
title DE LUXURY - Serverga Yuklash (Deploy)
echo ========================================================
echo       DE LUXURY - BOTNI SERVERDA YANGILASH (DEPLOY)
echo ========================================================
echo.

set SERVER=root@189.74.99.96
set APP_DIR=/var/www/deluxury-bot

rem .env serverdagi nusxasi saqlanadi (ustidan yozilmaydi). Birinchi o'rnatish uchun: deploy\setup_server.sh
echo 📁 1. Kod fayllari serverga nusxalanmoqda...
ssh %SERVER% "mkdir -p %APP_DIR%/handlers %APP_DIR%/deploy"
scp config.py main.py moysklad_api.py ai_agent.py excel_generator.py keyboards.py scheduler.py requirements.txt %SERVER%:%APP_DIR%/
scp handlers/*.py %SERVER%:%APP_DIR%/handlers/
scp deploy/* %SERVER%:%APP_DIR%/deploy/

echo.
echo ⚙️ 2. Paketlar tekshirilmoqda va bot qayta ishga tushirilmoqda...
ssh %SERVER% "cd %APP_DIR% && venv/bin/pip install -q -r requirements.txt && systemctl restart deluxury && sleep 3 && systemctl is-active deluxury"

echo.
echo ========================================================
echo ✅ BOT SERVERDA YANGILANDI
echo ========================================================
pause
