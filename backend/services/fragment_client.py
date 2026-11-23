"""Live Fragment (fragment.com/gifts) Marketplace Client — zero API keys required."""

from __future__ import annotations

import asyncio
import html
import re
import time
from typing import Any

import httpx
from loguru import logger

from backend.database import utc_now_iso
from backend.services.portals_client import to_float, to_int

FRAGMENT_BASE = "https://fragment.com"


class FragmentClient:
    """Fetches real live on-sale Telegram Gifts directly from fragment.com/gifts."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._lock = asyncio.Lock()
        self._cache: dict[str, tuple[Any, float]] = {}
        self.last_live_ok: bool = False

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=FRAGMENT_BASE,
                timeout=httpx.Timeout(10.0, connect=4.0),
                follow_redirects=True,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                    ),
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
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

    async def search_nfts(
        self,
        *,
        collection_short: str | None = None,
        sort: str = "price_asc",
        limit: int = 40,
        page: int = 0,
        search: str | None = None,
        force_refresh: bool = False,
    ) -> tuple[list[dict[str, Any]], bool]:
        """Fetch live on-sale Fragment gift listings with pagination."""
        clean_col = re.sub(r"[^a-z0-9]", "", (collection_short or "").strip().lower())
        clean_search = (search or "").strip().lstrip("#")
        page_num = max(0, int(page or 0))
        safe_limit = max(10, min(int(limit or 40), 60))

        frag_sort = "price_asc"
        if sort == "price_desc":
            frag_sort = "price_desc"
        elif sort == "newest":
            frag_sort = "listed"

        cache_key = f"frag:{clean_col}:{frag_sort}:{clean_search.lower()}"
        cached_all: list[dict[str, Any]] | None = None
        if not force_refresh:
            cached_all = self._cache_get(cache_key)

        if cached_all is None:
            path = f"/gifts/{clean_col}" if clean_col else "/gifts"
            params: dict[str, Any] = {"sort": frag_sort, "filter": "sale"}
            if clean_search:
                params["query"] = clean_search

            async with self._lock:
                if not force_refresh:
                    cached_all = self._cache_get(cache_key)
                if cached_all is None:
                    try:
                        client = self._get_client()
                        resp = await client.get(path, params=params)
                        if resp.status_code == 200 and resp.text:
                            parsed = self._parse_gifts_html(resp.text)
                            if parsed:
                                self.last_live_ok = True
                                self._cache_set(cache_key, parsed, ttl=45.0)
                                cached_all = parsed
                            else:
                                cached_all = []
                        else:
                            cached_all = self._cache_get(cache_key, allow_stale=True) or []
                    except Exception as exc:
                        logger.debug(f"Fragment fetch failed ({path}): {exc}")
                        cached_all = self._cache_get(cache_key, allow_stale=True) or []

        items = cached_all or []
        start = page_num * safe_limit
        chunk = items[start : start + safe_limit]
        has_more = (start + safe_limit) < len(items)
        return chunk, has_more

    @staticmethod
    def _parse_gifts_html(page_html: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        seen: set[str] = set()
        card_pattern = re.compile(
            r'<a\s+href="(/gift/([a-z0-9-]+)[^"]*)"\s+class="[^"]*tm-grid-item[^"]*"[^>]*>(.*?)</a>',
            re.DOTALL | re.IGNORECASE,
        )
        for m in card_pattern.finditer(page_html):
            slug = m.group(2).strip().lower()
            if not slug or slug in seen or "-" not in slug:
                continue
            body = m.group(3)

            name_m = re.search(r'<span\s+class="item-name">([^<]+)</span>', body)
            num_m = re.search(r'#(\d+)', body)
            price_m = re.search(r'tm-value\s+icon-before\s+icon-ton">([\d,.\s]+)<', body)
            img_m = re.search(r'<img\s+src="([^"]+)"', body)

            col_name = html.unescape(name_m.group(1)).strip() if name_m else slug.split("-", 1)[0].title()
            number = to_int(num_m.group(1), 0) if num_m else to_int(slug.rsplit("-", 1)[-1], 0)
            price_raw = (price_m.group(1) if price_m else "").replace(",", "").replace(" ", "").strip()
            price = round(to_float(price_raw, 0.0), 2)
            if price <= 0 or number <= 0:
                continue

            seen.add(slug)
            photo_url = (
                img_m.group(1).strip().replace(".medium.jpg", ".large.jpg")
                if img_m
                else f"https://nft.fragment.com/gift/{slug}.large.jpg"
            )
            pascal_col = re.sub(r"[^a-zA-Z0-9]", "", col_name)
            tg_id = f"{pascal_col}-{number}"

            results.append(
                {
                    "id": f"fragment-{slug}",
                    "tg_id": tg_id,
                    "name": col_name,
                    "external_collection_number": number,
                    "price": str(price),
                    "floor_price": str(price),
                    "photo_url": photo_url,
                    "attributes": [],
                    "listed_at": utc_now_iso(),
                    "market": "fragment",
                    "market_url": f"https://fragment.com/gift/{slug}",
                }
            )
        return results


fragment_client = FragmentClient()
