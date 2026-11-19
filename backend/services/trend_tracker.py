"""Live 24h Backdrop & Color Trend Tracker powered by Portals trait floor premiums."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from backend.services.portals_client import portals_client

# Visual color swatches for common Telegram Gift backdrops
BACKDROP_SWATCH_MAP: dict[str, str] = {
    "onyx black": "#111318",
    "black": "#0D0F14",
    "midnight blue": "#172554",
    "obsidian": "#1C1926",
    "pure gold": "#EAB308",
    "satin gold": "#D4AF37",
    "old gold": "#B8962E",
    "platinum": "#CBD5E1",
    "roman silver": "#94A3B8",
    "steel grey": "#475569",
    "steel gray": "#475569",
    "gunmetal": "#334155",
    "emerald": "#059669",
    "pine green": "#14532D",
    "hunter green": "#166534",
    "deep cyan": "#0E7490",
    "cyberpunk": "#7C3AED",
    "electric purple": "#6D28D9",
    "royal blue": "#1D4ED8",
    "crimson": "#B91C1C",
    "burgundy": "#7F1D1D",
    "amber": "#D97706",
    "copper": "#B45309",
    "ivory white": "#F8FAFC",
    "neon blue": "#0284C7",
    "indigo dye": "#312E81",
    "lavender": "#8B5CF6",
    "mint green": "#34D399",
    "coral red": "#EF4444",
    "camo green": "#3F6212",
    "cobalt blue": "#1E40AF",
    "aquamarine": "#14B8A6",
    "bronze": "#92400E",
    "chocolate": "#451A03",
    "navy blue": "#1E3A8A",
    "dark lilac": "#581C87",
    "burnt sienna": "#9A3412",
    "celtic blue": "#2563EB",
    "pacific cyan": "#06B6D4",
}

# Fallback baseline if Portals filters API is temporarily unavailable on cold start
_BASELINE_TRENDS: list[dict[str, Any]] = [
    {
        "name": "Onyx Black",
        "avg_premium_percent": 34.5,
        "collections_count": 12,
        "boost_percent": 13.5,
        "swatch_hex": "#111318",
        "sample_collections": ["Eternal Rose", "Plush Pepe", "Snoop Cigar"],
        "trend_label": "Тренд 24г: Onyx Black (+35%)",
    },
    {
        "name": "Black",
        "avg_premium_percent": 31.2,
        "collections_count": 10,
        "boost_percent": 12.5,
        "swatch_hex": "#0D0F14",
        "sample_collections": ["Eternal Rose", "Durov's Cap", "Loot Bag"],
        "trend_label": "Тренд 24г: Black (+31%)",
    },
    {
        "name": "Midnight Blue",
        "avg_premium_percent": 24.8,
        "collections_count": 9,
        "boost_percent": 10.0,
        "swatch_hex": "#172554",
        "sample_collections": ["Eternal Rose", "Astral Shard", "Star Notepad"],
        "trend_label": "Тренд 24г: Midnight Blue (+25%)",
    },
    {
        "name": "Pure Gold",
        "avg_premium_percent": 27.4,
        "collections_count": 8,
        "boost_percent": 11.0,
        "swatch_hex": "#EAB308",
        "sample_collections": ["Swiss Watch", "Signet Ring", "Snoop Cigar"],
        "trend_label": "Тренд 24г: Pure Gold (+27%)",
    },
    {
        "name": "Roman Silver",
        "avg_premium_percent": 19.6,
        "collections_count": 7,
        "boost_percent": 8.0,
        "swatch_hex": "#94A3B8",
        "sample_collections": ["Swiss Watch", "Vintage Cigar", "Eternal Rose"],
        "trend_label": "Тренд 24г: Roman Silver (+20%)",
    },
]


def _swatch_for_backdrop(name: str) -> str:
    low = name.strip().lower()
    if low in BACKDROP_SWATCH_MAP:
        return BACKDROP_SWATCH_MAP[low]
    for key, hx in BACKDROP_SWATCH_MAP.items():
        if key in low:
            return hx
    # Infer from common color words
    if "black" in low or "onyx" in low or "obsidian" in low or "night" in low:
        return "#14171F"
    if "gold" in low or "amber" in low or "yellow" in low or "honey" in low:
        return "#EAB308"
    if "silver" in low or "platinum" in low or "grey" in low or "gray" in low or "steel" in low:
        return "#94A3B8"
    if "blue" in low or "sapphire" in low or "cobalt" in low or "navy" in low:
        return "#2563EB"
    if "green" in low or "emerald" in low or "pine" in low or "mint" in low or "jade" in low:
        return "#10B981"
    if "purple" in low or "violet" in low or "lilac" in low or "indigo" in low or "lavender" in low:
        return "#7C3AED"
    if "red" in low or "crimson" in low or "ruby" in low or "rose" in low or "cherry" in low:
        return "#DC2626"
    if "cyan" in low or "aqua" in low or "teal" in low or "turquoise" in low:
        return "#06B6D4"
    if "orange" in low or "copper" in low or "bronze" in low:
        return "#EA580C"
    return "#3B82F6"


class TrendTracker:
    """Aggregates real-time Portals backdrop floor premiums across top liquid collections."""

    def __init__(self) -> None:
        self._cache_payload: dict[str, Any] | None = None
        self._cache_expires: float = 0.0
        self._boost_lookup: dict[str, tuple[float, str]] = {
            item["name"].lower(): (float(item["boost_percent"]), str(item["trend_label"]))
            for item in _BASELINE_TRENDS
        }
        self._lock = asyncio.Lock()

    async def get_trends(self, force_refresh: bool = False) -> dict[str, Any]:
        """Compute trending backdrops commanding real +15%..+60% premiums across top collections."""
        now = time.monotonic()
        if not force_refresh and self._cache_payload and now < self._cache_expires:
            return self._cache_payload

        async with self._lock:
            now = time.monotonic()
            if not force_refresh and self._cache_payload and now < self._cache_expires:
                return self._cache_payload

            try:
                raw_cols = await portals_client.get_collections(limit=120, force_refresh=force_refresh)
                # Pick top 24 most liquid collections by 24h volume & sales
                liquid_cols = [
                    c for c in raw_cols
                    if float(c.get("floor_price") or 0.0) >= 1.5
                ]
                liquid_cols.sort(
                    key=lambda c: (float(c.get("day_volume") or 0.0), int(c.get("sales_24h_count") or 0)),
                    reverse=True,
                )
                sample_cols = liquid_cols[:24]
                short_names = [c["short_name"] for c in sample_cols]
                filters_map = await portals_client.get_collection_filters(short_names, force_refresh=force_refresh)

                # Aggregate backdrop premiums
                agg: dict[str, dict[str, Any]] = {}
                analyzed_collections = 0

                for col in sample_cols:
                    sn = col["short_name"]
                    col_floor = float(col.get("floor_price") or 0.0)
                    if col_floor <= 0:
                        continue
                    traits = filters_map.get(sn) or {}
                    backdrops = traits.get("backdrops") or []
                    if not backdrops:
                        continue
                    analyzed_collections += 1

                    for bg in backdrops:
                        bg_name = str(bg.get("name") or "").strip()
                        bg_floor = float(bg.get("floor_price") or 0.0)
                        rarity = float(bg.get("rarity_percent") or 1.0)
                        if not bg_name or bg_floor <= col_floor:
                            continue
                        # Filter out ultra-rare <0.3% outlier traits
                        if 0 < rarity < 0.3:
                            continue

                        premium_pct = ((bg_floor - col_floor) / col_floor) * 100.0
                        # Capture meaningful real market premiums above floor (8%..135%),
                        # capping per-collection spike at 65% so outliers do not distort averages
                        if not (8.0 <= premium_pct <= 135.0):
                            continue
                        capped_prem = min(premium_pct, 65.0)

                        key = bg_name.lower()
                        bucket = agg.setdefault(
                            key,
                            {
                                "name": bg_name,
                                "premiums": [],
                                "raw_premiums": [],
                                "collections": [],
                                "rarities": [],
                            },
                        )
                        bucket["premiums"].append(capped_prem)
                        bucket["raw_premiums"].append(premium_pct)
                        bucket["collections"].append(col["name"])
                        bucket["rarities"].append(rarity)

                trending: list[dict[str, Any]] = []
                for key, info in agg.items():
                    col_count = len(info["collections"])
                    avg_prem = sum(info["premiums"]) / max(1, len(info["premiums"]))
                    # Require cross-collection consensus (>= 2 collections)
                    if analyzed_collections >= 5 and col_count < 2:
                        continue
                    if avg_prem < 10.0:
                        continue

                    # Dynamic 24h boost (+5% to +15%) scaled by real premium & cross-collection consensus
                    raw_boost = 5.0 + ((avg_prem - 10.0) / 40.0) * 7.0 + min(3.5, col_count * 0.45)
                    boost_pct = round(max(5.0, min(15.0, raw_boost)), 1)
                    avg_prem_round = round(avg_prem, 1)
                    label = f"Тренд 24г: {info['name']} (+{avg_prem_round:.0f}% у {col_count} кол.)"

                    trending.append(
                        {
                            "name": info["name"],
                            "avg_premium_percent": avg_prem_round,
                            "collections_count": col_count,
                            "avg_rarity_percent": round(
                                sum(info["rarities"]) / max(1, len(info["rarities"])), 2
                            ),
                            "boost_percent": boost_pct,
                            "swatch_hex": _swatch_for_backdrop(info["name"]),
                            "sample_collections": info["collections"][:4],
                            "trend_label": label,
                        }
                    )

                # Sort prioritizing consistent +15%..+60% real premiums across many collections
                def _trend_rank(item: dict[str, Any]) -> float:
                    in_sweet_spot = 1.15 if 15.0 <= item["avg_premium_percent"] <= 60.0 else 0.95
                    return (item["collections_count"] * 2.2 + item["avg_premium_percent"] * 0.35) * in_sweet_spot

                trending.sort(key=_trend_rank, reverse=True)

                is_live = bool(trending) and portals_client.last_live_ok
                if not trending:
                    trending = [dict(b) for b in _BASELINE_TRENDS]
                    is_live = False

                # Update fast O(1) lookup table
                new_lookup: dict[str, tuple[float, str]] = {}
                for item in trending[:25]:
                    new_lookup[item["name"].lower()] = (
                        float(item["boost_percent"]),
                        str(item["trend_label"]),
                    )
                self._boost_lookup = new_lookup

                payload = {
                    "trending_backdrops": trending[:16],
                    "analyzed_collections": analyzed_collections,
                    "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "is_live": is_live,
                }
                self._cache_payload = payload
                self._cache_expires = time.monotonic() + 600.0  # 10 min TTL
                return payload
            except Exception as exc:
                logger.warning(f"TrendTracker refresh error, using cached/baseline trends: {exc}")
                if self._cache_payload:
                    return self._cache_payload
                return {
                    "trending_backdrops": [dict(b) for b in _BASELINE_TRENDS],
                    "analyzed_collections": 0,
                    "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "is_live": False,
                }

    async def ensure_warm(self) -> None:
        """Warm trends cache once per TTL without blocking on errors."""
        if self._cache_payload and time.monotonic() < self._cache_expires:
            return
        try:
            await asyncio.wait_for(self.get_trends(), timeout=6.0)
        except Exception as exc:
            logger.debug(f"TrendTracker warm skipped: {exc}")

    def get_backdrop_boost(self, backdrop_name: str | None) -> tuple[float, str | None]:
        """Instant O(1) lookup returning (boost_percent, trend_label) for a backdrop."""
        if not backdrop_name:
            return 0.0, None
        key = backdrop_name.strip().lower()
        if key in self._boost_lookup:
            return self._boost_lookup[key]
        # Partial match for compound names like "Onyx Black Matte"
        for trend_key, val in self._boost_lookup.items():
            if len(trend_key) >= 4 and (trend_key in key or key in trend_key):
                return val
        return 0.0, None


trend_tracker = TrendTracker()
