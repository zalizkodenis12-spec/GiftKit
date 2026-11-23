"""Background Sniper Engine evaluating live listings against user rules."""

from __future__ import annotations

import asyncio
import html
import time
from typing import Any, Awaitable, Callable

import httpx
from loguru import logger

from backend.config import IS_VERCEL, base_settings, runtime_config
from backend.database import db
from backend.models import AnalyzedListing
from backend.services import auth_service
from backend.services.analytics_engine import analytics_engine
from backend.services.auth_service import DEFAULT_ADMIN_USER_ID
from backend.services.cloud_store import cloud_store
from backend.services.visual_analyzer import visual_analyzer
from backend.services.ws_manager import ws_manager


def _effective_reference_floor(listing: AnalyzedListing) -> float:
    """Use max(collection_floor, model_floor) so rare underpriced models (50-500 TON) aren't falsely rejected."""
    return max(float(listing.collection_floor or 0.0), float(listing.model_floor or 0.0))


def _collect_gem_reasons(listing: AnalyzedListing) -> list[str]:
    """Return crisp Ukrainian reasons why a listing is genuinely worth flipping."""
    ref_floor = _effective_reference_floor(listing)
    if (
        listing.discount_percent <= 0
        or listing.net_profit_ton <= 0
        or listing.verdict == "OVERPRICED"
        or (ref_floor > 0 and listing.price > ref_floor * 1.03)
    ):
        return []

    at_floor = ref_floor <= 0 or listing.price <= ref_floor * 1.03
    reasons: list[str] = []

    # 1. Real Monochrome / Aesthetic Harmony at or below floor
    if listing.is_monochrome and listing.visual_score >= 6.2 and at_floor:
        reasons.append("Монохром")
    elif listing.harmony_label and listing.visual_score >= 7.2 and at_floor:
        reasons.append(listing.harmony_label)

    # 2. Valuable Nice Number (e.g. #15550, #19091, #777, #8888) at floor with positive profit
    if listing.number_bonus_percent >= 15.0 and at_floor:
        reasons.append(listing.number_pattern or f"Топ номер #{listing.number}")
    elif listing.number_bonus_percent >= 10.0 and listing.visual_score >= 6.0 and at_floor:
        reasons.append(listing.number_pattern or f"Красивий номер #{listing.number}")

    # 3. Rare background icon (symbol) at floor
    if listing.symbol_badge and listing.symbol_bonus_percent >= 10.0 and at_floor:
        reasons.append(listing.symbol_badge)
    elif listing.symbol_badge and listing.symbol_bonus_percent >= 8.0 and listing.visual_score >= 6.2 and at_floor:
        reasons.append(listing.symbol_badge)

    # 4. Underpriced below collection or model floor
    if (
        ref_floor > 0
        and listing.price <= ref_floor * 0.94
        and listing.discount_percent >= 12.0
    ):
        pct_below = round((1.0 - listing.price / ref_floor) * 100.0, 1)
        label_base = "Нижче флора моделі" if listing.model_floor > listing.collection_floor * 1.05 else "Нижче флора"
        reasons.append(f"{label_base} (-{pct_below}%)")

    # 5. Pure top visual aesthetic at floor
    if listing.visual_score >= 7.8 and at_floor and not reasons:
        reasons.append(f"Топ візуал {listing.visual_score:.1f}/10")

    return reasons


def format_telegram_alert_html(listing: AnalyzedListing, rule_name: str = "Снайпер PRO") -> str:
    """Format crisp zero-emoji Telegram HTML alert card matching Mini App preview."""
    title = html.escape(f"{listing.collection_name} #{listing.number}")
    rule_esc = html.escape(rule_name)
    mode_tag = "DRY RUN" if runtime_config.dry_run else "LIVE"

    attrs_lines: list[str] = []
    for attr in listing.attributes:
        label_map = {"model": "Модель", "backdrop": "Фон", "symbol": "Символ"}
        lbl = label_map.get(attr.type, attr.type)
        attrs_lines.append(
            f"  - {lbl}: <b>{html.escape(attr.value)}</b> ({attr.rarity_percent}% | флор {attr.trait_floor} TON)"
        )
    attrs_block = "\n".join(attrs_lines) if attrs_lines else "  - Атрибути: Стандартні"

    sales_block = ", ".join(f"{s.price} TON" for s in listing.recent_sales[:3]) or f"{listing.collection_floor} TON"

    # Visual & harmony line (zero emojis)
    visual_details: list[str] = []
    if listing.is_monochrome:
        visual_details.append("Монохром")
    if listing.harmony_label and listing.harmony_label != "Монохром":
        visual_details.append(listing.harmony_label)
    if not visual_details and listing.visual_tag:
        visual_details.append(listing.visual_tag)
    visual_suffix = f" ({html.escape(' / '.join(visual_details))})" if visual_details else ""
    visual_line = f"\n<b>Візуал:</b> <b>{listing.visual_score:.1f}/10</b>{visual_suffix}"

    # Nice number line
    number_text = listing.number_pattern or (
        f"{listing.number_badge} #{listing.number}" if listing.number_badge else None
    )
    number_bonus_txt = f" (+{listing.number_bonus_percent:.0f}%)" if listing.number_bonus_percent > 0 else ""
    badge_line = (
        f"\n<b>Красивий номер:</b> {html.escape(number_text)}{number_bonus_txt}"
        if number_text
        else ""
    )

    # Background symbol (icon) line
    symbol_bonus_txt = f" (+{listing.symbol_bonus_percent:.0f}%)" if listing.symbol_bonus_percent > 0 else ""
    symbol_line = (
        f"\n<b>Фонова іконка:</b> {html.escape(listing.symbol_badge)}{symbol_bonus_txt}"
        if listing.symbol_badge
        else ""
    )

    # Exact reason why this deal passed the strict filter
    reasons = _collect_gem_reasons(listing)
    reasons_line = (
        f"\n<b>Чому годний:</b> {html.escape(' + '.join(reasons[:3]))}"
        if reasons
        else ""
    )

    # 24h Trend line
    trend_line = ""
    if listing.trend_label:
        trend_line = f"\n<b>Тренд 24г:</b> {html.escape(listing.trend_label)} (+{listing.trend_boost_percent:.0f}%)"

    combo_line = (
        f"\n<b>Рідкісне комбо:</b> {html.escape(listing.combo_label)}"
        if listing.is_rare_combo and listing.combo_label
        else ""
    )
    thin_line = (
        f"\n<b>Тонкий стакан:</b> {html.escape(listing.thin_floor_warning)}"
        if listing.thin_floor_warning
        else ""
    )
    vision_note = (
        f"\n<i>Оцінка візуалу: {html.escape(listing.ai_vision_comment)}</i>"
        if listing.ai_vision_comment
        else ""
    )

    return (
        f"<b>СНАЙПЕР-СИГНАЛ [{mode_tag}]</b>\n"
        f"Правило: <i>{rule_esc}</i>{reasons_line}\n\n"
        f"<b>{title}</b> ({listing.market.upper()})\n"
        f"Ціна лота: <b>{listing.price} TON</b>\n"
        f"Флор колекції: <b>{listing.collection_floor} TON</b> | Флор моделі: <b>{listing.model_floor} TON</b>\n"
        f"Справедлива ціна (Fair Value): <b>{listing.fair_value} TON</b> (знижка <b>{listing.discount_percent:+.1f}%</b>)\n"
        f"Чистий профіт після комісій: <b>{listing.net_profit_ton:+.2f} TON ({listing.net_profit_percent:+.1f}%)</b> -> продаж на <b>{listing.best_sell_market.upper()}</b>\n"
        f"Ліквідність: <b>{listing.liquidity_score}/100</b> | Продажів 24г: <b>{listing.sales_24h}</b>\n"
        f"Останні продажі: <code>{sales_block}</code>"
        f"{visual_line}{badge_line}{symbol_line}{trend_line}{combo_line}{thin_line}{vision_note}\n\n"
        f"<b>Трейт-аналіз:</b>\n{attrs_block}\n\n"
        f"Вердикт: <b>{html.escape(listing.verdict_label)}</b>"
    )


class SniperEngine:
    """Evaluates live analyzed listings against active DB sniper rules."""

    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self._seen_keys: set[str] = set()
        self._last_rule_alert_ts: dict[int, float] = {}
        self._send_tg_alert: Callable[..., Awaitable[bool]] | None = None

    def register_telegram_sender(
        self, sender: Callable[..., Awaitable[bool]]
    ) -> None:
        self._send_tg_alert = sender

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="sniper_engine_loop")
        logger.info("SniperEngine started")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    @staticmethod
    def _listing_matches_rule(listing: AnalyzedListing, rule: dict[str, Any]) -> bool:
        if not rule.get("enabled", True):
            return False

        col_filter = (rule.get("collection_short_name") or "").strip().lower()
        if col_filter and listing.short_name != col_filter:
            return False

        if listing.price > float(rule.get("max_price", 999999)):
            return False

        if listing.discount_percent < float(rule.get("min_discount_percent", 0)):
            return False

        if rule.get("rare_combo_only") and not listing.is_rare_combo:
            return False

        markets = [str(m).lower() for m in (rule.get("markets") or [])]
        if markets and listing.market.lower() not in markets:
            return False

        model_f = (rule.get("model_filter") or "").strip().lower()
        if model_f:
            has_model = any(
                a.type == "model" and model_f in a.value.lower() for a in listing.attributes
            )
            if not has_model:
                return False

        backdrop_f = (rule.get("backdrop_filter") or "").strip().lower()
        if backdrop_f:
            has_bg = any(
                a.type == "backdrop" and backdrop_f in a.value.lower() for a in listing.attributes
            )
            if not has_bg:
                return False

        return True

    async def _sync_with_remote_webapp(
        self,
        user_id: str,
        pushed_alerts: list[dict[str, Any]] | None = None,
    ) -> None:
        """Bi-directional state & alert sync between local @GiftKit_bot process and Vercel webapp."""
        if IS_VERCEL:
            return
        url = runtime_config.webapp_url.strip().rstrip("/")
        if not url.startswith("https://") or url in ("https://t.me", "https://your-miniapp-domain.com"):
            return

        endpoint = f"{url}/api/internal/bot-sync"
        headers = {"X-Bot-Sync-Signature": auth_service.get_bot_sync_signature()}
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(3.0, connect=2.0)) as client:
                if pushed_alerts:
                    local_env = await db.export_user_state(user_id)
                    await client.post(
                        endpoint,
                        headers=headers,
                        json={
                            "user_id": user_id,
                            "state_envelope": local_env,
                            "alerts": pushed_alerts,
                        },
                    )
                else:
                    resp = await client.get(endpoint, headers=headers, params={"user_id": user_id})
                    if resp.status_code == 200:
                        data = resp.json()
                        remote_env = data.get("state_envelope")
                        if isinstance(remote_env, dict):
                            await db.import_user_state(user_id, remote_env)
        except Exception as exc:
            logger.debug(f"Remote bot-sync skipped: {exc}")

    async def _gather_candidates_for_rules(self, rules: list[dict[str, Any]]) -> list[AnalyzedListing]:
        """Fetch live listings tailored to every active rule (including 50-500+ TON & specific collections)."""
        pool: list[AnalyzedListing] = []
        seen_ids: set[str] = set()

        def _merge(batch: list[AnalyzedListing]) -> None:
            for item in batch:
                if item.id and item.id not in seen_ids:
                    seen_ids.add(item.id)
                    pool.append(item)

        # 1. General freshest & best-discount pool
        try:
            base_items = await analytics_engine.get_analyzed_listings(sort="discount_desc", limit=50)
            _merge(base_items)
        except Exception as exc:
            logger.debug(f"Sniper base pool fetch skipped: {exc}")

        # 2. Targeted fetches for specific collections in rules
        target_cols: dict[str, float] = {}
        target_models: dict[str, tuple[str | None, float]] = {}
        high_budget_caps: list[float] = []

        for r in rules:
            col = (r.get("collection_short_name") or "").strip().lower()
            max_p = float(r.get("max_price") or 500.0)
            model_f = (r.get("model_filter") or "").strip()
            if col:
                target_cols[col] = max(target_cols.get(col, 0.0), max_p)
            elif max_p >= 25.0:
                high_budget_caps.append(max_p)
            if model_f:
                target_models[model_f.lower()] = (col or None, max_p)

        for col_short, max_p in list(target_cols.items())[:5]:
            try:
                col_items = await analytics_engine.get_analyzed_listings(
                    collection=col_short,
                    max_price=max_p,
                    sort="price_asc",
                    limit=35,
                )
                _merge(col_items)
            except Exception as exc:
                logger.debug(f"Sniper targeted collection {col_short} skipped: {exc}")

        for model_q, (col_opt, max_p) in list(target_models.items())[:3]:
            try:
                m_items = await analytics_engine.get_analyzed_listings(
                    collection=col_opt,
                    search=model_q,
                    max_price=max_p,
                    sort="price_asc",
                    limit=25,
                )
                _merge(m_items)
            except Exception as exc:
                logger.debug(f"Sniper targeted model {model_q} skipped: {exc}")

        # 3. High-budget sweep (e.g. rules with max_price = 50, 100, 300, 1000 TON across "All collections")
        if high_budget_caps:
            top_cap = max(high_budget_caps)
            low_band = round(max(15.0, min(top_cap * 0.25, 120.0)), 1)
            try:
                mid_high = await analytics_engine.get_analyzed_listings(
                    min_price=low_band,
                    max_price=top_cap,
                    sort="price_asc",
                    limit=40,
                )
                _merge(mid_high)
            except Exception as exc:
                logger.debug(f"Sniper high-budget range fetch skipped: {exc}")

            # Also inspect top 2 liquid collections whose floor sits in the user's target budget band
            try:
                all_cols = await analytics_engine.get_collections_summary(sort="volume_desc", limit=120)
                band_cols = [
                    c for c in all_cols
                    if low_band * 0.7 <= c.floor_price <= top_cap * 1.05
                    and c.short_name not in target_cols
                    and c.liquidity_score >= 45
                ][:2]
                for bc in band_cols:
                    b_items = await analytics_engine.get_analyzed_listings(
                        collection=bc.short_name,
                        max_price=top_cap,
                        sort="price_asc",
                        limit=25,
                    )
                    _merge(b_items)
            except Exception as exc:
                logger.debug(f"Sniper high-budget collections sweep skipped: {exc}")

        pool.sort(key=lambda x: (x.discount_percent, x.net_profit_percent), reverse=True)
        return pool

    async def evaluate_once(self, target_user_ids: list[str] | None = None) -> list[dict[str, Any]]:
        """Run one scan cycle across active sniper rules (works both locally and 24/7 on Vercel Cron)."""
        admin_uid = (runtime_config.tg_admin_chat_id or DEFAULT_ADMIN_USER_ID).strip() or DEFAULT_ADMIN_USER_ID
        if not IS_VERCEL:
            await self._sync_with_remote_webapp(admin_uid)

        user_ids: list[str] = []
        if target_user_ids:
            user_ids = [str(u).strip() for u in target_user_ids if str(u).strip()]
        else:
            cloud_users = await cloud_store.list_active_users() if cloud_store.is_configured else []
            user_ids = list(dict.fromkeys([*cloud_users, admin_uid]))

        # Hydrate latest user rules from persistent CloudStore (crucial for Vercel cold starts!)
        if cloud_store.is_configured:
            for uid in user_ids:
                try:
                    env = await cloud_store.load_user_state(uid)
                    if isinstance(env, dict):
                        await db.import_user_state(uid, env)
                except Exception as exc:
                    logger.debug(f"CloudStore hydrate skipped for {uid}: {exc}")

        rules: list[dict[str, Any]] = []
        for uid in user_ids:
            user_rules = await db.list_sniper_rules(user_id=uid)
            for r in user_rules:
                if r.get("enabled"):
                    rules.append(r)

        if not rules:
            return []

        listings = await self._gather_candidates_for_rules(rules)
        triggered_alerts: list[dict[str, Any]] = []
        now_ts = time.time()

        for listing in listings:
            # Liquidity guard: skip dead illiquid collections
            if listing.liquidity_score < 35:
                continue

            ref_floor = _effective_reference_floor(listing)
            # Hard anti-overpriced & floor guard: never alert on unprofitable or above-model-floor lots
            if (
                listing.discount_percent <= 0
                or listing.net_profit_ton <= 0
                or listing.verdict == "OVERPRICED"
                or (ref_floor > 0 and listing.price > ref_floor * 1.03)
            ):
                continue

            # Pre-filter: must have at least one genuine trader edge
            pre_reasons = _collect_gem_reasons(listing)
            if not pre_reasons:
                continue

            for rule in rules:
                if not self._listing_matches_rule(listing, rule):
                    continue

                rule_uid = str(rule.get("user_id") or admin_uid).strip()
                rule_id = int(rule["id"])
                if now_ts - self._last_rule_alert_ts.get(rule_id, 0.0) < 300.0:
                    continue

                dedup_key = f"{rule_uid}:{rule_id}:{listing.tg_id or listing.id}"
                if dedup_key in self._seen_keys:
                    continue
                if cloud_store.is_configured and await cloud_store.is_alert_seen(dedup_key):
                    self._seen_keys.add(dedup_key)
                    continue

                if len(self._seen_keys) > 2000:
                    self._seen_keys.clear()
                self._seen_keys.add(dedup_key)

                # FINAL GATE: verify finalist with AI Vision / Pixel CV
                try:
                    attrs_dicts = [{"type": a.type, "value": a.value} for a in listing.attributes]
                    ai_res = await visual_analyzer.evaluate_with_ai_vision(
                        photo_url=listing.photo_url,
                        collection_name=listing.collection_name,
                        number=listing.number,
                        attributes=attrs_dicts,
                        price=listing.price,
                        fair_value=listing.fair_value,
                    )
                    listing.visual_score = float(ai_res.get("visual_score", listing.visual_score))
                    listing.visual_tag = str(ai_res.get("visual_tag", listing.visual_tag))
                    if "is_monochrome" in ai_res:
                        listing.is_monochrome = bool(ai_res["is_monochrome"])
                    if not listing.is_monochrome and listing.harmony_label == "Монохром":
                        listing.harmony_label = None
                    elif ai_res.get("harmony_label"):
                        listing.harmony_label = str(ai_res["harmony_label"])
                    if ai_res.get("ai_vision_comment"):
                        listing.ai_vision_comment = str(ai_res["ai_vision_comment"])

                    ai_source = ai_res.get("source")
                    worth_alert = ai_res.get("worth_alert")
                except Exception as exc:
                    logger.debug(f"Sniper AI verification skipped: {exc}")
                    ai_source = "cv_pixels"
                    worth_alert = None

                has_strong_math_edge = (
                    (listing.number_bonus_percent >= 14.0 and (ref_floor <= 0 or listing.price <= ref_floor * 1.03))
                    or (
                        listing.symbol_bonus_percent >= 10.0
                        and (ref_floor <= 0 or listing.price <= ref_floor * 1.03)
                    )
                    or (listing.is_monochrome and listing.visual_score >= 6.2 and (ref_floor <= 0 or listing.price <= ref_floor * 1.03))
                    or (
                        ref_floor > 0
                        and listing.price <= ref_floor * 0.88
                    )
                )

                # Enforce visual quality floor ONLY when there is no strong monochrome/number/symbol/discount edge
                if listing.visual_score < 7.2 and not has_strong_math_edge:
                    logger.info(
                        f"Sniper vetoed weak visual {listing.collection_name} #{listing.number} (score={listing.visual_score})"
                    )
                    continue

                post_reasons = _collect_gem_reasons(listing)
                if not post_reasons:
                    logger.info(
                        f"Sniper vetoed {listing.collection_name} #{listing.number} after CV/AI verification (no valid edge left)"
                    )
                    continue

                if ai_source in {"gemini", "openai"}:
                    if worth_alert is False and not has_strong_math_edge:
                        logger.info(
                            f"Sniper AI Vision vetoed {listing.collection_name} #{listing.number} (score={listing.visual_score}, worth_alert=False)"
                        )
                        continue
                    if listing.visual_score < 7.2 and not has_strong_math_edge:
                        logger.info(
                            f"Sniper AI Vision vetoed weak visual {listing.collection_name} #{listing.number} (score={listing.visual_score})"
                        )
                        continue

                self._last_rule_alert_ts[rule_id] = now_ts
                if cloud_store.is_configured:
                    await cloud_store.mark_alert_seen(dedup_key)

                # Check risk guard if autobuy mode
                autobuy_note = ""
                if rule["mode"] == "autobuy":
                    today_spent = await db.get_today_spent_ton(user_id=rule_uid)
                    if listing.price > runtime_config.max_single_buy_ton:
                        autobuy_note = f" [Автовикуп пропущено: перевищено ліміт угоди {runtime_config.max_single_buy_ton} TON]"
                    elif today_spent + listing.price > runtime_config.daily_limit_ton:
                        autobuy_note = f" [Автовикуп пропущено: денний ліміт {runtime_config.daily_limit_ton} TON]"
                    else:
                        await db.record_trade(
                            listing.id,
                            listing.short_name,
                            listing.price,
                            runtime_config.dry_run,
                            user_id=rule_uid,
                        )
                        await db.create_portfolio_item(
                            {
                                "tg_id": listing.tg_id,
                                "collection_name": listing.collection_name,
                                "short_name": listing.short_name,
                                "number": listing.number,
                                "photo_url": listing.photo_url,
                                "buy_price": listing.price,
                                "listed_price": round(max(listing.fair_value * 0.96, listing.price * 1.15), 2),
                                "market": listing.best_sell_market,
                                "auto_undercut_enabled": True,
                                "undercut_mode": "notify",
                                "min_price_guard": round(listing.price * 1.07, 2),
                                "undercut_step": 0.05,
                                "status": "listed",
                            },
                            user_id=rule_uid,
                        )
                        mode_lbl = "DRY RUN симуляція" if runtime_config.dry_run else "LIVE ордер"
                        autobuy_note = f" [Автовикуп: {mode_lbl} — додано в портфель]"

                tg_html = format_telegram_alert_html(listing, rule["name"])
                tg_sent = False
                if self._send_tg_alert:
                    try:
                        tg_sent = await self._send_tg_alert(listing, rule["name"], chat_id=rule_uid)
                    except TypeError:
                        tg_sent = await self._send_tg_alert(listing, rule["name"])
                    except Exception as exc:
                        logger.warning(f"Sniper Telegram dispatch error: {exc}")

                await db.increment_rule_hits(rule["id"])
                log_entry = await db.add_alert_log(
                    alert_type="sniper",
                    rule_id=rule["id"],
                    rule_name=rule["name"],
                    listing_id=listing.id,
                    title=f"{listing.collection_name} #{listing.number} за {listing.price} TON",
                    summary=f"{listing.verdict_label} | Fair Value {listing.fair_value} TON{autobuy_note}",
                    payload=listing.model_dump(),
                    telegram_html=tg_html,
                    telegram_sent=tg_sent,
                    user_id=rule_uid,
                )
                if cloud_store.is_configured:
                    try:
                        updated_env = await db.export_user_state(rule_uid)
                        await cloud_store.save_user_state(rule_uid, updated_env)
                    except Exception:
                        pass
                await ws_manager.broadcast("sniper_alert", log_entry)
                triggered_alerts.append(log_entry)
                if len(triggered_alerts) >= 3:
                    break

            if len(triggered_alerts) >= 3:
                break

        if triggered_alerts and not IS_VERCEL:
            await self._sync_with_remote_webapp(admin_uid, pushed_alerts=triggered_alerts)

        return triggered_alerts

    async def trigger_test_alert(self, user_id: str = DEFAULT_ADMIN_USER_ID) -> dict[str, Any]:
        """Pick the strongest live deal right now, log it, broadcast WS & dispatch to Telegram."""
        uid = str(user_id or DEFAULT_ADMIN_USER_ID).strip()
        listings = await analytics_engine.get_analyzed_listings(sort="discount_desc", limit=40)
        if not listings:
            raise RuntimeError("Немає активних лотів для тестового алерту")

        valid_candidates = [
            it
            for it in listings
            if it.discount_percent > 0
            and it.net_profit_ton > 0
            and it.verdict != "OVERPRICED"
            and (it.collection_floor <= 0 or it.price <= it.collection_floor * 1.02)
        ]
        gem_candidates = [it for it in valid_candidates if _collect_gem_reasons(it)]
        if gem_candidates:
            best = gem_candidates[0]
        elif valid_candidates:
            best = max(valid_candidates, key=lambda x: (x.visual_score, x.discount_percent))
        else:
            base = listings[0]
            safe_price = round(max(0.5, base.collection_floor * 0.90), 2)
            safe_fair = round(max(base.fair_value, base.collection_floor * 1.15), 2)
            safe_profit = round(safe_fair * 0.95 - safe_price, 2)
            safe_profit_pct = round((safe_profit / max(safe_price, 0.01)) * 100.0, 1)
            safe_disc = round(((safe_fair - safe_price) / max(safe_fair, 0.01)) * 100.0, 1)
            best = base.model_copy(
                update={
                    "price": safe_price,
                    "fair_value": safe_fair,
                    "discount_percent": safe_disc,
                    "net_profit_ton": safe_profit,
                    "net_profit_percent": safe_profit_pct,
                    "visual_score": max(base.visual_score, 8.2),
                    "verdict": "STRONG_BUY" if safe_profit_pct >= 20.0 else "GOOD_DEAL",
                    "verdict_label": f"Вигідна угода ({safe_profit_pct:+.0f}%)",
                }
            )
        rule_name = "Тестовий Снайпер-сигнал PRO"
        tg_html = format_telegram_alert_html(best, rule_name)

        tg_sent = False
        if self._send_tg_alert:
            try:
                tg_sent = await self._send_tg_alert(best, rule_name)
            except Exception as exc:
                logger.warning(f"Test alert Telegram send error: {exc}")

        alert_log = await db.add_alert_log(
            alert_type="sniper_test",
            rule_name=rule_name,
            listing_id=best.id,
            title=f"Тест-сигнал: {best.collection_name} #{best.number} — {best.price} TON",
            summary=f"{best.verdict_label} | Fair Value {best.fair_value} TON | Чистий профіт {best.net_profit_ton:+.2f} TON",
            payload=best.model_dump(),
            telegram_html=tg_html,
            telegram_sent=tg_sent,
            user_id=uid,
        )
        await ws_manager.broadcast("sniper_alert", alert_log)
        msg = (
            "Тестову картку надіслано в Telegram та збережено в журналі!"
            if tg_sent
            else "Тестову картку сформовано! (Telegram не підключено — додайте токен бота і Chat ID у Налаштуваннях)"
        )
        return {
            "ok": True,
            "alert": alert_log,
            "listing": best.model_dump(),
            "sent_to_telegram": tg_sent,
            "telegram_sent": tg_sent,
            "telegram_html": tg_html,
            "html_preview": tg_html,
            "message": msg,
        }

    async def _loop(self) -> None:
        await asyncio.sleep(6)
        while self._running:
            try:
                alerts = await self.evaluate_once()
                if alerts:
                    logger.info(f"SniperEngine triggered {len(alerts)} alert(s)")
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"SniperEngine loop error: {exc}")
            await asyncio.sleep(base_settings.SNIPER_POLL_INTERVAL)


sniper_engine = SniperEngine()
