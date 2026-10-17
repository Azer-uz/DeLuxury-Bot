import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional
from aiogram import Bot
import config
from moysklad_api import ms_api

tz = pytz.timezone(config.TIMEZONE)
logger = logging.getLogger(__name__)

# Kassadan MoySkladga chek kechikib tushishi mumkin — hisobotni soat boshidan 2 daqiqa keyin olamiz
HOURLY_REPORT_MINUTE = 2
# Kun yakuni (kechagi kun) hisoboti vaqti
DAILY_REPORT_HOUR = 0
DAILY_REPORT_MINUTE = 5

WEEKDAYS_UZ = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"]

def format_sum(val: float) -> str:
    return f"{val:,.2f}".replace(",", " ")

def hour_range(hour: int) -> str:
    return f"{hour:02d}:00 - {(hour + 1) % 24:02d}:00"

def is_work_hour(hour: int) -> bool:
    """Soat oralig'i [hour, hour+1) do'kon ish vaqtiga (09:00–23:00) to'g'ri keladimi"""
    return config.WORK_START_HOUR <= hour < config.WORK_END_HOUR

def pct_change(cur: float, prev: float) -> str:
    if prev <= 0:
        return "—"
    diff = (cur - prev) / prev * 100
    arrow = "🟢" if diff >= 0 else "🔴"
    return f"{arrow} {diff:+.1f}%"

async def fetch_sales(target_date: date, attempts: int = 3, delay: int = 30) -> Optional[Dict[str, Any]]:
    """Savdoni keshsiz oladi; MoySklad javob bermasa bir necha marta qayta urinadi"""
    for attempt in range(1, attempts + 1):
        try:
            return await ms_api.get_hourly_sales(target_date, use_cache=False)
        except Exception as e:
            logger.warning(f"Savdo ma'lumotini olishda xato ({attempt}/{attempts}): {e}")
            if attempt < attempts:
                await asyncio.sleep(delay)
    return None

async def broadcast(bot: Bot, text: str, recipients: set):
    for user_id in recipients:
        try:
            await bot.send_message(user_id, text, parse_mode="HTML")
        except Exception as e:
            logger.warning(f"{user_id} ga xabar yuborilmadi: {e}")

def all_recipients() -> set:
    return config.SUPER_ADMIN_IDS | config.MANAGER_IDS

async def send_hourly_report(bot: Bot):
    """Har soatda o'tgan soat savdosini yuboradi.
    Ish vaqtida (09:00–23:00) — har doim; ish vaqtidan tashqarida — faqat savdo yoki vozvrat bo'lsa."""
    now = datetime.now(tz)
    period_start = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    hour = period_start.hour
    in_work_hours = is_work_hour(hour)

    # 00:02 dagi hisobot 23:00–00:00 ni, ya'ni kechagi kunni yopadi
    sales = await fetch_sales(period_start.date())
    if sales is None:
        if in_work_hours:
            await broadcast(
                bot,
                f"⚠️ <b>Soatlik hisobot ({hour_range(hour)}) shakllanmadi</b>\n"
                f"MoySklad javob bermadi. Ma'lumotlar keyingi hisobotda jami summaga qo'shiladi.",
                config.SUPER_ADMIN_IDS,
            )
        return

    h = sales["hourly"][hour]
    if not in_work_hours and h["count"] == 0 and h["return_count"] == 0:
        return

    title = (
        "⏱ <b>DE LUXURY — SOATLIK SAVDO AVTO-HISOBOTI</b>"
        if in_work_hours else
        "🌙 <b>DE LUXURY — ISH VAQTIDAN TASHQARI SAVDO</b>"
    )
    lines = [
        title,
        f"🕒 Vaqt: <b>{hour_range(hour)}</b>",
        f"📅 Sana: <b>{sales['date']}</b>\n",
        f"▫️ <b>O'tgan soatdagi savdo:</b> <code>{format_sum(h['sum'])} so'm</code> ({h['count']} ta chek)",
    ]
    if h["return_count"]:
        lines.append(f"↩️ <b>Vozvrat:</b> <code>-{format_sum(h['return_sum'])} so'm</code> ({h['return_count']} ta)")
    lines.extend([
        "━━━━━━━━━━━━━━━━━━━━━",
        f"💰 <b>Kun boshidan buyon SOF TUSHUM:</b> <code>{format_sum(sales['total_sum'])} so'm</code>",
        f"🧾 <b>Jami cheklar:</b> {sales['total_count']} ta",
    ])
    if sales["return_count"]:
        lines.append(f"↩️ <b>Jami vozvrat:</b> {format_sum(sales['return_sum'])} so'm ({sales['return_count']} ta)")
    lines.append(f"📊 <b>O'rtacha chek:</b> {format_sum(sales['avg_check'])} so'm")

    await broadcast(bot, "\n".join(lines), all_recipients())

async def send_daily_summary(bot: Bot):
    """Kechagi kun yakuni: sof tushum, vozvratlar, soatlar kesimi, kecha va o'tgan hafta bilan solishtirish"""
    day = datetime.now(tz).date() - timedelta(days=1)
    sales = await fetch_sales(day)
    if sales is None:
        await broadcast(
            bot,
            f"⚠️ <b>{day.strftime('%d.%m.%Y')} kun yakuni hisoboti shakllanmadi</b>\n"
            f"MoySklad javob bermadi.",
            config.SUPER_ADMIN_IDS,
        )
        return

    prev_day = day - timedelta(days=1)
    week_ago = day - timedelta(days=7)
    prev_sales, week_sales = await asyncio.gather(
        fetch_sales(prev_day, attempts=2, delay=10),
        fetch_sales(week_ago, attempts=2, delay=10),
    )

    lines = [
        "📊 <b>DE LUXURY — KUN YAKUNI HISOBOTI</b>",
        f"📅 Sana: <b>{sales['date']} ({WEEKDAYS_UZ[day.weekday()]})</b>\n",
        f"💰 <b>SOF TUSHUM:</b> <code>{format_sum(sales['total_sum'])} so'm</code>",
        f"🛒 <b>Savdo:</b> {format_sum(sales['gross_sum'])} so'm ({sales['total_count']} ta chek)",
    ]
    if sales["return_count"]:
        lines.append(f"↩️ <b>Vozvrat:</b> -{format_sum(sales['return_sum'])} so'm ({sales['return_count']} ta)")
    lines.append(f"📊 <b>O'rtacha chek:</b> {format_sum(sales['avg_check'])} so'm")

    if prev_sales or week_sales:
        lines.extend(["━━━━━━━━━━━━━━━━━━━━━", "📈 <b>Solishtirish (sof tushum):</b>"])
        if prev_sales:
            lines.append(
                f"▫️ Oldingi kun ({prev_sales['date'][:5]}): {format_sum(prev_sales['total_sum'])} so'm → "
                f"{pct_change(sales['total_sum'], prev_sales['total_sum'])}"
            )
        if week_sales:
            lines.append(
                f"▫️ O'tgan {WEEKDAYS_UZ[week_ago.weekday()].lower()} ({week_sales['date'][:5]}): "
                f"{format_sum(week_sales['total_sum'])} so'm → {pct_change(sales['total_sum'], week_sales['total_sum'])}"
            )

    active_hours = [
        (hour, d) for hour, d in sorted(sales["hourly"].items())
        if d["count"] or d["return_count"]
    ]
    if active_hours:
        lines.extend(["━━━━━━━━━━━━━━━━━━━━━", "🕒 <b>Soatlar kesimida:</b>"])
        for hour, d in active_hours:
            mark = "▫️" if is_work_hour(hour) else "🌙"
            row = f"{mark} {hour_range(hour)}: {format_sum(d['sum'])} so'm ({d['count']} ta chek)"
            if d["return_count"]:
                row += f" | ↩️ -{format_sum(d['return_sum'])}"
            lines.append(row)

        best_hour, best = max(active_hours, key=lambda x: x[1]["sum"])
        if best["sum"] > 0:
            lines.append(f"\n🏆 <b>Eng yaxshi soat:</b> {hour_range(best_hour)} — {format_sum(best['sum'])} so'm")

        night = [d for hour, d in active_hours if not is_work_hour(hour)]
        night_count = sum(d["count"] for d in night)
        if night_count:
            lines.append(
                f"🌙 <b>Ish vaqtidan tashqari savdo:</b> {format_sum(sum(d['sum'] for d in night))} so'm ({night_count} ta chek)"
            )
    else:
        lines.append("\nℹ️ Bu kunda savdo bo'lmagan.")

    await broadcast(bot, "\n".join(lines), all_recipients())

def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=tz)
    job_opts = {"args": [bot], "replace_existing": True, "misfire_grace_time": 600, "coalesce": True, "max_instances": 1}
    # Har soatning 2-daqiqasida, 24 soat davomida (ish vaqtidan tashqarida faqat savdo bo'lsa yuboriladi)
    scheduler.add_job(
        send_hourly_report,
        CronTrigger(minute=HOURLY_REPORT_MINUTE, timezone=tz),
        id="hourly_sales_job",
        **job_opts,
    )
    scheduler.add_job(
        send_daily_summary,
        CronTrigger(hour=DAILY_REPORT_HOUR, minute=DAILY_REPORT_MINUTE, timezone=tz),
        id="daily_summary_job",
        **job_opts,
    )
    return scheduler
