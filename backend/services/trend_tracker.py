"""Live 24h Backdrop & Color Trend Tracker powered by Portals trait floor premiums & official 80-backdrop catalog."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from backend.services.portals_client import portals_client

# Visual color swatches fallback for Telegram Gift backdrops
BACKDROP_SWATCH_MAP: dict[str, str] = {
    "onyx black": "#111318",
    "black": "#363738",
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
    "cyberpunk": "#858FF3",
    "electric purple": "#CA70C6",
    "royal blue": "#1D4ED8",
    "crimson": "#B91C1C",
    "burgundy": "#7F1D1D",
    "amber": "#D97706",
    "copper": "#B45309",
    "ivory white": "#F8FAFC",
    "neon blue": "#7596F9",
    "indigo dye": "#312E81",
    "lavender": "#B789E4",
    "mint green": "#7ECB82",
    "coral red": "#DA896B",
    "camo green": "#3F6212",
    "cobalt blue": "#6088CF",
    "aquamarine": "#60B1BA",
    "bronze": "#92400E",
    "chocolate": "#A46E58",
    "navy blue": "#6C9EDD",
    "dark lilac": "#581C87",
    "burnt sienna": "#9A3412",
    "celtic blue": "#45B8ED",
    "pacific cyan": "#5ABEA6",
}

_BASELINE_TRENDS: list[dict[str, Any]] = [
    {
        "name": "Onyx Black",
        "avg_premium_percent": 34.5,
        "collections_count": 12,
        "boost_percent": 13.5,
        "swatch_hex": "#111318",
        "center_hex": "#111318",
        "edge_hex": "#0B0C10",
        "sample_collections": ["Eternal Rose", "Plush Pepe", "Snoop Cigar"],
        "trend_label": "Тренд 24г: Onyx Black (+35%)",
    },
    {
        "name": "Black",
        "avg_premium_percent": 31.2,
        "collections_count": 10,
        "boost_percent": 12.5,
        "swatch_hex": "#363738",
        "center_hex": "#363738",
        "edge_hex": "#0E0F0F",
        "sample_collections": ["Eternal Rose", "Durov's Cap", "Loot Bag"],
        "trend_label": "Тренд 24г: Black (+31%)",
    },
    {
        "name": "Midnight Blue",
        "avg_premium_percent": 24.8,
        "collections_count": 9,
        "boost_percent": 10.0,
        "swatch_hex": "#172554",
        "center_hex": "#5C6985",
        "edge_hex": "#354057",
        "sample_collections": ["Eternal Rose", "Astral Shard", "Star Notepad"],
        "trend_label": "Тренд 24г: Midnight Blue (+25%)",
    },
    {
        "name": "Pure Gold",
        "avg_premium_percent": 27.4,
        "collections_count": 8,
        "boost_percent": 11.0,
        "swatch_hex": "#EAB308",
        "center_hex": "#CCAB41",
        "edge_hex": "#987B32",
        "sample_collections": ["Swiss Watch", "Signet Ring", "Snoop Cigar"],
        "trend_label": "Тренд 24г: Pure Gold (+27%)",
    },
    {
        "name": "Roman Silver",
        "avg_premium_percent": 19.6,
        "collections_count": 7,
        "boost_percent": 8.0,
        "swatch_hex": "#94A3B8",
        "center_hex": "#A3ABB5",
        "edge_hex": "#7C8591",
        "sample_collections": ["Swiss Watch", "Vintage Cigar", "Eternal Rose"],
        "trend_label": "Тренд 24г: Roman Silver (+20%)",
    },
]


def _swatch_for_backdrop(name: str, catalog: dict[str, dict[str, Any]] | None = None) -> tuple[str, str, str]:
    """Return (swatch_hex, center_hex, edge_hex) for a backdrop name."""
    low = name.strip().lower()
    if catalog and low in catalog:
        c = catalog[low]
        center_h = c.get("center_hex") or "#3B82F6"
        edge_h = c.get("edge_hex") or center_h
        return center_h, center_h, edge_h
    if low in BACKDROP_SWATCH_MAP:
        hx = BACKDROP_SWATCH_MAP[low]
        return hx, hx, hx
    for key, hx in BACKDROP_SWATCH_MAP.items():
        if key in low:
            return hx, hx, hx
    if "black" in low or "onyx" in low or "obsidian" in low or "night" in low:
        return "#14171F", "#14171F", "#0B0D12"
    if "gold" in low or "amber" in low or "yellow" in low or "honey" in low:
        return "#EAB308", "#EAB308", "#A16207"
    if "silver" in low or "platinum" in low or "grey" in low or "gray" in low or "steel" in low:
        return "#94A3B8", "#94A3B8", "#64748B"
    if "blue" in low or "sapphire" in low or "cobalt" in low or "navy" in low:
        return "#2563EB", "#2563EB", "#1D4ED8"
    if "green" in low or "emerald" in low or "pine" in low or "mint" in low or "jade" in low:
        return "#10B981", "#10B981", "#059669"
    if "purple" in low or "violet" in low or "lilac" in low or "indigo" in low or "lavender" in low:
        return "#7C3AED", "#7C3AED", "#5B21B6"
    if "red" in low or "crimson" in low or "ruby" in low or "rose" in low or "cherry" in low:
        return "#DC2626", "#DC2626", "#991B1B"
    if "cyan" in low or "aqua" in low or "teal" in low or "turquoise" in low:
        return "#06B6D4", "#06B6D4", "#0891B2"
    if "orange" in low or "copper" in low or "bronze" in low:
        return "#EA580C", "#EA580C", "#C2410C"
    return "#3B82F6", "#3B82F6", "#1D4ED8"


class TrendTracker:
    """Aggregates real-time Portals backdrop floor premiums across top liquid collections & all 80 backdrops."""

    def __init__(self) -> None:
        self._cache_payload: dict[str, Any] | None = None
        self._cache_expires: float = 0.0
        self._col_cache: dict[str, tuple[dict[str, Any], float]] = {}
        self._boost_lookup: dict[str, tuple[float, str]] = {
            item["name"].lower(): (float(item["boost_percent"]), str(item["trend_label"]))
            for item in _BASELINE_TRENDS
        }
        self._lock = asyncio.Lock()

    async def get_trends(
        self,
        force_refresh: bool = False,
        collection: str | None = None,
    ) -> dict[str, Any]:
        """Compute trending backdrops globally (all 80 official backdrops) or for a specific collection."""
        catalog = await portals_client.get_official_backdrops_catalog()
        col_short = (collection or "").strip().lower()
        if col_short and col_short != "all":
            return await self._get_collection_backdrops(col_short, catalog, force_refresh=force_refresh)

        now = time.monotonic()
        if not force_refresh and self._cache_payload and now < self._cache_expires:
            return self._cache_payload

        async with self._lock:
            now = time.monotonic()
            if not force_refresh and self._cache_payload and now < self._cache_expires:
                return self._cache_payload

            try:
                raw_cols = await portals_client.get_collections(limit=150, force_refresh=force_refresh)
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
                col_name_map = {c["short_name"]: str(c.get("name") or c["short_name"]) for c in sample_cols}
                filters_map = await portals_client.get_collection_filters(
                    short_names,
                    force_refresh=force_refresh,
                    col_name_map=col_name_map,
                )

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
                        supply = int(bg.get("supply") or 0)
                        if not bg_name:
                            continue

                        premium_pct = (
                            ((bg_floor - col_floor) / col_floor) * 100.0
                            if bg_floor > col_floor
                            else 0.0
                        )
                        capped_prem = min(max(0.0, premium_pct), 65.0)

                        key = bg_name.lower()
                        bucket = agg.setdefault(
                            key,
                            {
                                "name": bg_name,
                                "premiums": [],
                                "positive_premiums": [],
                                "all_collections": [],
                                "premium_collections": [],
                                "rarities": [],
                                "floors": [],
                                "supplies": [],
                            },
                        )
                        bucket["all_collections"].append(col["name"])
                        bucket["rarities"].append(rarity)
                        if bg_floor > 0:
                            bucket["floors"].append(bg_floor)
                        if supply > 0:
                            bucket["supplies"].append(supply)
                        if 0.3 <= rarity and 3.0 <= premium_pct <= 160.0:
                            bucket["premiums"].append(capped_prem)
                            bucket["positive_premiums"].append(premium_pct)
                            bucket["premium_collections"].append(col["name"])

                # Merge all 80 official Telegram backdrops from catalog + any backdrops found on Portals
                all_keys: list[str] = list(catalog.keys())
                for k in agg:
                    if k not in catalog:
                        all_keys.append(k)

                trending: list[dict[str, Any]] = []
                for key in all_keys:
                    cat_entry = catalog.get(key)
                    info = agg.get(key)
                    display_name = (
                        info["name"]
                        if info
                        else (cat_entry["name"] if cat_entry else key.title())
                    )
                    swatch_hex, center_hex, edge_hex = _swatch_for_backdrop(display_name, catalog)

                    if info and info["premiums"]:
                        prem_cols = info["premium_collections"]
                        col_count = len(prem_cols)
                        avg_prem = sum(info["premiums"]) / max(1, len(info["premiums"]))
                    elif info:
                        prem_cols = info["all_collections"]
                        col_count = len(prem_cols)
                        avg_prem = 0.0
                    else:
                        prem_cols = []
                        col_count = 0
                        avg_prem = 0.0

                    avg_prem_round = round(avg_prem, 1)
                    if avg_prem_round >= 10.0 and col_count >= 2:
                        raw_boost = 5.0 + ((avg_prem_round - 10.0) / 40.0) * 7.0 + min(3.5, col_count * 0.45)
                        boost_pct = round(max(5.0, min(15.0, raw_boost)), 1)
                        label = f"Тренд 24г: {display_name} (+{avg_prem_round:.0f}% у {col_count} кол.)"
                    elif avg_prem_round > 0:
                        boost_pct = round(min(4.5, max(1.0, avg_prem_round * 0.35)), 1)
                        label = f"Фон: {display_name} (+{avg_prem_round:.0f}%)"
                    else:
                        boost_pct = 0.0
                        label = f"Фон: {display_name} (Флор)"

                    avg_rarity = (
                        round(sum(info["rarities"]) / max(1, len(info["rarities"])), 2)
                        if info and info["rarities"]
                        else 1.5
                    )
                    min_floor = round(min(info["floors"]), 2) if info and info["floors"] else 0.0

                    trending.append(
                        {
                            "name": display_name,
                            "avg_premium_percent": avg_prem_round,
                            "collections_count": col_count or (len(info["all_collections"]) if info else 0),
                            "avg_rarity_percent": avg_rarity,
                            "rarity_percent": avg_rarity,
                            "floor_price": min_floor,
                            "boost_percent": boost_pct,
                            "swatch_hex": swatch_hex,
                            "center_hex": center_hex,
                            "edge_hex": edge_hex,
                            "sample_collections": (prem_cols or (info["all_collections"] if info else []))[:4],
                            "trend_label": label,
                        }
                    )

                trending.sort(
                    key=lambda item: (
                        item["avg_premium_percent"],
                        item["collections_count"],
                        item["name"],
                    ),
                    reverse=True,
                )

                is_live = bool(trending) and portals_client.last_live_ok
                if not trending:
                    trending = [dict(b) for b in _BASELINE_TRENDS]
                    is_live = False

                # Update fast O(1) lookup table for true high-premium backdrops
                new_lookup: dict[str, tuple[float, str]] = {}
                for item in trending:
                    if item["avg_premium_percent"] >= 10.0 and item["boost_percent"] >= 5.0:
                        new_lookup[item["name"].lower()] = (
                            float(item["boost_percent"]),
                            str(item["trend_label"]),
                        )
                if new_lookup:
                    self._boost_lookup = new_lookup

                payload = {
                    "trending_backdrops": trending,
                    "total_backdrops": len(trending),
                    "analyzed_collections": analyzed_collections,
                    "collection": None,
                    "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "is_live": is_live,
                }
                self._cache_payload = payload
                self._cache_expires = time.monotonic() + 600.0
                return payload
            except Exception as exc:
                logger.warning(f"TrendTracker refresh error, using cached/baseline trends: {exc}")
                if self._cache_payload:
                    return self._cache_payload
                return {
                    "trending_backdrops": [dict(b) for b in _BASELINE_TRENDS],
                    "total_backdrops": len(_BASELINE_TRENDS),
                    "analyzed_collections": 0,
                    "collection": None,
                    "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "is_live": False,
                }

    async def _get_collection_backdrops(
        self,
        short_name: str,
        catalog: dict[str, dict[str, Any]],
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        """Return ALL backdrops for a specific collection with real floor_price, rarity, supply & hex colors."""
        now = time.monotonic()
        cached = self._col_cache.get(short_name)
        if not force_refresh and cached and now < cached[1]:
            return cached[0]

        raw_cols = await portals_client.get_collections(limit=250, force_refresh=force_refresh)
        col = next((c for c in raw_cols if c.get("short_name") == short_name), None)
        col_name = str(col.get("name") or short_name.title()) if col else short_name.title()
        col_floor = float(col.get("floor_price") or 0.0) if col else 0.0

        filters_map = await portals_client.get_collection_filters(
            [short_name],
            force_refresh=force_refresh,
            col_name_map={short_name: col_name},
        )
        raw_backdrops = (filters_map.get(short_name) or {}).get("backdrops") or []

        items: list[dict[str, Any]] = []
        for bg in raw_backdrops:
            bg_name = str(bg.get("name") or "").strip()
            if not bg_name:
                continue
            bg_floor = round(float(bg.get("floor_price") or 0.0), 2)
            rarity = round(float(bg.get("rarity_percent") or 1.5), 2)
            supply = int(bg.get("supply") or 0)
            prem_pct = (
                round(((bg_floor - col_floor) / max(col_floor, 0.01)) * 100.0, 1)
                if col_floor > 0 and bg_floor > col_floor
                else 0.0
            )
            swatch_hex, center_hex, edge_hex = _swatch_for_backdrop(bg_name, catalog)
            boost_pct = round(min(15.0, max(0.0, prem_pct * 0.3)), 1)
            items.append(
                {
                    "name": bg_name,
                    "floor_price": bg_floor,
                    "collection_floor": round(col_floor, 2),
                    "rarity_percent": rarity,
                    "avg_rarity_percent": rarity,
                    "supply": supply,
                    "avg_premium_percent": prem_pct,
                    "boost_percent": boost_pct,
                    "collections_count": 1,
                    "sample_collections": [col_name],
                    "swatch_hex": swatch_hex,
                    "center_hex": center_hex,
                    "edge_hex": edge_hex,
                    "trend_label": (
                        f"{bg_name}: {bg_floor} TON (+{prem_pct:.0f}%)"
                        if prem_pct > 0
                        else f"{bg_name}: {bg_floor} TON"
                    ),
                }
            )

        items.sort(key=lambda x: (x["floor_price"], x["avg_premium_percent"]), reverse=True)
        payload = {
            "trending_backdrops": items,
            "total_backdrops": len(items),
            "analyzed_collections": 1,
            "collection": short_name,
            "collection_name": col_name,
            "collection_floor": round(col_floor, 2),
            "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "is_live": portals_client.last_live_ok,
        }
        self._col_cache[short_name] = (payload, now + 300.0)
        return payload

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
        for trend_key, val in self._boost_lookup.items():
            if len(trend_key) >= 4 and (trend_key in key or key in trend_key):
                return val
        return 0.0, None


trend_tracker = TrendTracker()
