"""Background Sniper Engine evaluating live listings against user rules."""

from __future__ import annotations

import asyncio
import html
from typing import Any, Awaitable, Callable

from loguru import logger

from backend.config import base_settings, runtime_config
from backend.database import db
from backend.models import AnalyzedListing
from backend.services.analytics_engine import analytics_engine
from backend.services.ws_manager import ws_manager


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
        f"\n<b>Номер:</b> {html.escape(number_text)}{number_bonus_txt}"
        if number_text
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
        f"Правило: <i>{rule_esc}</i>\n\n"
        f"<b>{title}</b> ({listing.market.upper()})\n"
        f"Ціна лота: <b>{listing.price} TON</b>\n"
        f"Флор колекції: <b>{listing.collection_floor} TON</b> | Флор моделі: <b>{listing.model_floor} TON</b>\n"
        f"Справедлива ціна (Fair Value): <b>{listing.fair_value} TON</b> (знижка <b>{listing.discount_percent:+.1f}%</b>)\n"
        f"Чистий профіт після комісій: <b>{listing.net_profit_ton:+.2f} TON ({listing.net_profit_percent:+.1f}%)</b> -> продаж на <b>{listing.best_sell_market.upper()}</b>\n"
        f"Ліквідність: <b>{listing.liquidity_score}/100</b> | Продажів 24г: <b>{listing.sales_24h}</b>\n"
        f"Останні продажі: <code>{sales_block}</code>"
        f"{visual_line}{badge_line}{trend_line}{combo_line}{thin_line}{vision_note}\n\n"
        f"<b>Трейт-аналіз:</b>\n{attrs_block}\n\n"
        f"Вердикт: <b>{html.escape(listing.verdict_label)}</b>"
    )


class SniperEngine:
    """Evaluates live analyzed listings against active DB sniper rules."""

    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self._seen_keys: set[str] = set()
        self._send_tg_alert: Callable[[AnalyzedListing, str], Awaitable[bool]] | None = None

    def register_telegram_sender(
        self, sender: Callable[[AnalyzedListing, str], Awaitable[bool]]
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

    async def evaluate_once(self) -> list[dict[str, Any]]:
        """Run one scan cycle across active sniper rules."""
        rules = [r for r in await db.list_sniper_rules() if r["enabled"]]
        if not rules:
            return []

        listings = await analytics_engine.get_analyzed_listings(sort="discount_desc", limit=50)
        triggered_alerts: list[dict[str, Any]] = []

        for listing in listings:
            for rule in rules:
                if not self._listing_matches_rule(listing, rule):
                    continue

                dedup_key = f"{rule['id']}:{listing.id}:{listing.price}"
                if dedup_key in self._seen_keys:
                    continue

                # Prevent unbounded memory growth
                if len(self._seen_keys) > 2000:
                    self._seen_keys.clear()
                self._seen_keys.add(dedup_key)

                # Check risk guard if autobuy mode
                autobuy_note = ""
                if rule["mode"] == "autobuy":
                    today_spent = await db.get_today_spent_ton()
                    if listing.price > runtime_config.max_single_buy_ton:
                        autobuy_note = f" [Автовикуп пропущено: перевищено ліміт угоди {runtime_config.max_single_buy_ton} TON]"
                    elif today_spent + listing.price > runtime_config.daily_limit_ton:
                        autobuy_note = f" [Автовикуп пропущено: денний ліміт {runtime_config.daily_limit_ton} TON]"
                    else:
                        await db.record_trade(listing.id, listing.short_name, listing.price, runtime_config.dry_run)
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
                            }
                        )
                        mode_lbl = "DRY RUN симуляція" if runtime_config.dry_run else "LIVE ордер"
                        autobuy_note = f" [Автовикуп: {mode_lbl} — додано в портфель]"

                tg_html = format_telegram_alert_html(listing, rule["name"])
                tg_sent = False
                if self._send_tg_alert:
                    try:
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
                )
                await ws_manager.broadcast("sniper_alert", log_entry)
                triggered_alerts.append(log_entry)
                # Cap alerts per scan cycle to avoid flooding user
                if len(triggered_alerts) >= 3:
                    return triggered_alerts

        return triggered_alerts

    async def trigger_test_alert(self) -> dict[str, Any]:
        """Pick the strongest live deal right now, log it, broadcast WS & dispatch to Telegram."""
        listings = await analytics_engine.get_analyzed_listings(sort="discount_desc", limit=10)
        if not listings:
            raise RuntimeError("Немає активних лотів для тестового алерту")
        best = listings[0]
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
        # Short warmup delay before first background scan
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
