from aiogram import Router, types, F, Bot
from aiogram.filters import Command
from aiogram.types import FSInputFile
from aiogram.utils.chat_action import ChatActionSender
from ai_agent import ai_agent
from moysklad_api import ms_api
from excel_generator import ExcelGenerator
from keyboards import get_excel_download_kb
import config
import html
import io
import logging
import os
import re

router = Router()
logger = logging.getLogger(__name__)

TG_LIMIT = 4000  # Telegram xabar limiti 4096 belgi, HTML teglar uchun zaxira bilan

def md_to_tg_html(text: str) -> str:
    """Gemini markdown javobini Telegram HTML ga o'tkazadi (teglar bitta qatordan oshmaydi — bo'laklashda buzilmaydi)"""
    out = []
    for line in html.escape(text, quote=False).split("\n"):
        heading = re.match(r"^\s*#{1,6}\s+(.*)$", line)
        if heading:
            line = f"<b>{heading.group(1).replace('**', '')}</b>"
        else:
            line = re.sub(r"^(\s*)[*-]\s+", r"\1• ", line)
        line = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", line)
        line = re.sub(r"(?<![*\w])\*(?!\s)([^*\n]+?)(?<!\s)\*(?![*\w])", r"<i>\1</i>", line)
        line = re.sub(r"`([^`]+)`", r"<code>\1</code>", line)
        if re.fullmatch(r"\s*-{3,}\s*", line):
            line = "━━━━━━━━━━━━━━━━━━━━━"
        out.append(line)
    return "\n".join(out)

def split_message(text: str, limit: int = TG_LIMIT) -> list[str]:
    chunks, current = [], ""
    for line in text.split("\n"):
        while len(line) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        if len(current) + len(line) + 1 > limit:
            chunks.append(current)
            current = line
        else:
            current = f"{current}\n{line}" if current else line
    if current.strip():
        chunks.append(current)
    return chunks

async def send_ai_reply(message: types.Message, text: str):
    """AI javobini bo'laklab, HTML formatda yuboradi; formatlash xato bersa oddiy matn sifatida"""
    if not text.strip():
        return
    for chunk in split_message(md_to_tg_html(text)):
        try:
            await message.answer(chunk, parse_mode="HTML")
        except Exception as e:
            logger.warning(f"HTML javob yuborilmadi, oddiy matnga o'tildi: {e}")
            plain = re.sub(r"</?(b|code)>", "", chunk)
            await message.answer(html.unescape(plain))

async def safe_delete(msg: types.Message):
    try:
        await msg.delete()
    except Exception:
        pass

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
        "2. AI MoySkladdagi haqiqiy bazani tekshirib, aniq hisoblab javob beradi va kerakli Excel hujjatni darhol jo'natadi.\n"
        "3. AI oxirgi savollaringizni eslab qoladi. Yangi mavzuni boshlash uchun: /yangi"
    )
    await message.answer(text, parse_mode="HTML")

@router.message(Command("yangi"))
async def cmd_new_chat(message: types.Message):
    if not config.get_user_role(message.from_user.id):
        return
    ai_agent.clear_history(message.from_user.id)
    await message.answer("🧹 AI suhbat tarixi tozalandi. Yangi savolingizni yozing.")

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

async def send_excel_file(message: types.Message, file_path: str, caption: str):
    try:
        doc = FSInputFile(file_path, filename=os.path.basename(file_path))
        await message.answer_document(doc, caption=caption, parse_mode="HTML")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

async def handle_ai_excel_delivery(message: types.Message, excel_meta: dict):
    """AI buyrug'i asosida tegishli Excel hisobotini generatsiya qilib jo'natadi"""
    if not excel_meta:
        return

    m_type = excel_meta.get("type")

    if m_type == "stock_folder":
        folder_name = excel_meta.get("folder_name", "")
        stock_data = await ms_api.get_stock_report()
        file_path = ExcelGenerator.generate_stock_excel(stock_data, folder_name=folder_name)

        # O'sha guruh statistikasini olamiz (AI guruh nomini boshqa registrda yozishi mumkin)
        f_info = next(
            (v for k, v in stock_data.get("by_folder", {}).items() if k.lower() == folder_name.lower()),
            {}
        )
        qty_str = f"{int(f_info.get('quantity', 0))} dona" if f_info else ""
        sale_sum_str = f"{f_info.get('sale_sum', 0):,.2f} so'm" if f_info else ""

        await send_excel_file(
            message, file_path,
            f"📊 <b>DE LUXURY — {html.escape(folder_name)} guruhi tovar qoldiqlari Excel hisoboti</b>\n"
            f"📦 Qoldiq: {qty_str} | 🏷 Sotuv qiymati: {sale_sum_str}"
        )

    elif m_type == "supply_agent":
        agent_id = excel_meta.get("agent_id")
        agent_name = excel_meta.get("agent_name", "Kontragent")
        supply_pos_data = await ms_api.get_supply_positions_detailed(agent_id=agent_id)

        file_path = ExcelGenerator.generate_supply_positions_excel(supply_pos_data, supplier_name=agent_name)
        await send_excel_file(
            message, file_path,
            f"📦 <b>DE LUXURY — {html.escape(agent_name)} bo'yicha tovar kirimlari Excel hisoboti</b>\n"
            f"📑 Jami pozitsiyalar: {supply_pos_data.get('total_positions', 0)} xil\n"
            f"💰 Jami summa: {supply_pos_data.get('total_sum', 0):,.2f} so'm"
        )

    elif m_type == "stocks":
        stock_data = await ms_api.get_stock_report()
        file_path = ExcelGenerator.generate_stock_excel(stock_data)
        await send_excel_file(message, file_path, "📊 <b>DE LUXURY — Tovar qoldiqlari to'liq Excel hisoboti</b>")

    elif m_type == "supplies":
        supply_pos_data = await ms_api.get_supply_positions_detailed()
        file_path = ExcelGenerator.generate_supply_positions_excel(supply_pos_data, supplier_name="Barcha kirimlar")
        await send_excel_file(message, file_path, "📦 <b>DE LUXURY — Barcha tovar kirimlari Excel hisoboti</b>")

async def deliver_ai_result(message: types.Message, result: dict):
    await send_ai_reply(message, result.get("text", ""))
    if result.get("excel_meta"):
        try:
            await handle_ai_excel_delivery(message, result["excel_meta"])
        except Exception:
            logger.exception("AI Excel hisobotini yaratishda xato")
            await message.answer("⚠️ Excel hisobotni tayyorlashda xatolik yuz berdi. «📑 Excel Hisobot Yuklash» bo'limidan urinib ko'ring.")

# Matnli AI so'rovlar
@router.message(F.text & ~F.text.startswith("/"))
async def handle_text_ai(message: types.Message, bot: Bot):
    user_id = message.from_user.id
    role = config.get_user_role(user_id)
    if not role:
        return

    wait_msg = await message.answer("🧠 <i>AI tahlil qilmoqda...</i>", parse_mode="HTML")
    try:
        async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
            result = await ai_agent.process_text_query(message.text, is_super_admin=(role == "super_admin"), user_id=user_id)
            await safe_delete(wait_msg)
            await deliver_ai_result(message, result)
    except Exception:
        logger.exception("AI matnli so'rovda xato")
        await safe_delete(wait_msg)
        await message.answer("⚠️ So'rovni qayta ishlashda xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring.")

# Ovozli AI so'rovlar (Voice message)
@router.message(F.voice)
async def handle_voice_ai(message: types.Message, bot: Bot):
    user_id = message.from_user.id
    role = config.get_user_role(user_id)
    if not role:
        return

    wait_msg = await message.answer("🎙 <i>Ovozingiz tinglanmoqda va tahlil qilinmoqda...</i>", parse_mode="HTML")
    try:
        async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
            file_info = await bot.get_file(message.voice.file_id)
            file_bytes_io = io.BytesIO()
            await bot.download_file(file_info.file_path, destination=file_bytes_io)

            result = await ai_agent.process_voice_query(
                file_bytes_io.getvalue(), mime_type="audio/ogg",
                is_super_admin=(role == "super_admin"), user_id=user_id
            )
            await safe_delete(wait_msg)
            await deliver_ai_result(message, result)
    except Exception:
        logger.exception("AI ovozli so'rovda xato")
        await safe_delete(wait_msg)
        await message.answer("⚠️ Ovozli xabarni qayta ishlashda xatolik yuz berdi. Iltimos, qaytadan yuboring.")
