"""Multi-market price aggregator for Portals (LIVE), Getgems (LIVE), MRKT & Tonnel."""

from __future__ import annotations

import hashlib
import time
import urllib.parse
from typing import Any

import httpx
from loguru import logger

from backend.config import runtime_config
from backend.models import MarketPricePoint
from backend.services.getgems_client import KNOWN_GIFT_COLLECTION_ADDRESSES, getgems_client
from backend.services.portals_client import is_valid_uuid, portals_client, to_float

MARKET_FEES: dict[str, float] = {
    "portals": 5.0,
    "getgems": 5.0,
    "mrkt": 4.0,
    "tonnel": 2.5,
    "fragment": 5.0,
}


def _deterministic_spread(short_name: str, market: str, salt_bucket: int) -> float:
    """Deterministic live-anchored spread factor in [-0.075, +0.085] for non-auth markets."""
    raw = f"{short_name}:{market}:{salt_bucket}".encode("utf-8")
    digest = int(hashlib.sha256(raw).hexdigest()[:8], 16)
    # Map to [-0.075, +0.085]
    ratio = (digest % 1601) / 10000.0 - 0.075
    return ratio


class MultiMarketAggregator:
    """Aggregates real Portals & Getgems data with optional live MRKT/Tonnel credentials."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._external_cache: dict[str, tuple[float, float]] = {}

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(6.0, connect=3.0))
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def get_live_markets(self) -> list[str]:
        markets: list[str] = ["portals"]
        if getgems_client.getgems_live_ok or runtime_config.getgems_api_key:
            markets.append("getgems")
        if runtime_config.mrkt_init_data:
            markets.append("mrkt")
        if runtime_config.tonnel_init_data:
            markets.append("tonnel")
        return markets

    async def _try_mrkt_live_floor(self, short_name: str) -> float | None:
        init_data = runtime_config.mrkt_init_data
        if not init_data:
            return None
        cache_key = f"mrkt:{short_name}"
        now = time.monotonic()
        if cache_key in self._external_cache and now < self._external_cache[cache_key][1]:
            return self._external_cache[cache_key][0]
        try:
            client = self._get_client()
            resp = await client.get(
                "https://api.tgmrkt.io/api/v1/gifts/collections",
                headers={"Authorization": init_data},
            )
            if resp.status_code == 200:
                items = resp.json()
                if isinstance(items, list):
                    for col in items:
                        name = str(col.get("name") or "").lower().replace(" ", "")
                        floor_nano = to_float(col.get("floorPriceNanoTokens"), 0.0)
                        floor = round(floor_nano / 1e9, 2) if floor_nano > 10000 else floor_nano
                        if name and floor > 0:
                            self._external_cache[f"mrkt:{name}"] = (floor, now + 60.0)
                if cache_key in self._external_cache:
                    return self._external_cache[cache_key][0]
        except Exception as exc:
            logger.debug(f"MRKT live fetch skipped: {exc}")
        return None

    async def _try_tonnel_live_floor(self, short_name: str) -> float | None:
        init_data = runtime_config.tonnel_init_data
        if not init_data:
            return None
        cache_key = f"tonnel:{short_name}"
        now = time.monotonic()
        if cache_key in self._external_cache and now < self._external_cache[cache_key][1]:
            return self._external_cache[cache_key][0]
        try:
            client = self._get_client()
            resp = await client.post(
                "https://gifts2.tonnel.network/api/filterStats",
                json={"authData": init_data},
            )
            if resp.status_code == 200:
                payload = resp.json()
                data = payload.get("data") if isinstance(payload, dict) else None
                if isinstance(data, dict):
                    for k, v in data.items():
                        clean = str(k).lower().replace(" ", "")
                        floor = to_float((v or {}).get("floorPrice") if isinstance(v, dict) else v, 0.0)
                        if clean and floor > 0:
                            self._external_cache[f"tonnel:{clean}"] = (floor, now + 60.0)
                if cache_key in self._external_cache:
                    return self._external_cache[cache_key][0]
        except Exception as exc:
            logger.debug(f"Tonnel live fetch skipped: {exc}")
        return None

    async def get_market_prices_for_collection(
        self,
        short_name: str,
        portals_floor: float,
        getgems_stats_map: dict[str, dict[str, Any]] | None = None,
        *,
        number: int = 0,
        collection_name: str = "",
        item_id: str = "",
        col_id: str = "",
    ) -> list[MarketPricePoint]:
        """Return cross-market floor prices with accurate is_live flags and direct NFT deep-links."""
        short = short_name.strip().lower()
        base_floor = max(portals_floor, 0.5)
        bucket = int(time.time() // 600)

        points: list[MarketPricePoint] = []

        # 1. Portals (LIVE) — official Telegram Mini App deep-link format
        if is_valid_uuid(item_id):
            portals_url = f"https://t.me/portals_market_bot/market?startapp=gift_{item_id}"
        elif is_valid_uuid(col_id):
            portals_url = f"https://t.me/portals_market_bot/market?startapp=collection-{col_id}"
        else:
            portals_url = "https://t.me/portals_market_bot/market"

        points.append(
            MarketPricePoint(
                market="portals",
                floor_price=round(base_floor, 2),
                fee_percent=MARKET_FEES["portals"],
                is_live=portals_client.last_live_ok,
                url=portals_url,
            )
        )

        # 2. Getgems (LIVE if fetched via REST/GraphQL, otherwise live-anchored)
        gg_stat = (getgems_stats_map or {}).get(short)
        gg_addr = KNOWN_GIFT_COLLECTION_ADDRESSES.get(short, "")
        if number > 0 and gg_addr and "placeholder" not in gg_addr:
            gg_url = f"https://getgems.io/collection/{gg_addr}?filter=%7B%22search%22%3A%22{number}%22%7D"
        elif gg_addr and "placeholder" not in gg_addr:
            gg_url = f"https://getgems.io/collection/{gg_addr}"
        else:
            query_text = f"{collection_name or short} {number if number > 0 else ''}".strip()
            gg_url = f"https://getgems.io/search?q={urllib.parse.quote(query_text)}"

        if gg_stat and gg_stat.get("floor_price", 0) > 0:
            points.append(
                MarketPricePoint(
                    market="getgems",
                    floor_price=round(float(gg_stat["floor_price"]), 2),
                    fee_percent=MARKET_FEES["getgems"],
                    is_live=True,
                    url=gg_url,
                )
            )
        else:
            spread = _deterministic_spread(short, "getgems", bucket)
            points.append(
                MarketPricePoint(
                    market="getgems",
                    floor_price=round(max(0.2, base_floor * (1.0 + spread + 0.025)), 2),
                    fee_percent=MARKET_FEES["getgems"],
                    is_live=False,
                    url=gg_url,
                )
            )

        # 3. MRKT (LIVE if initData provided, else live-anchored with is_live=False)
        mrkt_url = f"https://t.me/mrkt/app?startapp={short}_{number}" if number > 0 else "https://t.me/mrkt/app"
        mrkt_live = await self._try_mrkt_live_floor(short)
        if mrkt_live and mrkt_live > 0:
            points.append(
                MarketPricePoint(
                    market="mrkt",
                    floor_price=round(mrkt_live, 2),
                    fee_percent=MARKET_FEES["mrkt"],
                    is_live=True,
                    url=mrkt_url,
                )
            )
        else:
            spread = _deterministic_spread(short, "mrkt", bucket)
            points.append(
                MarketPricePoint(
                    market="mrkt",
                    floor_price=round(max(0.2, base_floor * (1.0 + spread + 0.015)), 2),
                    fee_percent=MARKET_FEES["mrkt"],
                    is_live=False,
                    url=mrkt_url,
                )
            )

        # 4. Tonnel (LIVE if initData provided, else live-anchored with is_live=False)
        tonnel_url = (
            f"https://t.me/tonnel_network_bot/gift?startapp={short}_{number}"
            if number > 0
            else "https://t.me/tonnel_network_bot/gift"
        )
        tonnel_live = await self._try_tonnel_live_floor(short)
        if tonnel_live and tonnel_live > 0:
            points.append(
                MarketPricePoint(
                    market="tonnel",
                    floor_price=round(tonnel_live, 2),
                    fee_percent=MARKET_FEES["tonnel"],
                    is_live=True,
                    url=tonnel_url,
                )
            )
        else:
            spread = _deterministic_spread(short, "tonnel", bucket)
            points.append(
                MarketPricePoint(
                    market="tonnel",
                    floor_price=round(max(0.2, base_floor * (1.0 + spread - 0.02)), 2),
                    fee_percent=MARKET_FEES["tonnel"],
                    is_live=False,
                    url=tonnel_url,
                )
            )

        return points

    @staticmethod
    def build_market_floors_dict(points: list[MarketPricePoint]) -> dict[str, float]:
        return {p.market: p.floor_price for p in points}


multi_market = MultiMarketAggregator()
