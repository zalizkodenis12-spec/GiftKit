"""Live MRKT (api.tgmrkt.io) Marketplace Client with auto-auth, rate-limiting & cursor pagination."""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any

import httpx
from loguru import logger

from backend.config import runtime_config
from backend.database import utc_now_iso
from backend.services.portals_client import to_float, to_int

MRKT_API_BASE = "https://api.tgmrkt.io/api/v1"
MRKT_CDN_BASE = "https://cdn.tgmrkt.io"


class MrktClient:
    """Async throttled client for live MRKT collections, floor prices & gift listings."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._lock = asyncio.Lock()
        self._last_req_ts: float = 0.0
        self._min_interval: float = 0.35  # Protect against MRKT 429 while staying snappy

        self._token: str = ""
        self._token_for_init: str = ""
        self._token_expires_at: float = 0.0
        self._auth_fail_until: float = 0.0

        self._cache: dict[str, tuple[Any, float]] = {}
        self._cursor_store: dict[str, dict[int, str]] = {}  # query_key -> {page: cursor}

        self.last_live_ok: bool = False
        self.last_error: str = ""

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=MRKT_API_BASE,
                timeout=httpx.Timeout(9.0, connect=4.0),
                headers={
                    "Accept": "application/json, text/plain, */*",
                    "Content-Type": "application/json",
                    "Origin": MRKT_CDN_BASE,
                    "Referer": f"{MRKT_CDN_BASE}/",
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
        self._cursor_store.clear()

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

    async def _throttle(self) -> None:
        now = time.monotonic()
        wait = self._min_interval - (now - self._last_req_ts)
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_req_ts = time.monotonic()

    async def _ensure_token(self, force: bool = False) -> str | None:
        init_data = (runtime_config.mrkt_init_data or "").strip()
        if not init_data:
            return None

        now = time.monotonic()
        if not force and now < self._auth_fail_until and self._token_for_init == init_data:
            return None
        if (
            not force
            and self._token
            and self._token_for_init == init_data
            and now < self._token_expires_at
        ):
            return self._token

        # If caller already pasted a raw Bearer/JWT/UUID token instead of query_id=...&user=...
        if "user=" not in init_data and "hash=" not in init_data and len(init_data) >= 24:
            self._token = init_data
            self._token_for_init = init_data
            self._token_expires_at = now + 1500.0
            return self._token

        async with self._lock:
            now = time.monotonic()
            if (
                not force
                and self._token
                and self._token_for_init == init_data
                and now < self._token_expires_at
            ):
                return self._token

            await self._throttle()
            try:
                client = self._get_client()
                resp = await client.post("/auth", json={"data": init_data})
                if resp.status_code == 200:
                    body = resp.json()
                    tok = ""
                    if isinstance(body, dict):
                        tok = str(
                            body.get("token")
                            or body.get("accessToken")
                            or body.get("access_token")
                            or ""
                        ).strip()
                    elif isinstance(body, str):
                        tok = body.strip()
                    if tok:
                        self._token = tok
                        self._token_for_init = init_data
                        self._token_expires_at = time.monotonic() + 1500.0
                        self.last_live_ok = True
                        self.last_error = ""
                        return self._token
                self.last_error = f"MRKT auth HTTP {resp.status_code}"
                self._token_for_init = init_data
                self._auth_fail_until = time.monotonic() + 20.0
                logger.warning(f"MRKT /auth failed: HTTP {resp.status_code}")
            except Exception as exc:
                self.last_error = f"MRKT auth error: {exc}"
                self._token_for_init = init_data
                self._auth_fail_until = time.monotonic() + 20.0
                logger.debug(f"MRKT /auth exception: {exc}")
        return None

    async def _authed_request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        retry_auth: bool = True,
    ) -> Any | None:
        token = await self._ensure_token()
        if not token:
            return None

        async with self._lock:
            await self._throttle()
            client = self._get_client()
            try:
                if method.upper() == "POST":
                    resp = await client.post(path, json=json_body, headers={"Authorization": token})
                else:
                    resp = await client.get(path, headers={"Authorization": token})

                if resp.status_code == 200:
                    self.last_live_ok = True
                    self.last_error = ""
                    return resp.json()

                if resp.status_code in (401, 403) and retry_auth:
                    self._token = ""
                    self._token_expires_at = 0.0
                elif resp.status_code == 429:
                    self.last_error = "MRKT rate limit (429)"
                    logger.debug("MRKT 429 rate-limit hit; serving cached data")
                    return None
                else:
                    self.last_error = f"MRKT HTTP {resp.status_code}"
                    logger.debug(f"MRKT {path} HTTP {resp.status_code}: {resp.text[:140]}")
                    return None
            except Exception as exc:
                self.last_error = str(exc)
                logger.debug(f"MRKT {path} error: {exc}")
                return None

        # Retry once with fresh auth token (and optional MTProto refresh)
        if retry_auth:
            try:
                from backend.services.mtproto_auth import mtproto_auth

                if mtproto_auth.is_authorized:
                    await mtproto_auth.refresh_mrkt_init_data()
            except Exception:
                pass
            fresh_token = await self._ensure_token(force=True)
            if fresh_token:
                return await self._authed_request(
                    method, path, json_body=json_body, retry_auth=False
                )
        return None

    async def get_collections(self, force_refresh: bool = False) -> dict[str, dict[str, Any]]:
        """GET /gifts/collections -> dict keyed by short_name with real TON floor prices."""
        cache_key = "mrkt:collections"
        if not force_refresh:
            cached = self._cache_get(cache_key)
            if cached is not None:
                return cached

        data = await self._authed_request("GET", "/gifts/collections")
        if isinstance(data, list) and data:
            result: dict[str, dict[str, Any]] = {}
            for col in data:
                if not isinstance(col, dict):
                    continue
                name = str(col.get("name") or col.get("title") or "").strip()
                if not name:
                    continue
                short = name.lower().replace(" ", "")
                floor_nano = to_float(
                    col.get("floorPriceNanoTons")
                    or col.get("floorPriceNanoTokens")
                    or col.get("floorPriceForGamesNanoTons"),
                    0.0,
                )
                floor_ton = round(floor_nano / 1e9, 2) if floor_nano > 10000 else round(floor_nano, 2)
                vol_nano = to_float(col.get("volume"), 0.0)
                vol_ton = round(vol_nano / 1e9, 2) if vol_nano > 1e6 else round(vol_nano, 2)
                thumb_key = str(col.get("thumbnailImageKey") or col.get("originalImageKey") or "").strip()
                photo_url = f"{MRKT_CDN_BASE}/{thumb_key.lstrip('/')}" if thumb_key else ""
                result[short] = {
                    "name": name,
                    "short_name": short,
                    "floor_price": floor_ton,
                    "volume": vol_ton,
                    "photo_url": photo_url,
                }
            if result:
                self._cache_set(cache_key, result, ttl=90.0)
                return result

        stale = self._cache_get(cache_key, allow_stale=True)
        if isinstance(stale, dict) and stale:
            self._cache_set(cache_key, stale, ttl=30.0)
            return stale
        self._cache_set(cache_key, {}, ttl=20.0)
        return {}

    async def get_floor_price(self, short_name: str) -> float | None:
        cols = await self.get_collections()
        entry = cols.get(short_name.strip().lower())
        if entry and entry.get("floor_price", 0.0) > 0:
            return float(entry["floor_price"])
        return None

    async def search_nfts(
        self,
        *,
        collection_name: str | None = None,
        sort: str = "price_asc",
        count: int = 30,
        page: int = 0,
        search: str | None = None,
        force_refresh: bool = False,
    ) -> tuple[list[dict[str, Any]], bool]:
        """POST /gifts/saling -> normalized live MRKT gift listings + has_more."""
        if not (runtime_config.mrkt_init_data or "").strip():
            return [], False

        clean_col = (collection_name or "").strip()
        clean_search = (search or "").strip().lstrip("#")
        safe_count = max(10, min(int(count or 30), 50))
        page_num = max(0, int(page or 0))

        # Ordering supported by MRKT /gifts/saling
        if sort == "price_desc":
            ordering, low_to_high = "Price", False
        elif sort == "newest":
            ordering, low_to_high = "Latest", False
        else:
            ordering, low_to_high = "Price", True

        query_key = f"{clean_col.lower()}|{clean_search.lower()}|{ordering}|{low_to_high}"
        cache_key = f"mrkt:saling:{query_key}:p{page_num}:c{safe_count}"

        if not force_refresh:
            cached = self._cache_get(cache_key)
            if cached is not None:
                return cached

        cursor = ""
        if page_num > 0:
            cursor = self._cursor_store.get(query_key, {}).get(page_num, "")
            if not cursor:
                return [], False

        payload: dict[str, Any] = {
            "CollectionNames": [clean_col] if clean_col else [],
            "ModelNames": [],
            "SymbolNames": [],
            "BackdropNames": [],
            "count": safe_count,
            "cursor": cursor,
            "ordering": ordering,
            "lowToHigh": low_to_high,
        }
        if clean_search:
            if clean_search.isdigit():
                payload["Number"] = int(clean_search)
            else:
                payload["ModelNames"] = [clean_search]

        data = await self._authed_request("POST", "/gifts/saling", json_body=payload)
        if not isinstance(data, dict):
            stale = self._cache_get(cache_key, allow_stale=True)
            return stale if stale is not None else ([], False)

        raw_gifts = data.get("gifts") if isinstance(data.get("gifts"), list) else []
        next_cursor = str(data.get("cursor") or "").strip()

        if next_cursor:
            self._cursor_store.setdefault(query_key, {})[page_num + 1] = next_cursor

        normalized = [self._normalize_gift(g) for g in raw_gifts if isinstance(g, dict)]
        normalized = [g for g in normalized if g is not None]
        has_more = bool(next_cursor) and len(normalized) >= max(5, safe_count // 2)

        res = (normalized, has_more)
        self._cache_set(cache_key, res, ttl=30.0)
        return res

    @staticmethod
    def _normalize_gift(g: dict[str, Any]) -> dict[str, Any] | None:
        raw_id = str(g.get("id") or "").strip()
        if not raw_id:
            return None
        sale_nano = to_float(g.get("salePrice") or g.get("salePriceWithoutFee"), 0.0)
        price_ton = round(sale_nano / 1e9, 2) if sale_nano > 10000 else round(sale_nano, 2)
        if price_ton <= 0:
            return None

        col_name = str(g.get("collectionName") or g.get("collectionTitle") or g.get("title") or "").strip()
        number = to_int(g.get("number"), 0)
        clean_short = re.sub(r"[^a-z0-9]", "", col_name.lower())
        pascal_col = re.sub(r"[^a-zA-Z0-9]", "", col_name)
        tg_slug = str(g.get("name") or "").strip()
        if not tg_slug and pascal_col and number:
            tg_slug = f"{pascal_col}-{number}"

        floor_nano = to_float(g.get("floorPriceNanoTONsByCollection"), 0.0)
        floor_ton = round(floor_nano / 1e9, 2) if floor_nano > 10000 else round(floor_nano, 2)

        # Official Telegram Fragment high-res gift image (exact background + model + symbol)
        frag_slug = re.sub(r"[^a-z0-9-]", "", tg_slug.lower()) if tg_slug else (f"{clean_short}-{number}" if clean_short and number else "")
        photo_url = f"https://nft.fragment.com/gift/{frag_slug}.large.jpg" if frag_slug else ""
        if not photo_url:
            thumb = str(g.get("modelStickerThumbnailKey") or "").strip()
            if thumb:
                photo_url = f"{MRKT_CDN_BASE}/{thumb.lstrip('/')}"

        attributes: list[dict[str, Any]] = []
        model_name = str(g.get("modelName") or g.get("modelTitle") or "").strip()
        if model_name:
            rar = to_float(g.get("modelRarityPerMille"), 15.0)
            attributes.append({
                "type": "model",
                "value": model_name,
                "rarity_per_mille": round(rar / 10.0, 2) if rar > 10 else round(rar, 2),
            })

        backdrop_name = str(g.get("backdropName") or "").strip()
        if backdrop_name:
            rar = to_float(g.get("backdropRarityPerMille"), 15.0)
            attributes.append({
                "type": "backdrop",
                "value": backdrop_name,
                "rarity_per_mille": round(rar / 10.0, 2) if rar > 10 else round(rar, 2),
            })

        symbol_name = str(g.get("symbolName") or "").strip()
        if symbol_name:
            rar = to_float(g.get("symbolRarityPerMille"), 10.0)
            attributes.append({
                "type": "symbol",
                "value": symbol_name,
                "rarity_per_mille": round(rar / 10.0, 2) if rar > 10 else round(rar, 2),
            })

        return {
            "id": f"mrkt-{raw_id}",
            "mrkt_uuid": raw_id,
            "tg_id": tg_slug,
            "name": col_name,
            "external_collection_number": number,
            "price": str(price_ton),
            "floor_price": str(floor_ton),
            "photo_url": photo_url,
            "attributes": attributes,
            "listed_at": str(g.get("receivedDate") or utc_now_iso()),
            "market": "mrkt",
            "market_url": f"https://t.me/mrkt/app?startapp=gift_{raw_id}",
        }


mrkt_client = MrktClient()
