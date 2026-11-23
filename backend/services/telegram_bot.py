"""Complete aiogram 3.x Telegram Bot for TON Gift Terminal Pro."""

from __future__ import annotations

import asyncio
import html
import re
import urllib.parse
from typing import Any

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonDefault,
    MenuButtonWebApp,
    Message,
    Update,
    WebAppInfo,
)
from loguru import logger

from backend.config import runtime_config
from backend.database import db
from backend.models import AnalyzedListing
from backend.services import auth_service
from backend.services.analytics_engine import analytics_engine
from backend.services.auth_service import DEFAULT_ADMIN_USER_ID
from backend.services.sniper_engine import format_telegram_alert_html
from backend.services.undercut_engine import undercut_engine
from backend.services.ws_manager import ws_manager


class TelegramBotService:
    """Manages aiogram 3.x lifecycle, polling, alerts, X-Ray commands & inline callbacks."""

    def __init__(self) -> None:
        self.bot: Bot | None = None
        self.dp: Dispatcher | None = None
        self._poll_task: asyncio.Task[None] | None = None
        self.is_connected: bool = False
        self.bot_username: str = "GiftKit_bot"
        # Short key -> listing dict (keeps Telegram callback_data <= 64 bytes)
        self._listing_cache: dict[str, dict[str, Any]] = {}
        self._admin_user_cache: dict[str, Any] | None = None

    def _cache_listing(self, listing: AnalyzedListing) -> str:
        key = listing.id[:20] if listing.id else f"{listing.short_name}_{listing.number}"[:20]
        if len(self._listing_cache) > 400:
            for old_k in list(self._listing_cache.keys())[:200]:
                self._listing_cache.pop(old_k, None)
        self._listing_cache[key] = listing.model_dump()
        return key

    def _get_admin_tg_auth(self) -> str:
        admin_id = (runtime_config.tg_admin_chat_id or DEFAULT_ADMIN_USER_ID).strip() or DEFAULT_ADMIN_USER_ID
        user_payload = self._admin_user_cache or {"tg_user_id": admin_id}
        return auth_service.create_signed_token(user_payload)

    def _build_main_keyboard(
        self,
        tg_auth: str | None = None,
        button_text: str = "Відкрити програму",
    ) -> InlineKeyboardMarkup:
        url = runtime_config.webapp_url.strip()
        if url.startswith("https://") and url not in ("https://t.me", "https://your-miniapp-domain.com"):
            token = tg_auth or self._get_admin_tg_auth()
            sep = "&" if "?" in url else "?"
            auth_url = f"{url.rstrip('/')}/{sep}tg_auth={urllib.parse.quote(token)}" if "?" not in url else f"{url}{sep}tg_auth={urllib.parse.quote(token)}"
            return InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=button_text,
                            web_app=WebAppInfo(url=auth_url),
                        )
                    ]
                ]
            )
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Відкрити програму (налаштуй HTTPS URL)",
                        callback_data="webapp_info",
                    )
                ]
            ]
        )

    def _build_sniper_keyboard(
        self,
        listing: AnalyzedListing,
        tg_auth: str | None = None,
    ) -> InlineKeyboardMarkup:
        key = self._cache_listing(listing)
        tg_nft_url = f"https://t.me/nft/{listing.tg_id}" if listing.tg_id else listing.market_url
        rows: list[list[InlineKeyboardButton]] = [
            [
                InlineKeyboardButton(text="Глянути NFT (Власник)", url=tg_nft_url),
                InlineKeyboardButton(text="Відкрити на маркеті", url=listing.market_url),
            ],
            [
                InlineKeyboardButton(text="Історія продажів", callback_data=f"history:{key}"),
                InlineKeyboardButton(
                    text=f"Купити ({listing.price} TON)" if not runtime_config.dry_run else "Купити (DRY)",
                    callback_data=f"buy:{key}",
                ),
            ],
        ]
        url = runtime_config.webapp_url.strip()
        if url.startswith("https://") and url not in ("https://t.me", "https://your-miniapp-domain.com"):
            admin_tg_auth = tg_auth or self._get_admin_tg_auth()
            nft_slug = urllib.parse.quote(listing.tg_id or listing.id)
            lid_slug = urllib.parse.quote(listing.id)
            col_slug = urllib.parse.quote(listing.collection_name)
            short_slug = urllib.parse.quote(listing.short_name)
            deep_url = (
                f"{url.rstrip('/')}/?nft={nft_slug}"
                f"&listing_id={lid_slug}"
                f"&col={col_slug}"
                f"&short={short_slug}"
                f"&num={listing.number}"
                f"&price={listing.price}"
                f"&floor={listing.collection_floor}"
                f"&fair={listing.fair_value}"
                f"&tg_auth={urllib.parse.quote(admin_tg_auth)}"
            )
            rows.append([InlineKeyboardButton(text="Відкрити в GiftKit", web_app=WebAppInfo(url=deep_url))])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    @staticmethod
    def _build_undercut_keyboard(item: dict[str, Any]) -> InlineKeyboardMarkup:
        item_id = item["id"]
        step = item.get("undercut_step", 0.05)
        suggested = item.get("suggested_price", item.get("listed_price", 0))
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=f"Знизити до {suggested} TON (-{step})",
                        callback_data=f"undercut_yes:{item_id}",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="Залишити поточну ціну",
                        callback_data=f"undercut_no:{item_id}",
                    ),
                ],
            ]
        )

    async def _resolve_and_upsert_tg_user(self, from_user: Any) -> dict[str, Any]:
        """Extract Telegram user profile, check avatar, and upsert into SQLite users table."""
        if not from_user:
            return await db.upsert_user({"tg_user_id": DEFAULT_ADMIN_USER_ID})

        uid = str(from_user.id)
        username = (getattr(from_user, "username", "") or "").strip()
        first_name = (getattr(from_user, "first_name", "") or "").strip()
        last_name = (getattr(from_user, "last_name", "") or "").strip()
        photo_url = f"https://t.me/i/userpic/320/{username}.jpg" if username else ""

        if self.bot and not photo_url:
            try:
                photos = await self.bot.get_user_profile_photos(user_id=int(uid), limit=1)
                if photos and photos.total_count > 0:
                    webapp_base = runtime_config.webapp_url.strip().rstrip("/")
                    if webapp_base.startswith("https://") and webapp_base not in ("https://t.me", "https://your-miniapp-domain.com"):
                        photo_url = f"{webapp_base}/api/auth/avatar/{uid}"
                    else:
                        photo_url = f"/api/auth/avatar/{uid}"
            except Exception:
                pass

        user_dict = await db.upsert_user(
            {
                "tg_user_id": uid,
                "username": username,
                "first_name": first_name,
                "last_name": last_name,
                "photo_url": photo_url,
            }
        )
        admin_id = (runtime_config.tg_admin_chat_id or DEFAULT_ADMIN_USER_ID).strip()
        if uid == admin_id:
            self._admin_user_cache = user_dict
        return user_dict

    async def resolve_chat_profile(self, tg_user_id: str) -> dict[str, Any]:
        """Resolve a Telegram user profile by chat_id via Bot API getChat when available."""
        uid = str(tg_user_id or DEFAULT_ADMIN_USER_ID).strip()
        existing = await db.get_user(uid)
        if existing and (existing.get("username") or existing.get("first_name")):
            if uid == (runtime_config.tg_admin_chat_id or DEFAULT_ADMIN_USER_ID).strip():
                self._admin_user_cache = existing
            return existing

        await self._ensure_bot_and_dp()
        if self.bot and uid.isdigit():
            try:
                chat = await self.bot.get_chat(chat_id=int(uid))
                username = (getattr(chat, "username", "") or "").strip()
                first_name = (getattr(chat, "first_name", "") or "").strip()
                last_name = (getattr(chat, "last_name", "") or "").strip()
                photo_url = f"https://t.me/i/userpic/320/{username}.jpg" if username else ""
                user_dict = await db.upsert_user(
                    {
                        "tg_user_id": uid,
                        "username": username,
                        "first_name": first_name,
                        "last_name": last_name,
                        "photo_url": photo_url,
                    }
                )
                if uid == (runtime_config.tg_admin_chat_id or DEFAULT_ADMIN_USER_ID).strip():
                    self._admin_user_cache = user_dict
                return user_dict
            except Exception as exc:
                logger.debug(f"get_chat({uid}) skipped: {exc}")

        return await db.upsert_user({"tg_user_id": uid})

    def _create_router(self) -> Router:
        router = Router(name="ton_gift_terminal")

        @router.message(CommandStart())
        async def cmd_start(message: Message) -> None:
            user_dict = await self._resolve_and_upsert_tg_user(message.from_user)
            tg_auth = auth_service.create_signed_token(user_dict)

            # Check if deep-linked login nonce: /start login_<nonce>
            parts = (message.text or "").split(maxsplit=1)
            arg = parts[1].strip() if len(parts) > 1 else ""
            if arg.startswith("login_"):
                nonce = arg[len("login_") :].strip()
                if nonce:
                    auth_service.approve_login_nonce(nonce, user_dict)
                    display_name = html.escape(
                        user_dict.get("first_name")
                        or (f"@{user_dict['username']}" if user_dict.get("username") else user_dict["tg_user_id"])
                    )
                    await message.answer(
                        f"<b>Авторизацію підтверджено!</b>\n\n"
                        f"Акаунт <b>{display_name}</b> успішно підключено до вашого браузера / термінала GiftKit.\n"
                        f"Ваші правила снайпера, офери та портфель синхронізовано.",
                        reply_markup=self._build_main_keyboard(
                            tg_auth=tg_auth,
                            button_text="Відкрити GiftKit (Акаунт підключено)",
                        ),
                    )
                    return

            text = (
                "Привіт, це <b>GiftKit</b> — бот, який закриває три задачі NFT-трейдера:\n\n"
                "• знайти дешеві NFT нижче ринку\n"
                "• оцінити реальну ціну та ліквідність\n"
                "• не проґавити конкурентів і продати з профітом\n\n"
                "Моніторю 100+ колекцій на Portals, Getgems, MRKT та Tonnel, рахую Fair Value по реальних продажах, "
                "веду портфель з Auto-Undercut і миттєво кидаю вигідні лоти в Telegram."
            )
            await message.answer(text, reply_markup=self._build_main_keyboard(tg_auth=tg_auth))

        @router.message(Command("xray"))
        async def cmd_xray(message: Message) -> None:
            await self._resolve_and_upsert_tg_user(message.from_user)
            parts = (message.text or "").split(maxsplit=1)
            if len(parts) < 2 or not parts[1].strip():
                await message.answer(
                    "Надішліть запит після команди, наприклад:\n"
                    "<code>/xray Eternal Rose #18718</code>\n"
                    "або просто вставте посилання <code>https://t.me/nft/EternalRose-18718</code>"
                )
                return
            await self._reply_xray(message, parts[1].strip())

        @router.message(F.text)
        async def handle_free_text(message: Message) -> None:
            text = (message.text or "").strip()
            if not text or text.startswith("/"):
                return
            if (
                "t.me/nft/" in text.lower()
                or re.search(r"#\d+", text)
                or re.search(r"[a-zA-Z]+-\d+", text)
            ):
                await self._resolve_and_upsert_tg_user(message.from_user)
                await self._reply_xray(message, text)

        @router.callback_query(F.data == "webapp_info")
        async def cb_webapp_info(cb: CallbackQuery) -> None:
            await cb.answer(
                "Додайте публічний HTTPS URL (наприклад Cloudflare Tunnel або ngrok) у Налаштуваннях термінала!",
                show_alert=True,
            )

        @router.callback_query(F.data == "xray_prompt")
        async def cb_xray_prompt(cb: CallbackQuery) -> None:
            await cb.answer()
            if cb.message:
                await cb.message.answer(
                    "<b>Рентген Telegram-подарунка</b>\n"
                    "Надішліть посилання (<code>https://t.me/nft/EternalRose-18718</code>) або назву "
                    "(<code>Eternal Rose #18718</code>) — я миттєво розрахую Fair Value, флор моделі та чистий профіт!"
                )

        @router.callback_query(F.data == "top_flips")
        async def cb_top_flips(cb: CallbackQuery) -> None:
            user_dict = await self._resolve_and_upsert_tg_user(cb.from_user)
            tg_auth = auth_service.create_signed_token(user_dict)
            await cb.answer("Завантажую топові фліпи...")
            listings = await analytics_engine.get_analyzed_listings(sort="discount_desc", limit=5)
            if not cb.message:
                return
            if not listings:
                await cb.message.answer("Наразі активних фліпів не знайдено.")
                return
            lines = ["<b>ТОП-5 ФЛІПІВ ЗАРАЗ (LIVE):</b>\n"]
            for idx, it in enumerate(listings, 1):
                vis_parts = []
                if it.is_monochrome:
                    vis_parts.append("Монохром")
                if it.harmony_label and it.harmony_label != "Монохром":
                    vis_parts.append(it.harmony_label)
                vis_tag = f" | Візуал {it.visual_score:.1f}/10" + (f" ({'/'.join(vis_parts)})" if vis_parts else "")
                num_tag = f" | Номер: {it.number_pattern}" if it.number_pattern else ""
                lines.append(
                    f"{idx}. <b>{html.escape(it.collection_name)} #{it.number}</b> — <b>{it.price} TON</b>\n"
                    f"   Fair Value: <b>{it.fair_value} TON</b> ({it.discount_percent:+.1f}%) | "
                    f"Профіт: <b>{it.net_profit_ton:+.2f} TON</b> ({it.best_sell_market.upper()}){vis_tag}{num_tag}"
                )
            await cb.message.answer("\n".join(lines), reply_markup=self._build_main_keyboard(tg_auth=tg_auth))

        @router.callback_query(F.data == "top_arb")
        async def cb_top_arb(cb: CallbackQuery) -> None:
            user_dict = await self._resolve_and_upsert_tg_user(cb.from_user)
            tg_auth = auth_service.create_signed_token(user_dict)
            await cb.answer("Сканую міжмаркетний арбітраж...")
            opps = await analytics_engine.get_arbitrage_opportunities(limit=5)
            if not cb.message:
                return
            if not opps:
                await cb.message.answer("Міжмаркетних вікон наразі немає.")
                return
            lines = ["<b>ТОП-5 АРБІТРАЖНИХ ВІКОН:</b>\n"]
            for idx, o in enumerate(opps, 1):
                lines.append(
                    f"{idx}. <b>{html.escape(o.collection_name)}</b>\n"
                    f"   Купити: <b>{o.buy_market.upper()} ({o.buy_price} TON)</b> → "
                    f"Продати: <b>{o.sell_market.upper()} ({o.sell_price} TON)</b>\n"
                    f"   Чистий профіт: <b>+{o.net_profit_ton} TON (ROI +{o.roi_percent}%)</b> | Лікв: {o.liquidity_score}/100"
                )
            await cb.message.answer("\n".join(lines), reply_markup=self._build_main_keyboard(tg_auth=tg_auth))

        @router.callback_query(F.data == "my_portfolio")
        async def cb_my_portfolio(cb: CallbackQuery) -> None:
            user_dict = await self._resolve_and_upsert_tg_user(cb.from_user)
            uid = user_dict["tg_user_id"]
            tg_auth = auth_service.create_signed_token(user_dict)
            await cb.answer("Оновлюю портфель...")
            pf = await undercut_engine.build_enriched_portfolio(user_id=uid)
            s = pf["summary"]
            if not cb.message:
                return
            lines = [
                "<b>ВАШ ПОРТФЕЛЬ & AUTO-UNDERCUT</b>\n",
                f"• Вкладено: <b>{s['total_invested_ton']} TON</b>",
                f"• Оцінка зараз: <b>{s['current_value_ton']} TON</b>",
                f"• PnL: <b>{s['unrealized_pnl_ton']:+.2f} TON ({s['unrealized_pnl_percent']:+.1f}%)</b>",
                f"• Активних лотів: <b>{s['active_listings']}</b> | Auto-Undercut: <b>{s['undercut_active_count']}</b>\n",
            ]
            for it in pf["items"][:6]:
                flag = "Перебито!" if it["is_undercut_by_competitor"] else "В ринку"
                lines.append(
                    f"• <b>{html.escape(it['collection_name'])} #{it['number']}</b>: "
                    f"лістинг {it['listed_price']} TON | флор {it['current_floor']} TON | {flag}"
                )
            await cb.message.answer("\n".join(lines), reply_markup=self._build_main_keyboard(tg_auth=tg_auth))

        @router.callback_query(F.data.startswith("buy:"))
        async def cb_buy(cb: CallbackQuery) -> None:
            user_dict = await self._resolve_and_upsert_tg_user(cb.from_user)
            uid = user_dict["tg_user_id"]
            key = (cb.data or "").split(":", 1)[1]
            cached = self._listing_cache.get(key)
            if not cached:
                await cb.answer("Лот застарів — оновіть сканер.", show_alert=True)
                return
            price = float(cached["price"])
            today_spent = await db.get_today_spent_ton(user_id=uid)
            if price > runtime_config.max_single_buy_ton:
                await cb.answer(
                    f"Перевищено ліміт однієї угоди ({runtime_config.max_single_buy_ton} TON)!",
                    show_alert=True,
                )
                return
            if today_spent + price > runtime_config.daily_limit_ton:
                await cb.answer(
                    f"Перевищено денний ліміт ({runtime_config.daily_limit_ton} TON)!",
                    show_alert=True,
                )
                return

            await db.record_trade(cached["id"], cached["short_name"], price, runtime_config.dry_run, user_id=uid)
            created = await db.create_portfolio_item(
                {
                    "tg_id": cached["tg_id"],
                    "collection_name": cached["collection_name"],
                    "short_name": cached["short_name"],
                    "number": cached["number"],
                    "photo_url": cached["photo_url"],
                    "buy_price": price,
                    "listed_price": round(max(float(cached["fair_value"]) * 0.96, price * 1.15), 2),
                    "market": cached.get("best_sell_market", "portals"),
                    "auto_undercut_enabled": True,
                    "undercut_mode": "notify",
                    "min_price_guard": round(price * 1.07, 2),
                    "undercut_step": 0.05,
                    "status": "listed",
                },
                user_id=uid,
            )
            await ws_manager.broadcast("trade_executed", {"source": "telegram", "item": created})
            mode_txt = "DRY RUN симуляція" if runtime_config.dry_run else "LIVE ордер"
            await cb.answer(f"{mode_txt}: куплено за {price} TON!", show_alert=True)
            if cb.message:
                await cb.message.answer(
                    f"<b>Угоду виконано [{mode_txt}]!</b>\n"
                    f"Лот <b>{html.escape(cached['collection_name'])} #{cached['number']}</b> "
                    f"додано в портфель за <b>{price} TON</b>."
                )

        @router.callback_query(F.data.startswith("offer:"))
        async def cb_offer(cb: CallbackQuery) -> None:
            user_dict = await self._resolve_and_upsert_tg_user(cb.from_user)
            uid = user_dict["tg_user_id"]
            key = (cb.data or "").split(":", 1)[1]
            cached = self._listing_cache.get(key)
            if not cached:
                await cb.answer("Лот застарів.", show_alert=True)
                return
            bid = round(float(cached["collection_floor"]) * 0.84, 2)
            max_bid = round(float(cached["collection_floor"]) * 0.92, 2)
            await db.create_offer(
                {
                    "collection_short_name": cached["short_name"],
                    "collection_name": cached["collection_name"],
                    "market": cached.get("market", "portals"),
                    "bid_price": bid,
                    "max_bid": max_bid,
                    "auto_outbid": True,
                },
                user_id=uid,
            )
            await cb.answer(f"Офер {bid} TON виставлено!", show_alert=True)

        @router.callback_query(F.data.startswith("history:"))
        async def cb_history(cb: CallbackQuery) -> None:
            key = (cb.data or "").split(":", 1)[1]
            cached = self._listing_cache.get(key)
            if not cached:
                await cb.answer("Історію не знайдено.", show_alert=True)
                return
            sales = cached.get("recent_sales") or []
            lines = [f"<b>Останні продажі {html.escape(cached['collection_name'])}:</b>\n"]
            for s in sales[:5]:
                tx_lbl = "Офер" if s.get("tx_type") == "offer_accepted" else "Продаж"
                lines.append(
                    f"• <b>{s['price']} TON</b> ({str(s['market']).upper()}) — {tx_lbl} | <code>{s['buyer']}</code>"
                )
            await cb.answer()
            if cb.message:
                await cb.message.answer("\n".join(lines))

        @router.callback_query(F.data.startswith("undercut_yes:"))
        async def cb_undercut_yes(cb: CallbackQuery) -> None:
            user_dict = await self._resolve_and_upsert_tg_user(cb.from_user)
            item_id = int((cb.data or "0:0").split(":", 1)[1])
            try:
                res = await undercut_engine.apply_undercut(item_id, user_id=user_dict["tg_user_id"])
                await cb.answer(f"Ціну оновлено до {res['new_price']} TON!", show_alert=True)
                if cb.message:
                    await cb.message.answer(f"<b>Auto-Undercut виконано:</b>\n{html.escape(res['message'])}")
            except Exception as exc:
                await cb.answer(f"Помилка: {exc}", show_alert=True)

        @router.callback_query(F.data.startswith("undercut_no:"))
        async def cb_undercut_no(cb: CallbackQuery) -> None:
            user_dict = await self._resolve_and_upsert_tg_user(cb.from_user)
            item_id = int((cb.data or "0:0").split(":", 1)[1])
            await db.update_portfolio_item(
                item_id,
                {"is_undercut_by_competitor": False},
                user_id=user_dict["tg_user_id"],
            )
            await cb.answer("Залишено поточну ціну без змін.", show_alert=False)

        return router

    async def _reply_xray(self, message: Message, query: str) -> None:
        try:
            user_dict = await self._resolve_and_upsert_tg_user(message.from_user)
            tg_auth = auth_service.create_signed_token(user_dict)
            res = await analytics_engine.xray_lookup(query)
            item = AnalyzedListing.model_validate(res["item"])
            caption = (
                format_telegram_alert_html(item, "Рентген NFT")
                + f"\n\n<i>{html.escape(res['recommendation'])}</i>"
            )
            kb = self._build_sniper_keyboard(item, tg_auth=tg_auth)
            try:
                await message.answer_photo(photo=item.photo_url, caption=caption, reply_markup=kb)
            except Exception:
                await message.answer(caption, reply_markup=kb)
        except Exception as exc:
            await message.answer(f"Не вдалося розпізнати NFT: {html.escape(str(exc))}")

    async def _ensure_bot_and_dp(self) -> bool:
        """Lazily initialize aiogram Bot & Dispatcher (used by Vercel Webhook & alerts)."""
        token = runtime_config.tg_bot_token.strip()
        if not token or ":" not in token:
            return False
        if self.bot is not None and self.dp is not None:
            return True
        try:
            self.bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
            self.dp = Dispatcher()
            self.dp.include_router(self._create_router())
            if not self.bot_username or self.bot_username == "GiftKit_bot":
                try:
                    me = await self.bot.get_me()
                    self.bot_username = me.username or "GiftKit_bot"
                except Exception:
                    pass
            self.is_connected = True
            return True
        except Exception as exc:
            logger.warning(f"Failed lazy Telegram Bot init: {exc}")
            return False

    async def process_webhook_update(self, update_data: dict[str, Any]) -> bool:
        """Feed raw Telegram Webhook Update JSON into aiogram Dispatcher (Vercel 24/7 mode)."""
        ready = await self._ensure_bot_and_dp()
        if not ready or not self.bot or not self.dp:
            logger.warning("Telegram webhook received update, but TG_BOT_TOKEN is not configured")
            return False
        try:
            update = Update.model_validate(update_data)
            await self.dp.feed_update(self.bot, update)
            return True
        except Exception as exc:
            logger.error(f"Telegram webhook update processing error: {exc}")
            return False

    async def send_sniper_alert(
        self,
        listing: AnalyzedListing,
        rule_name: str,
        chat_id: str | None = None,
    ) -> bool:
        """Send photo alert card with inline trade buttons to user's Telegram chat (works on Vercel 24/7)."""
        target_chat = (chat_id or "").strip()
        if not target_chat or not target_chat.lstrip("-").isdigit():
            target_chat = runtime_config.tg_admin_chat_id.strip()
        if not target_chat:
            return False
        if not self.bot or not self.is_connected:
            await self._ensure_bot_and_dp()
        if not self.bot or not self.is_connected:
            return False
        if not self._admin_user_cache:
            try:
                await self.resolve_chat_profile(target_chat)
            except Exception:
                pass
        caption = format_telegram_alert_html(listing, rule_name)
        kb = self._build_sniper_keyboard(listing)
        try:
            await self.bot.send_photo(chat_id=target_chat, photo=listing.photo_url, caption=caption, reply_markup=kb)
            return True
        except Exception:
            try:
                await self.bot.send_message(chat_id=target_chat, text=caption, reply_markup=kb)
                return True
            except Exception as exc:
                logger.warning(f"Failed to send sniper alert to Telegram ({target_chat}): {exc}")
                return False

    async def configure_webhook(self, webhook_url: str, secret_token: str = "") -> dict[str, Any]:
        """Configure official Telegram Webhook so @GiftKit_bot responds 24/7 in the cloud without a laptop."""
        ready = await self._ensure_bot_and_dp()
        if not ready or not self.bot:
            return {"ok": False, "error": "TG_BOT_TOKEN not configured"}
        try:
            await self.sync_menu_button()
            kwargs: dict[str, Any] = {
                "url": webhook_url,
                "allowed_updates": ["message", "callback_query"],
                "drop_pending_updates": False,
            }
            if secret_token:
                kwargs["secret_token"] = secret_token
            await self.bot.set_webhook(**kwargs)
            info = await self.bot.get_webhook_info()
            return {
                "ok": True,
                "webhook_url": info.url,
                "pending_update_count": info.pending_update_count,
                "bot_username": self.bot_username,
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    async def send_undercut_alert(self, item: dict[str, Any]) -> bool:
        """Send instant competitor undercut warning with 1-click price adjustment buttons."""
        chat_id = runtime_config.tg_admin_chat_id.strip()
        if not chat_id:
            return False
        if not self.bot or not self.is_connected:
            await self._ensure_bot_and_dp()
        if not self.bot or not self.is_connected:
            return False

        thin_note = (
            f"\n\n<b>Увага (Тонкий стакан):</b> {html.escape(item['thin_floor_warning'])}"
            if item.get("thin_floor_warning")
            else ""
        )
        text = (
            "<b>Конкурент перебив твій лот</b>\n\n"
            f"<b>{html.escape(item['collection_name'])} #{item['number']}</b> ({str(item['market']).upper()})\n"
            f"- Твоя ціна: <b>{item['listed_price']} TON</b>\n"
            f"- Ціна конкурента: <b>{item['competitor_price']} TON</b>\n"
            f"- Захисний мінімум: <b>{item['min_price_guard']} TON</b>\n"
            f"- Рекомендовано: <b>{item['suggested_price']} TON</b>"
            f"{thin_note}"
        )
        kb = self._build_undercut_keyboard(item)
        try:
            await self.bot.send_message(chat_id=chat_id, text=text, reply_markup=kb)
            return True
        except Exception as exc:
            logger.warning(f"Failed to send undercut alert to Telegram: {exc}")
            return False

    async def send_test_message(self) -> dict[str, Any]:
        """Diagnostic test for POST /api/settings/test-telegram."""
        token = runtime_config.tg_bot_token.strip()
        chat_id = runtime_config.tg_admin_chat_id.strip()
        if not token:
            return {
                "ok": False,
                "bot_connected": False,
                "message": "Токен Telegram-бота не вказано. Додайте TG_BOT_TOKEN у Налаштуваннях.",
            }
        if not chat_id:
            return {
                "ok": False,
                "bot_connected": self.is_connected,
                "message": "Не вказано TG_ADMIN_CHAT_ID (ваш Telegram ID). Дізнайтесь його через @userinfobot.",
            }

        if not self.bot or not self.is_connected:
            await self.restart()

        if not self.bot or not self.is_connected:
            return {
                "ok": False,
                "bot_connected": False,
                "message": "Не вдалося підключитися до Telegram Bot API. Перевірте коректність токена.",
            }

        try:
            await self.resolve_chat_profile(chat_id)
            await self.sync_menu_button()
            await self.bot.send_message(
                chat_id=chat_id,
                text=(
                    "<b>GiftKit підключено!</b>\n\n"
                    f"Бот: <b>@{html.escape(self.bot_username)}</b>\n"
                    f"Режим: <b>{'DRY RUN' if runtime_config.dry_run else 'LIVE'}</b>\n"
                    "Снайпер-сигнали, Рентген NFT та Auto-Undercut готові до роботи."
                ),
                reply_markup=self._build_main_keyboard(),
            )
            return {
                "ok": True,
                "bot_connected": True,
                "bot_username": self.bot_username,
                "message": f"Тестове повідомлення успішно надіслано від @{self.bot_username}!",
            }
        except Exception as exc:
            return {
                "ok": False,
                "bot_connected": self.is_connected,
                "message": f"Помилка надсилання в чат {chat_id}: {exc}. Переконайтесь, що ви натиснули /start у боті.",
            }

    async def sync_menu_button(self) -> None:
        if not self.bot:
            return
        url = runtime_config.webapp_url.strip()
        try:
            if url.startswith("https://") and url not in ("https://t.me", "https://your-miniapp-domain.com"):
                await self.bot.set_chat_menu_button(
                    menu_button=MenuButtonWebApp(text="GiftKit", web_app=WebAppInfo(url=url))
                )
                logger.info(f"Telegram MenuButtonWebApp set to {url}")
            else:
                await self.bot.set_chat_menu_button(menu_button=MenuButtonDefault())
        except Exception as exc:
            logger.debug(f"set_chat_menu_button skipped: {exc}")

    async def start(self) -> None:
        token = runtime_config.tg_bot_token.strip()
        if not token or ":" not in token:
            logger.info("Telegram Bot token not configured — skipping bot polling (Mini App & REST work normally)")
            self.is_connected = False
            return

        try:
            self.bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
            me = await self.bot.get_me()
            self.bot_username = me.username or "GiftKit_bot"
            self.dp = Dispatcher()
            self.dp.include_router(self._create_router())
            self.is_connected = True
            admin_id = (runtime_config.tg_admin_chat_id or DEFAULT_ADMIN_USER_ID).strip()
            if admin_id:
                try:
                    await self.resolve_chat_profile(admin_id)
                except Exception:
                    pass
            await self.sync_menu_button()
            # If a cloud webhook is already active on Vercel, do NOT kill it with local polling!
            try:
                wh_info = await self.bot.get_webhook_info()
                if wh_info and getattr(wh_info, "url", ""):
                    logger.info(
                        f"Telegram Bot @{self.bot_username} is running 24/7 via Cloud Webhook ({wh_info.url}) — skipping local polling"
                    )
                    return
            except Exception:
                pass
            self._poll_task = asyncio.create_task(self._run_polling(), name="telegram_bot_polling")
            logger.info(f"Telegram Bot started as @{self.bot_username}")
        except Exception as exc:
            logger.warning(f"Telegram Bot token invalid or unreachable ({exc}) — continuing without bot")
            self.is_connected = False
            if self.bot:
                try:
                    await self.bot.session.close()
                except Exception:
                    pass
                self.bot = None

    async def _run_polling(self) -> None:
        assert self.dp is not None and self.bot is not None
        try:
            await self.dp.start_polling(
                self.bot,
                handle_signals=False,
                allowed_updates=["message", "callback_query"],
            )
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.warning(f"Telegram Bot polling stopped: {exc}")
            self.is_connected = False

    async def stop(self) -> None:
        self.is_connected = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None
        if self.bot:
            try:
                await self.bot.session.close()
            except Exception:
                pass
            self.bot = None
        self.dp = None

    async def restart(self) -> None:
        await self.stop()
        await self.start()


telegram_bot_service = TelegramBotService()
