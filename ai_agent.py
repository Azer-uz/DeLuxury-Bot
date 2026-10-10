import aiohttp
import json
import base64
import os
import asyncio
import time
import re
from typing import Dict, Any, Optional
import config
from moysklad_api import ms_api
from excel_generator import ExcelGenerator

class AIAgent:
    def __init__(self, api_key: str = config.GEMINI_API_KEY):
        self.api_key = api_key
        # Eng barqaror va tezkor modellar ketma-ketligi (auto-fallback)
        self.models = [
            "gemini-3-flash-preview",
            "gemini-3.1-flash-lite-preview",
            "gemini-3.7-flash",
            "gemini-3.5-flash",
            "gemini-flash-latest"
        ]
        self._context_cache: Dict[str, Any] = {}
        self._cache_ttl = 60  # 60 soniya kesh (tezkor ishlash uchun)

    async def get_system_context(self, is_super_admin: bool = False) -> str:
        """MoySkladdan ayni damdagi biznes ma'lumotlarini to'plab, AI uchun kontekst yaratadi (Kesh bilan tezkor)"""
        cache_key = f"ctx_admin_{is_super_admin}"
        now_ts = time.time()
        cached = self._context_cache.get(cache_key)
        if cached and (now_ts - cached["time"] < self._cache_ttl):
            return cached["data"]

        try:
            sales_task = ms_api.get_hourly_sales()
            stock_task = ms_api.get_stock_report()
            counterparties_task = ms_api.get_counterparties()
            
            if is_super_admin:
                finance_task = ms_api.get_finance_balances()
                sales, stock, counterparties, finance = await asyncio.gather(
                    sales_task, stock_task, counterparties_task, finance_task
                )
            else:
                sales, stock, counterparties = await asyncio.gather(
                    sales_task, stock_task, counterparties_task
                )
                finance = None

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

            context_parts = [
                f"Siz 'DE LUXURY' erkaklar kiyim do'konining professional biznes-analitik va boshqaruvchi AI maslahatchisisiz.",
                f"Bugungi sana: {sales.get('date')}.",
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
                f"\n⏱ --- BUGUNGI SAVDO KO'RSATKICHLARI ---",
                f"Jami tushum: {sales.get('total_sum', 0):,.2f} so'm ({sales.get('total_count', 0)} ta chek)",
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
            )

            result_ctx = "\n".join(context_parts)
            self._context_cache[cache_key] = {"time": now_ts, "data": result_ctx}
            return result_ctx
        except Exception as e:
            print(f"Error building AI context: {e}")
            return "Siz 'DE LUXURY' do'konining AI analitikassisiz. Do'kon ma'lumotlari asosida tahlil bering."

    async def _call_gemini_with_fallback(self, payload: dict) -> Optional[str]:
        """Modellarni navbat bilan sinab, birinchisi ishlaganida natijani tezkor qaytaradi"""
        connector = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            for model_name in self.models:
                clean_name = model_name.replace("models/", "")
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{clean_name}:generateContent?key={self.api_key}"
                try:
                    async with session.post(url, json=payload, timeout=12) as resp:
                        if resp.status == 200:
                            res_json = await resp.json()
                            candidates = res_json.get("candidates", [])
                            if candidates and "content" in candidates[0]:
                                parts = candidates[0]["content"].get("parts", [])
                                if parts:
                                    return parts[0].get("text", "")
                        else:
                            print(f"Model {clean_name} returned status {resp.status}, trying next...")
                except Exception as e:
                    print(f"Exception on model {clean_name}: {e}")
                    continue
        return None

    def _extract_excel_meta(self, reply_text: str) -> tuple[str, Optional[dict]]:
        """AI javobidan Excel generatsiya teglarini ajratib oladi"""
        excel_meta = None
        
        # 1. Guruh bo'yicha qoldiq Excel: [GENERATE_EXCEL_STOCK_FOLDER:folder_name]
        if "[GENERATE_EXCEL_STOCK_FOLDER:" in reply_text:
            start_idx = reply_text.find("[GENERATE_EXCEL_STOCK_FOLDER:")
            end_idx = reply_text.find("]", start_idx)
            if end_idx != -1:
                tag = reply_text[start_idx:end_idx+1]
                folder_name = tag[len("[GENERATE_EXCEL_STOCK_FOLDER:"):-1].strip()
                excel_meta = {"type": "stock_folder", "folder_name": folder_name}
                reply_text = reply_text.replace(tag, "").strip()

        # 2. Yetkazib beruvchi kirimi Excel: [GENERATE_EXCEL_SUPPLY_AGENT:id:name]
        elif "[GENERATE_EXCEL_SUPPLY_AGENT:" in reply_text:
            start_idx = reply_text.find("[GENERATE_EXCEL_SUPPLY_AGENT:")
            end_idx = reply_text.find("]", start_idx)
            if end_idx != -1:
                tag = reply_text[start_idx:end_idx+1]
                inner = tag[len("[GENERATE_EXCEL_SUPPLY_AGENT:"):-1]
                parts = inner.split(":")
                agent_id = parts[0].strip()
                agent_name = parts[1].strip() if len(parts) > 1 else "Kontragent"
                excel_meta = {"type": "supply_agent", "agent_id": agent_id, "agent_name": agent_name}
                reply_text = reply_text.replace(tag, "").strip()

        # 3. Umumiy qoldiqlar: [GENERATE_EXCEL_STOCKS]
        elif "[GENERATE_EXCEL_STOCKS]" in reply_text:
            excel_meta = {"type": "stocks"}
            reply_text = reply_text.replace("[GENERATE_EXCEL_STOCKS]", "").strip()

        # 4. Umumiy kirimlar: [GENERATE_EXCEL_SUPPLIES]
        elif "[GENERATE_EXCEL_SUPPLIES]" in reply_text:
            excel_meta = {"type": "supplies"}
            reply_text = reply_text.replace("[GENERATE_EXCEL_SUPPLIES]", "").strip()

        return reply_text, excel_meta

    async def process_text_query(self, query: str, is_super_admin: bool = False) -> Dict[str, Any]:
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

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": f"SISTEMA KO'RSATMASI VA BAZA MA'LUMOTLARI:\n{system_instruction}{extra_match_info}\n\nFOYDALANUVCHI SAVOLI:\n{query}"}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 2048
            }
        }

        reply_text = await self._call_gemini_with_fallback(payload)
        
        if reply_text:
            clean_text, excel_meta = self._extract_excel_meta(reply_text)
            return {"text": clean_text, "excel_meta": excel_meta}

        return {"text": "Kechirasiz, sun'iy intellekt serverida vaqtincha uzilish bo'ldi. Iltimos, bir ozdan so'ng qayta urinib ko'ring.", "excel_meta": None}

    async def process_voice_query(self, audio_bytes: bytes, mime_type: str = "audio/ogg", is_super_admin: bool = False) -> Dict[str, Any]:
        """Ovozli xabarni (Telegram voice) qabul qilib, uni tushunadi va javob qaytaradi"""
        system_instruction = await self.get_system_context(is_super_admin=is_super_admin)
        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": f"SISTEMA KO'RSATMASI VA BAZA MA'LUMOTLARI:\n{system_instruction}\n\nQuyidagi ovozli xabarni diqqat bilan eshiting. Agar ovozda biror tovar kodi (masalan: 00488, 00627, 00224...) aytilsa, yuqoridagi BAZADAGI BARCHA TOVARLAR ro'yxatidan AYNAN O'SHA KODLI tovarning nomi, qoldig'i va narxini aniq ayting (aslo boshqa tovarlar bilan adashtirmang). Agar tovar guruhi yoki kontragent so'ralsa shunga mos javob bering:"},
                        {
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": audio_b64
                            }
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 2048
            }
        }

        reply_text = await self._call_gemini_with_fallback(payload)

        if reply_text:
            clean_text, excel_meta = self._extract_excel_meta(reply_text)
            return {"text": clean_text, "excel_meta": excel_meta}

        return {"text": "Ovozli xabarni qayta ishlashda xatolik yuz berdi. Iltimos, qaytadan yuboring.", "excel_meta": None}

ai_agent = AIAgent()
