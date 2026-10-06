import asyncio
import aiohttp
from datetime import datetime, timedelta
import pytz
from typing import Dict, List, Any, Optional
import config

tz = pytz.timezone(config.TIMEZONE)

class MoySkladClient:
    def __init__(self, token: str = config.MOYSKLAD_TOKEN):
        self.token = token
        self.base_url = config.MOYSKLAD_API_URL
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept-Encoding": "gzip",
            "Content-Type": "application/json"
        }

    async def _request(self, method: str, endpoint: str, params: dict = None, json_data: dict = None) -> Any:
        url = f"{self.base_url}/{endpoint}"
        async with aiohttp.ClientSession(headers=self.headers) as session:
            try:
                async with session.request(method, url, params=params, json=json_data, timeout=30) as resp:
                    if resp.status in (200, 201):
                        return await resp.json()
                    elif resp.status == 204:
                        return True
                    else:
                        error_text = await resp.text()
                        print(f"MoySklad API Error [{resp.status}] on {endpoint}: {error_text[:200]}")
                        return None
            except Exception as e:
                print(f"Request exception on {endpoint}: {e}")
                return None

    # ================= 1. SOATLIK VA KUNLIK SAVDO =================
    async def get_hourly_sales(self, target_date: Optional[datetime.date] = None) -> Dict[str, Any]:
        """Bugungi (yoki berilgan sanadagi) savdolarni soatma-soat hisoblaydi"""
        if target_date is None:
            now = datetime.now(tz)
            target_date = now.date()
        else:
            now = datetime.now(tz)

        start_str = f"{target_date.strftime('%Y-%m-%d')} 00:00:00"
        end_str = f"{target_date.strftime('%Y-%m-%d')} 23:59:59"

        # Retail demands (chakana savdo cheklari) va Demands (ulgurji/otgruzka)
        filter_str = f"moment>={start_str};moment<={end_str}"
        
        rd_task = self._request("GET", "entity/retaildemand", params={"filter": filter_str, "limit": 1000})
        dem_task = self._request("GET", "entity/demand", params={"filter": filter_str, "limit": 1000})
        
        rd_data, dem_data = await asyncio.gather(rd_task, dem_task)
        
        all_sales = []
        if rd_data and "rows" in rd_data:
            all_sales.extend(rd_data["rows"])
        if dem_data and "rows" in dem_data:
            all_sales.extend(dem_data["rows"])

        # Soatlar bo'yicha guruhlash (09:00 dan 23:00 gacha)
        hourly_data = {hour: {"count": 0, "sum": 0.0} for hour in range(config.WORK_START_HOUR, config.WORK_END_HOUR + 1)}
        total_sum = 0.0
        total_count = len(all_sales)

        for sale in all_sales:
            moment_str = sale.get("moment", "")
            sale_sum = (sale.get("sum", 0) or 0) / 100.0  # MoySklad tiyinda beradi
            total_sum += sale_sum

            if moment_str:
                try:
                    # '2026-10-07 14:35:10' yoki '2026-10-07 14:35:10.123'
                    dt = datetime.strptime(moment_str.split(".")[0], "%Y-%m-%d %H:%M:%S")
                    hour = dt.hour
                    if hour in hourly_data:
                        hourly_data[hour]["count"] += 1
                        hourly_data[hour]["sum"] += sale_sum
                except Exception:
                    pass

        avg_check = (total_sum / total_count) if total_count > 0 else 0.0

        return {
            "date": target_date.strftime("%d.%m.%Y"),
            "current_hour": now.hour,
            "total_sum": total_sum,
            "total_count": total_count,
            "avg_check": avg_check,
            "hourly": hourly_data
        }

    # ================= 2. TOVAR KIRIMI (PRIYOMKA / SUPPLY) =================
    async def get_supplies(self, date_from: Optional[str] = None, date_to: Optional[str] = None, agent_id: Optional[str] = None) -> Dict[str, Any]:
        """Priyomka (kirim) hujjatlarini filtrlar bilan yuklaydi"""
        params = {"limit": 100, "expand": "agent,positions.assortment", "order": "moment,desc"}
        filters = []
        
        if date_from:
            filters.append(f"moment>={date_from} 00:00:00")
        if date_to:
            filters.append(f"moment<={date_to} 23:59:59")
        if agent_id:
            filters.append(f"agent=https://api.moysklad.ru/api/remap/1.2/entity/counterparty/{agent_id}")

        if filters:
            params["filter"] = ";".join(filters)

        data = await self._request("GET", "entity/supply", params=params)
        
        supplies_list = []
        total_sum = 0.0
        total_qty_all = 0.0
        by_agent = {}

        if data and "rows" in data:
            for row in data["rows"]:
                s_sum = (row.get("sum", 0) or 0) / 100.0
                total_sum += s_sum
                agent_name = row.get("agent", {}).get("name", "Noma'lum")
                
                pos_meta_size = row.get("positions", {}).get("meta", {}).get("size", 0)

                if agent_name not in by_agent:
                    by_agent[agent_name] = {"count": 0, "sum": 0.0}
                by_agent[agent_name]["count"] += 1
                by_agent[agent_name]["sum"] += s_sum

                # Moment formatini chiroyli qilish
                moment_raw = row.get("moment", "")
                moment_fmt = ""
                if moment_raw:
                    try:
                        dt = datetime.strptime(moment_raw.split(".")[0], "%Y-%m-%d %H:%M:%S")
                        moment_fmt = dt.strftime("%d.%m.%Y %H:%M")
                    except Exception:
                        moment_fmt = moment_raw[:16]

                supplies_list.append({
                    "id": row.get("id"),
                    "name": row.get("name"),
                    "moment": moment_fmt,
                    "agent": agent_name,
                    "sum": s_sum,
                    "positions_count": pos_meta_size
                })

        return {
            "total_count": len(supplies_list),
            "total_sum": total_sum,
            "by_agent": by_agent,
            "rows": supplies_list
        }

    async def get_supply_positions_detailed(self, agent_id: Optional[str] = None, date_from: Optional[str] = None, date_to: Optional[str] = None) -> Dict[str, Any]:
        """Kontragent yoki sana bo'yicha kirim qilingan barcha tovar pozitsiyalarini to'liq atributlari bilan oladi"""
        supplies_data = await self.get_supplies(date_from=date_from, date_to=date_to, agent_id=agent_id)
        supplies = supplies_data.get("rows", [])

        # Barcha tovarlar xaritasini olamiz (dop polya: Kategoriya, Vid tovara uchun)
        prod_data = await self._request("GET", "entity/product", params={"limit": 1000, "expand": "productFolder,attributes"})
        prod_map = {}
        if prod_data and "rows" in prod_data:
            for p in prod_data["rows"]:
                attrs = {}
                for a in p.get("attributes", []):
                    val = a.get("value", "")
                    if isinstance(val, dict):
                        val = val.get("name", "")
                    attrs[a.get("name", "")] = str(val)

                prod_map[p.get("id")] = {
                    "code": p.get("code", ""),
                    "article": p.get("article", ""),
                    "folder": p.get("pathName") or p.get("productFolder", {}).get("name", "Guruhsiz"),
                    "category": attrs.get("Категория", "") or attrs.get("Kategoriya", ""),
                    "vid_tovara": attrs.get("Вид товара", "") or attrs.get("Vid tovara", "")
                }

        all_positions = []
        total_sum = 0.0
        total_qty = 0.0

        for s in supplies:
            s_id = s["id"]
            pos_resp = await self._request("GET", f"entity/supply/{s_id}/positions", params={"expand": "assortment"})
            if not pos_resp or "rows" not in pos_resp:
                continue

            for p in pos_resp["rows"]:
                qty = float(p.get("quantity", 0) or 0)
                price = (p.get("price", 0) or 0) / 100.0
                item_sum = qty * price
                
                assortment = p.get("assortment", {})
                p_href = assortment.get("meta", {}).get("href", "")
                p_id = p_href.split("/")[-1].split("?")[0] if "/" in p_href else ""
                
                p_info = prod_map.get(p_id, {})

                total_qty += qty
                total_sum += item_sum

                all_positions.append({
                    "supply_name": s["name"],
                    "moment": s["moment"],
                    "agent": s["agent"],
                    "code": p_info.get("code") or assortment.get("code", ""),
                    "name": assortment.get("name", "Noma'lum"),
                    "folder": p_info.get("folder") or "Guruhsiz",
                    "category": p_info.get("category", ""),
                    "vid_tovara": p_info.get("vid_tovara", ""),
                    "quantity": qty,
                    "price": price,
                    "sum": item_sum
                })

        return {
            "total_positions": len(all_positions),
            "total_qty": total_qty,
            "total_sum": total_sum,
            "positions": all_positions
        }

    # ================= 3. TOVAR QOLDIQLARI (OSTATKI) =================
    async def get_stock_report(self, folder_id: Optional[str] = None) -> Dict[str, Any]:
        """Barcha tovarlar qoldig'i, tan narxi va sotuv narxi summasini to'g'ri hisoblaydi va atributlar bilan boyitadi"""
        params = {"limit": 1000}
        if folder_id:
            params["productFolder"] = f"https://api.moysklad.ru/api/remap/1.2/entity/productfolder/{folder_id}"

        # 1. Qoldiqlar hisoboti
        stock_task = self._request("GET", "report/stock/all", params=params)
        # 2. Barcha tovarlar (kodi, dop polya: Kategoriya, Vid tovara uchun)
        prod_task = self._request("GET", "entity/product", params={"limit": 1000, "expand": "productFolder,attributes"})
        
        stock_data, prod_data = await asyncio.gather(stock_task, prod_task)

        # Mahsulotlar xaritasi: id -> {code, category, vid_tovara}
        prod_map = {}
        if prod_data and "rows" in prod_data:
            for p in prod_data["rows"]:
                attrs = {}
                for a in p.get("attributes", []):
                    val = a.get("value", "")
                    if isinstance(val, dict):
                        val = val.get("name", "")
                    attrs[a.get("name", "")] = str(val)

                prod_map[p.get("id")] = {
                    "code": p.get("code", ""),
                    "article": p.get("article", ""),
                    "category": attrs.get("Категория", "") or attrs.get("Kategoriya", ""),
                    "vid_tovara": attrs.get("Вид товара", "") or attrs.get("Vid tovara", "")
                }

        total_quantity = 0.0
        total_cost_sum = 0.0   # Tan narxi bo'yicha jami (price * qty)
        total_sale_sum = 0.0   # Sotuv narxi bo'yicha jami (salePrice * qty)
        by_folder = {}
        enriched_rows = []

        if stock_data and "rows" in stock_data:
            for row in stock_data["rows"]:
                qty = float(row.get("stock", 0) or 0)
                if qty <= 0:
                    continue

                total_quantity += qty
                folder_name = row.get("folder", {}).get("name", "Guruhsiz")
                
                # MoySklad report/stock/all da:
                # 'price' bu Tan Narx (Buy Price / Sebestoimost)
                # 'salePrice' bu Sotuv Narxi (Sale Price)
                buy_price = (row.get("price", 0) or 0) / 100.0
                sale_price = (row.get("salePrice", 0) or 0) / 100.0
                
                item_cost_total = buy_price * qty
                item_sale_total = sale_price * qty
                
                total_cost_sum += item_cost_total
                total_sale_sum += item_sale_total

                if folder_name not in by_folder:
                    by_folder[folder_name] = {
                        "quantity": 0.0,
                        "cost_sum": 0.0,
                        "sale_sum": 0.0,
                        "items_count": 0
                    }
                by_folder[folder_name]["quantity"] += qty
                by_folder[folder_name]["cost_sum"] += item_cost_total
                by_folder[folder_name]["sale_sum"] += item_sale_total
                by_folder[folder_name]["items_count"] += 1

                # Mahsulot ID sini aniqlash (query parametrlardan tozalaymiz)
                meta_href = row.get("meta", {}).get("href", "")
                p_id = meta_href.split("/")[-1].split("?")[0] if "/" in meta_href else ""
                row_code = row.get("code", "")
                row_name = row.get("name", "")

                p_info = prod_map.get(p_id) or prod_map.get(row_code) or prod_map.get(row_name) or {}

                enriched_rows.append({
                    "id": p_id,
                    "code": p_info.get("code") or row_code,
                    "name": row_name,
                    "folder": folder_name,
                    "category": p_info.get("category", ""),
                    "vid_tovara": p_info.get("vid_tovara", ""),
                    "stock": qty,
                    "buy_price": buy_price,
                    "cost_total": item_cost_total,
                    "sale_price": sale_price,
                    "sale_total": item_sale_total
                })

        return {
            "total_quantity": total_quantity,
            "total_cost_sum": total_cost_sum,
            "total_sale_sum": total_sale_sum,
            "by_folder": by_folder,
            "raw_rows": enriched_rows
        }

    # ================= 4. TEZKOR TOVAR QIDIRUV (SHTRIX-KOD / KOD) =================
    async def search_product(self, query: str) -> Optional[Dict[str, Any]]:
        """Shtrix-kod, tovar kodi, artikul yoki nomi bo'yicha tovar qidiradi"""
        query = query.strip()
        
        # Qidiruv parametrlarini tuzamiz
        params = {"search": query, "expand": "productFolder,attributes", "limit": 5}
        data = await self._request("GET", "entity/product", params=params)
        
        if not data or not data.get("rows"):
            # Agar oddiy search topmasa, barcode filtri bilan tekshirib ko'ramiz
            data = await self._request("GET", "entity/product", params={"filter": f"barcode={query}", "expand": "productFolder,attributes", "limit": 5})

        if not data or not data.get("rows"):
            return None

        product = data["rows"][0]
        prod_id = product.get("id")

        # Mahsulotning ayni damdagi qoldig'ini olish
        stock_resp = await self._request("GET", "report/stock/all", params={"filter": f"product=https://api.moysklad.ru/api/remap/1.2/entity/product/{prod_id}"})
        current_stock = 0.0
        if stock_resp and stock_resp.get("rows"):
            current_stock = float(stock_resp["rows"][0].get("stock", 0) or 0)

        # Sotuv narxini olish
        sale_prices = product.get("salePrices", [])
        price = 0.0
        if sale_prices:
            price = (sale_prices[0].get("value", 0) or 0) / 100.0

        # Maxsus atributlarni ajratib olish (Brend, O'lcham, Rang, Fasl, Model)
        attributes = {}
        for attr in product.get("attributes", []):
            attr_name = attr.get("name", "")
            val = attr.get("value", "")
            if isinstance(val, dict):
                val = val.get("name", "")
            attributes[attr_name] = str(val)

        # Shtrix-kodlar
        barcodes = [b.get("ean13") or b.get("code128") or str(b) for b in product.get("barcodes", []) if b]

        return {
            "id": prod_id,
            "name": product.get("name"),
            "code": product.get("code", ""),
            "article": product.get("article", ""),
            "barcodes": barcodes,
            "folder": product.get("productFolder", {}).get("name", "Guruhsiz"),
            "price": price,
            "buy_price": (product.get("buyPrice", {}).get("value", 0) or 0) / 100.0,
            "stock": current_stock,
            "attributes": attributes
        }

    # ================= 5. MOLIYA & KASSA & XARAJATLAR (RAHBAR UCHUN) =================
    async def get_finance_balances(self) -> Dict[str, Any]:
        """Kassalar, valyuta (Dollar), Terminal va Karta hisoblari qoldiqlarini oladi"""
        data = await self._request("GET", "report/money/byaccount")
        
        accounts = []
        total_uzs = 0.0
        dollar_balance = 0.0

        if data and "rows" in data:
            for row in data["rows"]:
                balance = float(row.get("balance", 0) or 0) / 100.0
                acc_name = row.get("account", {}).get("name")
                org_name = row.get("organization", {}).get("name", "DE LUXURY")
                
                if not acc_name:
                    display_name = f"💵 Asosiy Kassa (Naqd)"
                    total_uzs += balance
                else:
                    if "dollar" in acc_name.lower():
                        display_name = f"💲 {acc_name} (Valyuta)"
                        dollar_balance += balance
                    elif "terminal" in acc_name.lower():
                        display_name = f"📟 {acc_name}"
                        total_uzs += balance
                    elif "karta" in acc_name.lower():
                        display_name = f"💳 {acc_name}"
                        total_uzs += balance
                    else:
                        display_name = f"🏦 {acc_name}"
                        total_uzs += balance

                accounts.append({
                    "name": display_name,
                    "balance": balance,
                    "is_dollar": "dollar" in (acc_name or "").lower()
                })

        return {
            "accounts": accounts,
            "total_uzs": total_uzs,
            "dollar_balance": dollar_balance
        }

    async def get_expenses_report(self, date_from: Optional[str] = None, date_to: Optional[str] = None) -> Dict[str, Any]:
        """Chiqimlar va xarajatlar tahlili (Statya rasxodov va izohlar)"""
        if not date_from:
            now = datetime.now(tz)
            date_from = now.strftime("%Y-%m-%d")
            date_to = date_from

        filter_str = f"moment>={date_from} 00:00:00;moment<={date_to} 23:59:59"
        
        # Cashout (kassadan chiqim) va Paymentout (bankdan chiqim)
        co_task = self._request("GET", "entity/cashout", params={"filter": filter_str, "expand": "expenseItem", "limit": 500})
        po_task = self._request("GET", "entity/paymentout", params={"filter": filter_str, "expand": "expenseItem", "limit": 500})
        
        co_data, po_data = await asyncio.gather(co_task, po_task)
        
        all_expenses = []
        if co_data and "rows" in co_data:
            all_expenses.extend(co_data["rows"])
        if po_data and "rows" in po_data:
            all_expenses.extend(po_data["rows"])

        total_expense = 0.0
        by_item = {}
        details = []

        for exp in all_expenses:
            s = (exp.get("sum", 0) or 0) / 100.0
            total_expense += s
            item_name = exp.get("expenseItem", {}).get("name", "Boshqa xarajatlar")
            desc = exp.get("description", "") or exp.get("comment", "") or "Izohsiz"
            moment = exp.get("moment", "")[:16]

            if item_name not in by_item:
                by_item[item_name] = 0.0
            by_item[item_name] += s

            details.append({
                "item": item_name,
                "sum": s,
                "comment": desc,
                "moment": moment
            })

        return {
            "date_from": date_from,
            "date_to": date_to,
            "total_expense": total_expense,
            "by_item": by_item,
            "details": details
        }

    # ================= 6. CHUQUR TOVAR VA QOLDIQ TAHLILI (TOP / LOW STOCK) =================
    async def get_products_analytics(self) -> Dict[str, Any]:
        """Chuqur tovarlar tahlili: eng ko'p zaxira, eng kam qoldiq va tavsiyalar uchun ma'lumotlar"""
        stock_data = await self.get_stock_report()
        raw_rows = stock_data.get("raw_rows", [])

        # 1. Eng katta zaxiraga ega tovarlar (Muzlab turgan kapital bo'yicha)
        sorted_by_val = sorted(raw_rows, key=lambda x: float(x.get("sale_total", 0) or 0), reverse=True)
        top_capital_items = sorted_by_val[:10]

        # 2. Eng ko'p miqdorda qolgan tovarlar (Dona bo'yicha)
        sorted_by_qty = sorted(raw_rows, key=lambda x: float(x.get("stock", 0) or 0), reverse=True)
        top_qty_items = sorted_by_qty[:10]

        # 3. Tugab borayotgan / Kam qolgan tovarlar (1-3 dona)
        sorted_by_low = sorted([r for r in raw_rows if float(r.get("stock", 0) or 0) > 0], key=lambda x: float(x.get("stock", 0) or 0))
        low_stock_items = sorted_by_low[:10]

        return {
            "top_capital_items": top_capital_items,
            "top_qty_items": top_qty_items,
            "low_stock_items": low_stock_items,
            "total_items_count": len(raw_rows)
        }

    # ================= YORDAMCHI MA'LUMOTLAR =================
    async def get_counterparties(self) -> List[Dict[str, str]]:
        """Barcha yetkazib beruvchilar ro'yxati"""
        data = await self._request("GET", "entity/counterparty", params={"limit": 100})
        if not data or "rows" not in data:
            return []
        return [{"id": r["id"], "name": r.get("name", "")} for r in data["rows"]]

    async def get_product_folders(self) -> List[Dict[str, str]]:
        """Barcha tovar guruhlari / kategoriyalari"""
        data = await self._request("GET", "entity/productfolder", params={"limit": 100})
        if not data or "rows" not in data:
            return []
        return [{"id": r["id"], "name": r.get("name", "")} for r in data["rows"]]

# Global instansiya
ms_api = MoySkladClient()
