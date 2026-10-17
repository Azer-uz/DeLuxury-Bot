import aiohttp
import base64
import asyncio
import logging
import time
import re
from collections import deque
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import pytz
import config
from moysklad_api import ms_api

logger = logging.getLogger(__name__)
tz = pytz.timezone(config.TIMEZONE)

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
# Bitta modelga kutish (kontekst ~45k token, thinkingLevel=low bilan javob 6–10 s) va barcha urinishlar uchun umumiy limit
MODEL_TIMEOUT = 30
TOTAL_DEADLINE = 80
# Suhbat xotirasi: oxirgi 4 savol-javob, 30 daqiqa jimlikdan keyin tozalanadi
HISTORY_TURNS = 4
HISTORY_TTL = 30 * 60

EXCEL_TAG_RE = re.compile(r"\[GENERATE_EXCEL_(STOCK_FOLDER|SUPPLY_AGENT|STOCKS|SUPPLIES)(?::([^\]]*))?\]")

class AIAgent:
    def __init__(self, api_key: str = config.GEMINI_API_KEY):
        self.api_key = api_key
        # Modellar ketma-ketligi (auto-fallback): eng tezkori birinchi. Hammasi thinkingLevel ni qo'llab-quvvatlaydi
        self.models = [
            "gemini-3-flash-preview",
            "gemini-3.8-flash",
            "gemini-3.5-flash"
        ]
        self._context_cache: Dict[str, Any] = {}
        self._cache_ttl = 60  # 60 soniya kesh (tezkor ishlash uchun)
        self._history: Dict[int, Dict[str, Any]] = {}

    # ================= SUHBAT XOTIRASI =================
    def _get_history(self, user_id: Optional[int]) -> List[dict]:
        if user_id is None:
            return []
        entry = self._history.get(user_id)
        if not entry or time.time() - entry["time"] > HISTORY_TTL:
            self._history.pop(user_id, None)
            return []
        return list(entry["turns"])

    def _remember(self, user_id: Optional[int], user_text: str, reply_text: str):
        if user_id is None or not reply_text:
            return
        entry = self._history.setdefault(user_id, {"time": 0, "turns": deque(maxlen=HISTORY_TURNS * 2)})
        entry["turns"].append({"role": "user", "parts": [{"text": user_text}]})
        entry["turns"].append({"role": "model", "parts": [{"text": reply_text}]})
        entry["time"] = time.time()

    def clear_history(self, user_id: int):
        self._history.pop(user_id, None)

    async def get_system_context(self, is_super_admin: bool = False) -> str:
        """MoySkladdan ayni damdagi biznes ma'lumotlarini to'plab, AI uchun kontekst yaratadi (Kesh bilan tezkor)"""
        cache_key = f"ctx_admin_{is_super_admin}"
        now_ts = time.time()
        cached = self._context_cache.get(cache_key)
        if cached and (now_ts - cached["time"] < self._cache_ttl):
            return cached["data"]

        try:
            now = datetime.now(tz)
            yesterday = now.date() - timedelta(days=1)
            tasks = [
                ms_api.get_hourly_sales(),
                ms_api.get_hourly_sales(yesterday),
                ms_api.get_stock_report(),
                ms_api.get_counterparties(),
            ]
            if is_super_admin:
                tasks.append(ms_api.get_finance_balances())
            results = await asyncio.gather(*tasks, return_exceptions=True)
            # Savdo olinmasa ham AI ombor bo'yicha javob bera olsin
            sales, y_sales, stock, counterparties = [
                None if isinstance(r, Exception) else r for r in results[:4]
            ]
            finance = results[4] if is_super_admin and not isinstance(results[4], Exception) else None
            stock = stock or {}
            counterparties = counterparties or []

            # Analytics ni mavjud stock bilan hisoblaymiz (qayta MoySkladga so'rov yubormasdan)
            analytics = await ms_api.get_products_analytics(stock_data=stock)

            # Haqiqiy yetkazib beruvchilar ro'yxati
            sup_list = [c for c in counterparties if "покупатель" not in c["name"].lower()]
            sup_names_str = ", ".join([f"'{c['name']}' (ID: {c['id']})" for c in sup_list])

            # Guruhlar kesimidagi qoldiqlar
            folders_summary = []
            for f_name, f_data in stock.get("by_folder", {}).items():
                f_qty = f_data.get("quantity") if f_data.get("quantity") is not None else f_data.get("qty", 0)
                f_cost = f_data.get("cost_sum", 0.0)
                f_sale = f_data.get("sale_sum", 0.0)
                folders_summary.append(
                    f"  • Guruh: '{f_name}' — {int(f_qty)} dona, Tan narxi: {f_cost:,.2f} so'm, Sotuv narxi: {f_sale:,.2f} so'm"
                )
            folders_str = "\n".join(folders_summary)

            # Top eng katta zaxiradagi tovarlar (Muzlab turgan summa bo'yicha)
            top_cap_lines = []
            for i, p in enumerate(analytics.get("top_capital_items", [])[:8], 1):
                top_cap_lines.append(
                    f"  {i}. {p['name']} (Kod: {p['code']}, Guruh: {p['folder']}) — Qoldiq: {int(p['stock'])} dona | Tan: {p['buy_price']:,.2f} so'm | Sotuv: {p['sale_price']:,.2f} so'm | Jami sotuv qiymati: {p['sale_total']:,.2f} so'm"
                )
            top_cap_str = "\n".join(top_cap_lines)

            # Top kam qolgan tovarlar
            low_lines = []
            for i, p in enumerate(analytics.get("low_stock_items", [])[:8], 1):
                low_lines.append(
                    f"  {i}. {p['name']} (Kod: {p['code']}, Guruh: {p['folder']}) — Qoldiq: {int(p['stock'])} dona | Sotuv: {p['sale_price']:,.2f} so'm"
                )
            low_str = "\n".join(low_lines)

            # BAZADAGI BARCHA TOVARLAR RO'YXATI (KOD, NOM, QOLDIQ, NARX)
            all_products_lines = []
            for p in stock.get("raw_rows", []):
                code = p.get("code", "")
                name = p.get("name", "")
                stk = int(p.get("stock", 0))
                sale_p = p.get("sale_price", 0)
                buy_p = p.get("buy_price", 0)
                if is_super_admin:
                    all_products_lines.append(f"• Kod: {code} | {name} | Qoldiq: {stk} dona | Sotuv: {sale_p:,.0f} so'm | Tan: {buy_p:,.0f} so'm")
                else:
                    all_products_lines.append(f"• Kod: {code} | {name} | Qoldiq: {stk} dona | Sotuv: {sale_p:,.0f} so'm")
            all_products_str = "\n".join(all_products_lines)

            sales_str = self._format_sales_for_context(sales, "BUGUNGI")
            y_sales_str = self._format_sales_for_context(y_sales, f"KECHAGI ({yesterday.strftime('%d.%m.%Y')})")

            context_parts = [
                f"Siz 'DE LUXURY' erkaklar kiyim do'konining professional biznes-analitik va boshqaruvchi AI maslahatchisisiz.",
                f"Bugungi sana va hozirgi vaqt (Toshkent): {now.strftime('%d.%m.%Y %H:%M')}. Do'kon ish vaqti: {config.WORK_START_HOUR:02d}:00–{config.WORK_END_HOUR:02d}:00.",
                f"\n📦 --- OMBORNING UMUMIY HOLATI ---",
                f"Jami tovarlar soni: {stock.get('total_quantity', 0)} dona (jami {analytics.get('total_items_count', 0)} xil pozitsiya)",
                f"Jami tovarlar tan narxi (Sebestoimost): {stock.get('total_cost_sum', 0):,.2f} so'm",
                f"Jami tovarlar sotuv qiymati: {stock.get('total_sale_sum', 0):,.2f} so'm",
                f"\n📁 --- BAZADAGI TOVAR GURUHLARI KESIMIDA QOLDIQLAR ---",
                f"{folders_str}",
                f"\n🔥 --- ENG KATTA ZAXIRAGA EGA (MUZLAB TURGAN KAPITAL) TOVARLAR RO'YXATI ---",
                f"{top_cap_str}",
                f"\n⚠️ --- TUGAB BORAYOTGAN (ENG KAM QOLGAN - 1 DONADAN) TOVARLAR RO'YXATI ---",
                f"{low_str}",
                f"\n🏢 --- BAZADAGI HAQIQIY YETKAZIB BERUVCHILAR (KONTRAGENTLAR) ---",
                f"{sup_names_str}",
                sales_str,
                y_sales_str,
                f"\n📋 --- OMBORDAGI BARCHA TOVARLAR VA ULARNING ANIQ KODLARI RO'YXATI ---",
                f"{all_products_str}",
            ]

            if is_super_admin and finance:
                context_parts.extend([
                    f"\n💰 --- MOLIYA VA KASSA QOLDIQLARI (MAXFIY) ---",
                    f"Jami so'mdagi mablag': {finance.get('total_uzs', 0):,.2f} so'm",
                    f"Dollar hisobi: {finance.get('dollar_balance', 0):,.2f} $",
                    f"Hisoblar:"
                ])
                for acc in finance.get("accounts", []):
                    context_parts.append(f" - {acc['name']}: {acc['balance']:,.2f}")

            context_parts.append(
                f"\nQAT'IY KO'RSATMALAR VA JAVOB BERISH QOIDALARI:"
                f"1. TOVAR KODI YOKI NOMI SO'RALGANDA (MATN YOKI OVOZLI XABARDA):"
                f"   - Agar foydalanuvchi biror tovar kodini (masalan: 00488, 00627, 00224...) yoki nomini aytib qoldig'ini so'rasa, YUQORIGI 'BARCHA TOVARLAR' ro'yxatidan AYNAN O'SHA KODNI toping."
                f"   - O'sha tovarning nomi, ombordagi aniq qoldig'i va sotuv narxini aniq ayting."
                f"   - Boshqa tovarlar (masalan muzlab turgan kapitaldagi 00627 Brooman yoki boshqa) bilan MUTLAQO chalkashtirmang!"
                f"2. AGAR UMUMIY ENG KO'P/KAM SOTILGAN, QOLGAN YOKI MUZLAB TURGAN TOVARLARNI SO'RASA:"
                f"   - Aynan YUQORIGI ANIQ TOVARLAR kesimida ro'yxat qilib amaliy biznes tavsiya bering."
                f"3. QOLDIQ VA KIRIMNI FARQLASH:"
                f"   - 'Qoldiq' / 'Guruh' so'ralsa -> Ombor qoldig'i (Excel: [GENERATE_EXCEL_STOCK_FOLDER:Guruh_Nomi] yoki [GENERATE_EXCEL_STOCKS])."
                f"   - 'Kirim' / 'Yetkazib beruvchi' so'ralsa -> Kirim (Excel: [GENERATE_EXCEL_SUPPLY_AGENT:ID:NOMI] yoki [GENERATE_EXCEL_SUPPLIES])."
                f"4. Doimo professional, do'stona va tushunarli o'zbek tilida javob bering."
                f"5. JAVOB FORMATI: javob Telegram'da ko'rsatiladi — jadval (| ... |) ishlatmang, ro'yxat va **qalin** matndan foydalaning. Javob qisqa va aniq bo'lsin."
                f"6. Savdo summalari SOF tushum (savdo − vozvrat). Kontekstda yo'q davr (masalan o'tgan oy) savdosi so'ralsa, raqam o'ylab topmang — bu ma'lumot «⏱ Soatlik Savdo» bo'limida yoki MoySkladda ekanini ayting."
            )

            result_ctx = "\n".join(context_parts)
            self._context_cache[cache_key] = {"time": now_ts, "data": result_ctx}
            return result_ctx
        except Exception as e:
            logger.exception(f"Error building AI context: {e}")
            return "Siz 'DE LUXURY' do'konining AI analitikassisiz. Do'kon ma'lumotlari asosida tahlil bering."

    @staticmethod
    def _format_sales_for_context(sales: Optional[Dict[str, Any]], title: str) -> str:
        if not sales:
            return f"\n⏱ --- {title} SAVDO --- (MoySkladdan vaqtincha olinmadi)"
        lines = [
            f"\n⏱ --- {title} SAVDO KO'RSATKICHLARI ({sales['date']}) ---",
            f"Sof tushum: {sales['total_sum']:,.2f} so'm | Savdo: {sales['gross_sum']:,.2f} so'm ({sales['total_count']} ta chek) | "
            f"Vozvrat: {sales['return_sum']:,.2f} so'm ({sales['return_count']} ta) | O'rtacha chek: {sales['avg_check']:,.2f} so'm",
            "Soatlar kesimida (faqat savdo bo'lgan soatlar):",
        ]
        for hour, d in sorted(sales["hourly"].items()):
            if d["count"] or d["return_count"]:
                row = f"  {hour:02d}:00-{(hour + 1) % 24:02d}:00 — {d['sum']:,.0f} so'm ({d['count']} ta chek)"
                if d["return_count"]:
                    row += f", vozvrat {d['return_sum']:,.0f} so'm"
                lines.append(row)
        if len(lines) == 3:
            lines.append("  (savdo yo'q)")
        return "\n".join(lines)

    async def _call_gemini_with_fallback(self, payload: dict) -> Optional[str]:
        """Modellarni navbat bilan sinab, birinchisi ishlaganida natijani qaytaradi"""
        deadline = time.monotonic() + TOTAL_DEADLINE
        headers = {"x-goog-api-key": self.api_key}  # kalit URL'da emas — loglarga tushmasligi uchun
        async with aiohttp.ClientSession(headers=headers) as session:
            for model_name in self.models:
                remaining = deadline - time.monotonic()
                if remaining < 5:
                    break
                timeout = aiohttp.ClientTimeout(total=min(MODEL_TIMEOUT, remaining))
                try:
                    async with session.post(GEMINI_URL.format(model=model_name), json=payload, timeout=timeout) as resp:
                        if resp.status != 200:
                            body = await resp.text()
                            logger.warning(f"Model {model_name} returned status {resp.status}: {body[:200]}")
                            continue
                        res_json = await resp.json()
                except Exception as e:
                    logger.warning(f"Exception on model {model_name}: {e!r}")
                    continue

                candidates = res_json.get("candidates", [])
                if not candidates:
                    logger.warning(f"Model {model_name}: javob bo'sh ({res_json.get('promptFeedback')})")
                    continue
                parts = candidates[0].get("content", {}).get("parts", [])
                text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
                if text.strip():
                    return text
                logger.warning(f"Model {model_name}: matnsiz javob, finishReason={candidates[0].get('finishReason')}")
        return None

    def _extract_excel_meta(self, reply_text: str) -> tuple[str, Optional[dict]]:
        """AI javobidan Excel generatsiya tegini ajratib oladi (birinchisi ishlatiladi, hammasi matndan olib tashlanadi)"""
        excel_meta = None
        match = EXCEL_TAG_RE.search(reply_text)
        if match:
            kind, arg = match.group(1), (match.group(2) or "").strip()
            if kind == "STOCK_FOLDER" and arg:
                excel_meta = {"type": "stock_folder", "folder_name": arg}
            elif kind == "SUPPLY_AGENT" and arg:
                agent_id, _, agent_name = arg.partition(":")
                excel_meta = {"type": "supply_agent", "agent_id": agent_id.strip(), "agent_name": agent_name.strip() or "Kontragent"}
            elif kind == "STOCKS":
                excel_meta = {"type": "stocks"}
            elif kind == "SUPPLIES":
                excel_meta = {"type": "supplies"}
        return EXCEL_TAG_RE.sub("", reply_text).strip(), excel_meta

    def _build_payload(self, system_instruction: str, history: List[dict], user_parts: List[dict]) -> dict:
        return {
            "systemInstruction": {"parts": [{"text": system_instruction}]},
            "contents": history + [{"role": "user", "parts": user_parts}],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 4096,
                # "low" — sifat saqlangan holda javob ~2 baravar tez (standart thinking 10–17 s)
                "thinkingConfig": {"thinkingLevel": "low"}
            }
        }

    async def process_text_query(self, query: str, is_super_admin: bool = False, user_id: Optional[int] = None) -> Dict[str, Any]:
        """Matnli so'rovni tahlil qilib javob beradi"""
        system_instruction = await self.get_system_context(is_super_admin=is_super_admin)
        
        # Agar savolda tovar kodi yoki son bo'lsa, uni bazadan tezkor topib ajratib beramiz
        code_matches = re.findall(r'\b\d{3,6}\b', query)
        extra_match_info = ""
        if code_matches:
            try:
                stock_data = await ms_api.get_stock_report()
                found_items = []
                for row in stock_data.get("raw_rows", []):
                    r_code = str(row.get("code", "")).strip()
                    for c in code_matches:
                        if c == r_code or (r_code and c.lstrip('0') == r_code.lstrip('0')):
                            buy_str = f" | Tan narxi (Sebestoimost): {row.get('buy_price',0):,.0f} so'm" if is_super_admin else ""
                            found_items.append(
                                f"  • Nomi: '{row.get('name')}' | Kodi: {row.get('code')} | Ombordagi haqiqiy qoldiq: {int(row.get('stock',0))} dona | Sotuv narxi: {row.get('sale_price',0):,.0f} so'm{buy_str}"
                            )
                if found_items:
                    extra_match_info = "\n\n🎯 SAVOLDA SO'RALGAN TOVAR(LAR)NING MOYSKLAD BAZASIDAGI ANIQ HAQIQIY MA'LUMOTLARI:\n" + "\n".join(found_items)
            except Exception:
                pass

        history = self._get_history(user_id)
        user_text = f"{query}{extra_match_info}"
        payload = self._build_payload(system_instruction, history, [{"text": user_text}])

        reply_text = await self._call_gemini_with_fallback(payload)

        if reply_text:
            self._remember(user_id, query, reply_text)
            clean_text, excel_meta = self._extract_excel_meta(reply_text)
            return {"text": clean_text, "excel_meta": excel_meta}

        return {"text": "Kechirasiz, sun'iy intellekt serverida vaqtincha uzilish bo'ldi. Iltimos, bir ozdan so'ng qayta urinib ko'ring.", "excel_meta": None}

    async def process_voice_query(self, audio_bytes: bytes, mime_type: str = "audio/ogg", is_super_admin: bool = False, user_id: Optional[int] = None) -> Dict[str, Any]:
        """Ovozli xabarni (Telegram voice) qabul qilib, uni tushunadi va javob qaytaradi"""
        system_instruction = await self.get_system_context(is_super_admin=is_super_admin)
        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

        history = self._get_history(user_id)
        user_parts = [
            {"text": "Quyidagi ovozli xabarni diqqat bilan eshiting. Javobni birinchi qatorda «🎙 Savol: <ovozli xabar matni>» ko'rinishida boshlang. "
                     "Agar ovozda biror tovar kodi (masalan: 00488, 00627, 00224...) aytilsa, BAZADAGI BARCHA TOVARLAR ro'yxatidan AYNAN O'SHA KODLI tovarning nomi, qoldig'i va narxini aniq ayting (aslo boshqa tovarlar bilan adashtirmang). "
                     "Agar tovar guruhi yoki kontragent so'ralsa shunga mos javob bering:"},
            {"inline_data": {"mime_type": mime_type, "data": audio_b64}},
        ]
        payload = self._build_payload(system_instruction, history, user_parts)

        reply_text = await self._call_gemini_with_fallback(payload)

        if reply_text:
            # Xotiraga audio emas, javob saqlanadi (uning birinchi qatorida AI tushungan savol matni bor)
            self._remember(user_id, "(Ovozli xabar — savol matni javobning birinchi qatorida)", reply_text)
            clean_text, excel_meta = self._extract_excel_meta(reply_text)
            return {"text": clean_text, "excel_meta": excel_meta}

        return {"text": "Ovozli xabarni qayta ishlashda xatolik yuz berdi. Iltimos, qaytadan yuboring.", "excel_meta": None}

ai_agent = AIAgent()
