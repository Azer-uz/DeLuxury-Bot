import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz
from datetime import datetime
from aiogram import Bot
import config
from moysklad_api import ms_api

tz = pytz.timezone(config.TIMEZONE)

def format_sum(val: float) -> str:
    return f"{val:,.2f}".replace(",", " ")

async def send_hourly_report(bot: Bot):
    """Har soatda avtomatik savdo hisobotini yuboruvchi vazifa"""
    now = datetime.now(tz)
    current_hour = now.hour

    # Faqat ish soatlarida (09:00 dan 23:00 gacha) ishlaydi
    if not (config.WORK_START_HOUR <= current_hour <= config.WORK_END_HOUR):
        return

    try:
        sales = await ms_api.get_hourly_sales()
        prev_hour = current_hour - 1 if current_hour > 0 else 23
        prev_hour_data = sales["hourly"].get(prev_hour, {"count": 0, "sum": 0.0})

        msg_lines = [
            f"⏱ <b>DE LUXURY — SOATLIK SAVDO AVTO-HISOBOTI</b>",
            f"🕒 Vaqt: <b>{prev_hour:02d}:00 - {current_hour:02d}:00</b>",
            f"📅 Sana: <b>{sales['date']}</b>\n",
            f"▫️ <b>O'tgan soatdagi savdo:</b> <code>{format_sum(prev_hour_data['sum'])} so'm</code> ({prev_hour_data['count']} ta chek)",
            f"━━━━━━━━━━━━━━━━━━━━━",
            f"💰 <b>Kun boshidan buyon JAMI:</b> <code>{format_sum(sales['total_sum'])} so'm</code>",
            f"🧾 <b>Jami cheklar:</b> {sales['total_count']} ta",
            f"📊 <b>O'rtacha chek:</b> {format_sum(sales['avg_check'])} so'm"
        ]

        text = "\n".join(msg_lines)
        all_recipients = config.SUPER_ADMIN_IDS.union(config.MANAGER_IDS)

        for user_id in all_recipients:
            try:
                await bot.send_message(user_id, text, parse_mode="HTML")
            except Exception as e:
                print(f"Failed to send hourly report to {user_id}: {e}")

    except Exception as e:
        print(f"Error in send_hourly_report: {e}")

def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=tz)
    # Har soatning 0-daqiqasida (masalan 10:00, 11:00, 12:00 ...)
    scheduler.add_job(
        send_hourly_report,
        CronTrigger(minute=0, timezone=tz),
        args=[bot],
        id="hourly_sales_job",
        replace_existing=True
    )
    return scheduler
