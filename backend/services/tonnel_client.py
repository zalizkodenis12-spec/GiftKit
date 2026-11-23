"""Live Tonnel Network (gifts2.tonnel.network) Marketplace Client with caching & pagination."""

from __future__ import annotations

import asyncio
import json
import re
import time
import urllib.parse
from typing import Any

import httpx
from loguru import logger

from backend.config import runtime_config
from backend.database import utc_now_iso
from backend.services.portals_client import to_float, to_int

TONNEL_API_BASE = "https://gifts2.tonnel.network/api"


class TonnelClient:
    """Async throttled client for Tonnel live floor stats & listed NFTs."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._lock = asyncio.Lock()
        self._last_req_ts: float = 0.0
        self._min_interval: float = 0.75
        self._cache: dict[str, tuple[Any, float]] = {}

        self.last_live_ok: bool = False
        self.last_error: str = ""

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=TONNEL_API_BASE,
                timeout=httpx.Timeout(9.0, connect=4.0),
                headers={
                    "Accept": "application/json, text/plain, */*",
                    "Content-Type": "application/json",
                    "Origin": "https://market.tonnel.network",
                    "Referer": "https://market.tonnel.network/",
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                    ),
                },
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def clear_cache(self) -> None:
        self._cache.clear()

    def _cache_get(self, key: str, allow_stale: bool = False) -> Any | None:
        entry = self._cache.get(key)
        if not entry:
            return None
        val, exp = entry
        if allow_stale or time.monotonic() < exp:
            return val
        return None

    def _cache_set(self, key: str, val: Any, ttl: float) -> None:
        self._cache[key] = (val, time.monotonic() + ttl)

    async def _post(self, path: str, payload: dict[str, Any]) -> Any | None:
        init_data = (runtime_config.tonnel_init_data or "").strip()
        if not init_data:
            return None

        async with self._lock:
            now = time.monotonic()
            wait = self._min_interval - (now - self._last_req_ts)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_req_ts = time.monotonic()

            body = {**payload, "authData": init_data}
            try:
                client = self._get_client()
                resp = await client.post(path, json=body)
                if resp.status_code == 200:
                    self.last_live_ok = True
                    self.last_error = ""
                    return resp.json()
                self.last_error = f"Tonnel HTTP {resp.status_code}"
                logger.debug(f"Tonnel {path} HTTP {resp.status_code}")
            except Exception as exc:
                self.last_error = str(exc)
                logger.debug(f"Tonnel {path} error: {exc}")
        return None

    async def get_collections_floors(self, force_refresh: bool = False) -> dict[str, float]:
        """POST /filterStats -> dict of {short_name: floor_price_ton}."""
        cache_key = "tonnel:floors"
        if not force_refresh:
            cached = self._cache_get(cache_key)
            if cached is not None:
                return cached

        data = await self._post("/filterStats", {})
        if isinstance(data, dict):
            raw_map = data.get("data") if isinstance(data.get("data"), dict) else data
            floors: dict[str, float] = {}
            if isinstance(raw_map, dict):
                for key, val in raw_map.items():
                    # filterStats keys can be "Collection Name" or "Collection_Model"
                    if "_" in str(key):
                        continue
                    clean = str(key).strip().lower().replace(" ", "")
                    floor = to_float(
                        val.get("floorPrice") if isinstance(val, dict) else val,
                        0.0,
                    )
                    if clean and floor > 0:
                        floors[clean] = round(floor, 2)
            if floors:
                self._cache_set(cache_key, floors, ttl=90.0)
                return floors

        stale = self._cache_get(cache_key, allow_stale=True)
        if isinstance(stale, dict) and stale:
            self._cache_set(cache_key, stale, ttl=30.0)
            return stale
        self._cache_set(cache_key, {}, ttl=25.0)
        return {}

    async def get_floor_price(self, short_name: str) -> float | None:
        floors = await self.get_collections_floors()
        val = floors.get(short_name.strip().lower())
        return float(val) if val and val > 0 else None

    async def search_nfts(
        self,
        *,
        collection_name: str | None = None,
        sort: str = "price_asc",
        limit: int = 30,
        page: int = 0,
        search: str | None = None,
        force_refresh: bool = False,
    ) -> tuple[list[dict[str, Any]], bool]:
        """POST /pageGifts -> normalized live Tonnel gift listings + has_more."""
        if not (runtime_config.tonnel_init_data or "").strip():
            return [], False

        clean_col = (collection_name or "").strip()
        clean_search = (search or "").strip().lstrip("#")
        safe_limit = max(10, min(int(limit or 30), 30))
        page_1based = max(1, int(page or 0) + 1)

        if sort == "price_desc":
            sort_obj = {"price": -1, "gift_id": -1}
        elif sort == "newest":
            sort_obj = {"message_post_time": -1, "gift_id": -1}
        else:
            sort_obj = {"price": 1, "gift_id": -1}

        flt: dict[str, Any] = {"price": {"$exists": True}, "buyer": {"$exists": False}, "asset": "TON"}
        if clean_col:
            flt["gift_name"] = clean_col
        if clean_search:
            if clean_search.isdigit():
                flt["gift_num"] = int(clean_search)
            else:
                flt["model"] = {"$regex": clean_search, "$options": "i"}

        cache_key = f"tonnel:gifts:{clean_col.lower()}:{clean_search.lower()}:{sort}:p{page_1based}:l{safe_limit}"
        if not force_refresh:
            cached = self._cache_get(cache_key)
            if cached is not None:
                return cached

        payload = {
            "page": page_1based,
            "limit": safe_limit,
            "sort": json.dumps(sort_obj),
            "filter": json.dumps(flt),
            "price_range": None,
            "user_auth": runtime_config.tonnel_init_data,
        }

        data = await self._post("/pageGifts", payload)
        if not isinstance(data, list):
            stale = self._cache_get(cache_key, allow_stale=True)
            return stale if stale is not None else ([], False)

        normalized = [self._normalize_gift(g) for g in data if isinstance(g, dict)]
        normalized = [g for g in normalized if g is not None]
        has_more = len(normalized) >= max(5, safe_limit - 5)

        res = (normalized, has_more)
        self._cache_set(cache_key, res, ttl=30.0)
        return res

    @staticmethod
    def _normalize_gift(g: dict[str, Any]) -> dict[str, Any] | None:
        gift_id = str(g.get("gift_id") or g.get("_id") or "").strip()
        col_name = str(g.get("name") or g.get("gift_name") or "").strip()
        number = to_int(g.get("gift_num"), 0)
        price = round(to_float(g.get("price"), 0.0), 2)
        if not gift_id or not col_name or price <= 0:
            return None

        clean_short = re.sub(r"[^a-z0-9]", "", col_name.lower())
        pascal_col = re.sub(r"[^a-zA-Z0-9]", "", col_name)
        tg_slug = f"{pascal_col}-{number}" if number > 0 else pascal_col

        def _parse_trait(raw_val: Any) -> tuple[str, float]:
            txt = str(raw_val or "").strip()
            if not txt:
                return "", 1.5
            # Tonnel often formats traits as "Bronzy (2.6%)"
            if "(" in txt and "%" in txt:
                parts = txt.rsplit("(", 1)
                name = parts[0].strip()
                pct = to_float(parts[1].replace("%", "").replace(")", "").strip(), 1.5)
                return name, round(pct, 2)
            return txt, 1.5

        attributes: list[dict[str, Any]] = []
        m_name, m_rar = _parse_trait(g.get("model"))
        if m_name:
            attributes.append({"type": "model", "value": m_name, "rarity_per_mille": m_rar})
        b_name, b_rar = _parse_trait(g.get("backdrop"))
        if b_name:
            attributes.append({"type": "backdrop", "value": b_name, "rarity_per_mille": b_rar})
        s_name, s_rar = _parse_trait(g.get("symbol"))
        if s_name:
            attributes.append({"type": "symbol", "value": s_name, "rarity_per_mille": s_rar})

        # Official Changes.tg model PNG returns 200 OK for 100% of both off-chain and on-chain Tonnel gifts!
        if col_name and m_name:
            photo_url = (
                f"https://cdn.changes.tg/gifts/models/"
                f"{urllib.parse.quote(col_name)}/png/{urllib.parse.quote(m_name)}.png"
            )
        elif clean_short and number > 0:
            photo_url = f"https://nft.fragment.com/gift/{clean_short}-{number}.large.jpg"
        else:
            photo_url = ""

        return {
            "id": f"tonnel-{gift_id}",
            "tonnel_id": gift_id,
            "tg_id": tg_slug,
            "name": col_name,
            "external_collection_number": number,
            "price": str(price),
            "floor_price": str(price),
            "photo_url": photo_url,
            "attributes": attributes,
            "listed_at": utc_now_iso(),
            "market": "tonnel",
            "market_url": f"https://t.me/tonnel_network_bot/gifts?startapp=gift_{gift_id}",
        }


tonnel_client = TonnelClient()
