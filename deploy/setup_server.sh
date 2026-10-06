#!/bin/bash
# ==============================================================================
# DE LUXURY — TELEGRAM BOT VA AI ANALITIK SERVERN O'RNATISH SKRIPTI
# ==============================================================================

set -e

echo "🚀 1. Tizim paketlari yangilanmoqda..."
apt update && apt upgrade -y
apt install -y python3 python3-pip python3-venv

echo "📁 2. Loyiha papkasi (/var/www/deluxury-bot) sozlanmoqda..."
mkdir -p /var/www/deluxury-bot
cd /var/www/deluxury-bot

echo "🐍 3. Python virtual muhiti (venv) yaratilmoqda..."
python3 -m venv venv
venv/bin/pip install --upgrade pip
venv/bin/pip install -r requirements.txt

echo "⚙️ 4. Systemd servisi (/etc/systemd/system/deluxury.service) o'rnatilmoqda..."
cp deploy/deluxury.service /etc/systemd/system/deluxury.service
systemctl daemon-reload
systemctl enable deluxury
systemctl restart deluxury

echo "✅ 5. Bot muvaffaqiyatli ishga tushirildi!"
systemctl status deluxury --no-pager
