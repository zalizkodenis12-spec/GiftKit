"""Async httpx client for Portals Market API with TTL caching and graceful fallbacks."""

from __future__ import annotations

import asyncio
import html
import re
import time
import urllib.parse
from typing import Any

import httpx
from loguru import logger

from backend.config import runtime_config

PORTALS_BASE_URL = "https://portal-market.com/api"

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def is_valid_uuid(val: Any) -> bool:
    s = str(val or "").strip()
    if not s or s.startswith(("xray-", "synth-", "floor-", "live-anchored-")):
        return False
    return bool(_UUID_RE.fullmatch(s))


def to_float(val: Any, default: float = 0.0) -> float:
    if val is None or val == "":
        return default
    try:
        return float(str(val).replace(",", ".").replace("\u2212", "-").strip())
    except (ValueError, TypeError):
        return default


def to_int(val: Any, default: int = 0) -> int:
    if val is None or val == "":
        return default
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default


def collection_photo_url(short_name: str, raw_url: str | None = None) -> str:
    if raw_url and str(raw_url).strip().startswith("http"):
        return str(raw_url).strip()
    clean = short_name.strip().lower().replace(" ", "")
    return f"https://nft.fragment.com/collection/{clean}.webp"


def gift_photo_url(short_name: str, number: int, raw_url: str | None = None) -> str:
    if raw_url and str(raw_url).strip().startswith("http"):
        return str(raw_url).strip()
    clean = short_name.strip().lower().replace(" ", "")
    return f"https://nft.fragment.com/gift/{clean}-{number}.large.jpg"


class _TTLCacheEntry:
    __slots__ = ("value", "expires_at")

    def __init__(self, value: Any, ttl: float) -> None:
        self.value = value
        self.expires_at = time.monotonic() + ttl


class PortalsClient:
    """Production async client for https://portal-market.com/api."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._cache: dict[str, _TTLCacheEntry] = {}
        self._sem = asyncio.Semaphore(2)
        self._rate_limit_until: float = 0.0
        self.last_live_ok: bool = False
        self.last_sync_ts: float = 0.0

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=PORTALS_BASE_URL,
                timeout=httpx.Timeout(12.0, connect=5.0),
                headers={
                    "Accept": "application/json",
                    "User-Agent": "TONGiftTerminalPro/1.0",
                },
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def _auth_headers(self) -> dict[str, str]:
        init_data = runtime_config.portals_init_data
        if init_data:
            prefix = "" if init_data.lower().startswith("tma ") else "tma "
            return {"Authorization": f"{prefix}{init_data}"}
        return {}

    def _cache_get(self, key: str, allow_stale: bool = False) -> Any | None:
        entry = self._cache.get(key)
        if not entry:
            return None
        if allow_stale or time.monotonic() < entry.expires_at:
            return entry.value
        return None

    def _cache_set(self, key: str, value: Any, ttl: float) -> None:
        self._cache[key] = _TTLCacheEntry(value, ttl)

    def clear_cache(self) -> None:
        self._cache.clear()

    async def _request(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        if time.monotonic() < self._rate_limit_until:
            return None
        client = self._get_client()
        async with self._sem:
            for attempt in range(2):
                try:
                    resp = await client.get(path, params=params, headers=self._auth_headers())
                    if resp.status_code == 200:
                        self.last_live_ok = True
                        self.last_sync_ts = time.time()
                        return resp.json()
                    if resp.status_code == 429:
                        logger.warning(f"Portals API {path} returned HTTP 429 (attempt {attempt + 1})")
                        if attempt == 0:
                            await asyncio.sleep(0.8)
                            continue
                        self._rate_limit_until = time.monotonic() + 8.0
                        return None
                    logger.warning(f"Portals API {path} returned HTTP {resp.status_code}")
                    return None
                except httpx.TimeoutException:
                    logger.warning(f"Portals API timeout on {path}")
                    return None
                except httpx.HTTPError as exc:
                    logger.warning(f"Portals API HTTP error on {path}: {exc}")
                    return None
                except Exception as exc:
                    logger.error(f"Portals API unexpected error on {path}: {exc}")
                    return None
        return None

    async def get_collections(self, limit: int = 250, force_refresh: bool = False) -> list[dict[str, Any]]:
        """GET /collections with pagination to fetch ALL available Telegram Gift collections (cached 60s)."""
        cache_key = f"collections:all:{limit}"
        if not force_refresh:
            cached = self._cache_get(cache_key)
            if cached is not None:
                return cached

        all_raw: list[dict[str, Any]] = []
        offset = 0
        page_size = 100
        while len(all_raw) < limit:
            data = await self._request("/collections", params={"limit": page_size, "offset": offset})
            if not data or not isinstance(data.get("collections"), list):
                break
            batch = data["collections"]
            all_raw.extend(batch)
            if len(batch) < page_size:
                break
            offset += page_size

        if all_raw:
            seen_shorts: set[str] = set()
            normalized: list[dict[str, Any]] = []
            for raw in all_raw:
                short = str(raw.get("short_name") or "").strip().lower()
                if not short or short in seen_shorts:
                    continue
                seen_shorts.add(short)
                normalized.append(
                    {
                        "id": str(raw.get("id") or short),
                        "name": str(raw.get("name") or short),
                        "short_name": short,
                        "photo_url": collection_photo_url(short, raw.get("photo_url")),
                        "floor_price": to_float(raw.get("floor_price"), 0.0),
                        "day_volume": to_float(raw.get("day_volume"), 0.0),
                        "volume": to_float(raw.get("volume"), 0.0),
                        "supply": to_int(raw.get("supply"), 0),
                        "listed_count": to_int(raw.get("listed_count"), 0),
                        "sales_24h_count": to_int(raw.get("sales_24h_count"), 0),
                        "market_cap": to_float(raw.get("market_cap"), 0.0),
                        "is_crafted": bool(raw.get("is_crafted", False)),
                        "is_new": bool(raw.get("is_new", False)),
                        "zero_commission": bool(raw.get("zero_commission", False)),
                    }
                )
            self._cache_set(cache_key, normalized[:limit], ttl=60.0)
            return normalized[:limit]

        stale = self._cache_get(cache_key, allow_stale=True)
        if stale is not None:
            return stale
        return self._fallback_collections()

    async def get_floors(self, force_refresh: bool = False) -> dict[str, float]:
        """GET /collections/floors (cached 30s)."""
        cache_key = "floors"
        if not force_refresh:
            cached = self._cache_get(cache_key)
            if cached is not None:
                return cached

        data = await self._request("/collections/floors")
        if data and isinstance(data.get("floorPrices"), dict):
            floors = {
                str(k).strip().lower(): to_float(v, 0.0)
                for k, v in data["floorPrices"].items()
                if to_float(v, 0.0) > 0
            }
            self._cache_set(cache_key, floors, ttl=30.0)
            return floors

        stale = self._cache_get(cache_key, allow_stale=True)
        if stale is not None:
            return stale

        # Derive from collections if floors endpoint failed
        cols = await self.get_collections()
        return {c["short_name"]: c["floor_price"] for c in cols if c["floor_price"] > 0}

    async def get_collection_filters(
        self,
        short_names: list[str],
        force_refresh: bool = False,
        col_name_map: dict[str, str] | None = None,
    ) -> dict[str, dict[str, list[dict[str, Any]]]]:
        """GET /collections/filters?short_names=... (cached 5min per collection)."""
        cleaned = [s.strip().lower() for s in short_names if s and s.strip()]
        if not cleaned:
            return {}

        # Merge known collection display names from cache if available
        known_names: dict[str, str] = {}
        cached_cols = self._cache_get("collections:all:250", allow_stale=True) or self._cache_get("collections:all:120", allow_stale=True)
        if isinstance(cached_cols, list):
            for c in cached_cols:
                if isinstance(c, dict) and c.get("short_name") and c.get("name"):
                    known_names[str(c["short_name"]).lower()] = str(c["name"])
        if col_name_map:
            for k, v in col_name_map.items():
                if k and v:
                    known_names[k.strip().lower()] = str(v).strip()

        result: dict[str, dict[str, list[dict[str, Any]]]] = {}
        missing: list[str] = []
        for s in cleaned:
            if not force_refresh:
                cached = self._cache_get(f"filters:{s}")
                if cached is not None:
                    c_name = known_names.get(s, "")
                    if c_name:
                        for m in cached.get("models") or []:
                            if "cdn.changes.tg" not in str(m.get("photo_url") or ""):
                                m["photo_url"] = (
                                    f"https://cdn.changes.tg/gifts/models/"
                                    f"{urllib.parse.quote(c_name)}/png/{urllib.parse.quote(str(m.get('name') or ''))}.png"
                                )
                    result[s] = cached
                    continue
            missing.append(s)

        if missing:
            # Batch up to 15 short_names per request to keep URL safe
            for i in range(0, len(missing), 15):
                batch = missing[i : i + 15]
                data = await self._request(
                    "/collections/filters",
                    params={"short_names": ",".join(batch)},
                )
                cols_map = (data or {}).get("collections")
                if isinstance(cols_map, dict):
                    for s in batch:
                        raw_traits = cols_map.get(s) or {}
                        c_name = known_names.get(s, "")
                        parsed = self._normalize_filters(raw_traits, short_name=s, collection_name=c_name)
                        self._cache_set(f"filters:{s}", parsed, ttl=300.0)
                        result[s] = parsed
                else:
                    for s in batch:
                        stale = self._cache_get(f"filters:{s}", allow_stale=True)
                        result[s] = stale or {"models": [], "backdrops": [], "symbols": []}
        return result

    @staticmethod
    def _normalize_filters(
        raw: dict[str, Any],
        short_name: str = "",
        collection_name: str = "",
    ) -> dict[str, list[dict[str, Any]]]:
        out: dict[str, list[dict[str, Any]]] = {"models": [], "backdrops": [], "symbols": []}
        clean_short = (short_name or "").strip().lower()
        clean_col_name = (collection_name or "").strip()
        for key in ("models", "backdrops", "symbols"):
            items = raw.get(key)
            if not isinstance(items, list):
                continue
            parsed_items: list[dict[str, Any]] = []
            for item in items:
                name = str(item.get("name") or "").strip()
                if not name:
                    continue
                rarity = round(
                    to_float(item.get("rarity_per_mille") or item.get("rarityPermille"), 1.0),
                    2,
                )
                primary_url = (
                    f"https://cdn.changes.tg/gifts/models/{urllib.parse.quote(clean_col_name)}/png/{urllib.parse.quote(name)}.png"
                    if key == "models" and clean_col_name
                    else ""
                )
                fallback_url = (
                    f"https://storage.portal-market.com/portals-market/gifts/{clean_short}/models/png/{re.sub(r'[^a-z0-9]', '', name.lower())}.png"
                    if key == "models" and clean_short
                    else ""
                )
                raw_url = str(item.get("url") or "").strip()
                photo_url = raw_url or primary_url or fallback_url
                entry: dict[str, Any] = {
                    "name": name,
                    "rarity_percent": rarity,
                    "floor_price": round(to_float(item.get("floor_price"), 0.0), 2),
                    "supply": to_int(item.get("supply"), 0),
                    "photo_url": photo_url,
                }
                if key == "models":
                    entry["fallback_photo_url"] = fallback_url
                parsed_items.append(entry)
            parsed_items.sort(key=lambda x: x["floor_price"], reverse=True)
            out[key] = parsed_items
        return out

    async def get_official_backdrops_catalog(self) -> dict[str, dict[str, Any]]:
        """Fetch & cache (6h) all 80 official Telegram backdrops from https://cdn.changes.tg/gifts/backdrops.json."""
        cache_key = "official_backdrops_catalog_v1"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        catalog: dict[str, dict[str, Any]] = {}
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(6.0, connect=3.0),
                headers={"User-Agent": "Mozilla/5.0 (compatible; GiftKitBot/1.2)"},
                follow_redirects=True,
            ) as client:
                resp = await client.get("https://cdn.changes.tg/gifts/backdrops.json")
                if resp.status_code == 200:
                    raw_list = resp.json()
                    if isinstance(raw_list, list):
                        for item in raw_list:
                            if not isinstance(item, dict):
                                continue
                            name = str(item.get("name") or "").strip()
                            if not name:
                                continue
                            hex_obj = item.get("hex") if isinstance(item.get("hex"), dict) else {}
                            center_hex = str(hex_obj.get("centerColor") or "#1E293B").strip()
                            edge_hex = str(hex_obj.get("edgeColor") or center_hex).strip()
                            pattern_hex = str(hex_obj.get("patternColor") or edge_hex).strip()
                            text_hex = str(hex_obj.get("textColor") or "#F8FAFC").strip()
                            catalog[name.lower()] = {
                                "name": name,
                                "center_hex": center_hex,
                                "edge_hex": edge_hex,
                                "pattern_hex": pattern_hex,
                                "text_hex": text_hex,
                            }
        except Exception as exc:
            logger.debug(f"get_official_backdrops_catalog fetch skipped: {exc}")

        if catalog:
            self._cache_set(cache_key, catalog, ttl=21600.0)
            return catalog

        stale = self._cache_get(cache_key, allow_stale=True)
        if stale is not None:
            return stale
        return {}

    async def scrape_telegram_nft_metadata(self, slug: str) -> dict[str, Any] | None:
        """Scrape official https://t.me/nft/{slug} page for real Model, Backdrop, Symbol & Owner."""
        clean_slug = (slug or "").strip().strip("/")
        if not clean_slug or "-" not in clean_slug:
            return None

        cache_key = f"tg_nft_meta:{clean_slug.lower()}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        url = f"https://t.me/nft/{clean_slug}"
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(4.5, connect=2.5),
                headers={"User-Agent": "Mozilla/5.0 (compatible; GiftKitBot/1.2)"},
                follow_redirects=True,
            ) as client:
                resp = await client.get(url)
                if resp.status_code != 200 or not resp.text:
                    return None
                page_html = resp.text
        except Exception as exc:
            logger.debug(f"scrape_telegram_nft_metadata({clean_slug}) error: {exc}")
            return None

        title_m = re.search(r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']+)["\']', page_html, re.IGNORECASE)
        image_m = re.search(r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']', page_html, re.IGNORECASE)

        title = html.unescape(title_m.group(1)).strip() if title_m else clean_slug
        photo_url = html.unescape(image_m.group(1)).strip() if image_m else ""

        def _extract_row(header: str) -> tuple[str, float] | None:
            pattern = (
                rf"<th>\s*{header}\s*</th>\s*<td>\s*([^<]+?)\s*"
                r"(?:<mark>\s*([\d.,]+)\s*%\s*</mark>)?\s*</td>"
            )
            m = re.search(pattern, page_html, re.IGNORECASE | re.DOTALL)
            if not m:
                return None
            val = html.unescape(m.group(1)).strip()
            rar = round(to_float(m.group(2), 1.5), 2) if m.group(2) else 1.5
            return (val, rar) if val else None

        model_row = _extract_row("Model")
        backdrop_row = _extract_row("Backdrop")
        symbol_row = _extract_row("Symbol")

        if not model_row and not backdrop_row:
            return None

        attributes: list[dict[str, Any]] = []
        if model_row:
            attributes.append({"type": "model", "value": model_row[0], "rarity_per_mille": model_row[1]})
        if backdrop_row:
            attributes.append({"type": "backdrop", "value": backdrop_row[0], "rarity_per_mille": backdrop_row[1]})
        if symbol_row:
            attributes.append({"type": "symbol", "value": symbol_row[0], "rarity_per_mille": symbol_row[1]})

        owner = ""
        owner_m = re.search(r"<th>\s*Owner\s*</th>\s*<td>(.*?)</td>", page_html, re.IGNORECASE | re.DOTALL)
        if owner_m:
            owner_clean = re.sub(r"<[^>]+>", " ", owner_m.group(1))
            owner = " ".join(html.unescape(owner_clean).split()).strip()

        result = {
            "tg_id": clean_slug,
            "title": title,
            "photo_url": photo_url,
            "owner": owner,
            "attributes": attributes,
        }
        self._cache_set(cache_key, result, ttl=300.0)
        return result

    async def search_nfts(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        sort: str = "listed_at_desc",
        collection_ids: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        search: str | None = None,
        filter_by_models: str | None = None,
        force_refresh: bool = False,
    ) -> list[dict[str, Any]]:
        """GET /nfts/search (cached 12s)."""
        params: dict[str, Any] = {"limit": limit, "sort": sort}
        if offset > 0:
            params["offset"] = offset
        if collection_ids:
            params["collection_ids"] = collection_ids
        if min_price is not None and min_price > 0:
            params["min_price"] = min_price
        if max_price is not None and max_price > 0:
            params["max_price"] = max_price
        if search:
            params["search"] = search
        if filter_by_models:
            params["filter_by_models"] = filter_by_models

        cache_key = f"nfts:{sorted(params.items())}"
        if not force_refresh:
            cached = self._cache_get(cache_key)
            if cached is not None:
                return cached

        data = await self._request("/nfts/search", params=params)
        if data and isinstance(data.get("results"), list):
            items = data["results"]
            self._cache_set(cache_key, items, ttl=12.0)
            return items

        stale = self._cache_get(cache_key, allow_stale=True)
        return stale if stale is not None else []

    async def get_nft_by_id(self, nft_id: str) -> dict[str, Any] | None:
        """GET /nfts/{uuid} (cached 30s)."""
        cache_key = f"nft:{nft_id}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        data = await self._request(f"/nfts/{nft_id}")
        if data and isinstance(data, dict) and data.get("id"):
            self._cache_set(cache_key, data, ttl=30.0)
            return data
        return None

    @staticmethod
    def _fallback_collections() -> list[dict[str, Any]]:
        """Emergency fallback only if Portals is completely unreachable on cold start."""
        return [
            {
                "id": "eternalrose-fallback",
                "name": "Eternal Rose",
                "short_name": "eternalrose",
                "photo_url": collection_photo_url("eternalrose"),
                "floor_price": 30.8,
                "day_volume": 12450.5,
                "volume": 912822.9,
                "supply": 38400,
                "listed_count": 1120,
                "sales_24h_count": 142,
                "market_cap": 1182720.0,
                "is_crafted": False,
                "is_new": False,
                "zero_commission": False,
            },
            {
                "id": "plushpepe-fallback",
                "name": "Plush Pepe",
                "short_name": "plushpepe",
                "photo_url": collection_photo_url("plushpepe"),
                "floor_price": 465.0,
                "day_volume": 48200.0,
                "volume": 5840000.0,
                "supply": 2860,
                "listed_count": 195,
                "sales_24h_count": 34,
                "market_cap": 1329900.0,
                "is_crafted": False,
                "is_new": False,
                "zero_commission": False,
            },
            {
                "id": "snoopcigar-fallback",
                "name": "Snoop Cigar",
                "short_name": "snoopcigar",
                "photo_url": collection_photo_url("snoopcigar"),
                "floor_price": 18.5,
                "day_volume": 6420.0,
                "volume": 324000.0,
                "supply": 45000,
                "listed_count": 1840,
                "sales_24h_count": 210,
                "market_cap": 832500.0,
                "is_crafted": False,
                "is_new": False,
                "zero_commission": False,
            },
            {
                "id": "vicecream-fallback",
                "name": "Vice Cream",
                "short_name": "vicecream",
                "photo_url": collection_photo_url("vicecream"),
                "floor_price": 7.9,
                "day_volume": 3180.0,
                "volume": 152000.0,
                "supply": 62000,
                "listed_count": 2310,
                "sales_24h_count": 285,
                "market_cap": 489800.0,
                "is_crafted": False,
                "is_new": False,
                "zero_commission": False,
            },
        ]


portals_client = PortalsClient()
