"""Visual 1:1 Twins & Lookalike Finder Engine across all 5 TON Gift Marketplaces.

Given ANY gift reference (Telegram link t.me/nft/..., Fragment link, Getgems address/link,
'Collection #Number', 'Collection Model', listing ID, or explicit traits), resolves the target NFT,
scans Portals + MRKT + Tonnel + Getgems + Fragment in parallel, and ranks all visual twins
using exact model matching + perceptual CIELAB Delta-E color distance across all 80 official
Telegram Gift backdrops + symbol & monochrome harmony.
"""

from __future__ import annotations

import asyncio
import math
import re
import statistics
from typing import Any

import httpx
from loguru import logger

from backend.config import runtime_config
from backend.database import utc_now_iso
from backend.models import AnalyzedListing
from backend.services.fragment_client import fragment_client
from backend.services.getgems_client import getgems_client
from backend.services.mrkt_client import mrkt_client
from backend.services.portals_client import (
    gift_photo_url,
    is_valid_uuid,
    portals_client,
    to_int,
)
from backend.services.tonnel_client import tonnel_client

# Official Telegram Gifts radial backdrop palette [center_hex, edge_hex]
BACKDROP_HEX_PALETTE: dict[str, tuple[str, str]] = {
    "black": ("#363738", "#0E0F0F"),
    "onyx black": ("#4D5254", "#1E2124"),
    "obsidian": ("#3B3E45", "#15171A"),
    "midnight blue": ("#5C6E99", "#2E3A59"),
    "navy blue": ("#6C8EBF", "#3A537B"),
    "cobalt blue": ("#6088CF", "#2E4C8A"),
    "sapphire": ("#5C8AE6", "#2B4FA3"),
    "sky blue": ("#6CC2FF", "#3A8FD9"),
    "neon blue": ("#7596F9", "#3857C4"),
    "electric indigo": ("#9D7AF7", "#5E3AB8"),
    "electric purple": ("#C56DF0", "#7B34B5"),
    "lavender": ("#B794F6", "#7B5BC9"),
    "grape": ("#9D74C1", "#5D3C82"),
    "dark lilac": ("#9C74B3", "#5F3E73"),
    "fandango": ("#D66B9C", "#8F3161"),
    "raspberry": ("#E06B88", "#99324F"),
    "crimson": ("#DC5C68", "#8F2936"),
    "burgundy": ("#A34E5D", "#5E222E"),
    "rosewood": ("#B76B6B", "#6E3535"),
    "coral red": ("#EC8073", "#B0463C"),
    "strawberry": ("#E3717B", "#A33944"),
    "cherry red": ("#D95966", "#8C2733"),
    "tomato": ("#E86A58", "#A83B2D"),
    "tangerine": ("#F2A463", "#BA682B"),
    "amber": ("#DAB345", "#9E7317"),
    "satin gold": ("#D4B974", "#8F7334"),
    "old gold": ("#B5A462", "#73652E"),
    "desert sand": ("#D4B98C", "#8E734B"),
    "emerald": ("#68B884", "#2F7A4D"),
    "shamrock green": ("#6CC47E", "#338044"),
    "mint green": ("#7ED1A6", "#3F8E67"),
    "pistachio": ("#97AE7C", "#5C7544"),
    "hunter green": ("#78997B", "#405E45"),
    "pine green": ("#669984", "#31614E"),
    "aquamarine": ("#66C9C1", "#2E8780"),
    "turquoise": ("#5CC2D6", "#297E94"),
    "pacific cyan": ("#5AA7C2", "#2B6D85"),
    "steel grey": ("#97A2AC", "#5E6873"),
    "silver blue": ("#8EA5BD", "#546B82"),
    "roman silver": ("#A3A7B0", "#696D75"),
    "platinum": ("#B2B0A8", "#75736B"),
    "ivory white": ("#E3DDD1", "#ABA496"),
    "pure gold": ("#E5C25C", "#A68020"),
    "cyberpunk": ("#966BE8", "#4F2B9E"),
    "deep cyan": ("#4E9AA8", "#225F6E"),
    "burnt sienna": ("#C97A5C", "#85432B"),
    "celtic blue": ("#5485C9", "#285291"),
    "chestnut": ("#B07260", "#6E3E30"),
    "chocolate": ("#946854", "#573628"),
    "copper": ("#C48466", "#804A32"),
    "french blue": ("#598DC2", "#2B5B8C"),
    "french violet": ("#A36FD1", "#61388C"),
    "indigo dye": ("#537991", "#2B4B61"),
    "jade green": ("#58A883", "#276E4E"),
    "khaki green": ("#A3A675", "#676B3E"),
    "marine blue": ("#4E688A", "#263B57"),
    "mech purple": ("#9D7CE0", "#5B3E9E"),
    "mystic pearl": ("#C78DA3", "#824E63"),
    "orange": ("#ED995A", "#B56026"),
    "persian green": ("#4BA89B", "#226B61"),
    "plum": ("#9E628E", "#5E3052"),
    "purple": ("#A575D4", "#633B8F"),
    "ranger green": ("#758F78", "#415944"),
    "seafoam green": ("#7EC4A8", "#42856A"),
    "sky": ("#66B8F0", "#317DB8"),
    "vermilion": ("#E06F5B", "#9E3928"),
    "caramel": ("#D19462", "#8F582C"),
    "malachite": ("#58A97C", "#246B45"),
    "camo green": ("#7A8F6B", "#46573A"),
    "electric cyan": ("#5ED4E8", "#238CA3"),
    "indigo": ("#6872C9", "#343D8A"),
    "magenta": ("#D962A8", "#8F2968"),
    "maroon": ("#9C4858", "#571E2A"),
    "olive": ("#99A162", "#5F6632"),
    "peach": ("#F0A884", "#B86A48"),
    "pink": ("#EB8DB6", "#A84874"),
    "red": ("#DB5E5E", "#8F2929"),
    "teal": ("#4BA3A3", "#1F6363"),
    "violet": ("#9E72D9", "#5A358F"),
    "yellow": ("#E6C455", "#A6821E"),
    "gunmetal": ("#4A535C", "#1F252B"),
    "midnight": ("#3D4A6B", "#1A2238"),
    "cappuccino": ("#B5947B", "#73543E"),
    "battleship grey": ("#8C9298", "#555B61"),
    "pacific green": ("#59A68D", "#286954"),
    "lemongrass": ("#B2C263", "#738231"),
    "carrot juice": ("#EB8952", "#B05224"),
    "seal brown": ("#7A5446", "#42271D"),
    "saddle brown": ("#9C6644", "#5E381E"),
    "mahogany": ("#8C433B", "#4F1E18"),
    "baltic blue": ("#557D9E", "#294A66"),
}


def _hex_to_lab(hex_color: str) -> tuple[float, float, float]:
    """Convert #RRGGBB to perceptual CIELAB (L*, a*, b*) using D65 illuminant."""
    h = (hex_color or "#0098EA").strip().lstrip("#")
    if len(h) != 6:
        return (50.0, 0.0, 0.0)
    try:
        r = int(h[0:2], 16) / 255.0
        g = int(h[2:4], 16) / 255.0
        b = int(h[4:6], 16) / 255.0
    except ValueError:
        return (50.0, 0.0, 0.0)

    def _lin(c: float) -> float:
        return ((c + 0.055) / 1.055) ** 2.4 if c > 0.04045 else c / 12.92

    rl, gl, bl = _lin(r), _lin(g), _lin(b)
    x = (rl * 0.4124564 + gl * 0.3575761 + bl * 0.1804375) / 0.95047
    y = (rl * 0.2126729 + gl * 0.7151522 + bl * 0.0721750) / 1.00000
    z = (rl * 0.0193339 + gl * 0.1191920 + bl * 0.9503041) / 1.08883

    def _f(t: float) -> float:
        return t ** (1.0 / 3.0) if t > 0.008856 else (7.787 * t) + (16.0 / 116.0)

    fx, fy, fz = _f(x), _f(y), _f(z)
    return (116.0 * fy - 16.0, 500.0 * (fx - fy), 200.0 * (fy - fz))


_BACKDROP_LAB_CACHE: dict[str, tuple[tuple[float, float, float], tuple[float, float, float]]] = {
    k: (_hex_to_lab(c), _hex_to_lab(e)) for k, (c, e) in BACKDROP_HEX_PALETTE.items()
}


def _lookup_backdrop_lab(
    backdrop_name: str,
) -> tuple[tuple[float, float, float], tuple[float, float, float]] | None:
    key = (backdrop_name or "").strip().lower()
    if not key:
        return None
    if key in _BACKDROP_LAB_CACHE:
        return _BACKDROP_LAB_CACHE[key]
    for k, val in _BACKDROP_LAB_CACHE.items():
        if key in k or k in key:
            return val
    return None


def backdrop_delta_e(bg_a: str, bg_b: str) -> float:
    """Compute perceptual CIELAB color distance between two Telegram Gift backdrops."""
    a_low = (bg_a or "").strip().lower()
    b_low = (bg_b or "").strip().lower()
    if not a_low or not b_low:
        return 32.0
    if a_low == b_low:
        return 0.0

    lab_a = _lookup_backdrop_lab(a_low)
    lab_b = _lookup_backdrop_lab(b_low)
    if lab_a and lab_b:
        c1, e1 = lab_a
        c2, e2 = lab_b
        dc = math.sqrt((c1[0] - c2[0]) ** 2 + (c1[1] - c2[1]) ** 2 + (c1[2] - c2[2]) ** 2)
        de = math.sqrt((e1[0] - e2[0]) ** 2 + (e1[1] - e2[1]) ** 2 + (e1[2] - e2[2]) ** 2)
        return round(0.65 * dc + 0.35 * de, 2)

    # Word overlap fallback if an unseen backdrop name appears
    wa = set(re.findall(r"[a-z]+", a_low))
    wb = set(re.findall(r"[a-z]+", b_low))
    if wa & wb:
        return 16.0
    return 48.0


def _extract_traits(item: AnalyzedListing | dict[str, Any]) -> tuple[str, str, str]:
    attrs = item.attributes if isinstance(item, AnalyzedListing) else (item.get("attributes") or [])
    model = backdrop = symbol = ""
    for a in attrs:
        t = (a.type if hasattr(a, "type") else str(a.get("type") or "")).lower()
        v = (a.value if hasattr(a, "value") else str(a.get("value") or "")).strip()
        if t == "model" and not model:
            model = v
        elif t == "backdrop" and not backdrop:
            backdrop = v
        elif t == "symbol" and not symbol:
            symbol = v
    return model, backdrop, symbol


def _compute_visual_similarity(
    target: AnalyzedListing,
    candidate: AnalyzedListing,
    t_model: str,
    t_backdrop: str,
    t_symbol: str,
) -> tuple[int, str, str]:
    """Return (similarity_percent 0-100, match_tier_label, match_reason_uk)."""
    c_model, c_backdrop, c_symbol = _extract_traits(candidate)
    same_col = (target.short_name or "").lower() == (candidate.short_name or "").lower()
    if not same_col:
        return 0, "", ""

    same_model = bool(t_model and c_model and t_model.lower() == c_model.lower())
    same_symbol = bool(t_symbol and c_symbol and t_symbol.lower() == c_symbol.lower())
    same_backdrop = bool(t_backdrop and c_backdrop and t_backdrop.lower() == c_backdrop.lower())

    de = backdrop_delta_e(t_backdrop, c_backdrop) if (t_backdrop and c_backdrop) else 32.0

    # Also check real extracted pixel swatches if both listings have them
    swatch_bonus = 0
    if target.color_swatches and candidate.color_swatches:
        try:
            l1 = _hex_to_lab(target.color_swatches[0])
            l2 = _hex_to_lab(candidate.color_swatches[0])
            px_de = math.sqrt((l1[0] - l2[0]) ** 2 + (l1[1] - l2[1]) ** 2 + (l1[2] - l2[2]) ** 2)
            if px_de <= 10.0:
                swatch_bonus = 2
            elif px_de <= 18.0:
                swatch_bonus = 1
        except Exception:
            pass

    if same_model:
        if same_backdrop:
            score = 97 + (3 if same_symbol else swatch_bonus)
            score = min(100, score)
            reason = (
                "1 в 1: модель + фон + символ"
                if same_symbol
                else f"1 в 1: {c_model} · {c_backdrop}"
            )
            return score, "Двійник 1:1", reason

        if not t_backdrop or not c_backdrop:
            score = 84 + (2 if same_symbol else 0)
            return score, "Та сама модель", f"Модель {c_model}"

        if de <= 12.0:
            score = min(96, int(round(96 - (de / 12.0) * 4)) + (2 if same_symbol else 0))
            return score, "Майже 1 в 1", f"{c_model} · близький фон {c_backdrop}"
        if de <= 24.0:
            score = min(91, int(round(91 - ((de - 12.0) / 12.0) * 6)) + (2 if same_symbol else 0))
            return score, "Дуже схожий", f"{c_model} · схожий тон {c_backdrop}"
        if de <= 38.0:
            score = min(84, int(round(84 - ((de - 24.0) / 14.0) * 6)) + (1 if same_symbol else 0))
            return score, "Схожа палітра", f"{c_model} · фон {c_backdrop}"

        # Same exact 3D model, different backdrop
        score = max(68, int(round(77 - min(9.0, (de - 38.0) / 7.0))))
        return score, "Та сама модель", f"Та сама модель {c_model}"

    # Different model in same collection — only relevant if target has no model OR backdrop is virtually identical
    if not t_model:
        if same_backdrop:
            return 88, "Той самий фон", f"Фон {c_backdrop}"
        if de <= 14.0:
            return 80, "Схожий фон", f"Близький фон {c_backdrop}"
        return 66, "Та сама колекція", target.collection_name

    # Exact backdrop + monochrome/palette twin in same collection (secondary match when exact-model supply is small)
    if same_backdrop:
        score = 72 + (4 if same_symbol else 0) + (2 if target.is_monochrome and candidate.is_monochrome else 0)
        return min(77, score), "Той самий фон", f"Фон {c_backdrop} · {c_model}"
    if de <= 11.0 and target.is_monochrome and candidate.is_monochrome:
        return 68, "Схожий стиль", f"Монохром · {c_backdrop}"

    return 0, "", ""


async def _resolve_getgems_nft_via_tonapi(nft_addr: str) -> dict[str, Any] | None:
    """Resolve a Getgems NFT address (EQ.../UQ...) via official TonAPI v2."""
    clean = (nft_addr or "").strip()
    if not clean:
        return None
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(7.0, connect=3.5)) as client:
            resp = await client.get(
                f"https://tonapi.io/v2/nfts/{clean}",
                headers={"Accept": "application/json", "User-Agent": "GiftKit/2.0"},
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            if not isinstance(data, dict):
                return None
            meta = data.get("metadata") or {}
            name_full = str(meta.get("name") or "").strip()
            col_name = str((data.get("collection") or {}).get("name") or "").strip()
            number = 0
            m_num = re.search(r"#(\d+)", name_full)
            if m_num:
                number = int(m_num.group(1))
                if not col_name:
                    col_name = name_full.split("#")[0].strip()
            attrs: list[dict[str, Any]] = []
            for a in meta.get("attributes") or []:
                if not isinstance(a, dict):
                    continue
                tt = str(a.get("trait_type") or "").strip().lower()
                val = str(a.get("value") or "").strip()
                if tt in {"model", "backdrop", "symbol"} and val:
                    attrs.append({"type": tt, "value": val, "rarity_per_mille": 1.5})
            sale = data.get("sale") or {}
            price_nano = (sale.get("price") or {}).get("value")
            price = round(int(price_nano) / 1e9, 2) if price_nano else 0.0
            previews = data.get("previews") or []
            photo = str(meta.get("image") or "")
            if previews and isinstance(previews, list):
                photo = str(previews[-1].get("url") or photo)
            return {
                "collection_name": col_name,
                "number": number,
                "attributes": attrs,
                "price": price,
                "photo_url": photo,
                "market": "getgems",
                "market_url": f"https://getgems.io/nft/{clean}",
            }
    except Exception as exc:
        logger.debug(f"TonAPI single NFT lookup skipped: {exc}")
        return None


async def search_visual_twins(
    analytics_engine: Any,
    *,
    query: str = "",
    collection_hint: str = "",
    model_hint: str = "",
    backdrop_hint: str = "",
    symbol_hint: str = "",
    sort: str = "similarity",
    limit: int = 48,
) -> dict[str, Any]:
    """Resolve ANY gift input and find all 1:1 visual twins across Portals, MRKT, Tonnel, Getgems, Fragment."""
    raw_q = (query or "").strip()
    collections = await analytics_engine.get_collections_summary(limit=250)
    col_by_id = {c.id: c for c in collections}
    col_by_short = {c.short_name: c for c in collections}

    # --- STEP 1: Parse ANY URL / ID / free text to resolve the exact target NFT ---
    cleaned_q = raw_q
    forced_col = None
    forced_model = (model_hint or "").strip()
    forced_backdrop = (backdrop_hint or "").strip()
    forced_symbol = (symbol_hint or "").strip()
    resolved_target: AnalyzedListing | None = None

    if collection_hint:
        ch_short = re.sub(r"[^a-z0-9]", "", collection_hint.lower())
        forced_col = col_by_short.get(ch_short) or next(
            (c for c in collections if ch_short and (ch_short in c.short_name or ch_short in c.name.lower().replace(" ", ""))),
            None,
        )

    # Support Fragment links: https://fragment.com/gift/plushpepe-123
    m_frag = re.search(r"fragment\.com/gift/([A-Za-z0-9]+-\d+)", raw_q, re.IGNORECASE)
    if m_frag:
        cleaned_q = m_frag.group(1)

    # Support Getgems links: https://getgems.io/nft/EQ...
    m_gg = re.search(r"getgems\.io/nft/([A-Za-z0-9_\-]+)", raw_q, re.IGNORECASE)
    if m_gg:
        gg_info = await _resolve_getgems_nft_via_tonapi(m_gg.group(1))
        if gg_info and gg_info.get("collection_name"):
            cleaned_q = f"{gg_info['collection_name']} #{gg_info['number']}" if gg_info.get("number") else gg_info["collection_name"]
            for a in gg_info.get("attributes") or []:
                if a["type"] == "model" and not forced_model:
                    forced_model = a["value"]
                elif a["type"] == "backdrop" and not forced_backdrop:
                    forced_backdrop = a["value"]
                elif a["type"] == "symbol" and not forced_symbol:
                    forced_symbol = a["value"]

    # Support Portals direct links: startapp=gift_<uuid>
    m_portals_link = re.search(r"startapp=gift_([0-9a-fA-F\-]{32,36})", raw_q)
    if m_portals_link:
        cleaned_q = m_portals_link.group(1)

    # Check if query is "Collection Model [Backdrop]" (words without a serial number)
    has_number = bool(re.search(r"[\s#\-]\d+$", cleaned_q)) or is_valid_uuid(cleaned_q)
    if cleaned_q and not has_number and not forced_col:
        low_q = cleaned_q.lower()
        # Match longest collection name prefix/substring first (e.g. "Homemade Cake Sweet Bite")
        sorted_cols = sorted(collections, key=lambda c: len(c.name), reverse=True)
        for c in sorted_cols:
            cname_low = c.name.lower()
            if cname_low in low_q or c.short_name in re.sub(r"[^a-z0-9]", "", low_q):
                forced_col = c
                remainder = re.sub(re.escape(c.name), "", cleaned_q, flags=re.IGNORECASE).strip(" -#,")
                if remainder and not forced_model:
                    # Check if remainder contains a known backdrop name
                    rem_low = remainder.lower()
                    for bg_key in sorted(BACKDROP_HEX_PALETTE.keys(), key=len, reverse=True):
                        if bg_key in rem_low:
                            forced_backdrop = bg_key.title()
                            remainder = re.sub(re.escape(bg_key), "", remainder, flags=re.IGNORECASE).strip(" -#,")
                            break
                    if remainder:
                        forced_model = remainder
                break

    # Resolve the target NFT via X-Ray or direct collection+model search
    try:
        if forced_col and (forced_model or forced_backdrop) and not has_number:
            # Find a live exemplar of that exact Collection + Model (+ Backdrop)
            exemplars = await portals_client.search_nfts(
                limit=20,
                sort="price_asc",
                collection_ids=forced_col.id,
                filter_by_models=forced_model or None,
                filter_by_backdrops=forced_backdrop or None,
            )
            if not exemplars and forced_model:
                exemplars = await portals_client.search_nfts(
                    limit=20,
                    sort="price_asc",
                    collection_ids=forced_col.id,
                    search=forced_model,
                )
            if exemplars:
                filters_map, gg_stats = await asyncio.gather(
                    portals_client.get_collection_filters([forced_col.short_name]),
                    getgems_client.get_bulk_stats([forced_col.short_name]),
                )
                resolved_target = await analytics_engine.analyze_raw_listing(
                    exemplars[0], col_by_id, col_by_short, filters_map, gg_stats
                )
                if resolved_target:
                    await analytics_engine._enrich_listings_with_visuals([resolved_target])

        if not resolved_target and cleaned_q:
            # Try free-text search across Portals if no collection matched (e.g. user typed just a model name "Neon Lights")
            if not forced_col and not has_number:
                quick = await portals_client.search_nfts(limit=12, sort="price_asc", search=cleaned_q)
                if quick:
                    raw0 = quick[0]
                    cid0 = str(raw0.get("collection_id") or "")
                    c0 = col_by_id.get(cid0)
                    sn0 = c0.short_name if c0 else re.sub(r"[^a-z0-9]", "", str(raw0.get("name") or "").lower())
                    filters_map, gg_stats = await asyncio.gather(
                        portals_client.get_collection_filters([sn0]),
                        getgems_client.get_bulk_stats([sn0]),
                    )
                    resolved_target = await analytics_engine.analyze_raw_listing(
                        raw0, col_by_id, col_by_short, filters_map, gg_stats
                    )
                    if resolved_target:
                        await analytics_engine._enrich_listings_with_visuals([resolved_target])

            if not resolved_target:
                xray_res = await analytics_engine.xray_lookup(cleaned_q)
                item_dict = xray_res.get("item")
                if isinstance(item_dict, AnalyzedListing):
                    resolved_target = item_dict
                elif isinstance(item_dict, dict):
                    resolved_target = AnalyzedListing(**item_dict)
    except Exception as exc:
        logger.debug(f"Twins target resolution error for {raw_q!r}: {exc}")

    if not resolved_target:
        raise ValueError("Не вдалося знайти подарунок за цим запитом. Введіть посилання t.me/nft/..., назву + номер або модель.")

    t_model, t_backdrop, t_symbol = _extract_traits(resolved_target)
    if forced_model and not t_model:
        t_model = forced_model
    if forced_backdrop and not t_backdrop:
        t_backdrop = forced_backdrop
    if forced_symbol and not t_symbol:
        t_symbol = forced_symbol

    target_col = col_by_short.get(resolved_target.short_name) or col_by_id.get(resolved_target.collection_id) or forced_col
    col_id = target_col.id if target_col else resolved_target.collection_id
    col_name = target_col.name if target_col else resolved_target.collection_name
    col_short = target_col.short_name if target_col else resolved_target.short_name

    # --- STEP 2: Parallel multi-market sweep across ALL 5 marketplaces ---
    async def _fetch_portals_model() -> list[dict[str, Any]]:
        if not col_id:
            return []
        try:
            if t_model:
                rows = await portals_client.search_nfts(
                    limit=50,
                    sort="price_asc",
                    collection_ids=col_id,
                    filter_by_models=t_model,
                )
                if rows:
                    return rows
            return await portals_client.search_nfts(
                limit=50,
                sort="price_asc",
                collection_ids=col_id,
            )
        except Exception:
            return []

    async def _fetch_portals_backdrop() -> list[dict[str, Any]]:
        if not col_id or not t_backdrop:
            return []
        try:
            return await portals_client.search_nfts(
                limit=30,
                sort="price_asc",
                collection_ids=col_id,
                filter_by_backdrops=t_backdrop,
            )
        except Exception:
            return []

    async def _fetch_mrkt() -> list[dict[str, Any]]:
        if not runtime_config.mrkt_init_data and not mrkt_client.has_pushed_snapshot():
            return []
        try:
            rows, _ = await mrkt_client.search_nfts(
                collection_name=col_name,
                search=t_model or None,
                sort="price_asc",
                limit=30,
            )
            if not rows and t_model:
                rows, _ = await mrkt_client.search_nfts(
                    collection_name=col_name,
                    sort="price_asc",
                    limit=30,
                )
            return rows
        except Exception:
            return []

    async def _fetch_tonnel() -> list[dict[str, Any]]:
        if not runtime_config.tonnel_init_data:
            return []
        try:
            rows, _ = await tonnel_client.search_nfts(
                collection_name=col_name,
                search=t_model or None,
                sort="price_asc",
                limit=30,
            )
            if not rows and t_model:
                rows, _ = await tonnel_client.search_nfts(
                    collection_name=col_name,
                    sort="price_asc",
                    limit=30,
                )
            return rows
        except Exception:
            return []

    async def _fetch_getgems() -> list[dict[str, Any]]:
        try:
            rows, _ = await getgems_client.search_nfts(
                collection_short=col_short,
                limit=30,
            )
            return rows
        except Exception:
            return []

    async def _fetch_fragment() -> list[dict[str, Any]]:
        try:
            rows, _ = await fragment_client.search_nfts(
                collection_short=col_short,
                limit=30,
            )
            return rows
        except Exception:
            return []

    (
        p_model_rows,
        p_bg_rows,
        mrkt_rows,
        tonnel_rows,
        gg_rows,
        frag_rows,
        filters_map,
        gg_stats,
    ) = await asyncio.gather(
        _fetch_portals_model(),
        _fetch_portals_backdrop(),
        _fetch_mrkt(),
        _fetch_tonnel(),
        _fetch_getgems(),
        _fetch_fragment(),
        portals_client.get_collection_filters([col_short]),
        getgems_client.get_bulk_stats([col_short]),
    )

    # Deduplicate raw candidates across all 5 markets
    merged_raw: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, int, str]] = set()
    for row in [*p_model_rows, *mrkt_rows, *tonnel_rows, *gg_rows, *p_bg_rows, *frag_rows]:
        if not isinstance(row, dict):
            continue
        mkt = str(row.get("market") or "portals").lower()
        num = to_int(row.get("external_collection_number") or row.get("number"), 0)
        rid = str(row.get("id") or "")
        dedup_key = (mkt, num, rid if num == 0 else "")
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)
        merged_raw.append(row)

    # Analyze all candidates into full AnalyzedListing objects (identical to Scanner!)
    analyzed_candidates: list[AnalyzedListing] = []
    sem = asyncio.Semaphore(16)

    async def _analyze_one(raw_item: dict[str, Any]) -> AnalyzedListing | None:
        async with sem:
            return await analytics_engine.analyze_raw_listing(
                raw_item, col_by_id, col_by_short, filters_map, gg_stats
            )

    results = await asyncio.gather(*[_analyze_one(r) for r in merged_raw[:110]], return_exceptions=True)
    for res in results:
        if isinstance(res, AnalyzedListing):
            analyzed_candidates.append(res)

    if analyzed_candidates:
        await analytics_engine._enrich_listings_with_visuals(analyzed_candidates[:60])

    # --- STEP 3: Rank every candidate by true 1:1 visual similarity ---
    scored: list[tuple[int, str, str, AnalyzedListing]] = []
    for cand in analyzed_candidates:
        # If target was resolved via t.me/nft (xray-...) and we found its exact live listing, enrich target!
        if (
            cand.number == resolved_target.number
            and cand.short_name == resolved_target.short_name
        ):
            if str(resolved_target.id).startswith("xray-"):
                resolved_target = cand
                continue
            if cand.market == resolved_target.market:
                continue

        sim, tier, reason = _compute_visual_similarity(
            resolved_target, cand, t_model, t_backdrop, t_symbol
        )
        if sim >= 65:
            scored.append((sim, tier, reason, cand))

    # If we have plenty of exact-model twins (>= 8), keep only strong visual twins (same model or >= 78%)
    exact_model_count = sum(
        1
        for _, _, _, c in scored
        if t_model and (_extract_traits(c)[0].lower() == t_model.lower())
    )
    if exact_model_count >= 6:
        scored = [
            row for row in scored
            if row[0] >= 78 or (t_model and _extract_traits(row[3])[0].lower() == t_model.lower())
        ]

    # Sort according to user preference
    if sort == "price_asc":
        scored.sort(key=lambda r: (r[3].price, -r[0]))
    elif sort == "discount_desc":
        scored.sort(key=lambda r: (-r[3].discount_percent, -r[0], r[3].price))
    else:
        # Default: closest 1:1 visual look first, then cheapest price
        scored.sort(key=lambda r: (-r[0], r[3].price))

    trimmed = scored[: max(1, min(limit, 80))]

    # --- STEP 4: Compute Demand & Market Pricing Summary for this exact look ---
    twin_prices = [r[3].price for r in scored if r[3].price > 0]
    exact_1to1 = [r for r in scored if r[0] >= 92]
    close_visual = [r for r in scored if 82 <= r[0] < 92]
    markets_found = sorted({r[3].market for r in scored})

    min_price = round(min(twin_prices), 2) if twin_prices else round(resolved_target.collection_floor, 2)
    max_price = round(max(twin_prices), 2) if twin_prices else round(resolved_target.fair_value, 2)
    median_price = round(statistics.median(twin_prices), 2) if twin_prices else round(resolved_target.fair_value, 2)
    exact_prices = [r[3].price for r in exact_1to1 if r[3].price > 0]
    exact_floor = round(min(exact_prices), 2) if exact_prices else min_price

    sales_24h = resolved_target.sales_24h
    total_twins = len(scored)
    if total_twins <= 4 and sales_24h >= 12:
        demand_level = "rare"
        demand_label = "Дефіцитний вигляд"
    elif sales_24h >= 20 or len(markets_found) >= 3:
        demand_level = "high"
        demand_label = "Високий попит"
    elif total_twins > 0:
        demand_level = "medium"
        demand_label = "Стабільний попит"
    else:
        demand_level = "rare"
        demand_label = "Унікальний екземпляр"

    recommended_sell = round(max(min_price * 0.98, median_price * 0.94), 2) if twin_prices else round(resolved_target.fair_value, 2)

    if total_twins > 0:
        markets_str = ", ".join(m.upper() if m == "mrkt" else m.capitalize() for m in markets_found)
        demand_summary = (
            f"Знайдено {total_twins} схожих лотів на {markets_str} "
            f"(від {min_price:.2f} до {max_price:.2f} TON, медіана {median_price:.2f} TON). "
            f"Для швидкого продажу орієнтуйтесь на ~{recommended_sell:.2f} TON."
        )
    else:
        demand_summary = (
            f"Наразі точних двійників цієї комбінації у відкритому стакані не знайдено — "
            f"це рідкісний вигляд (орієнтир Fair Value: ~{resolved_target.fair_value:.2f} TON)."
        )

    # Serialize items as standard AnalyzedListing dicts + visual twin metadata
    items_payload: list[dict[str, Any]] = []
    for sim, tier, reason, lst in trimmed:
        d = lst.model_dump()
        d["similarity_percent"] = sim
        d["similarity_label"] = tier
        d["similarity_reason"] = reason
        items_payload.append(d)

    return {
        "query": raw_q,
        "target": resolved_target.model_dump(),
        "target_traits": {
            "collection": col_name,
            "short_name": col_short,
            "model": t_model,
            "backdrop": t_backdrop,
            "symbol": t_symbol,
        },
        "demand": {
            "total_twins": total_twins,
            "exact_count": len(exact_1to1),
            "close_count": len(close_visual),
            "markets_covered": markets_found,
            "min_price": min_price,
            "exact_floor": exact_floor,
            "median_price": median_price,
            "max_price": max_price,
            "recommended_sell": recommended_sell,
            "sales_24h": sales_24h,
            "liquidity_score": resolved_target.liquidity_score,
            "demand_level": demand_level,
            "demand_label": demand_label,
            "demand_summary": demand_summary,
        },
        "items": items_payload,
        "total": total_twins,
        "generated_at": utc_now_iso(),
    }
