import os
from dotenv import load_dotenv

# .env faylini yuklaymiz
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
MOYSKLAD_TOKEN = os.getenv("MOYSKLAD_TOKEN", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

# Bosh Rahbarlar (To'liq huquqli Super Adminlar)
def parse_id_list(env_val: str):
    if not env_val:
        return set()
    res = set()
    for item in env_val.split(","):
        item = item.strip()
        if item.isdigit():
            res.add(int(item))
    return res

SUPER_ADMIN_IDS = parse_id_list(os.getenv("SUPER_ADMIN_IDS", "1223243487"))
MANAGER_IDS = parse_id_list(os.getenv("MANAGER_IDS", ""))

# Timezone va do'kon ish vaqti
TIMEZONE = "Asia/Tashkent"
WORK_START_HOUR = 9   # 09:00
WORK_END_HOUR = 23    # 23:00

# MoySklad API Base
MOYSKLAD_API_URL = "https://api.moysklad.ru/api/remap/1.2"

def get_user_role(user_id: int) -> str | None:
    """Foydalanuvchi rolini aniqlaydi: 'super_admin', 'manager' yoki None"""
    if user_id in SUPER_ADMIN_IDS:
        return "super_admin"
    elif user_id in MANAGER_IDS:
        return "manager"
    return None
