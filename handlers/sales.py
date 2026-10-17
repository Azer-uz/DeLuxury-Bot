from aiogram import Router, types, F
from moysklad_api import ms_api
from scheduler import format_sum, hour_range, is_work_hour
import config

router = Router()

@router.message(F.text == "⏱ Soatlik Savdo (Bugun)")
async def handle_hourly_sales(message: types.Message):
    user_id = message.from_user.id
    if not config.get_user_role(user_id):
        return

    wait_msg = await message.answer("🔄 <i>MoySkladdan bugungi savdo ma'lumotlari hisoblanmoqda...</i>", parse_mode="HTML")

    try:
        sales = await ms_api.get_hourly_sales()
    except Exception:
        sales = None

    try:
        await wait_msg.delete()
    except Exception:
        pass

    if sales is None:
        await message.answer("⚠️ MoySklad hozir javob bermayapti. Iltimos, birozdan so'ng qayta urinib ko'ring.")
        return

    lines = [
        f"⏱ <b>DE LUXURY — BUGUNGI SOATLIK SAVDO HISOBOTI</b>",
        f"📅 Sana: <b>{sales['date']}</b>\n",
        f"━━━━━━━━━━━━━━━━━━━━━"
    ]

    curr_hour = int(sales.get("current_hour", 23))
    for hour, data in sorted(sales["hourly"].items()):
        if hour > curr_hour:
            break
        has_activity = data["count"] > 0 or data["return_count"] > 0
        # Ish vaqtidagi soatlar har doim, ish vaqtidan tashqaridagilar faqat savdo bo'lsa ko'rsatiladi
        if not has_activity and not is_work_hour(hour):
            continue

        mark = "▫️" if is_work_hour(hour) else "🌙"
        if has_activity:
            row = f"{mark} <b>{hour_range(hour)}:</b> {format_sum(data['sum'])} so'm ({data['count']} ta chek)"
            if data["return_count"]:
                row += f" | ↩️ -{format_sum(data['return_sum'])}"
        else:
            row = f"{mark} <i>{hour_range(hour)}:</i> 0.00 so'm"
        lines.append(row)

    lines.append(f"━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"💰 <b>SOF TUSHUM:</b> <code>{format_sum(sales['total_sum'])} so'm</code>")
    lines.append(f"🧾 <b>Cheklar soni:</b> {sales['total_count']} ta")
    if sales["return_count"]:
        lines.append(f"↩️ <b>Vozvrat:</b> {format_sum(sales['return_sum'])} so'm ({sales['return_count']} ta)")
    lines.append(f"📊 <b>O'rtacha chek:</b> {format_sum(sales['avg_check'])} so'm")

    await message.answer("\n".join(lines), parse_mode="HTML")
