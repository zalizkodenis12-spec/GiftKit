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
    "obsidian": "Obsidian",
}

_BLACK_KW = {
    "black", "onyx", "obsidian", "noir", "coal", "void", "eclipse", "ebony",
}
_GOLD_KW = {
    "gold", "golden", "amber", "yellow", "honey", "brass", "champagne",
    "sun", "solar", "mida", "crown", "luxury", "satin gold", "pure gold",
}
_WHITE_SILVER_KW = {
    "white", "silver", "platinum", "pearl", "ivory", "chrome", "diamond",
    "frost", "snow", "moon", "crystal", "marble",
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
# PART A — REGEX NICE-NUMBER & BACKGROUND SYMBOL (ICON) ANALYZERS
# ==============================================================================

_CULT_NUMBERS: set[int] = {
    7, 13, 21, 42, 69, 77, 88, 99, 100, 111, 222, 333, 404, 420, 555, 666, 777, 888, 999,
    1000, 1111, 1234, 1337, 2000, 2222, 3333, 4200, 4444, 5000, 5555, 6666, 6969,
    7777, 8888, 9999, 10000, 12345, 54321, 69420, 77777, 88888, 99999, 100000,
}

_SEQUENTIAL_RUNS: tuple[str, ...] = (
    "01234", "12345", "23456", "34567", "45678", "56789",
    "98765", "87654", "76543", "65432", "54321", "43210",
    "0123", "1234", "2345", "3456", "4567", "5678", "6789",
    "9876", "8765", "7654", "6543", "5432", "4321", "3210",
)

# Tier-1 high-demand background symbols (watermark icons on Telegram Gifts)
_TOP_SYMBOL_KEYWORDS: tuple[str, ...] = (
    "ton", "telegram", "diamond", "crystal", "crown", "bitcoin", "btc",
    "dollar", "money", "coin", "pepe", "frog", "skull", "dragon", "phoenix",
    "flame", "fire", "star", "heart", "rocket", "cat", "rose", "lightning",
    "bolt", "sword", "infinity", "moon", "gem", "gold", "durov", "king",
    "wings", "angel", "devil", "alien", "ufo", "clover", "spade", "shield",
    "key", "eye", "pyramid", "wolf", "lion", "shark", "tiger", "panda",
    "butterfly", "ghost", "spider", "bat", "chess", "420", "champagne",
)

# Semantic theme clusters for Symbol <-> Model/Collection synergy matching
_THEME_GROUPS: dict[str, set[str]] = {
    "love": {"heart", "love", "rose", "cupid", "kiss", "valentine", "romance", "locket", "ring", "bouquet", "flower", "tulip", "sakura", "cherry"},
    "wealth": {"ton", "telegram", "diamond", "crystal", "gem", "crown", "king", "queen", "gold", "golden", "money", "dollar", "bitcoin", "btc", "coin", "bank", "watch", "swiss", "ring", "signet", "cigar", "loot", "bag", "rich", "luxury", "bar", "ingot", "vault"},
    "dark": {"skull", "death", "ghost", "bat", "spider", "devil", "demon", "hell", "pumpkin", "witch", "reaper", "mask", "vampire", "coffin", "bone", "grave", "dark", "shadow", "phantom", "voodoo", "curse", "evil", "grim"},
    "space": {"star", "moon", "planet", "rocket", "ufo", "alien", "astronaut", "astral", "cosmic", "galaxy", "comet", "meteor", "sun", "solar", "eclipse", "saturn", "orbit", "nebula", "space", "shard"},
    "fire": {"flame", "fire", "dragon", "phoenix", "lightning", "bolt", "thunder", "sword", "blade", "spark", "inferno", "lava", "blaze", "volcano", "torch", "candle", "lighter"},
    "animal": {"cat", "kitty", "paw", "dog", "puppy", "pepe", "frog", "bear", "lion", "wolf", "shark", "tiger", "panda", "bunny", "rabbit", "duck", "bird", "owl", "fox", "snake", "monkey", "fish", "whale", "butterfly", "bee", "horse", "unicorn"},
    "party": {"cake", "cupcake", "candle", "champagne", "wine", "cocktail", "gift", "balloon", "cookie", "sweet", "candy", "lollipop", "ice", "cream", "party", "confetti", "star", "hat", "cap", "jelly"},
    "magic": {"crystal", "magic", "wand", "potion", "eye", "pyramid", "infinity", "angel", "wings", "clover", "luck", "lucky", "horseshoe", "key", "lock", "shield", "chess", "tarot", "rune", "mystic"},
}


def analyze_symbol_trait(
    symbol_name: str,
    model_name: str = "",
    collection_name: str = "",
    symbol_rarity: float = 2.0,
    symbol_floor: float = 0.0,
    collection_floor: float = 0.0,
) -> dict[str, Any]:
    """Evaluate background icon (symbol) appeal: thematic synergy, hype tier & real floor premium."""
    sym = (symbol_name or "").strip()
    if not sym:
        return {"symbol_bonus_percent": 0.0, "symbol_badge": None, "symbol_is_synergy": False}

    sym_low = sym.lower()
    ctx_low = f"{model_name} {collection_name}".lower()

    sym_words = {w for w in re.findall(r"[a-z0-9]+", sym_low) if len(w) >= 3}
    ctx_words = {w for w in re.findall(r"[a-z0-9]+", ctx_low) if len(w) >= 3}

    # 1. Exact or thematic Symbol <-> Model/Collection synergy (e.g. Heart + Rose, Diamond + Ring, Skull + Witch)
    direct_overlap = bool(sym_words & ctx_words)
    theme_overlap = False
    if not direct_overlap:
        for kw_set in _THEME_GROUPS.values():
            if any(k in sym_low for k in kw_set) and any(k in ctx_low for k in kw_set):
                theme_overlap = True
                break
    is_synergy = direct_overlap or theme_overlap

    # 2. Real market floor premium on Portals for this background symbol
    floor_premium_pct = 0.0
    if collection_floor > 0 and symbol_floor > collection_floor:
        floor_premium_pct = ((symbol_floor - collection_floor) / collection_floor) * 100.0

    # 3. Tier-1 universally popular collector symbols
    is_top_icon = any(kw in sym_low for kw in _TOP_SYMBOL_KEYWORDS)
    is_ultra_rare = 0.0 < symbol_rarity <= 0.55

    bonus = 0.0
    badge: str | None = None

    if is_synergy and (is_top_icon or floor_premium_pct >= 12.0 or is_ultra_rare):
        bonus = 11.0
        badge = f"Іконка в тему: {sym}"
    elif is_synergy:
        bonus = 8.5
        badge = f"Іконка в тему: {sym}"
    elif floor_premium_pct >= 20.0:
        bonus = 9.0
        badge = f"Топ іконка: {sym} (+{floor_premium_pct:.0f}%)"
    elif is_top_icon and (is_ultra_rare or floor_premium_pct >= 10.0):
        bonus = 8.0
        badge = f"Топ іконка: {sym}"
    elif is_top_icon:
        bonus = 5.0
        badge = f"Іконка: {sym}"
    elif is_ultra_rare:
        bonus = 6.0
        badge = f"Рідкісна іконка: {sym} ({symbol_rarity:.1f}%)"

    return {
        "symbol_bonus_percent": round(min(14.0, bonus), 1),
        "symbol_badge": badge,
        "symbol_is_synergy": is_synergy,
    }


def analyze_number_pattern(number: int) -> dict[str, Any]:
    """Evaluate collectible serial number patterns and return Fair Value bonus (up to +30%)."""
    if not isinstance(number, int) or number <= 0:
        return {
            "number_bonus_percent": 0.0,
            "number_badge": None,
            "number_pattern": None,
        }

    s = str(number)
    matches: list[tuple[str, float]] = []

    # 1. Cult / iconic collector numbers
    if number in _CULT_NUMBERS:
        matches.append(("Культовий номер", 22.0))

    # 2. Low mint tiers
    if number < 100:
        matches.append(("Топ-100", 26.0))
    elif number < 1000:
        matches.append(("Low Mint <1K", 16.0))
    elif number < 5000:
        matches.append(("Низький <5K", 7.0))

    # 3. 4+ or 3+ identical consecutive digits (7777, 777, 333, 000, 888, 17772)
    rep4 = re.search(r"(\d)\1{3,}", s)
    rep3 = re.search(r"(\d)\1{2,}", s)
    if rep4:
        matches.append((f"Четвірка {rep4.group(0)}", 24.0))
    elif rep3:
        matches.append((f"Повтор {rep3.group(0)}", 18.0))

    # 4. Palindrome / mirror (12321, 50405, 1221, 8448)
    if len(s) >= 3 and s == s[::-1]:
        matches.append(("Паліндром", 15.0))

    # 5. Sequential ladders (1234, 4321, 12345, 9876)
    for seq in _SEQUENTIAL_RUNS:
        if seq in s:
            matches.append((f"Послідовність {seq}", 15.0 if len(seq) >= 5 else 13.0))
            break

    # 6. Symmetric & repeating blocks (AABB, ABAB, ABCABC, AABBCC, AAABBB, AABCC like #33755)
    m_aabb = re.fullmatch(r"(\d)\1(\d)\2", s)
    m_abab = re.fullmatch(r"(\d)(\d)\1\2", s)
    m_abcabc = re.fullmatch(r"(\d)(\d)(\d)\1\2\3", s)
    m_aabbcc = re.fullmatch(r"(\d)\1(\d)\2(\d)\3", s)
    m_aaabbb = re.fullmatch(r"(\d)\1\1(\d)\2\2", s)
    if m_aaabbb and m_aaabbb.group(1) != m_aaabbb.group(2):
        matches.append(("Блок AAABBB", 18.0))
    elif m_abcabc:
        matches.append(("Блок ABCABC", 15.0))
    elif m_aabbcc:
        matches.append(("Блок AABBCC", 14.0))
    elif m_aabb and m_aabb.group(1) != m_aabb.group(2):
        matches.append(("Блок AABB", 12.0))
    elif m_abab and m_abab.group(1) != m_abab.group(2):
        matches.append(("Блок ABAB", 11.0))
    else:
        # Strict fullmatch on AABCC (#33755) or AAABB (#77722) — never partial search on #19911
        m_aabcc = re.fullmatch(r"(\d)\1(\d)(\d)\3", s)
        m_aaabb = re.fullmatch(r"(\d)\1\1(\d)\2", s)
        if m_aabcc and m_aabcc.group(1) != m_aabcc.group(3) and m_aabcc.group(1) != m_aabcc.group(2) and m_aabcc.group(2) != m_aabcc.group(3):
            matches.append(("Красивий блок", 9.0))
        elif m_aaabb and m_aaabb.group(1) != m_aaabb.group(2):
            matches.append(("Красивий блок", 9.0))

    # 7. Clean 2-digit numbers in 5+ digits: ONLY when symmetric/alternating (ABABA, AABAA, ABBBA) or ending with 000
    if len(s) >= 5 and len(set(s)) == 2:
        is_clean_two_digit = (
            s == s[::-1]
            or s.endswith("000")
            or bool(re.fullmatch(r"(\d)(\d)\1\2\1", s))
            or bool(re.fullmatch(r"(\d)\1\1(\d)\2|(\d)\3(\d)\4\4", s))
        )
        if is_clean_two_digit:
            matches.append(("2-цифровий номер", 11.0))

    # 8. Clean round numbers (1000, 5000, 12000, 500, 1500)
    if number >= 1000 and number % 1000 == 0:
        matches.append(("Круглий номер", 12.0))
    elif number >= 500 and number % 500 == 0:
        matches.append(("Круглий номер", 9.0))
    elif 100 <= number < 10000 and number % 100 == 0:
        matches.append(("Рівна сотня", 8.0))

    if not matches:
        return {
            "number_bonus_percent": 0.0,
            "number_badge": None,
            "number_pattern": None,
        }

    # Sort descending by bonus weight; deduplicate labels
    matches.sort(key=lambda item: item[1], reverse=True)
    primary_label, primary_bonus = matches[0]

    # Combine secondary distinct patterns gently, hard-capped at +30%
    total_bonus = primary_bonus
    secondary_labels: list[str] = []
    for lbl, b in matches[1:]:
        if lbl != primary_label:
            total_bonus += b * 0.35
            if len(secondary_labels) < 1:
                secondary_labels.append(lbl)

    total_bonus = round(min(30.0, total_bonus), 1)
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
    if v <= 0.16 or (v <= 0.20 and s <= 0.20):
        tags.add("black")
    if s < 0.17 and v >= 0.66:
        tags.add("white_silver")
    if 30.0 <= h_deg <= 58.0 and s >= 0.34 and v >= 0.46:
        tags.add("gold")
    if 95.0 <= h_deg <= 165.0 and s >= 0.24 and v <= 0.62:
        tags.add("green")
    if 250.0 <= h_deg <= 320.0 and s >= 0.24:
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
    """Evaluate luxury contrast whitelist strictly requiring matching FG + BG pairs."""
    _ = backdrop_name
    # Black backdrop + Gold foreground
    if "black" in bg_buckets and "gold" in fg_buckets:
        return "Чорний + Золото", 14.0

    # Black backdrop + White/Silver foreground
    if "black" in bg_buckets and "white_silver" in fg_buckets:
        return "Чорний + Білий", 12.0

    # Dark/Purple backdrop + Neon/Cyan/Blue foreground
    if ("purple" in bg_buckets or "black" in bg_buckets) and "neon_blue" in fg_buckets:
        return "Фіолетовий + Неон", 10.0

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
    """Synchronous Pillow 64x64 pixel analysis (runs in ~3-5ms) extracting true NFT colors."""
    model_name, backdrop_name, _ = _extract_attr_names(attributes)

    with Image.open(io.BytesIO(image_bytes)) as raw_img:
        img = raw_img.convert("RGB").resize((64, 64), Image.Resampling.BILINEAR)

    # Extract outer 7px border ring for true backdrop color
    pixels = list(img.getdata())
    bg_pixels: list[tuple[int, int, int]] = []
    for y in range(64):
        row_offset = y * 64
        if y < 7 or y >= 57:
            bg_pixels.extend(pixels[row_offset : row_offset + 64])
        else:
            bg_pixels.extend(pixels[row_offset : row_offset + 7])
            bg_pixels.extend(pixels[row_offset + 57 : row_offset + 64])

    bg_strip = Image.new("RGB", (len(bg_pixels), 1))
    bg_strip.putdata(bg_pixels)
    bg_dom_list = _quantize_dominant_colors(bg_strip, n_colors=4)
    bg_rgb = bg_dom_list[0][0]

    # Center 12..52 (40x40) box for full foreground gift inspection
    fg_crop = img.crop((12, 12, 52, 52))
    fg_all_pixels = list(fg_crop.getdata())
    # Keep only true gift pixels that clearly differ from the backdrop color
    obj_pixels = [px for px in fg_all_pixels if _rgb_distance(px, bg_rgb) >= 24.0]
    if len(obj_pixels) < 16:
        obj_pixels = fg_all_pixels

    obj_strip = Image.new("RGB", (len(obj_pixels), 1))
    obj_strip.putdata(obj_pixels)
    fg_dom_list = _quantize_dominant_colors(obj_strip, n_colors=8)
    fg_rgb = fg_dom_list[0][0]

    # Build top 4 REAL, visually distinct colors of the ENTIRE NFT (backdrop + true gift colors)
    swatch_rgbs: list[tuple[int, int, int]] = [bg_rgb]
    total_obj_count = max(sum(cnt for _, cnt in fg_dom_list), 1)
    # Pass 1: pick prominent, clearly distinct object colors (>= 4% of object area, dist >= 36)
    for candidate_rgb, cnt in fg_dom_list:
        if cnt / total_obj_count < 0.04:
            continue
        if all(_rgb_distance(candidate_rgb, existing) >= 36.0 for existing in swatch_rgbs):
            swatch_rgbs.append(candidate_rgb)
        if len(swatch_rgbs) >= 4:
            break
    # Pass 2: relax distance slightly if gift is monochrome / 2-tone
    if len(swatch_rgbs) < 3:
        for candidate_rgb, _ in fg_dom_list + bg_dom_list[1:]:
            if all(_rgb_distance(candidate_rgb, existing) >= 22.0 for existing in swatch_rgbs):
                swatch_rgbs.append(candidate_rgb)
            if len(swatch_rgbs) >= 3:
                break
    color_swatches = [_rgb_to_hex(c) for c in swatch_rgbs[:4]]

    # HSV conversion for backdrop & primary foreground
    bg_h, bg_s, bg_v = colorsys.rgb_to_hsv(bg_rgb[0] / 255.0, bg_rgb[1] / 255.0, bg_rgb[2] / 255.0)
    fg_h, fg_s, fg_v = colorsys.rgb_to_hsv(fg_rgb[0] / 255.0, fg_rgb[1] / 255.0, fg_rgb[2] / 255.0)
    hue_diff = _hue_diff_degrees(fg_h, bg_h)

    bg_lum = _rgb_luminance(bg_rgb)
    fg_lum = _rgb_luminance(fg_rgb)
    lum_diff = abs(fg_lum - bg_lum)

    # STRICT PIXEL-WIDE MONOCHROME DETECTOR:
    # Checks ALL foreground object pixels so multicolored objects (e.g. brown+green cookie on blue bg)
    # and grey/muddy backdrops are NEVER falsely tagged as Monochrome!
    total_obj = max(len(obj_pixels), 1)
    same_hue_px = 0
    same_hue_colored_px = 0
    achromatic_px = 0
    clashing_color_px = 0
    for r, g, b in obj_pixels:
        ph, ps, pv = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
        p_hue_diff = _hue_diff_degrees(ph, bg_h)
        if ps <= 0.16 or pv <= 0.16:
            achromatic_px += 1
            same_hue_px += 1  # neutral white/black highlights/shadows don't break monochrome
        elif p_hue_diff <= 16.0 and ps >= 0.20:
            same_hue_px += 1
            same_hue_colored_px += 1
        elif p_hue_diff > 24.0 and ps >= 0.20:
            clashing_color_px += 1

    same_hue_colored_ratio = same_hue_colored_px / total_obj
    achromatic_ratio = achromatic_px / total_obj
    clashing_ratio = clashing_color_px / total_obj

    bg_low = backdrop_name.strip().lower()
    is_grey_or_muddy_bg = (0.15 < bg_v and bg_s < 0.30)
    is_pitch_black_bg = (bg_v <= 0.15) or (bg_low in {"black", "onyx black", "obsidian"} and bg_v <= 0.22)

    # Case 1: True Pitch-Black Achromatic Monochrome (pitch-black bg + >=86% achromatic object + <=5% clashing)
    is_achromatic_mono = (
        not is_grey_or_muddy_bg
        and is_pitch_black_bg
        and achromatic_ratio >= 0.86
        and clashing_ratio <= 0.05
    )

    # Case 2: True Same-Color Monochrome (saturated colored bg + saturated same-hue fg + >=75% same-hue colored pixels + <=6% clashing)
    is_color_mono = (
        not is_grey_or_muddy_bg
        and bg_s >= 0.30
        and bg_v >= 0.22
        and fg_s >= 0.24
        and hue_diff <= 15.0
        and same_hue_colored_ratio >= 0.75
        and clashing_ratio <= 0.06
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

    # Clashing loud neon or mismatched saturated color check (e.g. blue book on green backdrop)
    is_clashing_neon = (
        (
            (fg_s > 0.65 and bg_s > 0.65 and 70.0 <= hue_diff <= 165.0)
            or (fg_s >= 0.35 and bg_s >= 0.30 and hue_diff >= 45.0 and clashing_ratio >= 0.35)
        )
        and not is_monochrome
        and whitelist_bonus == 0.0
    )

    # Aesthetic Computer Vision Score (1.0 - 10.0)
    score = 5.8

    # Silhouette readability (luminance contrast)
    if 0.22 <= lum_diff <= 0.78:
        score += 0.8
    elif 0.14 <= lum_diff < 0.22 or lum_diff > 0.78:
        score += 0.35
    elif lum_diff < 0.11:
        score -= 1.2

    # Harmony & Luxury bonuses
    if harmony_bonus >= 14.0:
        score += 2.1
    elif harmony_bonus >= 12.0:
        score += 1.8
    elif harmony_bonus >= 9.0:
        score += 1.4

    if is_monochrome and harmony_label != "Монохром":
        score += 0.4

    # Saturation balance & multi-color mismatch penalty
    avg_sat = (fg_s + bg_s) / 2.0
    if is_clashing_neon:
        score -= 1.6
    elif 0.12 <= avg_sat <= 0.66:
        score += 0.25

    if not is_monochrome and harmony_bonus == 0.0:
        if clashing_ratio >= 0.45:
            score -= 0.75
        elif clashing_ratio >= 0.25:
            score -= 0.4
        if is_grey_or_muddy_bg:
            score -= 0.4

    if lum_diff < 0.12 and is_clashing_neon:
        score -= 0.7

    # Plain items without monochrome or luxury harmony never exceed 7.1
    if not is_monochrome and not harmony_label:
        score = min(score, 7.1)

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
            "clashing_ratio": round(clashing_ratio, 3),
            "bg_hex": _rgb_to_hex(bg_rgb),
            "fg_hex": _rgb_to_hex(fg_rgb),
        },
    }


def _heuristic_fallback_from_attributes(attributes: list[Any] | None = None) -> dict[str, Any]:
    """Instant zero-network fallback if an image URL fails or times out."""
    model_name, backdrop_name, _ = _extract_attr_names(attributes)
    bg_buckets = _text_color_buckets(backdrop_name)
    fg_buckets = _text_color_buckets(model_name)

    is_monochrome = bool(
        len(bg_buckets) == 1 and len(fg_buckets) == 1 and bg_buckets == fg_buckets
    )
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

    # Never invent fake hardcoded colors when actual image pixels haven't been analyzed yet
    swatches: list[str] = []

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

    async def _fetch_image_bytes(self, photo_url: str, timeout: float = 4.5) -> bytes | None:
        url = (photo_url or "").strip()
        if not url or not url.startswith("http"):
            return None
        cached = self._image_bytes_cache.get(url)
        if cached is not None:
            self._image_bytes_cache.move_to_end(url)
            return cached

        candidates = [url]
        if ".large.jpg" in url:
            candidates.append(url.replace(".large.jpg", ".medium.jpg"))
        elif ".medium.jpg" in url:
            candidates.append(url.replace(".medium.jpg", ".large.jpg"))

        client = self._get_client()
        for candidate in candidates:
            try:
                resp = await client.get(candidate, timeout=timeout)
                if resp.status_code == 200 and resp.content and len(resp.content) > 100:
                    self._cache_put(self._image_bytes_cache, url, resp.content, 250)
                    return resp.content
            except Exception as exc:
                logger.debug(f"Image fetch failed for {candidate}: {exc}")
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
            "Ти — досвідчений фліпер та жорсткий оцінювач Telegram Gift NFT на TON. "
            f"Колекція: {collection_name or 'Telegram Gift'} #{number}. "
            f"Атрибути: Модель={model_name or 'N/A'}, Фон={backdrop_name or 'N/A'}, Фоновий символ (іконки на фоні)={symbol_name or 'N/A'}. "
            f"Ціна: {price or 'N/A'} TON, Fair Value: {fair_value or 'N/A'} TON. "
            "Суворо оціни візуал як реальний покупець:\n"
            "1) is_monochrome = true ЛИШЕ коли сам предмет і фон реально одного кольору/відтінку (чорний на чорному, синій на синьому, рожевий на рожевому тощо). Якщо предмет різнокольоровий або іншого кольору ніж фон — СТРОГО is_monochrome: false!\n"
            "2) Оціни чи пасують фонові іконки (символ) до подарунка та чи виглядає композиція стильно/дорого.\n"
            "3) Якщо кольори строкаті, несмачні або це звичайний пересічний лот — став visual_score <= 6.8 і worth_alert: false. "
            "Став visual_score >= 8.0 і worth_alert: true ТІЛЬКИ якщо картинка реально кайфова, чиста і продасться дорожче флора.\n"
            "Поверни ЛИШЕ валідний JSON без markdown і без емодзі: "
            '{"visual_score": 8.5, "is_monochrome": false, "worth_alert": true, '
            '"visual_tag": "Топ візуал" | "Стильний" | "Стандарт" | "Візуальний шум", '
            '"harmony_label": "коротка назва поєднання або null", '
            '"ai_vision_comment": "1-2 чітких речення українською чому це годний чи слабкий візуал для фліпу"}.'
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
                if "is_monochrome" in llm_parsed and isinstance(llm_parsed["is_monochrome"], bool):
                    combined["is_monochrome"] = llm_parsed["is_monochrome"]
                    if not llm_parsed["is_monochrome"] and combined.get("harmony_label") == "Монохром":
                        combined["harmony_label"] = None
                if "worth_alert" in llm_parsed and isinstance(llm_parsed["worth_alert"], bool):
                    combined["worth_alert"] = llm_parsed["worth_alert"]
                if llm_parsed.get("harmony_label"):
                    hl = str(llm_parsed["harmony_label"]).strip()
                    if hl.lower() not in {"null", "none", ""}:
                        combined["harmony_label"] = hl
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
