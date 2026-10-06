from aiogram import Router, types, F
from aiogram.filters import CommandStart, Command
import config
from keyboards import get_main_keyboard

router = Router()

@router.message(CommandStart())
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    role = config.get_user_role(user_id)

    if not role:
        await message.answer(
            f"🚫 <b>Kechirasiz, siz ushbu botdan foydalanish uchun ro'yxatdan o'tmagansiz.</b>\n\n"
            f"Sizning Telegram ID raqamingiz: <code>{user_id}</code>\n"
            f"Iltimos, botdan foydalanish uchun ushbu ID raqamni tizim rahbariga taqdim eting.",
            parse_mode="HTML"
        )
        return

    role_title = "👑 Bosh Rahbar (Super Admin)" if role == "super_admin" else "👔 Do'kon Boshqaruvchisi (Menejer)"
    
    welcome_text = (
        f"Assalomu alaykum, <b>{message.from_user.full_name}</b>!\n\n"
        f"💎 <b>DE LUXURY</b> boshqaruv va tahlil tizimiga xush kelibsiz.\n"
        f"Sizning rolingiz: <b>{role_title}</b>\n\n"
        f"Kerakli bo'limni tanlash uchun quyidagi menyudan foydalaning yoki menga to'g'ridan-to'g'ri matn/ovozli xabar yuboring:"
    )

    await message.answer(welcome_text, reply_markup=get_main_keyboard(role), parse_mode="HTML")

@router.message(Command("myid"))
async def cmd_myid(message: types.Message):
    await message.answer(f"Sizning Telegram ID raqamingiz: <code>{message.from_user.id}</code>", parse_mode="HTML")
