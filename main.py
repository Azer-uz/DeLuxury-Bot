import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
import config
from scheduler import setup_scheduler
from receipt_watcher import ReceiptWatcher

# Handlerlarni import qilish
from handlers import common, sales, stocks, supplies, finance, ai_chat

# Log sozlamalari
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
logger = logging.getLogger(__name__)

async def main():
    if not config.TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN topilmadi! .env faylini tekshiring.")
        return

    bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()

    # Routerni ro'yxatdan o'tkazish (tartib muhim)
    dp.include_router(common.router)
    dp.include_router(sales.router)
    dp.include_router(stocks.router)
    dp.include_router(supplies.router)
    dp.include_router(finance.router)
    dp.include_router(ai_chat.router) # AI chat har doim oxirida turadi

    # Schedulerni ishga tushiramiz
    scheduler = setup_scheduler(bot)
    scheduler.start()
    logger.info("📅 Kun yakuni scheduler ishga tushirildi.")

    # Har bir chek yaratilgan zahoti Telegram'ga
    watcher_task = asyncio.create_task(ReceiptWatcher(bot).run())

    # Super Adminlarga bot ishga tushgani haqida xabar yuborish
    for admin_id in config.SUPER_ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                "🚀 <b>DE LUXURY Boshqaruv Boti muvaffaqiyatli ishga tushirildi!</b>\n"
                "Barcha funksiyalar va AI Analitik faol holatda.",
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.warning(f"Admin {admin_id} ga start xabari yuborilmadi: {e}")

    logger.info("🤖 Bot polling rejimida ishga tushdi...")
    try:
        await bot.delete_webhook(drop_pending_updates=False)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        watcher_task.cancel()
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
