"""Smart Auto-Undercut & Portfolio Valuation Engine with Thin Floor Protection."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from loguru import logger

from backend.config import base_settings
from backend.database import db, utc_now_iso
from backend.services.analytics_engine import analytics_engine
from backend.services.multi_market import MARKET_FEES
from backend.services.ws_manager import ws_manager


class UndercutEngine:
    """Monitors user portfolio listings against live floors & protects against dumping thin floors."""

    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self._notified_keys: set[str] = set()
        self._send_tg_undercut: Callable[[dict[str, Any]], Awaitable[bool]] | None = None

    def register_telegram_sender(
        self, sender: Callable[[dict[str, Any]], Awaitable[bool]]
    ) -> None:
        self._send_tg_undercut = sender

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="undercut_engine_loop")
        logger.info("UndercutEngine started")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def build_enriched_portfolio(self) -> dict[str, Any]:
        """Return portfolio summary + fully enriched items matching API_CONTRACT.md."""
        raw_items = await db.list_portfolio_items()
        collections = await analytics_engine.get_collections_summary(limit=100)
        col_by_short = {c.short_name: c for c in collections}

        enriched_items: list[dict[str, Any]] = []
        total_invested = 0.0
        current_value = 0.0
        active_listings = 0
        undercut_active_count = 0

        for row in raw_items:
            col = col_by_short.get(row["short_name"])
            current_floor = round(col.floor_price, 2) if col else round(row["buy_price"] * 1.12, 2)
            # Determine competitor price (uses simulated override if present, else live market floor)
            competitor_price = (
                round(row["competitor_override"], 2)
                if row.get("competitor_override") is not None
                else current_floor
            )

            # Best cross-market sell venue
            best_sell_market = row["market"]
            best_sell_price = current_floor
            if col and col.market_floors:
                best_net = -1.0
                for m, fl in col.market_floors.items():
                    net = fl * (1.0 - MARKET_FEES.get(m, 5.0) / 100.0)
                    if net > best_net:
                        best_net = net
                        best_sell_market = m
                        best_sell_price = round(fl, 2)

            fair_value = round(max(current_floor * 1.08, best_sell_price), 2)

            # Thin Floor Protection check
            thin_warning: str | None = None
            if col and col.thin_floor_count <= 2 and col.thin_floor_gap_percent >= 12.0:
                target_jump = round(current_floor * (1.0 + col.thin_floor_gap_percent / 100.0), 1)
                thin_warning = (
                    f"Тонкий стакан: {col.thin_floor_count} лот{'и' if col.thin_floor_count > 1 else ''} "
                    f"до {target_jump} TON (+{col.thin_floor_gap_percent:.0f}%) — краще не демпінгувати!"
                )

            listed_price = round(float(row["listed_price"]), 2)
            buy_price = round(float(row["buy_price"]), 2)
            min_guard = round(float(row["min_price_guard"]), 2)
            step = round(float(row["undercut_step"]), 2)

            suggested_price = round(max(min_guard, competitor_price - step), 2)
            hit_min_guard = (
                row["status"] == "listed"
                and competitor_price < listed_price - 0.009
                and suggested_price >= listed_price - 0.009
            )
            is_undercut = (
                row["status"] == "listed"
                and suggested_price < listed_price - 0.009
                and (competitor_price < listed_price - 0.009 or bool(row["is_undercut_by_competitor"]))
            )

            mark_price = listed_price if row["status"] == "sold" else max(current_floor, listed_price * 0.96)
            pnl_ton = round(mark_price * 0.95 - buy_price, 2)
            pnl_percent = round((pnl_ton / max(buy_price, 0.01)) * 100.0, 1)

            total_invested += buy_price
            current_value += mark_price
            if row["status"] == "listed":
                active_listings += 1
                if row["auto_undercut_enabled"]:
                    undercut_active_count += 1

            enriched_items.append(
                {
                    "id": row["id"],
                    "tg_id": row["tg_id"],
                    "collection_name": row["collection_name"],
                    "short_name": row["short_name"],
                    "number": row["number"],
                    "photo_url": row["photo_url"],
                    "buy_price": buy_price,
                    "listed_price": listed_price,
                    "market": row["market"],
                    "current_floor": current_floor,
                    "competitor_price": competitor_price,
                    "fair_value": fair_value,
                    "best_sell_market": best_sell_market,
                    "best_sell_price": best_sell_price,
                    "auto_undercut_enabled": bool(row["auto_undercut_enabled"]),
                    "undercut_mode": row["undercut_mode"],
                    "min_price_guard": min_guard,
                    "undercut_step": step,
                    "thin_floor_warning": thin_warning,
                    "status": row["status"],
                    "is_undercut_by_competitor": is_undercut,
                    "hit_min_guard": hit_min_guard,
                    "suggested_price": suggested_price,
                    "pnl_ton": pnl_ton,
                    "pnl_percent": pnl_percent,
                    "last_undercut_at": row["last_undercut_at"],
                }
            )

        unrealized_pnl = round(current_value - total_invested, 2)
        unrealized_pct = round((unrealized_pnl / max(total_invested, 0.01)) * 100.0, 1) if total_invested > 0 else 0.0

        return {
            "summary": {
                "total_invested_ton": round(total_invested, 2),
                "current_value_ton": round(current_value, 2),
                "unrealized_pnl_ton": unrealized_pnl,
                "unrealized_pnl_percent": unrealized_pct,
                "active_listings": active_listings,
                "undercut_active_count": undercut_active_count,
            },
            "items": enriched_items,
        }

    async def get_enriched_item(self, item_id: int) -> dict[str, Any] | None:
        portfolio = await self.build_enriched_portfolio()
        return next((i for i in portfolio["items"] if i["id"] == item_id), None)

    async def apply_undercut(self, item_id: int) -> dict[str, Any]:
        """Apply -step TON below competitor price (strictly respecting min_price_guard)."""
        enriched = await self.get_enriched_item(item_id)
        if not enriched:
            raise ValueError("Лот у портфелі не знайдено")

        old_price = enriched["listed_price"]
        new_price = round(
            max(enriched["min_price_guard"], enriched["competitor_price"] - enriched["undercut_step"]),
            2,
        )
        hit_guard = new_price <= enriched["min_price_guard"] + 1e-6 and (
            enriched["competitor_price"] - enriched["undercut_step"] < enriched["min_price_guard"]
        )

        now = utc_now_iso()
        await db.update_portfolio_item(
            item_id,
            {
                "listed_price": new_price,
                "competitor_override": None,
                "is_undercut_by_competitor": False,
                "last_undercut_at": now,
            },
        )
        updated = await self.get_enriched_item(item_id)
        assert updated is not None

        guard_note = " (досягнуто захисний мінімум!)" if hit_guard else ""
        msg = f"Ціну {updated['collection_name']} #{updated['number']} знижено: {old_price} → {new_price} TON{guard_note}"

        alert_log = await db.add_alert_log(
            alert_type="undercut_applied",
            listing_id=str(item_id),
            title=f"Авто-перебиття: {updated['collection_name']} #{updated['number']}",
            summary=msg,
            payload=updated,
            telegram_html=f"<b>GiftKit · Ціну оновлено</b>\n{msg}",
            telegram_sent=False,
        )
        await ws_manager.broadcast("undercut_alert", {"action": "applied", "item": updated, "alert": alert_log})
        return {
            "item": updated,
            "old_price": old_price,
            "new_price": new_price,
            "hit_min_guard": hit_guard,
            "message": msg,
        }

    async def simulate_competitor_undercut(self, item_id: int, drop_ton: float = 0.1) -> dict[str, Any]:
        """Simulate a competitor listing below our price to test Auto-Undercut live."""
        enriched = await self.get_enriched_item(item_id)
        if not enriched:
            raise ValueError("Лот у портфелі не знайдено")

        sim_competitor = round(max(0.1, enriched["listed_price"] - drop_ton), 2)
        await db.update_portfolio_item(
            item_id,
            {
                "competitor_override": sim_competitor,
                "is_undercut_by_competitor": True,
                "status": "listed",
            },
        )
        refreshed = await self.get_enriched_item(item_id)
        assert refreshed is not None

        # React according to configured mode & Thin Floor Protection
        if refreshed["auto_undercut_enabled"] and refreshed["undercut_mode"] == "auto":
            if refreshed["thin_floor_warning"]:
                action = "thin_floor_hold"
                msg = (
                    f"Захист тонкого стакану зупинив демпінг для {refreshed['collection_name']} "
                    f"(конкурент {sim_competitor} TON): {refreshed['thin_floor_warning']}"
                )
                if self._send_tg_undercut:
                    await self._send_tg_undercut(refreshed)
                await ws_manager.broadcast("undercut_alert", {"action": action, "item": refreshed, "message": msg})
                return {"item": refreshed, "action_taken": action, "message": msg}
            else:
                res = await self.apply_undercut(item_id)
                return {
                    "item": res["item"],
                    "action_taken": "auto_undercut",
                    "message": f"Auto-Undercut спрацював. Конкурент: {sim_competitor} TON -> {res['message']}",
                }

        # Notify mode
        tg_sent = False
        if self._send_tg_undercut:
            try:
                tg_sent = await self._send_tg_undercut(refreshed)
            except Exception as exc:
                logger.warning(f"Undercut Telegram alert failed: {exc}")

        msg = (
            f"Конкурент перебив {refreshed['collection_name']} #{refreshed['number']} до {sim_competitor} TON. "
            f"Рекомендована ціна: {refreshed['suggested_price']} TON."
        )
        await db.add_alert_log(
            alert_type="undercut_detected",
            listing_id=str(item_id),
            title=f"Конкурент перебив {refreshed['collection_name']} #{refreshed['number']}",
            summary=msg,
            payload=refreshed,
            telegram_html=f"<b>GiftKit · Конкурент перебив ваш лот</b>\n{msg}",
            telegram_sent=tg_sent,
        )
        await ws_manager.broadcast("undercut_alert", {"action": "notify", "item": refreshed, "message": msg})
        return {"item": refreshed, "action_taken": "notify", "message": msg}

    async def check_all_once(self) -> None:
        """Background check of all active listed holdings against live market floors."""
        portfolio = await self.build_enriched_portfolio()
        for item in portfolio["items"]:
            if item["status"] != "listed" or not item["auto_undercut_enabled"]:
                continue
            if item["competitor_price"] >= item["listed_price"] - 0.009:
                continue

            dedup = f"{item['id']}:{item['competitor_price']}:{item['listed_price']}"
            if dedup in self._notified_keys:
                continue
            self._notified_keys.add(dedup)

            if item["undercut_mode"] == "auto" and not item["thin_floor_warning"]:
                if item["listed_price"] > item["min_price_guard"]:
                    await self.apply_undercut(item["id"])
                    continue

            # Notify mode or thin floor protection triggered — update UI state silently without spamming Telegram
            await db.update_portfolio_item(item["id"], {"is_undercut_by_competitor": True})
            await ws_manager.broadcast("undercut_alert", {"action": "notify", "item": item})

    async def _loop(self) -> None:
        await asyncio.sleep(10)
        while self._running:
            try:
                await self.check_all_once()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"UndercutEngine loop error: {exc}")
            await asyncio.sleep(base_settings.UNDERCUT_POLL_INTERVAL)


undercut_engine = UndercutEngine()
