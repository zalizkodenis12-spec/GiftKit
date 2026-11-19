"""Visual & Flipping Intelligence Analyzer for GiftKit.

Pure Python stdlib + Pillow + httpx (zero numpy dependency — fast Vercel Serverless cold starts).
Modules:
- Part A: Regex Nice-Number Analyzer (Low Mint, Repeating, Palindrome, AABB/ABAB/AABCC, Round)
- Part B: Pixel Color Harmony, Monochrome & Silhouette Readability Analyzer (48x48 Pillow CV)
- Part C: Optional Lightweight AI Vision LLM Evaluator (Gemini 2.0 Flash / OpenAI GPT-4o-mini)
"""

from __future__ import annotations

import asyncio
import base64
import colorsys
import io
import json
import math
import re
from collections import OrderedDict
from typing import Any

import httpx
from loguru import logger
from PIL import Image

from backend.config import runtime_config

# Premium high-liquidity backdrops consistently sought by Telegram Gift collectors
PREMIUM_BACKDROPS: dict[str, str] = {
    "onyx black": "Onyx Black",
    "black": "Black",
    "midnight blue": "Midnight Blue",
    "obsidian": "Obsidian",
    "pure gold": "Pure Gold",
    "satin gold": "Satin Gold",
    "old gold": "Old Gold",
    "platinum": "Platinum",
    "roman silver": "Roman Silver",
    "steel grey": "Steel Grey",
    "steel gray": "Steel Grey",
    "gunmetal": "Gunmetal",
}

_BLACK_KW = {
    "black", "onyx", "midnight", "obsidian", "noir", "shadow", "dark",
    "coal", "void", "eclipse", "phantom", "charcoal", "ebony", "gunmetal",
}
_GOLD_KW = {
    "gold", "golden", "amber", "yellow", "honey", "brass", "champagne",
    "sun", "solar", "mida", "crown", "luxury", "satin gold", "pure gold",
}
_WHITE_SILVER_KW = {
    "white", "silver", "platinum", "pearl", "ivory", "chrome", "diamond",
    "frost", "snow", "moon", "steel", "crystal", "marble", "roman silver",
}
_GREEN_KW = {
    "green", "emerald", "pine", "forest", "jade", "hunter", "olive",
    "shamrock", "malachite", "clover", "mint", "cypress",
}
_PURPLE_KW = {
    "purple", "violet", "amethyst", "indigo", "lavender", "cosmic",
    "royal", "grape", "mystic", "plum", "orchid", "astral",
}
_NEON_BLUE_KW = {
    "neon", "cyan", "electric", "laser", "cyber", "blue", "azure",
    "aqua", "ice", "sapphire", "plasma", "holo", "matrix", "cobalt",
}


# ==============================================================================
# PART A — REGEX NICE-NUMBER ANALYZER
# ==============================================================================


def analyze_number_pattern(number: int) -> dict[str, Any]:
    """Evaluate collectible serial number patterns and return Fair Value bonus (up to +28%)."""
    if not isinstance(number, int) or number <= 0:
        return {
            "number_bonus_percent": 0.0,
            "number_badge": None,
            "number_pattern": None,
        }

    s = str(number)
    matches: list[tuple[str, float]] = []

    # 1. Low mint tiers
    if number < 100:
        matches.append(("Топ-100", 25.0))
    elif number < 1000:
        matches.append(("Low Mint <1K", 15.0))
    elif number < 5000:
        matches.append(("Низький <5K", 6.0))

    # 2. 3+ identical consecutive digits (777, 333, 000, 888, 17772)
    rep_match = re.search(r"(\d)\1{2,}", s)
    if rep_match:
        matches.append((f"Повтор {rep_match.group(0)}", 18.0))

    # 3. Palindrome (12321, 50405, 1221, 777)
    if len(s) >= 3 and s == s[::-1]:
        matches.append(("Паліндром", 14.0))

    # 4. Repeating blocks & Round numbers
    m_aabb = re.fullmatch(r"(\d)\1(\d)\2", s)
    m_abab = re.fullmatch(r"(\d)(\d)\1\2", s)
    if m_aabb and m_aabb.group(1) != m_aabb.group(2):
        matches.append(("Блок AABB", 10.0))
    elif m_abab and m_abab.group(1) != m_abab.group(2):
        matches.append(("Блок ABAB", 9.0))
    else:
        # AABCC / ABBCC / AABBC / embedded AABB like #33755 or #14488
        m_aabcc = re.search(r"(\d)\1\d(\d)\2", s)
        m_pair_pair = re.search(r"(\d)\1(\d)\2", s)
        if m_aabcc and m_aabcc.group(1) != m_aabcc.group(2):
            matches.append(("Красивий блок", 8.0))
        elif m_pair_pair and m_pair_pair.group(1) != m_pair_pair.group(2):
            matches.append(("Красивий блок", 8.0))

    if (number >= 1000 and number % 1000 == 0) or (number >= 500 and number % 500 == 0):
        matches.append(("Круглий номер", 10.0))

    if not matches:
        return {
            "number_bonus_percent": 0.0,
            "number_badge": None,
            "number_pattern": None,
        }

    # Sort descending by bonus weight; deduplicate labels
    matches.sort(key=lambda item: item[1], reverse=True)
    primary_label, primary_bonus = matches[0]

    # Combine secondary distinct patterns gently, hard-capped at +28%
    total_bonus = primary_bonus
    secondary_labels: list[str] = []
    for lbl, b in matches[1:]:
        if lbl != primary_label:
            total_bonus += b * 0.35
            if len(secondary_labels) < 1:
                secondary_labels.append(lbl)

    total_bonus = round(min(28.0, total_bonus), 1)
    if secondary_labels:
        pattern_text = f"{primary_label} + {secondary_labels[0]} #{number}"
    else:
        pattern_text = f"{primary_label} #{number}"

    return {
        "number_bonus_percent": total_bonus,
        "number_badge": primary_label,
        "number_pattern": pattern_text,
    }


# ==============================================================================
# PART B — PIXEL COLOR HARMONY, MONOCHROME & SILHOUETTE CV ANALYZER
# ==============================================================================


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    r, g, b = (max(0, min(255, int(c))) for c in rgb)
    return f"#{r:02X}{g:02X}{b:02X}"


def _rgb_luminance(rgb: tuple[int, int, int]) -> float:
    return (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) / 255.0


def _rgb_distance(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)


def _hue_diff_degrees(h1: float, h2: float) -> float:
    diff = abs(h1 - h2)
    return min(diff, 1.0 - diff) * 360.0


def _quantize_dominant_colors(img: Image.Image, n_colors: int = 4) -> list[tuple[tuple[int, int, int], int]]:
    """Quantize an RGB Pillow Image to dominant (RGB, pixel_count) tuples."""
    if img.width == 0 or img.height == 0:
        return [((128, 128, 128), 1)]
    q = img.quantize(colors=n_colors, method=Image.Quantize.MEDIANCUT)
    palette = q.getpalette() or []
    counts = q.getcolors(maxcolors=max(16, n_colors * 2)) or []
    results: list[tuple[tuple[int, int, int], int]] = []
    for count, idx in sorted(counts, key=lambda x: x[0], reverse=True):
        base = int(idx) * 3
        if base + 2 < len(palette):
            rgb = (palette[base], palette[base + 1], palette[base + 2])
            results.append((rgb, int(count)))
    return results or [((128, 128, 128), 1)]


def _classify_hsv_bucket(rgb: tuple[int, int, int]) -> set[str]:
    """Map an RGB pixel to semantic collector color buckets."""
    h, s, v = colorsys.rgb_to_hsv(rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0)
    h_deg = h * 360.0
    tags: set[str] = set()
    if v < 0.24 or (v < 0.30 and s < 0.28):
        tags.add("black")
    if s < 0.17 and v >= 0.66:
        tags.add("white_silver")
    if 30.0 <= h_deg <= 58.0 and s >= 0.32 and v >= 0.44:
        tags.add("gold")
    if 95.0 <= h_deg <= 165.0 and s >= 0.24 and v <= 0.62:
        tags.add("green")
    if 250.0 <= h_deg <= 320.0 and s >= 0.22:
        tags.add("purple")
    if 172.0 <= h_deg <= 240.0 and s >= 0.42 and v >= 0.50:
        tags.add("neon_blue")
    return tags


def _extract_attr_names(attributes: list[Any] | None) -> tuple[str, str, str]:
    """Extract (model_name, backdrop_name, symbol_name) from list of dicts or TraitAttribute."""
    model_name = ""
    backdrop_name = ""
    symbol_name = ""
    for attr in attributes or []:
        if isinstance(attr, dict):
            atype = str(attr.get("type") or "").lower()
            val = str(attr.get("value") or "").strip()
        else:
            atype = str(getattr(attr, "type", "") or "").lower()
            val = str(getattr(attr, "value", "") or "").strip()
        if atype == "model":
            model_name = val
        elif atype == "backdrop":
            backdrop_name = val
        elif atype == "symbol":
            symbol_name = val
    return model_name, backdrop_name, symbol_name


def _text_color_buckets(text: str) -> set[str]:
    low = text.lower()
    tags: set[str] = set()
    if any(k in low for k in _BLACK_KW):
        tags.add("black")
    if any(k in low for k in _GOLD_KW):
        tags.add("gold")
    if any(k in low for k in _WHITE_SILVER_KW):
        tags.add("white_silver")
    if any(k in low for k in _GREEN_KW):
        tags.add("green")
    if any(k in low for k in _PURPLE_KW):
        tags.add("purple")
    if any(k in low for k in _NEON_BLUE_KW):
        tags.add("neon_blue")
    return tags


def _check_luxury_whitelist(
    bg_buckets: set[str],
    fg_buckets: set[str],
    backdrop_name: str,
) -> tuple[str | None, float]:
    """Evaluate luxury contrast whitelist from combined pixel & attribute buckets."""
    # Black + Gold (either direction)
    if ("black" in bg_buckets and "gold" in fg_buckets) or (
        "gold" in bg_buckets and "black" in fg_buckets
    ):
        return "Чорний + Золото", 14.0

    # Black + White/Silver
    if ("black" in bg_buckets and "white_silver" in fg_buckets) or (
        "white_silver" in bg_buckets and "black" in fg_buckets
    ):
        return "Чорний + Білий", 12.0

    # Dark Green + Gold/Silver
    if ("green" in bg_buckets and ("gold" in fg_buckets or "white_silver" in fg_buckets)) or (
        "green" in fg_buckets and ("gold" in bg_buckets or "white_silver" in bg_buckets)
    ):
        return "Зелений + Золото", 10.0

    # Purple/Dark + Neon/Cyan/Blue
    if (("purple" in bg_buckets or "black" in bg_buckets) and "neon_blue" in fg_buckets) or (
        "purple" in fg_buckets and "neon_blue" in bg_buckets
    ):
        return "Фіолетовий + Неон", 10.0

    # Popular premium backdrops
    bg_low = backdrop_name.strip().lower()
    if bg_low:
        for key, display in PREMIUM_BACKDROPS.items():
            if key == bg_low or key in bg_low:
                return f"Топ фон: {display}", 9.0

    return None, 0.0


def _score_to_tag(score: float) -> str:
    if score >= 8.0:
        return "Топ візуал"
    if score >= 6.8:
        return "Стильний"
    if score < 4.8:
        return "Візуальний шум"
    return "Стандарт"


def _build_vision_comment(
    *,
    visual_score: float,
    is_monochrome: bool,
    harmony_label: str | None,
    lum_diff: float,
    is_clashing_neon: bool,
    backdrop_name: str,
) -> str:
    """Generate crisp, natural Ukrainian trader commentary (zero emojis)."""
    if is_clashing_neon or visual_score < 4.8:
        return (
            "Слабка читабельність силуету та перенасичені контрасти — "
            "візуальний шум, краще купувати лише з великою знижкою до флора."
        )
    if harmony_label == "Чорний + Золото":
        return (
            "Преміальний контраст Чорний + Золото з чітким силуетом — "
            "колекційне поєднання з високим попитом і потенціалом фліпу +2–4 TON."
        )
    if harmony_label == "Чорний + Білий":
        return (
            "Класичний висококонтрастний Чорний + Білий стиль — "
            "чистий силует привертає покупців на вторинному ринку."
        )
    if is_monochrome:
        return (
            "Чіткий силует, гармонійний монохром у спокійній палітрі — "
            "високий шанс швидкого фліпу +1.5–3 TON вище флора."
        )
    if harmony_label and harmony_label.startswith("Топ фон:"):
        return (
            f"Ліквідний преміум-фон ({backdrop_name or harmony_label}) та збалансована композиція — "
            "стабільний попит серед фліперів."
        )
    if harmony_label:
        return (
            f"Вдале поєднання ({harmony_label}) із доброю читабельністю силуету — "
            "виглядає дорожче за стандартний флор."
        )
    if lum_diff >= 0.25 and visual_score >= 7.0:
        return (
            "Чистий контраст об'єкта та фону, приємна збалансована палітра — "
            "ліквідний лот для перепродажу."
        )
    if lum_diff < 0.14:
        return (
            "Силует частково зливається з фоном — візуальної премії майже немає, "
            "орієнтуйтесь на чистий дисконт до флора."
        )
    return (
        "Акуратний стандартний візуал без різких перекосів — "
        "робочий варіант для фліпу при вигідній ціні входу."
    )


def _analyze_image_bytes_sync(image_bytes: bytes, attributes: list[Any] | None = None) -> dict[str, Any]:
    """Synchronous Pillow 48x48 pixel analysis (runs in ~2-4ms)."""
    model_name, backdrop_name, _ = _extract_attr_names(attributes)

    with Image.open(io.BytesIO(image_bytes)) as raw_img:
        img = raw_img.convert("RGB").resize((48, 48), Image.Resampling.BILINEAR)

    # Extract outer 6px border ring for backdrop
    pixels = list(img.getdata())
    bg_pixels: list[tuple[int, int, int]] = []
    for y in range(48):
        row_offset = y * 48
        if y < 6 or y >= 42:
            bg_pixels.extend(pixels[row_offset : row_offset + 48])
        else:
            bg_pixels.extend(pixels[row_offset : row_offset + 6])
            bg_pixels.extend(pixels[row_offset + 42 : row_offset + 48])

    bg_strip = Image.new("RGB", (len(bg_pixels), 1))
    bg_strip.putdata(bg_pixels)
    bg_dom_list = _quantize_dominant_colors(bg_strip, n_colors=4)
    bg_rgb = bg_dom_list[0][0]

    # Center 10..38 (28x28) box for full foreground object inspection
    fg_crop = img.crop((10, 10, 38, 38))
    fg_all_pixels = list(fg_crop.getdata())
    # Keep only true object pixels that differ from the backdrop color
    obj_pixels = [px for px in fg_all_pixels if _rgb_distance(px, bg_rgb) >= 22.0]
    if len(obj_pixels) < 12:
        obj_pixels = fg_all_pixels

    obj_strip = Image.new("RGB", (len(obj_pixels), 1))
    obj_strip.putdata(obj_pixels)
    fg_dom_list = _quantize_dominant_colors(obj_strip, n_colors=4)
    fg_rgb = fg_dom_list[0][0]

    # Build top 3 clean, visually distinct hex swatches
    swatch_rgbs: list[tuple[int, int, int]] = [bg_rgb]
    for candidate_rgb, _ in fg_dom_list + bg_dom_list[1:]:
        if all(_rgb_distance(candidate_rgb, existing) >= 26.0 for existing in swatch_rgbs):
            swatch_rgbs.append(candidate_rgb)
        if len(swatch_rgbs) >= 3:
            break
    for candidate_rgb, _ in fg_dom_list + bg_dom_list:
        if len(swatch_rgbs) >= 3:
            break
        if candidate_rgb not in swatch_rgbs:
            swatch_rgbs.append(candidate_rgb)
    color_swatches = [_rgb_to_hex(c) for c in swatch_rgbs[:3]]

    # HSV conversion for backdrop & primary foreground
    bg_h, bg_s, bg_v = colorsys.rgb_to_hsv(bg_rgb[0] / 255.0, bg_rgb[1] / 255.0, bg_rgb[2] / 255.0)
    fg_h, fg_s, fg_v = colorsys.rgb_to_hsv(fg_rgb[0] / 255.0, fg_rgb[1] / 255.0, fg_rgb[2] / 255.0)
    hue_diff = _hue_diff_degrees(fg_h, bg_h)

    bg_lum = _rgb_luminance(bg_rgb)
    fg_lum = _rgb_luminance(fg_rgb)
    lum_diff = abs(fg_lum - bg_lum)

    # STRICT PIXEL-WIDE MONOCHROME DETECTOR:
    # Checks ALL foreground object pixels so multicolored objects (e.g. brown+green cookie on blue bg)
    # are NEVER falsely tagged as Monochrome!
    total_obj = max(len(obj_pixels), 1)
    same_hue_px = 0
    achromatic_px = 0
    clashing_color_px = 0
    for r, g, b in obj_pixels:
        ph, ps, pv = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
        p_hue_diff = _hue_diff_degrees(ph, bg_h)
        if ps <= 0.18 or pv <= 0.16:
            achromatic_px += 1
            same_hue_px += 1  # neutral white/black highlights/shadows don't break monochrome
        elif p_hue_diff <= 18.0:
            same_hue_px += 1
        elif p_hue_diff > 30.0 and ps >= 0.24:
            clashing_color_px += 1

    same_hue_ratio = same_hue_px / total_obj
    achromatic_ratio = achromatic_px / total_obj
    clashing_ratio = clashing_color_px / total_obj

    bg_is_achromatic = bg_s <= 0.15 or bg_v <= 0.16
    # Case 1: True Black/White/Grey Monochrome (neutral bg + >=82% neutral object)
    is_achromatic_mono = bg_is_achromatic and achromatic_ratio >= 0.82 and clashing_ratio <= 0.08
    # Case 2: True Same-Color Monochrome (colored bg + >=75% same hue + <=10% other colors + distinct fg)
    is_color_mono = (
        not bg_is_achromatic
        and bg_s >= 0.18
        and same_hue_ratio >= 0.75
        and clashing_ratio <= 0.10
        and achromatic_ratio < 0.75
        and hue_diff <= 20.0
    )
    is_monochrome = is_achromatic_mono or is_color_mono

    # Combine pixel buckets + attribute name buckets for Luxury Whitelist
    bg_buckets = _classify_hsv_bucket(bg_rgb) | _text_color_buckets(backdrop_name)
    fg_buckets = _classify_hsv_bucket(fg_rgb) | _text_color_buckets(model_name)
    # Also include second foreground swatch if strong
    if len(fg_dom_list) > 1:
        fg_buckets |= _classify_hsv_bucket(fg_dom_list[1][0])

    whitelist_label, whitelist_bonus = _check_luxury_whitelist(bg_buckets, fg_buckets, backdrop_name)

    harmony_label: str | None = None
    harmony_bonus = 0.0
    if whitelist_label and whitelist_bonus >= 12.0:
        harmony_label = whitelist_label
        harmony_bonus = whitelist_bonus
    elif is_monochrome:
        harmony_label = "Монохром"
        harmony_bonus = 12.0
    elif whitelist_label:
        harmony_label = whitelist_label
        harmony_bonus = whitelist_bonus

    # Clashing loud neon check
    is_clashing_neon = (
        fg_s > 0.65
        and bg_s > 0.65
        and 70.0 <= hue_diff <= 165.0
        and not is_monochrome
        and whitelist_bonus == 0.0
    )

    # Aesthetic Computer Vision Score (1.0 - 10.0)
    score = 6.2

    # Silhouette readability (luminance contrast)
    if 0.22 <= lum_diff <= 0.78:
        score += 1.2
    elif 0.14 <= lum_diff < 0.22 or lum_diff > 0.78:
        score += 0.5
    elif lum_diff < 0.11:
        score -= 1.3

    # Harmony & Luxury bonuses
    if harmony_bonus >= 14.0:
        score += 1.9
    elif harmony_bonus >= 12.0:
        score += 1.6
    elif harmony_bonus >= 9.0:
        score += 1.2

    if is_monochrome and harmony_label != "Монохром":
        score += 0.4

    # Saturation balance
    avg_sat = (fg_s + bg_s) / 2.0
    if 0.12 <= avg_sat <= 0.66:
        score += 0.35
    elif is_clashing_neon:
        score -= 1.9

    if lum_diff < 0.12 and is_clashing_neon:
        score -= 0.7

    visual_score = round(max(1.0, min(9.7, score)), 1)
    visual_tag = _score_to_tag(visual_score)
    ai_vision_comment = _build_vision_comment(
        visual_score=visual_score,
        is_monochrome=is_monochrome,
        harmony_label=harmony_label,
        lum_diff=lum_diff,
        is_clashing_neon=is_clashing_neon,
        backdrop_name=backdrop_name,
    )

    return {
        "visual_score": visual_score,
        "visual_tag": visual_tag,
        "is_monochrome": is_monochrome,
        "harmony_label": harmony_label,
        "harmony_bonus": harmony_bonus,
        "color_swatches": color_swatches,
        "ai_vision_comment": ai_vision_comment,
        "source": "cv_pixels",
        "metrics": {
            "luminance_contrast": round(lum_diff, 3),
            "hue_diff_deg": round(hue_diff, 1),
            "bg_hex": _rgb_to_hex(bg_rgb),
            "fg_hex": _rgb_to_hex(fg_rgb),
        },
    }


def _heuristic_fallback_from_attributes(attributes: list[Any] | None = None) -> dict[str, Any]:
    """Instant zero-network fallback if an image URL fails or times out."""
    model_name, backdrop_name, _ = _extract_attr_names(attributes)
    bg_buckets = _text_color_buckets(backdrop_name)
    fg_buckets = _text_color_buckets(model_name)

    is_monochrome = bool(bg_buckets and fg_buckets and (bg_buckets & fg_buckets))
    whitelist_label, whitelist_bonus = _check_luxury_whitelist(bg_buckets, fg_buckets, backdrop_name)

    harmony_label: str | None = None
    harmony_bonus = 0.0
    if whitelist_label and whitelist_bonus >= 12.0:
        harmony_label = whitelist_label
        harmony_bonus = whitelist_bonus
    elif is_monochrome:
        harmony_label = "Монохром"
        harmony_bonus = 12.0
    elif whitelist_label:
        harmony_label = whitelist_label
        harmony_bonus = whitelist_bonus

    score = 6.5
    if harmony_bonus >= 14.0:
        score = 8.8
    elif harmony_bonus >= 12.0:
        score = 8.4
    elif harmony_bonus >= 9.0:
        score = 7.7

    swatch_map = {
        "black": "#14161D",
        "gold": "#E5B94C",
        "white_silver": "#DCE3EE",
        "green": "#1D6B4F",
        "purple": "#6B42C6",
        "neon_blue": "#22C6F0",
    }
    swatches: list[str] = []
    for bucket in list(bg_buckets) + list(fg_buckets):
        hx = swatch_map.get(bucket)
        if hx and hx not in swatches:
            swatches.append(hx)
    for default_hex in ("#1A1E29", "#3B82F6", "#CBD5E1"):
        if len(swatches) >= 3:
            break
        if default_hex not in swatches:
            swatches.append(default_hex)

    visual_tag = _score_to_tag(score)
    comment = _build_vision_comment(
        visual_score=score,
        is_monochrome=is_monochrome,
        harmony_label=harmony_label,
        lum_diff=0.35,
        is_clashing_neon=False,
        backdrop_name=backdrop_name,
    )
    return {
        "visual_score": round(score, 1),
        "visual_tag": visual_tag,
        "is_monochrome": is_monochrome,
        "harmony_label": harmony_label,
        "harmony_bonus": harmony_bonus,
        "color_swatches": swatches[:3],
        "ai_vision_comment": comment,
        "source": "heuristic_attrs",
    }


class VisualAnalyzer:
    """Async visual analyzer with 600-item LRU cache and optional Gemini/OpenAI Vision."""

    def __init__(self, max_cache: int = 600) -> None:
        self._max_cache = max_cache
        self._pixel_cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._image_bytes_cache: OrderedDict[str, bytes] = OrderedDict()
        self._ai_cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(3.5, connect=2.0),
                headers={"User-Agent": "GiftKitVisualAnalyzer/1.0"},
                follow_redirects=True,
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def _cache_put(self, store: OrderedDict[str, Any], key: str, value: Any, limit: int) -> None:
        if key in store:
            store.move_to_end(key)
        store[key] = value
        while len(store) > limit:
            store.popitem(last=False)

    async def _fetch_image_bytes(self, photo_url: str, timeout: float = 3.5) -> bytes | None:
        url = (photo_url or "").strip()
        if not url or not url.startswith("http"):
            return None
        cached = self._image_bytes_cache.get(url)
        if cached is not None:
            self._image_bytes_cache.move_to_end(url)
            return cached

        client = self._get_client()
        try:
            resp = await client.get(url, timeout=timeout)
            if resp.status_code == 200 and resp.content and len(resp.content) > 100:
                self._cache_put(self._image_bytes_cache, url, resp.content, 250)
                return resp.content
        except Exception as exc:
            logger.debug(f"Image fetch failed for {url}: {exc}")
        return None

    async def analyze_image_pixels(
        self,
        photo_url: str,
        attributes: list[Any] | None = None,
        timeout: float = 3.5,
    ) -> dict[str, Any]:
        """Download image (LRU cached), analyze 48x48 Pillow foreground/backdrop harmony."""
        model_name, backdrop_name, _ = _extract_attr_names(attributes)
        cache_key = f"{photo_url}|{model_name.lower()}|{backdrop_name.lower()}"
        cached = self._pixel_cache.get(cache_key)
        if cached is not None:
            self._pixel_cache.move_to_end(cache_key)
            return dict(cached)

        img_bytes = await self._fetch_image_bytes(photo_url, timeout=timeout)
        if img_bytes:
            try:
                result = await asyncio.to_thread(_analyze_image_bytes_sync, img_bytes, attributes)
                self._cache_put(self._pixel_cache, cache_key, result, self._max_cache)
                return dict(result)
            except Exception as exc:
                logger.debug(f"Pillow pixel analysis error for {photo_url}: {exc}")

        fallback = _heuristic_fallback_from_attributes(attributes)
        self._cache_put(self._pixel_cache, cache_key, fallback, self._max_cache)
        return dict(fallback)

    async def analyze_fast(
        self,
        photo_url: str,
        attributes: list[Any] | None = None,
        timeout: float = 2.5,
    ) -> dict[str, Any]:
        """Fast bounded-timeout wrapper for batch scanner enrichment."""
        try:
            return await asyncio.wait_for(
                self.analyze_image_pixels(photo_url, attributes, timeout=timeout),
                timeout=timeout + 0.3,
            )
        except Exception:
            return _heuristic_fallback_from_attributes(attributes)

    # ==========================================================================
    # PART C — OPTIONAL LIGHTWEIGHT AI VISION LLM (GEMINI / OPENAI)
    # ==========================================================================

    @staticmethod
    def _parse_llm_json(raw_text: str) -> dict[str, Any] | None:
        cleaned = (raw_text or "").strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None

    async def evaluate_with_ai_vision(
        self,
        *,
        photo_url: str,
        collection_name: str = "",
        number: int = 0,
        attributes: list[Any] | None = None,
        price: float | None = None,
        fair_value: float | None = None,
    ) -> dict[str, Any]:
        """Run deep visual evaluation using Gemini 2.0 Flash, OpenAI gpt-4o-mini, or local CV."""
        cv_result = await self.analyze_image_pixels(photo_url, attributes, timeout=3.5)
        num_result = analyze_number_pattern(number) if number > 0 else {
            "number_bonus_percent": 0.0,
            "number_badge": None,
            "number_pattern": None,
        }

        gemini_key = runtime_config.gemini_api_key.strip()
        openai_key = runtime_config.openai_api_key.strip()
        ai_provider = "gemini" if gemini_key else ("openai" if openai_key else "cv_pixels")

        cache_key = f"{ai_provider}:{photo_url}:{collection_name}:{number}"
        cached_ai = self._ai_cache.get(cache_key)
        if cached_ai is not None:
            self._ai_cache.move_to_end(cache_key)
            return dict(cached_ai)

        combined = {
            **cv_result,
            **num_result,
            "source": "cv_pixels" if cv_result.get("source") == "cv_pixels" else cv_result.get("source", "cv_pixels"),
        }

        if ai_provider == "cv_pixels":
            return combined

        img_bytes = await self._fetch_image_bytes(photo_url, timeout=4.0)
        if not img_bytes:
            return combined

        # Downscale image to 256x256 JPEG to minimize token usage & latency
        try:
            def _prepare_b64(raw: bytes) -> str:
                with Image.open(io.BytesIO(raw)) as im:
                    im_rgb = im.convert("RGB")
                    im_rgb.thumbnail((256, 256), Image.Resampling.LANCZOS)
                    buf = io.BytesIO()
                    im_rgb.save(buf, format="JPEG", quality=82)
                    return base64.b64encode(buf.getvalue()).decode("ascii")

            b64_img = await asyncio.to_thread(_prepare_b64, img_bytes)
        except Exception as exc:
            logger.debug(f"AI Vision image encode skipped: {exc}")
            return combined

        model_name, backdrop_name, symbol_name = _extract_attr_names(attributes)
        prompt = (
            "Ти — професійний оцінювач Telegram Gift NFT на TON. "
            f"Колекція: {collection_name or 'Telegram Gift'} #{number}. "
            f"Атрибути: Модель={model_name or 'N/A'}, Фон={backdrop_name or 'N/A'}, Символ={symbol_name or 'N/A'}. "
            f"Ціна: {price or 'N/A'} TON, Fair Value: {fair_value or 'N/A'} TON. "
            "Оціни візуальну естетику, читабельність силуету, гармонію кольорів та колекційну привабливість для фліпу. "
            "Поверни ЛИШЕ валідний JSON без markdown і без емодзі: "
            '{"visual_score": 8.5, "visual_tag": "Топ візуал" | "Стильний" | "Стандарт" | "Візуальний шум", '
            '"harmony_label": "коротка назва поєднання або null", '
            '"ai_vision_comment": "1-2 чітких речення українською чому це гарний чи слабкий візуал для фліпу"}.'
        )

        llm_parsed: dict[str, Any] | None = None
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(12.0, connect=4.0)) as client:
                if ai_provider == "gemini":
                    payload = {
                        "contents": [
                            {
                                "parts": [
                                    {"text": prompt},
                                    {"inline_data": {"mime_type": "image/jpeg", "data": b64_img}},
                                ]
                            }
                        ],
                        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 250},
                    }
                    for model_id in ("gemini-2.5-flash", "gemini-3.8-flash"):
                        url = (
                            "https://generativelanguage.googleapis.com/v1beta/models/"
                            f"{model_id}:generateContent"
                        )
                        resp = await client.post(
                            url,
                            headers={"x-goog-api-key": gemini_key},
                            json=payload,
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            raw_txt = (
                                data.get("candidates", [{}])[0]
                                .get("content", {})
                                .get("parts", [{}])[0]
                                .get("text", "")
                            )
                            llm_parsed = self._parse_llm_json(raw_txt)
                            if llm_parsed:
                                break
                        else:
                            logger.warning(f"Gemini Vision ({model_id}) returned HTTP {resp.status_code}")

                elif ai_provider == "openai":
                    resp = await client.post(
                        "https://api.openai.com/v1/chat/completions",
                        headers={"Authorization": f"Bearer {openai_key}"},
                        json={
                            "model": "gpt-4o-mini",
                            "temperature": 0.2,
                            "max_tokens": 250,
                            "messages": [
                                {
                                    "role": "user",
                                    "content": [
                                        {"type": "text", "text": prompt},
                                        {
                                            "type": "image_url",
                                            "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"},
                                        },
                                    ],
                                }
                            ],
                        },
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        raw_txt = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                        llm_parsed = self._parse_llm_json(raw_txt)
                    else:
                        logger.warning(f"OpenAI Vision API returned HTTP {resp.status_code}")
        except Exception as exc:
            logger.warning(f"AI Vision ({ai_provider}) fallback to CV pixels: {exc}")

        if llm_parsed:
            try:
                ai_score = float(llm_parsed.get("visual_score", combined["visual_score"]))
                ai_score = round(max(1.0, min(10.0, ai_score)), 1)
                combined["visual_score"] = ai_score
                combined["visual_tag"] = str(llm_parsed.get("visual_tag") or _score_to_tag(ai_score))
                if llm_parsed.get("harmony_label"):
                    combined["harmony_label"] = str(llm_parsed["harmony_label"])
                if llm_parsed.get("ai_vision_comment"):
                    # Strip any stray emojis
                    comment_clean = re.sub(
                        r"[\U0001F300-\U0001FAFF\u2600-\u27BF]+", "", str(llm_parsed["ai_vision_comment"])
                    ).strip()
                    if comment_clean:
                        combined["ai_vision_comment"] = comment_clean
                combined["source"] = ai_provider
            except Exception as exc:
                logger.debug(f"Failed applying AI Vision response: {exc}")

        self._cache_put(self._ai_cache, cache_key, combined, 200)
        return dict(combined)


visual_analyzer = VisualAnalyzer()
