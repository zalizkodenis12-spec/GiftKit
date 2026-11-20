"""Async SQLite database layer using aiosqlite with multi-user isolation & signed state sync."""

from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite
from loguru import logger

from backend.config import IS_VERCEL, SETTINGS_KEYS, base_settings, runtime_config
from backend.services import auth_service
from backend.services.auth_service import DEFAULT_ADMIN_USER_ID


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _strip_emojis(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]+", "", text).strip()


def _next_state_version(current_version: int = 1) -> int:
    return max(int(time.time() * 1000), int(current_version or 1) + 1)


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
            CREATE TABLE IF NOT EXISTS users (
                tg_user_id TEXT PRIMARY KEY,
                username TEXT DEFAULT '',
                first_name TEXT DEFAULT '',
                last_name TEXT DEFAULT '',
                photo_url TEXT DEFAULT '',
                state_version INTEGER DEFAULT 1,
                deleted_rule_ids_json TEXT DEFAULT '[]',
                deleted_offer_ids_json TEXT DEFAULT '[]',
                deleted_portfolio_ids_json TEXT DEFAULT '[]',
                created_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sniper_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL DEFAULT 'owner',
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
                user_id TEXT NOT NULL DEFAULT 'owner',
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
                user_id TEXT NOT NULL DEFAULT 'owner',
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
                user_id TEXT NOT NULL DEFAULT 'owner',
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
                user_id TEXT NOT NULL DEFAULT 'owner',
                listing_id TEXT DEFAULT '',
                short_name TEXT NOT NULL,
                price_ton REAL NOT NULL,
                dry_run INTEGER DEFAULT 1,
                created_at TEXT NOT NULL
            );
            """
        )

        # Safely migrate existing tables if user_id column is missing
        scoped_tables = (
            "sniper_rules",
            "portfolio_items",
            "user_offers",
            "alert_logs",
            "trade_ledger",
        )
        for tbl in scoped_tables:
            async with self.conn.execute(f"PRAGMA table_info({tbl})") as cur:
                cols = [r["name"] for r in await cur.fetchall()]
            if "user_id" not in cols:
                await self.conn.execute(
                    f"ALTER TABLE {tbl} ADD COLUMN user_id TEXT NOT NULL DEFAULT 'owner'"
                )

        await self.conn.commit()

    async def _seed_defaults(self) -> None:
        """Clean up legacy fake seeded offers — no fake rules, offers, or portfolio items are seeded."""
        await self.conn.execute(
            """
            DELETE FROM user_offers
            WHERE collection_short_name IN ('eternalrose', 'plushpepe')
              AND bid_price IN (24.8, 415.0)
            """
        )
        await self.conn.commit()

    # -------------------- USERS & STATE VERSIONING --------------------

    @staticmethod
    def _parse_int_list(raw_json: str | None) -> list[int]:
        if not raw_json:
            return []
        try:
            items = json.loads(raw_json)
            if isinstance(items, list):
                return sorted({int(x) for x in items})
        except Exception:
            pass
        return []

    @classmethod
    def _row_to_user(cls, row: aiosqlite.Row) -> dict[str, Any]:
        username = row["username"] or ""
        photo_url = row["photo_url"] or ""
        if not photo_url and username:
            photo_url = f"https://t.me/i/userpic/320/{username}.jpg"
        return {
            "tg_user_id": str(row["tg_user_id"]),
            "username": username,
            "first_name": row["first_name"] or "",
            "last_name": row["last_name"] or "",
            "photo_url": photo_url,
            "state_version": int(row["state_version"] or 1),
            "deleted_rule_ids": cls._parse_int_list(row["deleted_rule_ids_json"]),
            "deleted_offer_ids": cls._parse_int_list(row["deleted_offer_ids_json"]),
            "deleted_portfolio_ids": cls._parse_int_list(row["deleted_portfolio_ids_json"]),
            "created_at": row["created_at"],
            "last_seen_at": row["last_seen_at"],
        }

    async def get_user(self, tg_user_id: str) -> dict[str, Any] | None:
        uid = str(tg_user_id or DEFAULT_ADMIN_USER_ID).strip()
        async with self.conn.execute("SELECT * FROM users WHERE tg_user_id = ?", (uid,)) as cur:
            row = await cur.fetchone()
        return self._row_to_user(row) if row else None

    async def upsert_user(self, user_dict: dict[str, Any]) -> dict[str, Any]:
        norm = auth_service.normalize_user_dict(user_dict)
        uid = norm["tg_user_id"] or DEFAULT_ADMIN_USER_ID
        now = utc_now_iso()
        existing = await self.get_user(uid)
        if not existing:
            await self.conn.execute(
                """
                INSERT INTO users (
                    tg_user_id, username, first_name, last_name, photo_url,
                    state_version, deleted_rule_ids_json, deleted_offer_ids_json,
                    deleted_portfolio_ids_json, created_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, 1, '[]', '[]', '[]', ?, ?)
                """,
                (
                    uid,
                    norm["username"],
                    norm["first_name"],
                    norm["last_name"],
                    norm["photo_url"],
                    now,
                    now,
                ),
            )
        else:
            username = norm["username"] or existing["username"]
            first_name = norm["first_name"] or existing["first_name"]
            last_name = norm["last_name"] or existing["last_name"]
            photo_url = norm["photo_url"] or existing["photo_url"]
            await self.conn.execute(
                """
                UPDATE users
                SET username = ?, first_name = ?, last_name = ?, photo_url = ?, last_seen_at = ?
                WHERE tg_user_id = ?
                """,
                (username, first_name, last_name, photo_url, now, uid),
            )
        await self.conn.commit()
        user = await self.get_user(uid)
        assert user is not None
        return user

    async def update_user_profile(
        self,
        tg_user_id: str,
        updates: dict[str, Any],
    ) -> dict[str, Any]:
        """Update user's editable profile fields (first_name, last_name, username, photo_url) and bump state_version."""
        user = await self._ensure_user_row(tg_user_id)
        uid = user["tg_user_id"]
        username = (
            str(updates["username"]).strip().lstrip("@")
            if "username" in updates and updates["username"] is not None
            else user["username"]
        )
        first_name = (
            str(updates["first_name"]).strip()
            if "first_name" in updates and updates["first_name"] is not None
            else user["first_name"]
        )
        last_name = (
            str(updates["last_name"]).strip()
            if "last_name" in updates and updates["last_name"] is not None
            else user["last_name"]
        )
        photo_url = (
            str(updates["photo_url"]).strip()
            if "photo_url" in updates and updates["photo_url"] is not None
            else user["photo_url"]
        )
        if not photo_url and username:
            photo_url = f"https://t.me/i/userpic/320/{username}.jpg"

        new_version = _next_state_version(user["state_version"])
        await self.conn.execute(
            """
            UPDATE users
            SET username = ?,
                first_name = ?,
                last_name = ?,
                photo_url = ?,
                state_version = ?,
                last_seen_at = ?
            WHERE tg_user_id = ?
            """,
            (username, first_name, last_name, photo_url, new_version, utc_now_iso(), uid),
        )
        await self.conn.commit()
        updated = await self.get_user(uid)
        assert updated is not None
        return updated

    async def _ensure_user_row(self, user_id: str) -> dict[str, Any]:
        uid = str(user_id or DEFAULT_ADMIN_USER_ID).strip()
        user = await self.get_user(uid)
        if user is None:
            user = await self.upsert_user({"tg_user_id": uid})
        return user

    async def _bump_user_state(
        self,
        user_id: str,
        *,
        deleted_rule_id: int | None = None,
        deleted_offer_id: int | None = None,
        deleted_portfolio_id: int | None = None,
        restored_rule_id: int | None = None,
        restored_offer_id: int | None = None,
        restored_portfolio_id: int | None = None,
    ) -> int:
        user = await self._ensure_user_row(user_id)
        uid = user["tg_user_id"]
        new_version = _next_state_version(user["state_version"])

        del_rules = set(user["deleted_rule_ids"])
        del_offers = set(user["deleted_offer_ids"])
        del_portfolio = set(user["deleted_portfolio_ids"])

        if deleted_rule_id is not None:
            del_rules.add(int(deleted_rule_id))
        if restored_rule_id is not None:
            del_rules.discard(int(restored_rule_id))

        if deleted_offer_id is not None:
            del_offers.add(int(deleted_offer_id))
        if restored_offer_id is not None:
            del_offers.discard(int(restored_offer_id))

        if deleted_portfolio_id is not None:
            del_portfolio.add(int(deleted_portfolio_id))
        if restored_portfolio_id is not None:
            del_portfolio.discard(int(restored_portfolio_id))

        await self.conn.execute(
            """
            UPDATE users
            SET state_version = ?,
                deleted_rule_ids_json = ?,
                deleted_offer_ids_json = ?,
                deleted_portfolio_ids_json = ?,
                last_seen_at = ?
            WHERE tg_user_id = ?
            """,
            (
                new_version,
                json.dumps(sorted(del_rules)),
                json.dumps(sorted(del_offers)),
                json.dumps(sorted(del_portfolio)),
                utc_now_iso(),
                uid,
            ),
        )
        await self.conn.commit()
        return new_version

    async def export_user_state(self, user_id: str = DEFAULT_ADMIN_USER_ID) -> dict[str, Any]:
        """Export HMAC-signed state snapshot for cross-device & Vercel cold-start restoration."""
        uid = str(user_id or DEFAULT_ADMIN_USER_ID).strip()
        user = await self._ensure_user_row(uid)
        rules = await self.list_sniper_rules(user_id=uid)
        offers = await self.list_offers(user_id=uid)
        portfolio = await self.list_portfolio_items(user_id=uid)
        payload = {
            "state_version": user["state_version"],
            "user_profile": {
                "tg_user_id": user["tg_user_id"],
                "username": user["username"],
                "first_name": user["first_name"],
                "last_name": user["last_name"],
                "photo_url": user["photo_url"],
            },
            "rules": rules,
            "offers": offers,
            "portfolio": portfolio,
            "deleted_rule_ids": user["deleted_rule_ids"],
            "deleted_offer_ids": user["deleted_offer_ids"],
            "deleted_portfolio_ids": user["deleted_portfolio_ids"],
        }
        return auth_service.sign_state_envelope(uid, payload)

    async def import_user_state(self, user_id: str, envelope_data: dict[str, Any]) -> bool:
        """Verify and restore user's rules, offers, portfolio & tombstones from a signed envelope."""
        uid = str(user_id or DEFAULT_ADMIN_USER_ID).strip()
        verified = auth_service.verify_state_envelope(uid, envelope_data)
        if not verified:
            return False

        local_user = await self.get_user(uid)
        incoming_version = int(verified.get("state_version") or 1)
        local_version = int(local_user["state_version"]) if local_user else 0

        if local_user is not None and incoming_version <= local_version:
            return False

        user = await self._ensure_user_row(uid)
        del_rules = sorted(set(user["deleted_rule_ids"]) | set(verified["deleted_rule_ids"]))
        del_offers = sorted(set(user["deleted_offer_ids"]) | set(verified["deleted_offer_ids"]))
        del_portfolio = sorted(set(user["deleted_portfolio_ids"]) | set(verified["deleted_portfolio_ids"]))

        del_rules_set = set(del_rules)
        del_offers_set = set(del_offers)
        del_portfolio_set = set(del_portfolio)

        now = utc_now_iso()

        # 1. Reconcile sniper_rules for this user
        await self.conn.execute("DELETE FROM sniper_rules WHERE user_id = ?", (uid,))
        for r in verified["rules"]:
            if not isinstance(r, dict) or not r.get("name"):
                continue
            rid = int(r["id"]) if r.get("id") is not None else None
            if rid is not None and rid in del_rules_set:
                continue
            markets_json = json.dumps(r.get("markets") or ["portals", "getgems", "mrkt", "tonnel"])
            can_use_id = False
            if rid is not None:
                async with self.conn.execute("SELECT id FROM sniper_rules WHERE id = ?", (rid,)) as cur:
                    can_use_id = (await cur.fetchone()) is None
            if can_use_id and rid is not None:
                await self.conn.execute(
                    """
                    INSERT INTO sniper_rules (
                        id, user_id, name, collection_short_name, collection_name, model_filter,
                        backdrop_filter, max_price, min_discount_percent, rare_combo_only,
                        markets_json, mode, enabled, hits_count, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        rid,
                        uid,
                        str(r["name"]),
                        str(r.get("collection_short_name") or "").strip().lower(),
                        str(r.get("collection_name") or "Усі колекції"),
                        str(r.get("model_filter") or "").strip(),
                        str(r.get("backdrop_filter") or "").strip(),
                        float(r.get("max_price", 500.0)),
                        float(r.get("min_discount_percent", 15.0)),
                        1 if r.get("rare_combo_only") else 0,
                        markets_json,
                        str(r.get("mode") or "alert"),
                        1 if r.get("enabled", True) else 0,
                        int(r.get("hits_count") or 0),
                        str(r.get("created_at") or now),
                    ),
                )
            else:
                await self.conn.execute(
                    """
                    INSERT INTO sniper_rules (
                        user_id, name, collection_short_name, collection_name, model_filter,
                        backdrop_filter, max_price, min_discount_percent, rare_combo_only,
                        markets_json, mode, enabled, hits_count, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        uid,
                        str(r["name"]),
                        str(r.get("collection_short_name") or "").strip().lower(),
                        str(r.get("collection_name") or "Усі колекції"),
                        str(r.get("model_filter") or "").strip(),
                        str(r.get("backdrop_filter") or "").strip(),
                        float(r.get("max_price", 500.0)),
                        float(r.get("min_discount_percent", 15.0)),
                        1 if r.get("rare_combo_only") else 0,
                        markets_json,
                        str(r.get("mode") or "alert"),
                        1 if r.get("enabled", True) else 0,
                        int(r.get("hits_count") or 0),
                        str(r.get("created_at") or now),
                    ),
                )

        # 2. Reconcile user_offers for this user
        await self.conn.execute("DELETE FROM user_offers WHERE user_id = ?", (uid,))
        for o in verified["offers"]:
            if not isinstance(o, dict) or not o.get("collection_short_name"):
                continue
            oid = int(o["id"]) if o.get("id") is not None else None
            if oid is not None and oid in del_offers_set:
                continue
            can_use_id = False
            if oid is not None:
                async with self.conn.execute("SELECT id FROM user_offers WHERE id = ?", (oid,)) as cur:
                    can_use_id = (await cur.fetchone()) is None
            if can_use_id and oid is not None:
                await self.conn.execute(
                    """
                    INSERT INTO user_offers (
                        id, user_id, collection_short_name, collection_name, market,
                        bid_price, max_bid, auto_outbid, status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        oid,
                        uid,
                        str(o["collection_short_name"]).strip().lower(),
                        str(o.get("collection_name") or o["collection_short_name"]),
                        str(o.get("market") or "portals"),
                        round(float(o.get("bid_price", 1.0)), 2),
                        round(float(o.get("max_bid", o.get("bid_price", 1.0))), 2),
                        1 if o.get("auto_outbid", True) else 0,
                        str(o.get("status") or "active"),
                        str(o.get("created_at") or now),
                        str(o.get("updated_at") or now),
                    ),
                )
            else:
                await self.conn.execute(
                    """
                    INSERT INTO user_offers (
                        user_id, collection_short_name, collection_name, market,
                        bid_price, max_bid, auto_outbid, status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        uid,
                        str(o["collection_short_name"]).strip().lower(),
                        str(o.get("collection_name") or o["collection_short_name"]),
                        str(o.get("market") or "portals"),
                        round(float(o.get("bid_price", 1.0)), 2),
                        round(float(o.get("max_bid", o.get("bid_price", 1.0))), 2),
                        1 if o.get("auto_outbid", True) else 0,
                        str(o.get("status") or "active"),
                        str(o.get("created_at") or now),
                        str(o.get("updated_at") or now),
                    ),
                )

        # 3. Reconcile portfolio_items for this user
        await self.conn.execute("DELETE FROM portfolio_items WHERE user_id = ?", (uid,))
        for p in verified["portfolio"]:
            if not isinstance(p, dict) or not p.get("short_name"):
                continue
            pid = int(p["id"]) if p.get("id") is not None else None
            if pid is not None and pid in del_portfolio_set:
                continue
            short_name = str(p["short_name"]).strip().lower().replace(" ", "")
            number = int(p.get("number") or 1)
            col_name = str(p.get("collection_name") or short_name.title())
            tg_id = str(p.get("tg_id") or f"{col_name.replace(' ', '')}-{number}")
            buy_price = round(float(p.get("buy_price", 1.0)), 2)
            listed_price = round(float(p.get("listed_price") or round(buy_price * 1.18, 2)), 2)
            min_guard = round(float(p.get("min_price_guard") or round(buy_price * 1.06, 2)), 2)
            photo_url = str(p.get("photo_url") or f"https://nft.fragment.com/collection/{short_name}.webp")
            comp_override = float(p["competitor_override"]) if p.get("competitor_override") is not None else None

            can_use_id = False
            if pid is not None:
                async with self.conn.execute("SELECT id FROM portfolio_items WHERE id = ?", (pid,)) as cur:
                    can_use_id = (await cur.fetchone()) is None

            if can_use_id and pid is not None:
                await self.conn.execute(
                    """
                    INSERT INTO portfolio_items (
                        id, user_id, tg_id, collection_name, short_name, number, photo_url,
                        buy_price, listed_price, market, auto_undercut_enabled,
                        undercut_mode, min_price_guard, undercut_step, status,
                        competitor_override, is_undercut_by_competitor, last_undercut_at, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        pid,
                        uid,
                        tg_id,
                        col_name,
                        short_name,
                        number,
                        photo_url,
                        buy_price,
                        listed_price,
                        str(p.get("market") or "portals"),
                        1 if p.get("auto_undercut_enabled", True) else 0,
                        str(p.get("undercut_mode") or "notify"),
                        min_guard,
                        float(p.get("undercut_step", 0.05)),
                        str(p.get("status") or "listed"),
                        comp_override,
                        1 if p.get("is_undercut_by_competitor") else 0,
                        p.get("last_undercut_at"),
                        str(p.get("created_at") or now),
                    ),
                )
            else:
                await self.conn.execute(
                    """
                    INSERT INTO portfolio_items (
                        user_id, tg_id, collection_name, short_name, number, photo_url,
                        buy_price, listed_price, market, auto_undercut_enabled,
                        undercut_mode, min_price_guard, undercut_step, status,
                        competitor_override, is_undercut_by_competitor, last_undercut_at, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        uid,
                        tg_id,
                        col_name,
                        short_name,
                        number,
                        photo_url,
                        buy_price,
                        listed_price,
                        str(p.get("market") or "portals"),
                        1 if p.get("auto_undercut_enabled", True) else 0,
                        str(p.get("undercut_mode") or "notify"),
                        min_guard,
                        float(p.get("undercut_step", 0.05)),
                        str(p.get("status") or "listed"),
                        comp_override,
                        1 if p.get("is_undercut_by_competitor") else 0,
                        p.get("last_undercut_at"),
                        str(p.get("created_at") or now),
                    ),
                )

        # 4. Update user's state_version, tombstones & user_profile
        prof = verified.get("user_profile") if isinstance(verified.get("user_profile"), dict) else {}
        new_username = str(prof.get("username") or user["username"] or "").strip().lstrip("@")
        new_first = str(prof.get("first_name") or user["first_name"] or "").strip()
        new_last = str(prof.get("last_name") or user["last_name"] or "").strip()
        new_photo = str(prof.get("photo_url") or user["photo_url"] or "").strip()

        await self.conn.execute(
            """
            UPDATE users
            SET username = ?,
                first_name = ?,
                last_name = ?,
                photo_url = ?,
                state_version = ?,
                deleted_rule_ids_json = ?,
                deleted_offer_ids_json = ?,
                deleted_portfolio_ids_json = ?,
                last_seen_at = ?
            WHERE tg_user_id = ?
            """,
            (
                new_username,
                new_first,
                new_last,
                new_photo,
                incoming_version,
                json.dumps(del_rules),
                json.dumps(del_offers),
                json.dumps(del_portfolio),
                now,
                uid,
            ),
        )
        await self.conn.commit()
        return True

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
            "user_id": str(row["user_id"] if "user_id" in row.keys() else DEFAULT_ADMIN_USER_ID),
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

    async def list_sniper_rules(self, user_id: str = DEFAULT_ADMIN_USER_ID) -> list[dict[str, Any]]:
        uid = str(user_id or DEFAULT_ADMIN_USER_ID).strip()
        async with self.conn.execute(
            "SELECT * FROM sniper_rules WHERE user_id = ? ORDER BY id DESC",
            (uid,),
        ) as cur:
            rows = await cur.fetchall()
        return [self._row_to_rule(r) for r in rows]

    async def get_sniper_rule(self, rule_id: int, user_id: str | None = None) -> dict[str, Any] | None:
        if user_id is not None:
            async with self.conn.execute(
                "SELECT * FROM sniper_rules WHERE id = ? AND user_id = ?",
                (rule_id, str(user_id).strip()),
            ) as cur:
                row = await cur.fetchone()
        else:
            async with self.conn.execute("SELECT * FROM sniper_rules WHERE id = ?", (rule_id,)) as cur:
                row = await cur.fetchone()
        return self._row_to_rule(row) if row else None

    async def create_sniper_rule(
        self,
        data: dict[str, Any],
        user_id: str = DEFAULT_ADMIN_USER_ID,
    ) -> dict[str, Any]:
        uid = str(user_id or DEFAULT_ADMIN_USER_ID).strip()
        now = utc_now_iso()
        markets_json = json.dumps(data.get("markets") or ["portals", "getgems", "mrkt", "tonnel"])
        cur = await self.conn.execute(
            """
            INSERT INTO sniper_rules (
                user_id, name, collection_short_name, collection_name, model_filter,
                backdrop_filter, max_price, min_discount_percent, rare_combo_only,
                markets_json, mode, enabled, hits_count, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
            """,
            (
                uid,
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
        created = await self.get_sniper_rule(cur.lastrowid, user_id=uid)
        assert created is not None
        await self._bump_user_state(uid, restored_rule_id=created["id"])
        return created

    async def update_sniper_rule(
        self,
        rule_id: int,
        updates: dict[str, Any],
        user_id: str = DEFAULT_ADMIN_USER_ID,
    ) -> dict[str, Any] | None:
        uid = str(user_id or DEFAULT_ADMIN_USER_ID).strip()
        existing = await self.get_sniper_rule(rule_id, user_id=uid)
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
            values.extend([rule_id, uid])
            await self.conn.execute(
                f"UPDATE sniper_rules SET {', '.join(fields)} WHERE id = ? AND user_id = ?",
                values,
            )
            await self.conn.commit()
            await self._bump_user_state(uid)
        return await self.get_sniper_rule(rule_id, user_id=uid)

    async def increment_rule_hits(self, rule_id: int) -> None:
        await self.conn.execute(
            "UPDATE sniper_rules SET hits_count = hits_count + 1 WHERE id = ?",
            (rule_id,),
        )
        await self.conn.commit()

    async def delete_sniper_rule(self, rule_id: int, user_id: str = DEFAULT_ADMIN_USER_ID) -> bool:
        uid = str(user_id or DEFAULT_ADMIN_USER_ID).strip()
        cur = await self.conn.execute(
            "DELETE FROM sniper_rules WHERE id = ? AND user_id = ?",
            (rule_id, uid),
        )
        await self.conn.commit()
        deleted = cur.rowcount > 0
        await self._bump_user_state(uid, deleted_rule_id=rule_id)
        return deleted

    # -------------------- PORTFOLIO --------------------

    @staticmethod
    def _row_to_portfolio(row: aiosqlite.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "user_id": str(row["user_id"] if "user_id" in row.keys() else DEFAULT_ADMIN_USER_ID),
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

    async def list_portfolio_items(self, user_id: str = DEFAULT_ADMIN_USER_ID) -> list[dict[str, Any]]:
        uid = str(user_id or DEFAULT_ADMIN_USER_ID).strip()
        async with self.conn.execute(
            "SELECT * FROM portfolio_items WHERE user_id = ? ORDER BY id DESC",
            (uid,),
        ) as cur:
            rows = await cur.fetchall()
        return [self._row_to_portfolio(r) for r in rows]

    async def get_portfolio_item(self, item_id: int, user_id: str | None = None) -> dict[str, Any] | None:
        if user_id is not None:
            async with self.conn.execute(
                "SELECT * FROM portfolio_items WHERE id = ? AND user_id = ?",
                (item_id, str(user_id).strip()),
            ) as cur:
                row = await cur.fetchone()
        else:
            async with self.conn.execute("SELECT * FROM portfolio_items WHERE id = ?", (item_id,)) as cur:
                row = await cur.fetchone()
        return self._row_to_portfolio(row) if row else None

    async def create_portfolio_item(
        self,
        data: dict[str, Any],
        user_id: str = DEFAULT_ADMIN_USER_ID,
    ) -> dict[str, Any]:
        uid = str(user_id or data.get("user_id") or DEFAULT_ADMIN_USER_ID).strip()
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
                user_id, tg_id, collection_name, short_name, number, photo_url,
                buy_price, listed_price, market, auto_undercut_enabled,
                undercut_mode, min_price_guard, undercut_step, status,
                competitor_override, is_undercut_by_competitor, last_undercut_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 0, NULL, ?)
            """,
            (
                uid,
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
        item = await self.get_portfolio_item(cur.lastrowid, user_id=uid)
        assert item is not None
        await self._bump_user_state(uid, restored_portfolio_id=item["id"])
        return item

    async def update_portfolio_item(
        self,
        item_id: int,
        updates: dict[str, Any],
        user_id: str | None = None,
    ) -> dict[str, Any] | None:
        existing = await self.get_portfolio_item(item_id, user_id=user_id)
        if not existing:
            return None
        uid = existing["user_id"]
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
            values.extend([item_id, uid])
            await self.conn.execute(
                f"UPDATE portfolio_items SET {', '.join(fields)} WHERE id = ? AND user_id = ?",
                values,
            )
            await self.conn.commit()
            await self._bump_user_state(uid)
        return await self.get_portfolio_item(item_id, user_id=uid)

    async def delete_portfolio_item(self, item_id: int, user_id: str = DEFAULT_ADMIN_USER_ID) -> bool:
        uid = str(user_id or DEFAULT_ADMIN_USER_ID).strip()
        cur = await self.conn.execute(
            "DELETE FROM portfolio_items WHERE id = ? AND user_id = ?",
            (item_id, uid),
        )
        await self.conn.commit()
        deleted = cur.rowcount > 0
        await self._bump_user_state(uid, deleted_portfolio_id=item_id)
        return deleted

    # -------------------- USER OFFERS --------------------

    @staticmethod
    def _row_to_offer(row: aiosqlite.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "user_id": str(row["user_id"] if "user_id" in row.keys() else DEFAULT_ADMIN_USER_ID),
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

    async def list_offers(self, user_id: str = DEFAULT_ADMIN_USER_ID) -> list[dict[str, Any]]:
        uid = str(user_id or DEFAULT_ADMIN_USER_ID).strip()
        async with self.conn.execute(
            "SELECT * FROM user_offers WHERE user_id = ? ORDER BY id DESC",
            (uid,),
        ) as cur:
            rows = await cur.fetchall()
        return [self._row_to_offer(r) for r in rows]

    async def get_offer(self, offer_id: int, user_id: str | None = None) -> dict[str, Any] | None:
        if user_id is not None:
            async with self.conn.execute(
                "SELECT * FROM user_offers WHERE id = ? AND user_id = ?",
                (offer_id, str(user_id).strip()),
            ) as cur:
                row = await cur.fetchone()
        else:
            async with self.conn.execute("SELECT * FROM user_offers WHERE id = ?", (offer_id,)) as cur:
                row = await cur.fetchone()
        return self._row_to_offer(row) if row else None

    async def create_offer(
        self,
        data: dict[str, Any],
        user_id: str = DEFAULT_ADMIN_USER_ID,
    ) -> dict[str, Any]:
        uid = str(user_id or DEFAULT_ADMIN_USER_ID).strip()
        now = utc_now_iso()
        cur = await self.conn.execute(
            """
            INSERT INTO user_offers (
                user_id, collection_short_name, collection_name, market, bid_price,
                max_bid, auto_outbid, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
            """,
            (
                uid,
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
        offer = await self.get_offer(cur.lastrowid, user_id=uid)
        assert offer is not None
        await self._bump_user_state(uid, restored_offer_id=offer["id"])
        return offer

    async def bump_offer(
        self,
        offer_id: int,
        step: float = 0.1,
        user_id: str = DEFAULT_ADMIN_USER_ID,
    ) -> dict[str, Any] | None:
        uid = str(user_id or DEFAULT_ADMIN_USER_ID).strip()
        offer = await self.get_offer(offer_id, user_id=uid)
        if not offer:
            return None
        new_bid = round(min(offer["max_bid"], offer["bid_price"] + step), 2)
        now = utc_now_iso()
        await self.conn.execute(
            "UPDATE user_offers SET bid_price = ?, updated_at = ? WHERE id = ? AND user_id = ?",
            (new_bid, now, offer_id, uid),
        )
        await self.conn.commit()
        await self._bump_user_state(uid)
        return await self.get_offer(offer_id, user_id=uid)

    async def delete_offer(self, offer_id: int, user_id: str = DEFAULT_ADMIN_USER_ID) -> bool:
        uid = str(user_id or DEFAULT_ADMIN_USER_ID).strip()
        cur = await self.conn.execute(
            "DELETE FROM user_offers WHERE id = ? AND user_id = ?",
            (offer_id, uid),
        )
        await self.conn.commit()
        deleted = cur.rowcount > 0
        await self._bump_user_state(uid, deleted_offer_id=offer_id)
        return deleted

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
        user_id: str = DEFAULT_ADMIN_USER_ID,
    ) -> dict[str, Any]:
        uid = str(user_id or DEFAULT_ADMIN_USER_ID).strip()
        now = utc_now_iso()
        cur = await self.conn.execute(
            """
            INSERT INTO alert_logs (
                user_id, alert_type, rule_id, rule_name, listing_id, title, summary,
                payload_json, telegram_html, telegram_sent, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                uid,
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
            "user_id": uid,
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

    async def list_alert_logs(
        self,
        limit: int = 40,
        user_id: str = DEFAULT_ADMIN_USER_ID,
    ) -> list[dict[str, Any]]:
        uid = str(user_id or DEFAULT_ADMIN_USER_ID).strip()
        async with self.conn.execute(
            "SELECT * FROM alert_logs WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (uid, limit),
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
                    "user_id": str(r["user_id"] if "user_id" in r.keys() else uid),
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

    async def record_trade(
        self,
        listing_id: str,
        short_name: str,
        price_ton: float,
        dry_run: bool,
        user_id: str = DEFAULT_ADMIN_USER_ID,
    ) -> None:
        uid = str(user_id or DEFAULT_ADMIN_USER_ID).strip()
        await self.conn.execute(
            """
            INSERT INTO trade_ledger (user_id, listing_id, short_name, price_ton, dry_run, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (uid, listing_id, short_name, float(price_ton), 1 if dry_run else 0, utc_now_iso()),
        )
        await self.conn.commit()

    async def get_today_spent_ton(self, user_id: str = DEFAULT_ADMIN_USER_ID) -> float:
        uid = str(user_id or DEFAULT_ADMIN_USER_ID).strip()
        today_prefix = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        async with self.conn.execute(
            "SELECT COALESCE(SUM(price_ton), 0) AS total FROM trade_ledger WHERE user_id = ? AND created_at LIKE ?",
            (uid, f"{today_prefix}%"),
        ) as cur:
            row = await cur.fetchone()
        return float(row["total"]) if row else 0.0


db = Database()
