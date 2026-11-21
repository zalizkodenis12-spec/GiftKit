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
from backend.services.mrkt_client import mrkt_client
from backend.services.portals_client import is_valid_uuid, portals_client, to_float
from backend.services.tonnel_client import tonnel_client

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
        if mrkt_client.last_live_ok or mrkt_client.has_pushed_snapshot() or runtime_config.mrkt_init_data:
            markets.append("mrkt")
        if tonnel_client.last_live_ok or runtime_config.tonnel_init_data:
            markets.append("tonnel")
        return markets

    async def _try_mrkt_live_floor(self, short_name: str) -> float | None:
        if not runtime_config.mrkt_init_data and not mrkt_client.has_pushed_snapshot():
            return None
        return await mrkt_client.get_floor_price(short_name)

    async def _try_tonnel_live_floor(self, short_name: str) -> float | None:
        if not runtime_config.tonnel_init_data:
            return None
        return await tonnel_client.get_floor_price(short_name)

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
        mrkt_uuid = item_id[5:] if item_id.startswith("mrkt-") else (item_id if is_valid_uuid(item_id) else "")
        mrkt_url = (
            f"https://t.me/mrkt/app?startapp=gift_{mrkt_uuid}"
            if mrkt_uuid and item_id.startswith("mrkt-")
            else "https://t.me/mrkt/app"
        )
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
        tonnel_id = item_id[7:] if item_id.startswith("tonnel-") else ""
        tonnel_url = (
            f"https://t.me/tonnel_network_bot/gifts?startapp=gift_{tonnel_id}"
            if tonnel_id
            else "https://t.me/tonnel_network_bot/gifts"
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
