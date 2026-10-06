from aiogram import Router, types, F, Bot
from aiogram.types import FSInputFile
from ai_agent import ai_agent
from moysklad_api import ms_api
from excel_generator import ExcelGenerator
from keyboards import get_excel_download_kb
import config
import os
import io

router = Router()

@router.message(F.text.in_(["🧠 AI Analitik", "🧠 AI Maslahatchi"]))
async def handle_ai_intro(message: types.Message):
    user_id = message.from_user.id
    if not config.get_user_role(user_id):
        return

    text = (
        "🧠 <b>DE LUXURY — AI PROFESSIONAL ANALITIK</b>\n\n"
        "Men sizga do'kon savdosi, ombor qoldiqlari, yetkazib beruvchilar va moliya bo'yicha har qanday tahlilni chiqarib bera olaman.\n\n"
        "<b>Qanday foydalanish mumkin?</b>\n"
        "1. <b>Ovozli xabar (golosovoy)</b> yoki <b>matn</b> yuboring — masalan: <i>'Karvon yetkazib beruvchisining kirimlarini Excel qilib ber'</i> yoki <i>'Omborda qancha tovar bor?'</i>.\n"
        "2. AI MoySkladdagi haqiqiy bazani tekshirib, aniq hisoblab javob beradi va kerakli Excel hujjatni darhol jo'natadi."
    )
    await message.answer(text, parse_mode="HTML")

@router.message(F.text == "📑 Excel Hisobot Yuklash")
async def handle_excel_menu(message: types.Message):
    user_id = message.from_user.id
    if not config.get_user_role(user_id):
        return

    await message.answer(
        "📑 <b>Qaysi hisobotni Excel formatida yuklab olmoqchisiz?</b>",
        reply_markup=get_excel_download_kb(),
        parse_mode="HTML"
    )

async def handle_ai_excel_delivery(message: types.Message, excel_meta: dict):
    """AI buyrug'i asosida tegishli Excel hisobotini generatsiya qilib jo'natadi"""
    if not excel_meta:
        return

    m_type = excel_meta.get("type")
    
    if m_type == "stock_folder":
        folder_name = excel_meta.get("folder_name", "")
        stock_data = await ms_api.get_stock_report()
        file_path = ExcelGenerator.generate_stock_excel(stock_data, folder_name=folder_name)
        
        # O'sha guruh statistikasini olamiz
        f_info = stock_data.get("by_folder", {}).get(folder_name, {})
        qty_str = f"{int(f_info.get('quantity', 0))} dona" if f_info else ""
        sale_sum_str = f"{f_info.get('sale_sum', 0):,.2f} so'm" if f_info else ""

        doc = FSInputFile(file_path, filename=os.path.basename(file_path))
        await message.answer_document(
            doc,
            caption=f"📊 <b>DE LUXURY — {folder_name} guruhi tovar qoldiqlari Excel hisoboti</b>\n"
                    f"📦 Qoldiq: {qty_str} | 🏷 Sotuv qiymati: {sale_sum_str}",
            parse_mode="HTML"
        )
        if os.path.exists(file_path):
            os.remove(file_path)

    elif m_type == "supply_agent":
        agent_id = excel_meta.get("agent_id")
        agent_name = excel_meta.get("agent_name", "Kontragent")
        supply_pos_data = await ms_api.get_supply_positions_detailed(agent_id=agent_id)
        
        file_path = ExcelGenerator.generate_supply_positions_excel(supply_pos_data, supplier_name=agent_name)
        doc = FSInputFile(file_path, filename=os.path.basename(file_path))
        await message.answer_document(
            doc,
            caption=f"📦 <b>DE LUXURY — {agent_name} bo'yicha tovar kirimlari Excel hisoboti</b>\n"
                    f"📑 Jami pozitsiyalar: {supply_pos_data.get('total_positions', 0)} xil\n"
                    f"💰 Jami summa: {supply_pos_data.get('total_sum', 0):,.2f} so'm",
            parse_mode="HTML"
        )
        if os.path.exists(file_path):
            os.remove(file_path)

    elif m_type == "stocks":
        stock_data = await ms_api.get_stock_report()
        file_path = ExcelGenerator.generate_stock_excel(stock_data)
        doc = FSInputFile(file_path, filename=os.path.basename(file_path))
        await message.answer_document(doc, caption="📊 <b>DE LUXURY — Tovar qoldiqlari to'liq Excel hisoboti</b>", parse_mode="HTML")
        if os.path.exists(file_path):
            os.remove(file_path)

    elif m_type == "supplies":
        supply_pos_data = await ms_api.get_supply_positions_detailed()
        file_path = ExcelGenerator.generate_supply_positions_excel(supply_pos_data, supplier_name="Barcha kirimlar")
        doc = FSInputFile(file_path, filename=os.path.basename(file_path))
        await message.answer_document(doc, caption="📦 <b>DE LUXURY — Barcha tovar kirimlari Excel hisoboti</b>", parse_mode="HTML")
        if os.path.exists(file_path):
            os.remove(file_path)

# Matnli AI so'rovlar
@router.message(F.text & ~F.text.startswith("/"))
async def handle_text_ai(message: types.Message):
    user_id = message.from_user.id
    role = config.get_user_role(user_id)
    if not role:
        return

    wait_msg = await message.answer("🧠 <i>AI tahlil qilmoqda...</i>", parse_mode="HTML")
    
    is_super = (role == "super_admin")
    result = await ai_agent.process_text_query(message.text, is_super_admin=is_super)
    
    await wait_msg.delete()
    await message.answer(result["text"])

    if result.get("excel_meta"):
        await handle_ai_excel_delivery(message, result["excel_meta"])

# Ovozli AI so'rovlar (Voice message)
@router.message(F.voice)
async def handle_voice_ai(message: types.Message, bot: Bot):
    user_id = message.from_user.id
    role = config.get_user_role(user_id)
    if not role:
        return

    wait_msg = await message.answer("🎙 <i>Ovozingiz tinglanmoqda va tahlil qilinmoqda...</i>", parse_mode="HTML")

    file_info = await bot.get_file(message.voice.file_id)
    file_bytes_io = io.BytesIO()
    await bot.download_file(file_info.file_path, destination=file_bytes_io)
    audio_bytes = file_bytes_io.getvalue()

    is_super = (role == "super_admin")
    result = await ai_agent.process_voice_query(audio_bytes, mime_type="audio/ogg", is_super_admin=is_super)

    await wait_msg.delete()
    await message.answer(result["text"])

    if result.get("excel_meta"):
        await handle_ai_excel_delivery(message, result["excel_meta"])
