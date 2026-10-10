from aiogram import Router, types, F
from moysklad_api import ms_api
import config

router = Router()

def format_sum(val: float) -> str:
    return f"{val:,.2f}".replace(",", " ")

@router.message(F.text == "⏱ Soatlik Savdo (Bugun)")
async def handle_hourly_sales(message: types.Message):
    user_id = message.from_user.id
    if not config.get_user_role(user_id):
        return

    wait_msg = await message.answer("🔄 <i>MoySkladdan bugungi savdo ma'lumotlari hisoblanmoqda...</i>", parse_mode="HTML")
    
    sales = await ms_api.get_hourly_sales()
    
    lines = [
        f"⏱ <b>DE LUXURY — BUGUNGI SOATLIK SAVDO HISOBOTI</b>",
        f"📅 Sana: <b>{sales['date']}</b>\n",
        f"━━━━━━━━━━━━━━━━━━━━━"
    ]

    has_any_sale = False
    curr_hour = int(sales.get("current_hour", 23))
    for hour_k, data in sales.get("hourly", {}).items():
        try:
            hour = int(hour_k)
        except (ValueError, TypeError):
            continue

        # Faqat o'tgan soatlar va savdo bo'lgan yoki hozirgi soatni ko'rsatamiz
        if hour <= curr_hour:
            hour_str = f"{hour:02d}:00 - {hour+1:02d}:00"
            if data.get("count", 0) > 0:
                has_any_sale = True
                lines.append(f"▫️ <b>{hour_str}:</b> {format_sum(data.get('sum', 0.0))} so'm ({data.get('count', 0)} ta chek)")
            else:
                lines.append(f"▫️ <i>{hour_str}:</i> 0.00 so'm")

    lines.append(f"━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"💰 <b>JAMI TUSHUM:</b> <code>{format_sum(sales.get('total_sum', 0.0))} so'm</code>")
    lines.append(f"🧾 <b>Cheklar soni:</b> {sales.get('total_count', 0)} ta")
    lines.append(f"📊 <b>O'rtacha chek:</b> {format_sum(sales.get('avg_check', 0.0))} so'm")

    try:
        await wait_msg.delete()
    except Exception:
        pass
    await message.answer("\n".join(lines), parse_mode="HTML")
