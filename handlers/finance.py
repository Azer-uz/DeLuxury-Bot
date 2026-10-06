from aiogram import Router, types, F
from datetime import datetime
import pytz
from moysklad_api import ms_api
from keyboards import get_expense_filters_kb
import config

router = Router()
tz = pytz.timezone(config.TIMEZONE)

def format_sum(val: float) -> str:
    return f"{val:,.2f}".replace(",", " ")

@router.message(F.text == "💰 Moliya & Kassa Qoldiqlari")
async def handle_finance_balances(message: types.Message):
    user_id = message.from_user.id
    role = config.get_user_role(user_id)

    # Faqat Super Admin (Bosh Rahbar) ko'ra oladi
    if role != "super_admin":
        await message.answer("🔒 <i>Ushbu bo'lim faqat Bosh Rahbariyat uchun ochiq.</i>", parse_mode="HTML")
        return

    wait_msg = await message.answer("🔄 <i>Kassa va hisob raqamlar qoldiqlari tekshirilmoqda...</i>", parse_mode="HTML")
    
    fin = await ms_api.get_finance_balances()
    await wait_msg.delete()

    lines = [
        "💰 <b>DE LUXURY — MOLIYA VA KASSA QOLDIQLARI</b>\n",
        "━━━━━━━━━━━━━━━━━━━━━",
        "🏦 <b>Hisoblar va Kassalar:</b>\n"
    ]

    for acc in fin["accounts"]:
        val_str = f"{format_sum(acc['balance'])} $" if acc["is_dollar"] else f"{format_sum(acc['balance'])} so'm"
        lines.append(f"▫️ <b>{acc['name']}:</b> <code>{val_str}</code>")

    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"💵 <b>JAMI MILLIY VALYUTA (UZS):</b> <code>{format_sum(fin['total_uzs'])} so'm</code>")
    if fin["dollar_balance"] > 0:
        lines.append(f"💲 <b>JAMI VALYUTA (USD):</b> <code>{format_sum(fin['dollar_balance'])} $</code>")

    await message.answer("\n".join(lines), parse_mode="HTML")

@router.message(F.text == "📉 Xarajatlar (Chiqim)")
async def handle_expenses_menu(message: types.Message):
    user_id = message.from_user.id
    role = config.get_user_role(user_id)

    if role != "super_admin":
        await message.answer("🔒 <i>Ushbu bo'lim faqat Bosh Rahbariyat uchun ochiq.</i>", parse_mode="HTML")
        return

    await message.answer(
        "📉 <b>DE LUXURY — XARAJATLAR (CHIQIM) TAHLILI</b>\n\n"
        "Qaysi davr bo'yicha xarajatlarni ko'rmoqchisiz?",
        reply_markup=get_expense_filters_kb(),
        parse_mode="HTML"
    )

async def render_expense_report(callback: types.CallbackQuery, date_from: str, date_to: str, title: str):
    await callback.answer("Yuklanmoqda...")
    wait_msg = await callback.message.answer(f"🔄 <i>{title} bo'yicha xarajatlar tahlil qilinmoqda...</i>", parse_mode="HTML")
    
    exp_data = await ms_api.get_expenses_report(date_from=date_from, date_to=date_to)
    await wait_msg.delete()

    if exp_data["total_expense"] == 0:
        await callback.message.answer(f"ℹ️ <b>{title}</b> bo'yicha hech qanday chiqim yoki xarajat mavjud emas.", parse_mode="HTML")
        return

    lines = [
        f"📉 <b>DE LUXURY — XARAJATLAR ({title.upper()})</b>\n",
        f"💸 <b>Jami xarajat:</b> <code>{format_sum(exp_data['total_expense'])} so'm</code>",
        "\n━━━━━━━━━━━━━━━━━━━━━",
        "📂 <b>Xarajat moddalari (Statyalar) kesimida:</b>\n"
    ]

    for item_name, item_sum in exp_data["by_item"].items():
        percent = (item_sum / exp_data["total_expense"]) * 100 if exp_data["total_expense"] > 0 else 0
        lines.append(f"▫️ <b>{item_name}:</b> {format_sum(item_sum)} so'm (<i>{percent:.1f}%</i>)")

    if exp_data.get("details"):
        lines.append("\n━━━━━━━━━━━━━━━━━━━━━")
        lines.append("📝 <b>So'nggi chiqimlar va izohlar:</b>")
        for d in exp_data["details"][:5]:
            lines.append(f"• <b>{d['item']}</b> — {format_sum(d['sum'])} so'm\n  └ <i>Izoh: {d['comment']} ({d['moment']})</i>")

    await callback.message.answer("\n".join(lines), parse_mode="HTML")

@router.callback_query(F.data == "exp_today")
async def exp_today(callback: types.CallbackQuery):
    today = datetime.now(tz).strftime("%Y-%m-%d")
    await render_expense_report(callback, date_from=today, date_to=today, title="Bugun")

@router.callback_query(F.data == "exp_month")
async def exp_month(callback: types.CallbackQuery):
    month_start = datetime.now(tz).strftime("%Y-%m-01")
    today = datetime.now(tz).strftime("%Y-%m-%d")
    await render_expense_report(callback, date_from=month_start, date_to=today, title="Bu oy")
