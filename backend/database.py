"""Async SQLite database layer using aiosqlite."""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite
from loguru import logger

from backend.config import IS_VERCEL, SETTINGS_KEYS, base_settings, runtime_config


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _strip_emojis(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]+", "", text).strip()


class Database:
    """Async SQLite repository for TON Gift Terminal Pro."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path: Path = db_path or base_settings.resolved_db_path()
        self._conn: aiosqlite.Connection | None = None
        self._init_lock = asyncio.Lock()

    async def init(self) -> None:
        if self._conn is not None:
            return
        async with self._init_lock:
            if self._conn is not None:
                return
            self.db_path = Path("/tmp/giftkit.db") if IS_VERCEL else self.db_path
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = await aiosqlite.connect(str(self.db_path))
            self._conn.row_factory = aiosqlite.Row
            try:
                await self._conn.execute("PRAGMA journal_mode=WAL;")
            except Exception:
                await self._conn.execute("PRAGMA journal_mode=DELETE;")
            await self._conn.execute("PRAGMA foreign_keys=ON;")
            await self._create_tables()
            await self._seed_defaults()
            await self.load_settings_into_runtime()
            logger.info(f"Database initialized at {self.db_path}")

    async def ensure_initialized(self) -> None:
        if self._conn is None:
            await self.init()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database is not initialized")
        return self._conn

    async def _create_tables(self) -> None:
        await self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sniper_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                collection_short_name TEXT DEFAULT '',
                collection_name TEXT DEFAULT 'Усі колекції',
                model_filter TEXT DEFAULT '',
                backdrop_filter TEXT DEFAULT '',
                max_price REAL DEFAULT 500.0,
                min_discount_percent REAL DEFAULT 15.0,
                rare_combo_only INTEGER DEFAULT 0,
                markets_json TEXT DEFAULT '["portals","getgems","mrkt","tonnel"]',
                mode TEXT DEFAULT 'alert',
                enabled INTEGER DEFAULT 1,
                hits_count INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS portfolio_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_id TEXT NOT NULL,
                collection_name TEXT NOT NULL,
                short_name TEXT NOT NULL,
                number INTEGER DEFAULT 1,
                photo_url TEXT DEFAULT '',
                buy_price REAL NOT NULL,
                listed_price REAL NOT NULL,
                market TEXT DEFAULT 'portals',
                auto_undercut_enabled INTEGER DEFAULT 1,
                undercut_mode TEXT DEFAULT 'notify',
                min_price_guard REAL NOT NULL,
                undercut_step REAL DEFAULT 0.05,
                status TEXT DEFAULT 'listed',
                competitor_override REAL DEFAULT NULL,
                is_undercut_by_competitor INTEGER DEFAULT 0,
                last_undercut_at TEXT DEFAULT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_offers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                collection_short_name TEXT NOT NULL,
                collection_name TEXT NOT NULL,
                market TEXT DEFAULT 'portals',
                bid_price REAL NOT NULL,
                max_bid REAL NOT NULL,
                auto_outbid INTEGER DEFAULT 1,
                status TEXT DEFAULT 'active',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS alert_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_type TEXT NOT NULL,
                rule_id INTEGER DEFAULT NULL,
                rule_name TEXT DEFAULT '',
                listing_id TEXT DEFAULT '',
                title TEXT NOT NULL,
                summary TEXT DEFAULT '',
                payload_json TEXT NOT NULL,
                telegram_html TEXT DEFAULT '',
                telegram_sent INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS price_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                short_name TEXT NOT NULL,
                floor_price REAL NOT NULL,
                day_volume REAL DEFAULT 0,
                listed_count INTEGER DEFAULT 0,
                sales_24h INTEGER DEFAULT 0,
                ts INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_snapshots_short_ts
                ON price_snapshots (short_name, ts DESC);

            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS trade_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                listing_id TEXT DEFAULT '',
                short_name TEXT NOT NULL,
                price_ton REAL NOT NULL,
                dry_run INTEGER DEFAULT 1,
                created_at TEXT NOT NULL
            );
            """
        )
        await self.conn.commit()

    async def _seed_defaults(self) -> None:
        now = utc_now_iso()

        # Seed 3 starter sniper rules if empty
        async with self.conn.execute("SELECT COUNT(*) AS c FROM sniper_rules") as cur:
            row = await cur.fetchone()
        if row and row["c"] == 0:
            starter_rules = [
                (
                    "Eternal Rose — Фліп від -15%",
                    "eternalrose",
                    "Eternal Rose",
                    "",
                    "",
                    45.0,
                    15.0,
                    0,
                    json.dumps(["portals", "getgems", "mrkt", "tonnel"]),
                    "alert",
                    1,
                    0,
                    now,
                ),
                (
                    "Рідкісні комбо (Monochrome / Gold)",
                    "",
                    "Усі колекції",
                    "",
                    "",
                    120.0,
                    10.0,
                    1,
                    json.dumps(["portals", "getgems", "mrkt", "tonnel"]),
                    "alert",
                    1,
                    0,
                    now,
                ),
                (
                    "Бюджетні фліпи до 25 TON (-18%)",
                    "",
                    "Усі колекції",
                    "",
                    "",
                    25.0,
                    18.0,
                    0,
                    json.dumps(["portals", "tonnel"]),
                    "alert",
                    1,
                    0,
                    now,
                ),
            ]
            await self.conn.executemany(
                """
                INSERT INTO sniper_rules (
                    name, collection_short_name, collection_name, model_filter,
                    backdrop_filter, max_price, min_discount_percent, rare_combo_only,
                    markets_json, mode, enabled, hits_count, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                starter_rules,
            )

        # Seed 2 realistic offers if empty
        async with self.conn.execute("SELECT COUNT(*) AS c FROM user_offers") as cur:
            row = await cur.fetchone()
        if row and row["c"] == 0:
            starter_offers = [
                ("eternalrose", "Eternal Rose", "portals", 24.8, 27.5, 1, "active", now, now),
                ("plushpepe", "Plush Pepe", "getgems", 415.0, 445.0, 1, "active", now, now),
            ]
            await self.conn.executemany(
                """
                INSERT INTO user_offers (
                    collection_short_name, collection_name, market, bid_price,
                    max_bid, auto_outbid, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                starter_offers,
            )

        await self.conn.commit()

    # -------------------- SETTINGS --------------------

    async def load_settings_into_runtime(self) -> None:
        async with self.conn.execute("SELECT key, value FROM app_settings") as cur:
            rows = await cur.fetchall()
        overrides = {r["key"]: r["value"] for r in rows}
        runtime_config.apply_overrides(overrides)

    async def save_settings(self, updates: dict[str, Any]) -> None:
        now = utc_now_iso()
        filtered: dict[str, Any] = {}
        for k, v in updates.items():
            if k not in SETTINGS_KEYS or v is None:
                continue
            # Ignore masked secrets sent back unchanged from frontend
            if isinstance(v, str) and "••••" in v:
                continue
            filtered[k] = v
            val_str = "true" if v is True else ("false" if v is False else str(v))
            await self.conn.execute(
                """
                INSERT INTO app_settings (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
                """,
                (k, val_str, now),
            )
        await self.conn.commit()
        if filtered:
            runtime_config.apply_overrides(filtered)

    # -------------------- SNIPER RULES --------------------

    @staticmethod
    def _row_to_rule(row: aiosqlite.Row) -> dict[str, Any]:
        try:
            markets = json.loads(row["markets_json"] or "[]")
        except json.JSONDecodeError:
            markets = ["portals", "getgems", "mrkt", "tonnel"]
        return {
            "id": row["id"],
            "name": row["name"],
            "collection_short_name": row["collection_short_name"] or "",
            "collection_name": row["collection_name"] or "Усі колекції",
            "model_filter": row["model_filter"] or "",
            "backdrop_filter": row["backdrop_filter"] or "",
            "max_price": float(row["max_price"]),
            "min_discount_percent": float(row["min_discount_percent"]),
            "rare_combo_only": bool(row["rare_combo_only"]),
            "markets": markets,
            "mode": row["mode"] or "alert",
            "enabled": bool(row["enabled"]),
            "hits_count": int(row["hits_count"] or 0),
            "created_at": row["created_at"],
        }

    async def list_sniper_rules(self) -> list[dict[str, Any]]:
        async with self.conn.execute("SELECT * FROM sniper_rules ORDER BY id DESC") as cur:
            rows = await cur.fetchall()
        return [self._row_to_rule(r) for r in rows]

    async def get_sniper_rule(self, rule_id: int) -> dict[str, Any] | None:
        async with self.conn.execute("SELECT * FROM sniper_rules WHERE id = ?", (rule_id,)) as cur:
            row = await cur.fetchone()
        return self._row_to_rule(row) if row else None

    async def create_sniper_rule(self, data: dict[str, Any]) -> dict[str, Any]:
        now = utc_now_iso()
        markets_json = json.dumps(data.get("markets") or ["portals", "getgems", "mrkt", "tonnel"])
        cur = await self.conn.execute(
            """
            INSERT INTO sniper_rules (
                name, collection_short_name, collection_name, model_filter,
                backdrop_filter, max_price, min_discount_percent, rare_combo_only,
                markets_json, mode, enabled, hits_count, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
            """,
            (
                data["name"],
                data.get("collection_short_name", "").strip().lower(),
                data.get("collection_name") or "Усі колекції",
                data.get("model_filter", "").strip(),
                data.get("backdrop_filter", "").strip(),
                float(data.get("max_price", 500.0)),
                float(data.get("min_discount_percent", 15.0)),
                1 if data.get("rare_combo_only") else 0,
                markets_json,
                data.get("mode", "alert"),
                1 if data.get("enabled", True) else 0,
                now,
            ),
        )
        await self.conn.commit()
        created = await self.get_sniper_rule(cur.lastrowid)
        assert created is not None
        return created

    async def update_sniper_rule(self, rule_id: int, updates: dict[str, Any]) -> dict[str, Any] | None:
        existing = await self.get_sniper_rule(rule_id)
        if not existing:
            return None
        fields: list[str] = []
        values: list[Any] = []
        mapping = {
            "name": "name",
            "collection_short_name": "collection_short_name",
            "collection_name": "collection_name",
            "model_filter": "model_filter",
            "backdrop_filter": "backdrop_filter",
            "max_price": "max_price",
            "min_discount_percent": "min_discount_percent",
            "rare_combo_only": "rare_combo_only",
            "mode": "mode",
            "enabled": "enabled",
        }
        for key, col in mapping.items():
            if key in updates and updates[key] is not None:
                val = updates[key]
                if key in {"rare_combo_only", "enabled"}:
                    val = 1 if val else 0
                elif key == "collection_short_name":
                    val = str(val).strip().lower()
                fields.append(f"{col} = ?")
                values.append(val)
        if "markets" in updates and updates["markets"] is not None:
            fields.append("markets_json = ?")
            values.append(json.dumps(updates["markets"]))
        if fields:
            values.append(rule_id)
            await self.conn.execute(
                f"UPDATE sniper_rules SET {', '.join(fields)} WHERE id = ?",
                values,
            )
            await self.conn.commit()
        return await self.get_sniper_rule(rule_id)

    async def increment_rule_hits(self, rule_id: int) -> None:
        await self.conn.execute(
            "UPDATE sniper_rules SET hits_count = hits_count + 1 WHERE id = ?",
            (rule_id,),
        )
        await self.conn.commit()

    async def delete_sniper_rule(self, rule_id: int) -> bool:
        cur = await self.conn.execute("DELETE FROM sniper_rules WHERE id = ?", (rule_id,))
        await self.conn.commit()
        return cur.rowcount > 0

    # -------------------- PORTFOLIO --------------------

    @staticmethod
    def _row_to_portfolio(row: aiosqlite.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "tg_id": row["tg_id"],
            "collection_name": row["collection_name"],
            "short_name": row["short_name"],
            "number": int(row["number"] or 1),
            "photo_url": row["photo_url"] or f"https://nft.fragment.com/collection/{row['short_name']}.webp",
            "buy_price": float(row["buy_price"]),
            "listed_price": float(row["listed_price"]),
            "market": row["market"] or "portals",
            "auto_undercut_enabled": bool(row["auto_undercut_enabled"]),
            "undercut_mode": row["undercut_mode"] or "notify",
            "min_price_guard": float(row["min_price_guard"]),
            "undercut_step": float(row["undercut_step"] or 0.05),
            "status": row["status"] or "listed",
            "competitor_override": float(row["competitor_override"]) if row["competitor_override"] is not None else None,
            "is_undercut_by_competitor": bool(row["is_undercut_by_competitor"]),
            "last_undercut_at": row["last_undercut_at"],
            "created_at": row["created_at"],
        }

    async def list_portfolio_items(self) -> list[dict[str, Any]]:
        async with self.conn.execute("SELECT * FROM portfolio_items ORDER BY id DESC") as cur:
            rows = await cur.fetchall()
        return [self._row_to_portfolio(r) for r in rows]

    async def get_portfolio_item(self, item_id: int) -> dict[str, Any] | None:
        async with self.conn.execute("SELECT * FROM portfolio_items WHERE id = ?", (item_id,)) as cur:
            row = await cur.fetchone()
        return self._row_to_portfolio(row) if row else None

    async def create_portfolio_item(self, data: dict[str, Any]) -> dict[str, Any]:
        now = utc_now_iso()
        short_name = str(data["short_name"]).strip().lower().replace(" ", "")
        number = int(data.get("number") or 1)
        tg_id = data.get("tg_id") or f"{data['collection_name'].replace(' ', '')}-{number}"
        buy_price = round(float(data["buy_price"]), 2)
        listed_price = round(float(data.get("listed_price") or round(buy_price * 1.18, 2)), 2)
        min_guard = round(float(data.get("min_price_guard") or round(buy_price * 1.06, 2)), 2)
        photo_url = data.get("photo_url") or f"https://nft.fragment.com/collection/{short_name}.webp"
        cur = await self.conn.execute(
            """
            INSERT INTO portfolio_items (
                tg_id, collection_name, short_name, number, photo_url,
                buy_price, listed_price, market, auto_undercut_enabled,
                undercut_mode, min_price_guard, undercut_step, status,
                competitor_override, is_undercut_by_competitor, last_undercut_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 0, NULL, ?)
            """,
            (
                tg_id,
                data["collection_name"],
                short_name,
                number,
                photo_url,
                buy_price,
                listed_price,
                data.get("market", "portals"),
                1 if data.get("auto_undercut_enabled", True) else 0,
                data.get("undercut_mode", "notify"),
                min_guard,
                float(data.get("undercut_step", 0.05)),
                data.get("status", "listed"),
                now,
            ),
        )
        await self.conn.commit()
        item = await self.get_portfolio_item(cur.lastrowid)
        assert item is not None
        return item

    async def update_portfolio_item(self, item_id: int, updates: dict[str, Any]) -> dict[str, Any] | None:
        existing = await self.get_portfolio_item(item_id)
        if not existing:
            return None
        allowed = {
            "listed_price",
            "market",
            "auto_undercut_enabled",
            "undercut_mode",
            "min_price_guard",
            "undercut_step",
            "status",
            "competitor_override",
            "is_undercut_by_competitor",
            "last_undercut_at",
        }
        fields: list[str] = []
        values: list[Any] = []
        for k, v in updates.items():
            if k not in allowed:
                continue
            if k in {"auto_undercut_enabled", "is_undercut_by_competitor"}:
                v = 1 if v else 0
            fields.append(f"{k} = ?")
            values.append(v)
        if fields:
            values.append(item_id)
            await self.conn.execute(
                f"UPDATE portfolio_items SET {', '.join(fields)} WHERE id = ?",
                values,
            )
            await self.conn.commit()
        return await self.get_portfolio_item(item_id)

    async def delete_portfolio_item(self, item_id: int) -> bool:
        cur = await self.conn.execute("DELETE FROM portfolio_items WHERE id = ?", (item_id,))
        await self.conn.commit()
        return cur.rowcount > 0

    # -------------------- USER OFFERS --------------------

    @staticmethod
    def _row_to_offer(row: aiosqlite.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "collection_short_name": row["collection_short_name"],
            "collection_name": row["collection_name"],
            "market": row["market"],
            "bid_price": float(row["bid_price"]),
            "max_bid": float(row["max_bid"]),
            "auto_outbid": bool(row["auto_outbid"]),
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    async def list_offers(self) -> list[dict[str, Any]]:
        async with self.conn.execute("SELECT * FROM user_offers ORDER BY id DESC") as cur:
            rows = await cur.fetchall()
        return [self._row_to_offer(r) for r in rows]

    async def get_offer(self, offer_id: int) -> dict[str, Any] | None:
        async with self.conn.execute("SELECT * FROM user_offers WHERE id = ?", (offer_id,)) as cur:
            row = await cur.fetchone()
        return self._row_to_offer(row) if row else None

    async def create_offer(self, data: dict[str, Any]) -> dict[str, Any]:
        now = utc_now_iso()
        cur = await self.conn.execute(
            """
            INSERT INTO user_offers (
                collection_short_name, collection_name, market, bid_price,
                max_bid, auto_outbid, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?)
            """,
            (
                str(data["collection_short_name"]).strip().lower(),
                data["collection_name"],
                data.get("market", "portals"),
                round(float(data["bid_price"]), 2),
                round(float(data["max_bid"]), 2),
                1 if data.get("auto_outbid", True) else 0,
                now,
                now,
            ),
        )
        await self.conn.commit()
        offer = await self.get_offer(cur.lastrowid)
        assert offer is not None
        return offer

    async def bump_offer(self, offer_id: int, step: float = 0.1) -> dict[str, Any] | None:
        offer = await self.get_offer(offer_id)
        if not offer:
            return None
        new_bid = round(min(offer["max_bid"], offer["bid_price"] + step), 2)
        now = utc_now_iso()
        await self.conn.execute(
            "UPDATE user_offers SET bid_price = ?, updated_at = ? WHERE id = ?",
            (new_bid, now, offer_id),
        )
        await self.conn.commit()
        return await self.get_offer(offer_id)

    async def delete_offer(self, offer_id: int) -> bool:
        cur = await self.conn.execute("DELETE FROM user_offers WHERE id = ?", (offer_id,))
        await self.conn.commit()
        return cur.rowcount > 0

    # -------------------- ALERT LOGS --------------------

    async def add_alert_log(
        self,
        *,
        alert_type: str,
        title: str,
        summary: str,
        payload: dict[str, Any],
        telegram_html: str = "",
        telegram_sent: bool = False,
        rule_id: int | None = None,
        rule_name: str = "",
        listing_id: str = "",
    ) -> dict[str, Any]:
        now = utc_now_iso()
        cur = await self.conn.execute(
            """
            INSERT INTO alert_logs (
                alert_type, rule_id, rule_name, listing_id, title, summary,
                payload_json, telegram_html, telegram_sent, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                alert_type,
                rule_id,
                rule_name,
                listing_id,
                title,
                summary,
                json.dumps(payload, ensure_ascii=False),
                telegram_html,
                1 if telegram_sent else 0,
                now,
            ),
        )
        await self.conn.commit()
        is_listing = isinstance(payload, dict) and "collection_name" in payload and "fair_value" in payload
        return {
            "id": cur.lastrowid,
            "alert_type": alert_type,
            "rule_id": rule_id,
            "rule_name": rule_name,
            "listing_id": listing_id,
            "title": title,
            "summary": summary,
            "message": summary,
            "payload": payload,
            "listing": payload if is_listing else None,
            "telegram_html": telegram_html,
            "html_preview": telegram_html,
            "telegram_sent": telegram_sent,
            "created_at": now,
        }

    async def list_alert_logs(self, limit: int = 40) -> list[dict[str, Any]]:
        async with self.conn.execute(
            "SELECT * FROM alert_logs ORDER BY id DESC LIMIT ?", (limit,)
        ) as cur:
            rows = await cur.fetchall()
        results: list[dict[str, Any]] = []
        for r in rows:
            try:
                payload = json.loads(r["payload_json"] or "{}")
            except json.JSONDecodeError:
                payload = {}
            is_listing = isinstance(payload, dict) and "collection_name" in payload and "fair_value" in payload
            results.append(
                {
                    "id": r["id"],
                    "alert_type": r["alert_type"],
                    "rule_id": r["rule_id"],
                    "rule_name": r["rule_name"],
                    "listing_id": r["listing_id"],
                    "title": _strip_emojis(r["title"] or ""),
                    "summary": _strip_emojis(r["summary"] or ""),
                    "message": _strip_emojis(r["summary"] or ""),
                    "payload": payload,
                    "listing": payload if is_listing else None,
                    "telegram_html": r["telegram_html"] or "",
                    "html_preview": r["telegram_html"] or "",
                    "telegram_sent": bool(r["telegram_sent"]),
                    "created_at": r["created_at"],
                }
            )
        return results

    # -------------------- PRICE SNAPSHOTS --------------------

    async def insert_price_snapshots(self, snapshots: list[tuple[str, float, float, int, int, int]]) -> None:
        if not snapshots:
            return
        await self.conn.executemany(
            """
            INSERT INTO price_snapshots (short_name, floor_price, day_volume, listed_count, sales_24h, ts)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            snapshots,
        )
        await self.conn.commit()

    async def get_price_snapshots(self, short_name: str, since_ts: int) -> list[dict[str, Any]]:
        async with self.conn.execute(
            """
            SELECT short_name, floor_price, day_volume, listed_count, sales_24h, ts
            FROM price_snapshots
            WHERE short_name = ? AND ts >= ?
            ORDER BY ts ASC
            """,
            (short_name.lower(), since_ts),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    # -------------------- TRADE LEDGER (DAILY RISK LIMIT) --------------------

    async def record_trade(self, listing_id: str, short_name: str, price_ton: float, dry_run: bool) -> None:
        await self.conn.execute(
            """
            INSERT INTO trade_ledger (listing_id, short_name, price_ton, dry_run, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (listing_id, short_name, float(price_ton), 1 if dry_run else 0, utc_now_iso()),
        )
        await self.conn.commit()

    async def get_today_spent_ton(self) -> float:
        today_prefix = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        async with self.conn.execute(
            "SELECT COALESCE(SUM(price_ton), 0) AS total FROM trade_ledger WHERE created_at LIKE ?",
            (f"{today_prefix}%",),
        ) as cur:
            row = await cur.fetchone()
        return float(row["total"]) if row else 0.0


db = Database()
