"""Har bir chek yaratilgan zahoti Telegram'ga yuborish.

MoySklad'ni har RECEIPT_POLL_SECONDS soniyada so'raydi: oxirgi tekshiruvdan keyin o'zgargan (updated>=) va
o'tkazilgan (applicable=true) chakana cheklar, vozvratlar va otgruzkalar. Har bir hujjat faqat bir marta yuboriladi
(ko'rilgan ID lar faylda saqlanadi — bot qayta ishga tushganda ham takror kelmaydi).
"""
import asyncio
import html
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from aiogram import Bot
import config
from moysklad_api import ms_api, to_tashkent_dt, MoySkladError

logger = logging.getLogger(__name__)

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state", "receipts_seen.json")
POLL_SECONDS = getattr(config, "RECEIPT_POLL_SECONDS", 15)
OVERLAP = timedelta(minutes=3)   # soat farqi/kechikishlarga zaxira — takrorni ID bo'yicha filtrlaymiz
MAX_SEEN = 2000

# (endpoint, sarlavha, belgi, summa ishorasi)
DOC_TYPES = [
    ("entity/retaildemand", "YANGI CHEK", "🧾", 1),
    ("entity/retailsalesreturn", "VOZVRAT (QAYTARISH)", "↩️", -1),
    ("entity/demand", "OTGRUZKA (ULGURJI)", "📦", 1),
    ("entity/salesreturn", "VOZVRAT (ULGURJI)", "↩️", -1),
]

def moscow_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=3)

def fmt(val: float) -> str:
    return f"{val:,.0f}".replace(",", " ")

class ReceiptWatcher:
    def __init__(self, bot: Bot):
        self.bot = bot
        self.seen: List[str] = []
        self.checkpoint: Optional[str] = None  # Moskva vaqti "YYYY-MM-DD HH:MM:SS"
        self._load()

    # ---------- holat ----------
    def _load(self):
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                data = json.load(f)
            self.seen = list(data.get("seen", []))[-MAX_SEEN:]
            self.checkpoint = data.get("checkpoint")
        except (OSError, ValueError):
            pass
        if not self.checkpoint:
            # Birinchi ishga tushish: eski cheklar bilan to'ldirib yubormaymiz
            self.checkpoint = (moscow_now() - timedelta(minutes=2)).strftime("%Y-%m-%d %H:%M:%S")

    def _save(self):
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"checkpoint": self.checkpoint, "seen": self.seen[-MAX_SEEN:]}, f)
        os.replace(tmp, STATE_FILE)

    # ---------- MoySklad ----------
    async def _fetch_new(self, endpoint: str) -> List[Dict[str, Any]]:
        since = (datetime.strptime(self.checkpoint, "%Y-%m-%d %H:%M:%S") - OVERLAP).strftime("%Y-%m-%d %H:%M:%S")
        params = {
            "filter": f"updated>={since};applicable=true",
            "expand": "positions.assortment,retailStore,agent",
            "order": "updated,asc",
            "limit": 100,
        }
        data = await ms_api._request("GET", endpoint, params=params)
        if not isinstance(data, dict) or "rows" not in data:
            raise MoySkladError(f"{endpoint} javob bermadi")
        return data["rows"]

    async def _positions(self, doc: Dict[str, Any]) -> List[Dict[str, Any]]:
        pos = doc.get("positions", {})
        rows = pos.get("rows", [])
        if pos.get("meta", {}).get("size", len(rows)) > len(rows):
            # 100 dan ko'p pozitsiya — alohida olamiz
            href = pos.get("meta", {}).get("href", "")
            data = await ms_api._request("GET", href.split("/remap/1.2/")[-1], params={"expand": "assortment", "limit": 1000})
            if isinstance(data, dict):
                rows = data.get("rows", rows)
        return rows

    # ---------- xabar ----------
    async def _build_message(self, doc: Dict[str, Any], title: str, icon: str, sign: int) -> str:
        dt_uz = to_tashkent_dt(doc.get("moment", ""))
        when = dt_uz.strftime("%d.%m.%Y %H:%M") if dt_uz else doc.get("moment", "")[:16]
        store = doc.get("retailStore", {}).get("name") or doc.get("store", {}).get("name") or ""
        agent = doc.get("agent", {}).get("name", "")
        total = (doc.get("sum", 0) or 0) / 100.0

        lines = [f"{icon} <b>{title} №{html.escape(doc.get('name', ''))}</b>", f"🕒 {when}" + (f" | 🏪 {html.escape(store)}" if store else "")]
        if agent and "розничный покупатель" not in agent.lower():
            lines.append(f"🤝 {html.escape(agent)}")
        lines.append("━━━━━━━━━━━━━━━━━━━━━")

        positions = await self._positions(doc)
        total_qty = 0.0
        for i, p in enumerate(positions, 1):
            a = p.get("assortment", {})
            qty = float(p.get("quantity", 0) or 0)
            price = (p.get("price", 0) or 0) / 100.0
            disc = float(p.get("discount", 0) or 0)
            line_sum = qty * price * (1 - disc / 100.0)
            total_qty += qty
            name = html.escape(a.get("name", "Noma'lum"))
            code = a.get("code") or a.get("article") or ""
            code_s = f" (<code>{html.escape(code)}</code>)" if code else ""
            disc_s = f" −{disc:g}%" if disc else ""
            lines.append(f"{i}. {name}{code_s} — {qty:g} × {fmt(price)}{disc_s} = <b>{fmt(line_sum)}</b>")
        if not positions:
            lines.append("<i>(pozitsiyalar yo'q)</i>")

        lines.append("━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"💰 <b>Jami: {'-' if sign < 0 else ''}{fmt(total)} so'm</b> ({total_qty:g} dona, {len(positions)} ta pozitsiya)")

        cash = (doc.get("cashSum", 0) or 0) / 100.0
        card = (doc.get("noCashSum", 0) or 0) / 100.0
        qr = (doc.get("qrSum", 0) or 0) / 100.0
        if cash or card or qr:
            pay = [f"💵 Naqd: {fmt(cash)}" if cash else "", f"💳 Karta: {fmt(card)}" if card else "", f"📱 QR: {fmt(qr)}" if qr else ""]
            lines.append(" | ".join(x for x in pay if x))

        # Kun boshidan buyon (keshsiz — hozirgi chek ham kirsin)
        try:
            day = await ms_api.get_hourly_sales(use_cache=False)
            day_line = f"📊 Bugun: <b>{fmt(day['total_sum'])} so'm</b> ({day['total_count']} ta chek"
            if day["return_count"]:
                day_line += f", vozvrat {fmt(day['return_sum'])}"
            lines.append(day_line + ")")
        except Exception as e:
            logger.warning(f"Kunlik jami olinmadi: {e}")

        return "\n".join(lines)

    async def _broadcast(self, text: str):
        for user_id in config.SUPER_ADMIN_IDS | config.MANAGER_IDS:
            try:
                await self.bot.send_message(user_id, text, parse_mode="HTML")
            except Exception as e:
                logger.warning(f"{user_id} ga chek yuborilmadi: {e}")

    # ---------- sikl ----------
    async def poll_once(self) -> int:
        sent = 0
        new_checkpoint = self.checkpoint
        for endpoint, title, icon, sign in DOC_TYPES:
            rows = await self._fetch_new(endpoint)
            for doc in rows:
                upd = (doc.get("updated") or "")[:19]
                if upd > new_checkpoint:
                    new_checkpoint = upd
                doc_id = doc.get("id")
                if not doc_id or doc_id in self.seen:
                    continue
                self.seen.append(doc_id)
                self._save()  # yuborishdan OLDIN belgilaymiz — xato bo'lsa ham takror yubormaymiz
                try:
                    text = await self._build_message(doc, title, icon, sign)
                except Exception as e:
                    logger.exception(f"Chek {doc.get('name')} xabari tuzilmadi: {e}")
                    text = f"{icon} <b>{title} №{html.escape(doc.get('name', ''))}</b>\n💰 {fmt((doc.get('sum', 0) or 0) / 100.0)} so'm\n<i>(tafsilotlar olinmadi)</i>"
                await self._broadcast(text)
                sent += 1
        if new_checkpoint != self.checkpoint:
            self.checkpoint = new_checkpoint
            self._save()
        return sent

    async def run(self):
        logger.info(f"🧾 Chek kuzatuvchisi ishga tushdi (har {POLL_SECONDS} s, checkpoint {self.checkpoint} MSK)")
        failures = 0
        while True:
            try:
                await self.poll_once()
                failures = 0
            except asyncio.CancelledError:
                raise
            except Exception as e:
                failures += 1
                logger.warning(f"Chek kuzatuvida xato ({failures}): {e}")
                if failures == 20:  # ~5 daqiqa davomida MoySklad javob bermayapti
                    for admin_id in config.SUPER_ADMIN_IDS:
                        try:
                            await self.bot.send_message(admin_id, "⚠️ <b>Chek kuzatuvi:</b> MoySklad 5 daqiqadan beri javob bermayapti. Cheklar aloqa tiklangach yuboriladi.", parse_mode="HTML")
                        except Exception:
                            pass
            await asyncio.sleep(POLL_SECONDS if failures < 5 else min(POLL_SECONDS * failures, 120))
