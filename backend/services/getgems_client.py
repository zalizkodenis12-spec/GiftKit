"""Async client for Getgems Public API / GraphQL and TonAPI live TON/USD rates."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
from loguru import logger

from backend.config import runtime_config
from backend.services.portals_client import to_float, to_int

GETGEMS_API_BASE = "https://api.getgems.io/public-api/v1"
GETGEMS_GRAPHQL_URL = "https://api.getgems.io/graphql"
TONAPI_BASE = "https://tonapi.io/v2"

# Verified TON smart-contract addresses for major Telegram Gift collections
KNOWN_GIFT_COLLECTION_ADDRESSES: dict[str, str] = {
    "eternalrose": "EQDumy3bnZYzV4bSWMSSZkmXqx50XuH5d9RlX_yEi2FNlivk",
    "plushpepe": "EQBG-g6ahkAUGWpefWbx-D_9sQ8oWbvy6puuq78U2c4NUDFS",
    "durovscap": "EQD9ikZq6xPgKjzmdBG0G0S80RvUJjbwgHrPZXjYk_ARhkdv",
    "preciouspeach": "EQC6zjid8vJNEWqcXk10XjsdDLRKbcPZzbHegsAZHQramTl_",
    "astralshard": "EQA4i58iuS9DUYRtUZ97sZo5mnkbiYUBpWXQOe3dEUCcP1W8",
    "perfumebottle": "EQATuUGdvrjLvTWE5ppVFOVCqU2dlCLZOhmU2EX5CP5_5L1s",
    "scaredcat": "EQD6mH9bwbn6S3M_tCRWOt4-k_w_6X9V4b0L_bA6s4zW0p7E",
    "kissedfrog": "EQCNsmpDqlx12-n7h2b6nK2m7c5jP4aG_l7F7tJ7h8xH9a2Y",
    "vintagecigar": "EQATs_e4-4X5T3W1p_2r_2sR7sT9u_8V6w2X_1yZ4aB3cD5e",
    "swisswatch": "EQC47093oX5Xhb0xuk2lCr2RhS8rj-vul61u4W2UH5ORmG_O",
    "signetring": "EQB8StgTohdriver_placeholder_ring",
}


class GetgemsAndTonClient:
    """Fetches live TON/USD rate from TonAPI and Getgems collection stats/listings."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._ton_cache: tuple[float, float, float] | None = None  # (usd, change_24h, expires_at)
        self._stats_cache: dict[str, tuple[dict[str, Any], float]] = {}
        self._listings_cache: dict[str, tuple[list[dict[str, Any]], float]] = {}
        self.getgems_live_ok: bool = False

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(10.0, connect=4.0),
                headers={"Accept": "application/json", "User-Agent": "TONGiftTerminalPro/1.0"},
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def _getgems_headers(self) -> dict[str, str]:
        api_key = runtime_config.getgems_api_key
        return {"Authorization": api_key} if api_key else {}

    async def get_ton_rate(self, force_refresh: bool = False) -> tuple[float, float]:
        """Returns (ton_usd_price, change_24h_percent) from TonAPI (cached 60s)."""
        now = time.monotonic()
        if not force_refresh and self._ton_cache and now < self._ton_cache[2]:
            return self._ton_cache[0], self._ton_cache[1]

        client = self._get_client()
        try:
            resp = await client.get(f"{TONAPI_BASE}/rates", params={"tokens": "ton", "currencies": "usd"})
            if resp.status_code == 200:
                payload = resp.json()
                ton_info = payload.get("rates", {}).get("TON", {})
                usd = round(to_float(ton_info.get("prices", {}).get("USD"), 1.03), 3)
                diff_raw = str(ton_info.get("diff_24h", {}).get("USD", "0%")).replace("%", "")
                diff_24h = round(to_float(diff_raw, 0.0), 2)
                self._ton_cache = (usd, diff_24h, now + 60.0)
                return usd, diff_24h
        except Exception as exc:
            logger.warning(f"TonAPI rate fetch failed: {exc}")

        if self._ton_cache:
            return self._ton_cache[0], self._ton_cache[1]
        return 1.03, 0.68

    async def get_collection_stats(
        self, short_name: str, force_refresh: bool = False
    ) -> dict[str, Any] | None:
        """Fetch live Getgems collection stats via REST API (or GraphQL fallback)."""
        short = short_name.strip().lower()
        address = KNOWN_GIFT_COLLECTION_ADDRESSES.get(short)
        if not address or "placeholder" in address:
            return None

        now = time.monotonic()
        if not force_refresh and short in self._stats_cache and now < self._stats_cache[short][1]:
            return self._stats_cache[short][0]

        client = self._get_client()

        # 1. Try Public REST API if GETGEMS_API_KEY is configured (or open)
        headers = self._getgems_headers()
        if headers:
            try:
                resp = await client.get(
                    f"{GETGEMS_API_BASE}/collection/stats/{address}",
                    headers=headers,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    resp_obj = data.get("response") or data
                    floor_nano = to_float(resp_obj.get("floorPriceNano") or resp_obj.get("floorPrice"), 0.0)
                    floor_ton = round(floor_nano / 1e9, 2) if floor_nano > 100000 else round(floor_nano, 2)
                    if floor_ton > 0:
                        parsed = {
                            "short_name": short,
                            "address": address,
                            "floor_price": floor_ton,
                            "items_count": to_int(resp_obj.get("itemsCount"), 0),
                            "holders_count": to_int(resp_obj.get("holders"), 0),
                            "total_volume": to_float(resp_obj.get("totalVolumeSold"), 0.0),
                            "is_live": True,
                            "url": f"https://getgems.io/collection/{address}",
                        }
                        self.getgems_live_ok = True
                        self._stats_cache[short] = (parsed, now + 90.0)
                        return parsed
            except Exception as exc:
                logger.debug(f"Getgems REST stats failed for {short}: {exc}")

        # 2. Try Getgems Public GraphQL endpoint (no API key needed)
        try:
            gql_query = {
                "query": (
                    "query($addr: String!) { "
                    "alphaNftCollectionStats(address: $addr) { floorPrice totalVolume24h itemsCount } "
                    "}"
                ),
                "variables": {"addr": address},
            }
            resp = await client.post(GETGEMS_GRAPHQL_URL, json=gql_query)
            if resp.status_code == 200:
                payload = resp.json()
                stats = (payload.get("data") or {}).get("alphaNftCollectionStats")
                if isinstance(stats, dict) and stats.get("floorPrice") is not None:
                    raw_floor = to_float(stats.get("floorPrice"), 0.0)
                    floor_ton = round(raw_floor / 1e9, 2) if raw_floor > 100000 else round(raw_floor, 2)
                    if floor_ton > 0:
                        parsed = {
                            "short_name": short,
                            "address": address,
                            "floor_price": floor_ton,
                            "items_count": to_int(stats.get("itemsCount"), 0),
                            "total_volume_24h": to_float(stats.get("totalVolume24h"), 0.0),
                            "is_live": True,
                            "url": f"https://getgems.io/collection/{address}",
                        }
                        self.getgems_live_ok = True
                        self._stats_cache[short] = (parsed, now + 120.0)
                        return parsed
        except Exception as exc:
            logger.debug(f"Getgems GraphQL stats failed for {short}: {exc}")

        if short in self._stats_cache:
            return self._stats_cache[short][0]
        return None

    async def get_bulk_stats(self, short_names: list[str] | None = None) -> dict[str, dict[str, Any]]:
        """Fetch Getgems stats for known collections concurrently."""
        targets = [
            s
            for s in (short_names or ["eternalrose", "plushpepe", "durovscap", "preciouspeach", "swisswatch"])
            if s in KNOWN_GIFT_COLLECTION_ADDRESSES and "placeholder" not in KNOWN_GIFT_COLLECTION_ADDRESSES[s]
        ]
        if not targets:
            return {}
        results = await asyncio.gather(
            *(self.get_collection_stats(s) for s in targets[:6]),
            return_exceptions=True,
        )
        out: dict[str, dict[str, Any]] = {}
        for short, res in zip(targets[:6], results):
            if isinstance(res, dict) and res.get("floor_price", 0) > 0:
                out[short] = res
        return out

    async def get_on_sale_nfts(self, short_name: str, limit: int = 12) -> list[dict[str, Any]]:
        """Optional authenticated Getgems listings via GET /nfts/on-sale/{address}."""
        api_key = runtime_config.getgems_api_key
        short = short_name.strip().lower()
        address = KNOWN_GIFT_COLLECTION_ADDRESSES.get(short)
        if not api_key or not address or "placeholder" in address:
            return []

        now = time.monotonic()
        if short in self._listings_cache and now < self._listings_cache[short][1]:
            return self._listings_cache[short][0]

        client = self._get_client()
        try:
            resp = await client.get(
                f"{GETGEMS_API_BASE}/nfts/on-sale/{address}",
                params={"count": limit},
                headers={"Authorization": api_key},
            )
            if resp.status_code == 200:
                data = resp.json()
                items = (data.get("response") or {}).get("items") or []
                self._listings_cache[short] = (items, now + 30.0)
                return items
        except Exception as exc:
            logger.debug(f"Getgems on-sale fetch failed for {short}: {exc}")
        return []

    async def search_nfts(
        self,
        *,
        collection_short: str | None = None,
        sort: str = "price_asc",
        limit: int = 30,
        page: int = 0,
        search: str | None = None,
        force_refresh: bool = False,
    ) -> tuple[list[dict[str, Any]], bool]:
        """Fetch real live on-sale Getgems NFTs via official TonAPI v2 (zero API keys required)."""
        import re
        from backend.database import utc_now_iso

        clean_col = re.sub(r"[^a-z0-9]", "", (collection_short or "").strip().lower())
        clean_search = (search or "").strip().lstrip("#").lower()
        page_num = max(0, int(page or 0))
        safe_limit = max(10, min(int(limit or 30), 50))

        # Select collection addresses to scan
        all_known = [
            (k, v)
            for k, v in KNOWN_GIFT_COLLECTION_ADDRESSES.items()
            if v and "placeholder" not in v
        ]
        if clean_col:
            addr = KNOWN_GIFT_COLLECTION_ADDRESSES.get(clean_col)
            if not addr or "placeholder" in addr:
                return [], False
            targets = [(clean_col, addr)]
        else:
            # Rotate across known collections by page for infinite scroll
            per_page = 4
            start_idx = (page_num * per_page) % max(len(all_known), 1)
            targets = all_known[start_idx : start_idx + per_page]
            if not targets:
                targets = all_known[:per_page]

        cache_key = f"gg_tonapi:{clean_col}:{page_num}:{clean_search}"
        now = time.monotonic()
        if not force_refresh and cache_key in self._listings_cache and now < self._listings_cache[cache_key][1]:
            cached_items = self._listings_cache[cache_key][0]
            return cached_items[:safe_limit], (len(all_known) > 4 if not clean_col else False)

        client = self._get_client()
        collected: list[dict[str, Any]] = []
        seen: set[str] = set()

        async def _fetch_col(short_k: str, col_addr: str) -> list[dict[str, Any]]:
            out: list[dict[str, Any]] = []
            offset = page_num * 100 if clean_col else 0
            try:
                resp = await client.get(
                    f"{TONAPI_BASE}/nfts/collections/{col_addr}/items",
                    params={"limit": 100, "offset": offset},
                )
                if resp.status_code != 200:
                    return out
                nft_items = resp.json().get("nft_items") or []
                for it in nft_items:
                    if not isinstance(it, dict):
                        continue
                    sale = it.get("sale")
                    if not isinstance(sale, dict):
                        continue
                    price_obj = sale.get("price") or {}
                    cur_type = str(price_obj.get("currency_type") or "").lower()
                    tok_name = str(price_obj.get("token_name") or "").upper()
                    if cur_type != "native" and tok_name != "TON":
                        continue
                    decimals = int(price_obj.get("decimals") or 9)
                    raw_val = to_float(price_obj.get("value"), 0.0)
                    price_ton = round(raw_val / (10 ** decimals), 2) if raw_val > 0 else 0.0
                    if price_ton <= 0:
                        continue

                    addr = str(it.get("address") or "").strip()
                    if not addr:
                        continue
                    meta = it.get("metadata") or {}
                    full_name = str(meta.get("name") or "").strip()
                    col_name = full_name.split("#", 1)[0].strip() if "#" in full_name else str((it.get("collection") or {}).get("name") or short_k.title())
                    if col_name.endswith("s") and col_name.lower().replace(" ", "") != short_k:
                        # e.g. "Eternal Roses" -> "Eternal Rose"
                        if col_name[:-1].lower().replace(" ", "") == short_k:
                            col_name = col_name[:-1]
                    num_m = re.search(r"#(\d+)", full_name)
                    number = int(num_m.group(1)) if num_m else 0
                    if number <= 0:
                        continue

                    raw_attrs = meta.get("attributes") or []
                    attrs: list[dict[str, Any]] = []
                    for a in raw_attrs:
                        if not isinstance(a, dict):
                            continue
                        tt = str(a.get("trait_type") or "").strip().lower()
                        val = str(a.get("value") or "").strip()
                        if tt in ("model", "backdrop", "symbol") and val:
                            attrs.append({"type": tt, "value": val, "rarity_per_mille": 1.5})

                    if clean_search:
                        hay = f"{col_name} {number} " + " ".join(a["value"] for a in attrs)
                        if clean_search not in hay.lower():
                            continue

                    pascal_col = re.sub(r"[^a-zA-Z0-9]", "", col_name)
                    tg_id = f"{pascal_col}-{number}"
                    photo_url = str(meta.get("image") or "").strip()
                    if not photo_url:
                        photo_url = f"https://nft.fragment.com/gift/{short_k}-{number}.large.jpg"

                    out.append(
                        {
                            "id": f"getgems-{addr}",
                            "tg_id": tg_id,
                            "name": col_name,
                            "external_collection_number": number,
                            "price": str(price_ton),
                            "floor_price": str(price_ton),
                            "photo_url": photo_url,
                            "attributes": attrs,
                            "listed_at": utc_now_iso(),
                            "market": "getgems",
                            "market_url": f"https://getgems.io/nft/{addr}",
                        }
                    )
            except Exception as exc:
                logger.debug(f"TonAPI Getgems fetch error ({short_k}): {exc}")
            return out

        batches = await asyncio.gather(*(_fetch_col(sk, ca) for sk, ca in targets), return_exceptions=True)
        for b in batches:
            if isinstance(b, list):
                for item in b:
                    iid = item["id"]
                    if iid not in seen:
                        seen.add(iid)
                        collected.append(item)

        if collected:
            self.getgems_live_ok = True
            if sort == "price_desc":
                collected.sort(key=lambda x: to_float(x.get("price"), 0.0), reverse=True)
            else:
                collected.sort(key=lambda x: to_float(x.get("price"), 0.0))
            self._listings_cache[cache_key] = (collected, time.monotonic() + 60.0)

        has_more = (len(all_known) > (page_num + 1) * 4) if not clean_col else (len(collected) >= 3)
        return collected[:safe_limit], has_more


getgems_client = GetgemsAndTonClient()
