from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

def get_main_keyboard(role: str) -> ReplyKeyboardMarkup:
    """Foydalanuvchi roliga mos asosiy menyu tugmalarini qaytaradi"""
    if role == "super_admin":
        kb = [
            [
                KeyboardButton(text="⏱ Soatlik Savdo (Bugun)"),
                KeyboardButton(text="📦 Tovar Kirimi (Priyomka)")
            ],
            [
                KeyboardButton(text="📊 Qoldiqlar (Ostatki)"),
                KeyboardButton(text="🔍 Tovar Qidirish")
            ],
            [
                KeyboardButton(text="💰 Moliya & Kassa Qoldiqlari"),
                KeyboardButton(text="📉 Xarajatlar (Chiqim)")
            ],
            [
                KeyboardButton(text="📑 Excel Hisobot Yuklash"),
                KeyboardButton(text="🧠 AI Analitik")
            ]
        ]
    else: # manager
        kb = [
            [
                KeyboardButton(text="⏱ Soatlik Savdo (Bugun)"),
                KeyboardButton(text="📦 Tovar Kirimi (Priyomka)")
            ],
            [
                KeyboardButton(text="📊 Qoldiqlar (Ostatki)"),
                KeyboardButton(text="🔍 Tovar Qidirish")
            ],
            [
                KeyboardButton(text="📑 Excel Hisobot Yuklash"),
                KeyboardButton(text="🧠 AI Maslahatchi")
            ]
        ]

    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_supply_filters_kb() -> InlineKeyboardMarkup:
    """Kirimlar (priyomka) uchun davr va kontragent filtrlari"""
    kb = [
        [
            InlineKeyboardButton(text="📅 Bugun", callback_data="supply_today"),
            InlineKeyboardButton(text="📅 Kecha", callback_data="supply_yesterday")
        ],
        [
            InlineKeyboardButton(text="🗓 Oxirgi 7 kun", callback_data="supply_week"),
            InlineKeyboardButton(text="🗓 Bu oy", callback_data="supply_month")
        ],
        [
            InlineKeyboardButton(text="🏢 Kontragent tanlash (Yetkazib beruvchi)", callback_data="supply_by_agent")
        ],
        [
            InlineKeyboardButton(text="✍️ Sana kiritish (Oraliq)", callback_data="supply_custom_date")
        ],
        [
            InlineKeyboardButton(text="📥 Barcha Kirimlar (So'nggi 50 ta)", callback_data="supply_all")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_counterparties_kb(counterparties: list) -> InlineKeyboardMarkup:
    """Yetkazib beruvchilar ro'yxati tugmalari"""
    kb = []
    for c in counterparties:
        c_id = c.get("id")
        c_name = c.get("name")
        # Faqat yetkazib beruvchilarni ko'rsatamiz (xaridorlar emas)
        if c_name and "покупатель" not in c_name.lower():
            kb.append([InlineKeyboardButton(text=f"🏢 {c_name}", callback_data=f"supp_agent_{c_id}")])
    
    kb.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="supply_back")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_excel_download_kb() -> InlineKeyboardMarkup:
    """Excel hisobotlarni yuklab olish tugmalari"""
    kb = [
        [
            InlineKeyboardButton(text="📊 Tovar Qoldiqlari (Excel)", callback_data="excel_stocks"),
        ],
        [
            InlineKeyboardButton(text="📦 Tovar Kirimlari (Excel)", callback_data="excel_supplies")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_expense_filters_kb() -> InlineKeyboardMarkup:
    """Xarajatlar bo'yicha davr filtrlari"""
    kb = [
        [
            InlineKeyboardButton(text="📅 Bugungi xarajatlar", callback_data="exp_today"),
            InlineKeyboardButton(text="🗓 Bu oylik xarajatlar", callback_data="exp_month")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)
