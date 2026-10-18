# 💎 DE LUXURY — Savdo Hisoboti va Super AI Agent Telegram Boti

Ushbu loyiha **"DE LUXURY"** erkaklar kiyim do'koni uchun yaratilgan maxsus boshqaruv, soatlik monitoring, ombor tahlili va professional **AI Biznes Maslahatchisi** hisoblanadi.

---

## 🚀 Asosiy Imkoniyatlar

1. **🧾 Har bir chek — darhol Telegram'ga:**
   - MoySklad'da chek (chakana/ulgurji savdo, vozvrat) o'tkazilgan zahoti (~15 soniya ichida) pozitsiyalari, chegirma, naqd/karta/QR to'lovi va kun boshidan buyon jami bilan yuboriladi.
   - Har bir hujjat faqat bir marta keladi (bot qayta ishga tushganda ham).
   - Soatlar kesimi avtomatik yuborilmaydi — «⏱ Soatlik Savdo (Bugun)» tugmasi bilan olinadi.
   - Har kuni 00:05 da **Kun yakuni** hisoboti: soatlar kesimi, eng yaxshi soat, oldingi kun va o'tgan hafta bilan solishtirish.
   - MoySklad 5 daqiqa javob bermasa, rahbarga ogohlantirish yuboriladi.
2. **📦 Tovar Kirimlari (Priyomka) & Yetkazib Beruvchilar:**
   - Kontragentlar (*Karvon, Turkiya Istanbul, Xitoy Abu Saxiy va h.k.*) yoki sanalar bo'yicha kirim hujjatlarini ko'rish.
   - Har bir kontragent bo'yicha tovar kodi, nomi, guruhi, kategoriyasi, vid tovari va narxlari aks etgan batafsil **Excel (.xlsx)** hisobotini yuklab berish.
3. **📊 Tovar Qoldiqlari (Ostatki) & Shtrix-kod Qidiruvi:**
   - Barcha tovarlar soni, tan narxi (Sebestoimost) va sotuv narxi bo'yicha umumiy va guruhlar kesimidagi qoldiqlar.
   - Shtrix-kod, tovar kodi yoki nomi orqali lahzali tovar qidirish.
4. **💰 Moliya va Kassa Qoldiqlari (Faqat Bosh Rahbarga):**
   - Asosiy Naqd Kassa, Valyuta (Dollar), Karta va Terminal hisoblaridagi real pul qoldiqlari.
   - Chiqimlar (Statya rasxodov) va izohlar tahlili.
5. **🧠 Super AI Professional Analitik (Ovozli & Matnli):**
   - Ovozli xabarlarni tushunish va MoySklad bazasi asosida professional tahlillar taqdim etish.
   - Eng ko'p zaxiraga ega (muzlab turgan kapital) va tugab borayotgan tovarlar kesimida amaliy biznes tavsiyalar.
   - Foydalanuvchi so'rovi bilan avtomatik Excel jadvallar yaratish.
   - Oxirgi 4 ta savol-javobni eslab qoladi (30 daqiqa); yangi mavzu uchun /yangi.

---

## 🛠 Texnologiyalar

- **Dasturlash tili:** Python 3.10+
- **Telegram Bot Framework:** Aiogram 3.x
- **Sun'iy Intellekt:** Google Gemini Flash (Multimodal Audio & Text)
- **ERP / Baza Integratsiyasi:** MoySklad JSON API 1.2
- **Excel Generator:** OpenPyXL
- **Scheduler:** APScheduler (AsyncIO)

---

## ⚙️ O'rnatish va Ishga Tushirish

```bash
# 1. Virtual muhit yaratish
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 2. Paketlarni o'rnatish
pip install -r requirements.txt

# 3. .env faylini sozlash
cp .env.example .env
# .env ichiga bot token, moysklad token va gemini kalitini yozing

# 4. Botni ishga tushirish
python main.py
```
