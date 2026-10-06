@echo off
chcp 65001 > nul
title DE LUXURY - Serverga Yuklash (Deploy)
echo ========================================================
echo       DE LUXURY - BOTNI SERVERGA YUKLASH (DEPLOY)
echo ========================================================
echo.

set /p SERVER_IP="Serveringiz IP manzilini kiriting (masalan 189.74.99.96): "

echo.
echo 📁 1. Loyiha fayllari serverga (/var/www/deluxury-bot) nusxalanmoqda...
ssh root@%SERVER_IP% "mkdir -p /var/www/deluxury-bot/handlers /var/www/deluxury-bot/deploy"
scp -r .env config.py main.py moysklad_api.py ai_agent.py excel_generator.py keyboards.py scheduler.py requirements.txt root@%SERVER_IP%:/var/www/deluxury-bot/
scp -r handlers/* root@%SERVER_IP%:/var/www/deluxury-bot/handlers/
scp -r deploy/* root@%SERVER_IP%:/var/www/deluxury-bot/deploy/

echo.
echo ⚙️ 2. Serverda servis va paketlar sozlanmoqda...
ssh root@%SERVER_IP% "bash /var/www/deluxury-bot/deploy/setup_server.sh"

echo.
echo ========================================================
echo ✅ BOT SERVERDA 24/7 REJIMDA ISHLAY BOSHLADI!
echo ========================================================
pause
