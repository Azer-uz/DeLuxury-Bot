from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import FSInputFile
from datetime import datetime, timedelta
import pytz
import re
from moysklad_api import ms_api
from excel_generator import ExcelGenerator
from keyboards import get_supply_filters_kb, get_counterparties_kb
import config
import os

router = Router()
tz = pytz.timezone(config.TIMEZONE)

class SupplyDateState(StatesGroup):
    waiting_for_date = State()

def format_sum(val: float) -> str:
    return f"{val:,.2f}".replace(",", " ")

@router.message(F.text == "📦 Tovar Kirimi (Priyomka)")
async def handle_supplies_menu(message: types.Message):
    user_id = message.from_user.id
    if not config.get_user_role(user_id):
        return

    await message.answer(
        "📦 <b>DE LUXURY — TOVAR KIRIMLARI (PRIYOMKA)</b>\n\n"
        "Qaysi davr yoki qaysi yetkazib beruvchi bo'yicha hisobot kerak? Quyidagilardan tanlang:",
        reply_markup=get_supply_filters_kb(),
        parse_mode="HTML"
    )

async def render_supply_report(callback_or_msg, date_from: str = None, date_to: str = None, agent_id: str = None, period_title: str = "Bugun"):
    wait_msg = await callback_or_msg.answer(f"🔄 <i>{period_title} bo'yicha kirimlar hisoblanmoqda...</i>", parse_mode="HTML")
    
    supply_data = await ms_api.get_supplies(date_from=date_from, date_to=date_to, agent_id=agent_id)
    await wait_msg.delete()

    if supply_data["total_count"] == 0:
        await callback_or_msg.answer(f"ℹ️ <b>{period_title}</b> bo'yicha hech qanday tovar kirimi (priyomka) topilmadi.", parse_mode="HTML")
        return

    lines = [
        f"📦 <b>DE LUXURY — KIRIMLAR ({period_title.upper()})</b>\n",
        f"📑 <b>Hujjatlar soni:</b> {supply_data['total_count']} ta",
        f"💰 <b>JAMI KIRIM SUMMASI:</b> <code>{format_sum(supply_data['total_sum'])} so'm</code>",
        "\n━━━━━━━━━━━━━━━━━━━━━"
    ]

    # Agar bitta kontragent tanlangan bo'lsa yoki bir nechta hujjat bo'lsa:
    if agent_id or supply_data["total_count"] <= 15:
        lines.append("📋 <b>Kirim hujjatlari (Priyomkalar) kesimida:</b>\n")
        for s in supply_data["rows"]:
            lines.append(
                f"▫️ <b>Hujjat №{s['name']}</b> ({s['moment']})\n"
                f"   └ <i>{s['agent']}</i> — <b>{s['positions_count']} xil</b> tovar | <b>{format_sum(s['sum'])}</b> so'm"
            )
    else:
        lines.append("🏢 <b>Yetkazib beruvchilar (Kontragentlar) kesimida:</b>\n")
        for agent_name, a_data in supply_data["by_agent"].items():
            lines.append(f"▫️ <b>{agent_name}:</b> {format_sum(a_data['sum'])} so'm ({a_data['count']} ta kirim)")

    lines.append("\n━━━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 <i>Barcha tovarlar ro'yxati, kodi, kategoriyasi va narxlari bilan Excel hujjatni yuklab olishingiz mumkin.</i>")

    # Excel tugmasi
    cb_data = f"excel_sup_agent_{agent_id}" if agent_id else "excel_supplies"
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📥 To'liq Excel hisobotini yuklash (.xlsx)", callback_data=cb_data)],
        [types.InlineKeyboardButton(text="🔙 Kirimlar menyusiga qaytish", callback_data="supply_back")]
    ])

    await callback_or_msg.answer("\n".join(lines), parse_mode="HTML", reply_markup=kb)

@router.callback_query(F.data == "supply_today")
async def supply_today(callback: types.CallbackQuery):
    await callback.answer()
    today = datetime.now(tz).strftime("%Y-%m-%d")
    await render_supply_report(callback.message, date_from=today, date_to=today, period_title="Bugun")

@router.callback_query(F.data == "supply_yesterday")
async def supply_yesterday(callback: types.CallbackQuery):
    await callback.answer()
    yesterday = (datetime.now(tz) - timedelta(days=1)).strftime("%Y-%m-%d")
    await render_supply_report(callback.message, date_from=yesterday, date_to=yesterday, period_title="Kecha")

@router.callback_query(F.data == "supply_week")
async def supply_week(callback: types.CallbackQuery):
    await callback.answer()
    week_ago = (datetime.now(tz) - timedelta(days=7)).strftime("%Y-%m-%d")
    today = datetime.now(tz).strftime("%Y-%m-%d")
    await render_supply_report(callback.message, date_from=week_ago, date_to=today, period_title="Oxirgi 7 kun")

@router.callback_query(F.data == "supply_month")
async def supply_month(callback: types.CallbackQuery):
    await callback.answer()
    month_start = datetime.now(tz).strftime("%Y-%m-01")
    today = datetime.now(tz).strftime("%Y-%m-%d")
    await render_supply_report(callback.message, date_from=month_start, date_to=today, period_title="Bu oy")

@router.callback_query(F.data == "supply_all")
async def supply_all(callback: types.CallbackQuery):
    await callback.answer()
    await render_supply_report(callback.message, date_from=None, date_to=None, period_title="Barcha kirimlar")

@router.callback_query(F.data == "supply_by_agent")
async def supply_by_agent_menu(callback: types.CallbackQuery):
    await callback.answer()
    counterparties = await ms_api.get_counterparties()
    await callback.message.edit_text(
        "🏢 <b>Yetkazib beruvchini (Kontragentni) tanlang:</b>",
        reply_markup=get_counterparties_kb(counterparties),
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("supp_agent_"))
async def supply_by_agent_selected(callback: types.CallbackQuery):
    await callback.answer()
    agent_id = callback.data.replace("supp_agent_", "")
    counterparties = await ms_api.get_counterparties()
    agent_name = next((c["name"] for c in counterparties if c["id"] == agent_id), "Tanlangan Kontragent")
    
    await render_supply_report(callback.message, agent_id=agent_id, period_title=f"Yetkazib beruvchi: {agent_name}")

@router.callback_query(F.data == "supply_back")
async def supply_back_to_menu(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "📦 <b>DE LUXURY — TOVAR KIRIMLARI (PRIYOMKA)</b>\n\n"
        "Qaysi davr yoki qaysi yetkazib beruvchi bo'yicha hisobot kerak? Quyidagilardan tanlang:",
        reply_markup=get_supply_filters_kb(),
        parse_mode="HTML"
    )

# ✍️ Maxsus sana kiritish
@router.callback_query(F.data == "supply_custom_date")
async def supply_custom_date_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(SupplyDateState.waiting_for_date)
    await callback.message.answer(
        "✍️ <b>Sana yoki oraliqni kiriting:</b>\n\n"
        "Namuna:\n"
        "• Bitta kun: <code>05.10.2026</code>\n"
        "• Oraliq sana: <code>01.10.2026 - 06.10.2026</code>",
        parse_mode="HTML"
    )

@router.message(SupplyDateState.waiting_for_date)
async def supply_custom_date_process(message: types.Message, state: FSMContext):
    text = message.text.strip()
    await state.clear()

    # Sana formatlarini tahlil qilish (DD.MM.YYYY yoki DD.MM.YYYY - DD.MM.YYYY)
    dates = re.findall(r"\d{1,2}\.\d{1,2}\.?\d{0,4}", text)
    if not dates:
        await message.answer("❌ Noto'g'ri sana formati kiritildi. Masalan: <code>05.10.2026</code> yoki <code>01.10.2026 - 06.10.2026</code>", parse_mode="HTML")
        return

    current_year = datetime.now(tz).year

    def parse_dt(d_str):
        parts = d_str.strip(".").split(".")
        day = int(parts[0])
        month = int(parts[1])
        year = int(parts[2]) if len(parts) > 2 and parts[2] else current_year
        if year < 100:
            year += 2000
        return f"{year:04d}-{month:02d}-{day:02d}"

    try:
        if len(dates) == 1:
            d_from = parse_dt(dates[0])
            d_to = d_from
            title = f"{dates[0]}"
        else:
            d_from = parse_dt(dates[0])
            d_to = parse_dt(dates[1])
            title = f"{dates[0]} - {dates[1]}"

        await render_supply_report(message, date_from=d_from, date_to=d_to, period_title=title)
    except Exception as e:
        await message.answer(f"❌ Sanani hisoblashda xatolik: {e}")

# Excel yuklash handlerlari
@router.callback_query(F.data == "excel_supplies")
async def send_supply_excel(callback: types.CallbackQuery):
    await callback.answer("Excel tayyorlanmoqda...")
    supply_pos_data = await ms_api.get_supply_positions_detailed()
    file_path = ExcelGenerator.generate_supply_positions_excel(supply_pos_data, supplier_name="Barcha kirimlar")

    doc = FSInputFile(file_path, filename=os.path.basename(file_path))
    await callback.message.answer_document(
        doc,
        caption="📦 <b>DE LUXURY — Barcha tovar kirimlari batafsil Excel hisoboti</b>",
        parse_mode="HTML"
    )
    if os.path.exists(file_path):
        os.remove(file_path)

@router.callback_query(F.data.startswith("excel_sup_agent_"))
async def send_supply_agent_excel(callback: types.CallbackQuery):
    await callback.answer("Excel tayyorlanmoqda...")
    agent_id = callback.data.replace("excel_sup_agent_", "")
    counterparties = await ms_api.get_counterparties()
    agent_name = next((c["name"] for c in counterparties if c["id"] == agent_id), "Kontragent")

    supply_pos_data = await ms_api.get_supply_positions_detailed(agent_id=agent_id)
    file_path = ExcelGenerator.generate_supply_positions_excel(supply_pos_data, supplier_name=agent_name)

    doc = FSInputFile(file_path, filename=os.path.basename(file_path))
    await callback.message.answer_document(
        doc,
        caption=f"📦 <b>DE LUXURY — {agent_name} bo'yicha tovar kirimlari Excel hisoboti</b>",
        parse_mode="HTML"
    )
    if os.path.exists(file_path):
        os.remove(file_path)
