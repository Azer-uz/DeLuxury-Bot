from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import FSInputFile
from moysklad_api import ms_api
from excel_generator import ExcelGenerator
from keyboards import get_excel_download_kb
import config
import os

router = Router()

class SearchState(StatesGroup):
    waiting_for_query = State()

def format_sum(val: float) -> str:
    return f"{val:,.2f}".replace(",", " ")

@router.message(F.text == "📊 Qoldiqlar (Ostatki)")
async def handle_stock_report(message: types.Message):
    user_id = message.from_user.id
    role = config.get_user_role(user_id)
    if not role:
        return

    wait_msg = await message.answer("🔄 <i>Ombor qoldiqlari va narxlar tahlil qilinmoqda...</i>", parse_mode="HTML")
    
    stock_data = await ms_api.get_stock_report()
    
    lines = [
        f"📊 <b>DE LUXURY — OMBOR VA TOVAR QOLDIQLARI</b>\n",
        f"📦 <b>Jami tovarlar soni:</b> <code>{int(stock_data['total_quantity'])} dona</code>",
    ]

    # Agar bosh rahbar bo'lsa tan narxi (sebestoimost) ni ham ko'rsatamiz
    if role == "super_admin":
        lines.append(f"💵 <b>Tan narxi bo'yicha qiymat:</b> <code>{format_sum(stock_data['total_cost_sum'])} so'm</code>")
    
    lines.append(f"🏷 <b>Sotuv narxi bo'yicha qiymat:</b> <code>{format_sum(stock_data['total_sale_sum'])} so'm</code>")
    lines.append("\n━━━━━━━━━━━━━━━━━━━━━")
    lines.append("📁 <b>Kategoriyalar kesimida:</b>\n")

    for folder_name, f_data in stock_data["by_folder"].items():
        if f_data["quantity"] > 0:
            folder_line = f"▫️ <b>{folder_name}:</b> {int(f_data['quantity'])} dona"
            if role == "super_admin" and f_data["cost_sum"] > 0:
                folder_line += f" | Tan: <i>{format_sum(f_data['cost_sum'])}</i>"
            folder_line += f" | Sotuv: <b>{format_sum(f_data['sale_sum'])}</b> so'm"
            lines.append(folder_line)

    lines.append("\n💡 <i>To'liq jadvalli ma'lumotni Excel formatida yuklab olishingiz mumkin.</i>")

    await wait_msg.delete()
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=get_excel_download_kb())

@router.message(F.text == "🔍 Tovar Qidirish")
async def start_search(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if not config.get_user_role(user_id):
        return

    await state.set_state(SearchState.waiting_for_query)
    await message.answer(
        "🔍 <b>Tovar qidirish rejimi</b>\n\n"
        "Qidirmoqchi bo'lgan tovarning <b>shtrix-kodi, tovar kodi, artikuli yoki nomini</b> yozing yoki skaner qilib yuboring:",
        parse_mode="HTML"
    )

@router.message(SearchState.waiting_for_query)
async def process_search_query(message: types.Message, state: FSMContext):
    query = message.text.strip()
    await state.clear()

    wait_msg = await message.answer(f"🔍 <i>'{query}' bo'yicha qidirilmoqda...</i>", parse_mode="HTML")
    
    prod = await ms_api.search_product(query)
    await wait_msg.delete()

    if not prod:
        await message.answer(f"❌ <b>'{query}'</b> bo'yicha hech qanday tovar topilmadi.", parse_mode="HTML")
        return

    role = config.get_user_role(message.from_user.id)
    
    lines = [
        f"🏷 <b>{prod['name']}</b>\n",
        f"📁 <b>Guruhi:</b> {prod['folder']}",
        f"🔢 <b>Kodi:</b> <code>{prod['code']}</code> | <b>Artikul:</b> <code>{prod['article']}</code>",
    ]

    if prod.get("barcodes"):
        lines.append(f"📊 <b>Shtrix-kod:</b> <code>{', '.join(prod['barcodes'])}</code>")

    # Qo'shimcha parametrlar (Brend, O'lcham, Rang, Fasl, Model)
    if prod.get("attributes"):
        lines.append("\n📋 <b>Xususiyatlari:</b>")
        for k, v in prod["attributes"].items():
            if v:
                lines.append(f"  • {k}: <b>{v}</b>")

    lines.append("\n━━━━━━━━━━━━━━━━━━━━━")
    if role == "super_admin" and prod.get("buy_price", 0) > 0:
        lines.append(f"💵 <b>Tan narxi:</b> <code>{format_sum(prod['buy_price'])} so'm</code>")
    
    lines.append(f"🏷 <b>Sotuv narxi:</b> <code>{format_sum(prod['price'])} so'm</code>")
    
    stock_status = f"🟢 <b>{int(prod['stock'])} dona mavjud</b>" if prod["stock"] > 0 else "🔴 <b>Qolmagan (0 dona)</b>"
    lines.append(f"📦 <b>Qoldiq:</b> {stock_status}")

    await message.answer("\n".join(lines), parse_mode="HTML")

# Excel yuklab olish callback
@router.callback_query(F.data == "excel_stocks")
async def send_stock_excel(callback: types.CallbackQuery):
    await callback.answer("Excel hisobot tayyorlanmoqda...")
    stock_data = await ms_api.get_stock_report()
    file_path = ExcelGenerator.generate_stock_excel(stock_data)

    doc = FSInputFile(file_path, filename=os.path.basename(file_path))
    await callback.message.answer_document(
        doc,
        caption="📊 <b>DE LUXURY — Tovar qoldiqlari to'liq Excel hisoboti</b>",
        parse_mode="HTML"
    )
    if os.path.exists(file_path):
        os.remove(file_path)
