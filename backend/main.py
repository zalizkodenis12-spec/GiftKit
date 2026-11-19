"""FastAPI entrypoint for TON Gift Terminal Pro."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from backend.config import IS_VERCEL, base_settings, runtime_config
from backend.database import db, utc_now_iso
from backend.models import (
    OfferOutbidRequest,
    PortfolioCreate,
    PortfolioUpdate,
    SettingsUpdate,
    SimulateCompetitorRequest,
    SniperRuleCreate,
    SniperRuleUpdate,
    TradeExecuteRequest,
    UserOfferCreate,
    VisionScoreRequest,
)
from backend.services.analytics_engine import analytics_engine
from backend.services.getgems_client import getgems_client
from backend.services.multi_market import multi_market
from backend.services.portals_client import portals_client
from backend.services.sniper_engine import sniper_engine
from backend.services.telegram_bot import telegram_bot_service
from backend.services.trend_tracker import trend_tracker
from backend.services.undercut_engine import undercut_engine
from backend.services.visual_analyzer import visual_analyzer
from backend.services.ws_manager import ws_manager


async def _snapshot_loop() -> None:
    """Periodic background task capturing real floor snapshots for charts."""
    await asyncio.sleep(8)
    while True:
        try:
            count = await analytics_engine.capture_price_snapshots()
            logger.debug(f"Captured {count} live price snapshots")
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning(f"Snapshot loop error: {exc}")
        await asyncio.sleep(base_settings.SNAPSHOT_INTERVAL)


async def _warmup_cache() -> None:
    """Warm Portals/Getgems & 24h Trend caches immediately at boot so first Mini App load is instant."""
    try:
        await asyncio.gather(
            analytics_engine.get_collections_summary(limit=100),
            analytics_engine.get_analyzed_listings(limit=40),
            trend_tracker.get_trends(),
            return_exceptions=True,
        )
        logger.info("GiftKit live market & trends cache warmed up")
    except Exception as exc:
        logger.debug(f"Warmup skipped: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB, wire engines & Telegram bot, start background loops (skipped on Vercel)."""
    await db.init()

    sniper_engine.register_telegram_sender(telegram_bot_service.send_sniper_alert)
    undercut_engine.register_telegram_sender(telegram_bot_service.send_undercut_alert)

    snapshot_task: asyncio.Task[None] | None = None
    warmup_task: asyncio.Task[None] | None = None

    if IS_VERCEL:
        logger.info("GiftKit backend started in Vercel Serverless mode (background loops & polling skipped)")
    else:
        await telegram_bot_service.start()
        sniper_engine.start()
        undercut_engine.start()
        snapshot_task = asyncio.create_task(_snapshot_loop(), name="price_snapshot_loop")
        warmup_task = asyncio.create_task(_warmup_cache(), name="cache_warmup")
        logger.info("GiftKit backend started successfully")

    try:
        yield
    finally:
        if warmup_task is not None:
            warmup_task.cancel()
        if snapshot_task is not None:
            snapshot_task.cancel()
            try:
                await snapshot_task
            except asyncio.CancelledError:
                pass
        if not IS_VERCEL:
            await sniper_engine.stop()
            await undercut_engine.stop()
        await telegram_bot_service.stop()
        await visual_analyzer.close()
        await portals_client.close()
        await getgems_client.close()
        await multi_market.close()
        await db.close()
        logger.info("GiftKit backend stopped cleanly")


app = FastAPI(
    title="GiftKit API",
    version="1.1.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def _ensure_db_middleware(request: Request, call_next):
    await db.ensure_initialized()
    return await call_next(request)

app.add_middleware(GZipMiddleware, minimum_size=500)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==============================================================================
# 1. SYSTEM & OVERVIEW
# ==============================================================================


@app.get("/api/overview")
async def get_overview() -> dict[str, Any]:
    (ton_usd, ton_change), cols, rules, portfolio, arb = await asyncio.gather(
        getgems_client.get_ton_rate(),
        analytics_engine.get_collections_summary(limit=100),
        db.list_sniper_rules(),
        undercut_engine.build_enriched_portfolio(),
        analytics_engine.get_arbitrage_opportunities(limit=25),
    )
    active_rules = sum(1 for r in rules if r["enabled"])
    return {
        "ton_usd": ton_usd,
        "ton_change_24h": ton_change,
        "total_collections": len(cols),
        "active_rules": active_rules,
        "portfolio_count": len(portfolio["items"]),
        "portfolio_pnl_ton": portfolio["summary"]["unrealized_pnl_ton"],
        "arbitrage_opportunities_count": len(arb),
        "live_markets": multi_market.get_live_markets(),
        "bot_connected": telegram_bot_service.is_connected,
        "dry_run": runtime_config.dry_run,
        "last_sync": utc_now_iso(),
    }


# ==============================================================================
# 2. SCANNER & LISTINGS
# ==============================================================================


@app.get("/api/scanner/listings")
async def get_scanner_listings(
    collection: str | None = Query(default=None),
    market: str | None = Query(default=None),
    min_discount: float = Query(default=-100.0),
    max_price: float | None = Query(default=None),
    rare_combo_only: bool = Query(default=False),
    visual_top_only: bool = Query(default=False),
    nice_number_only: bool = Query(default=False),
    sort: str = Query(default="discount_desc"),
    limit: int = Query(default=40, ge=1, le=100),
) -> dict[str, Any]:
    items, arb_top = await asyncio.gather(
        analytics_engine.get_analyzed_listings(
            collection=collection,
            market=market,
            min_discount=min_discount,
            max_price=max_price,
            rare_combo_only=rare_combo_only,
            visual_top_only=visual_top_only,
            nice_number_only=nice_number_only,
            sort=sort,
            limit=limit,
        ),
        analytics_engine.get_arbitrage_opportunities(limit=5),
    )
    return {
        "items": [i.model_dump() for i in items],
        "arbitrage_top": [a.model_dump() for a in arb_top],
        "total": len(items),
    }


@app.get("/api/scanner/arbitrage")
async def get_scanner_arbitrage(limit: int = Query(default=20, ge=1, le=60)) -> dict[str, Any]:
    opps = await analytics_engine.get_arbitrage_opportunities(limit=limit)
    return {"opportunities": [o.model_dump() for o in opps]}


@app.post("/api/scanner/refresh")
async def post_scanner_refresh() -> dict[str, Any]:
    analytics_engine.clear_caches()
    cols, items = await asyncio.gather(
        analytics_engine.get_collections_summary(limit=250, force_refresh=True),
        analytics_engine.get_analyzed_listings(limit=40, force_refresh=True),
    )
    now = utc_now_iso()
    await ws_manager.broadcast(
        "market_sync",
        {"collections_count": len(cols), "listings_count": len(items), "synced_at": now},
    )
    return {
        "status": "ok",
        "refreshed_at": now,
        "collections_count": len(cols),
        "listings_count": len(items),
    }


# ==============================================================================
# 3. ANALYTICS & X-RAY
# ==============================================================================


@app.get("/api/analytics/collections")
async def get_analytics_collections(
    search: str = Query(default=""),
    sort: str = Query(default="volume_desc"),
    limit: int = Query(default=250, ge=1, le=300),
) -> dict[str, Any]:
    cols = await analytics_engine.get_collections_summary(search=search, sort=sort, limit=limit)
    heatmap = sorted(cols, key=lambda c: c.day_volume, reverse=True)[:16]
    return {
        "collections": [c.model_dump() for c in cols],
        "heatmap": [c.model_dump() for c in heatmap],
    }


@app.get("/api/analytics/collections/{short_name}/chart")
async def get_collection_chart(
    short_name: str,
    timeframe: str = Query(default="7d", pattern="^(24h|7d|30d)$"),
) -> dict[str, Any]:
    return await analytics_engine.get_collection_chart(short_name=short_name, timeframe=timeframe)


@app.get("/api/analytics/xray")
async def get_analytics_xray(query: str = Query(..., min_length=1)) -> dict[str, Any]:
    try:
        return await analytics_engine.xray_lookup(query)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/analytics/whales")
async def get_analytics_whales(limit: int = Query(default=12, ge=1, le=30)) -> dict[str, Any]:
    events = await analytics_engine.get_whale_events(limit=limit)
    return {"events": [e.model_dump() for e in events]}


@app.get("/api/analytics/trends")
async def get_analytics_trends(force_refresh: bool = Query(default=False)) -> dict[str, Any]:
    """Return live 24h trending backdrops from Portals trait floors + top visual picks."""
    trends, top_visual = await asyncio.gather(
        trend_tracker.get_trends(force_refresh=force_refresh),
        analytics_engine.get_analyzed_listings(sort="visual_desc", limit=10),
    )
    return {
        **trends,
        "top_visual_picks": [it.model_dump() for it in top_visual[:8]],
    }


@app.post("/api/analytics/vision-score")
async def post_analytics_vision_score(body: VisionScoreRequest) -> dict[str, Any]:
    """Run deep pixel CV + optional Gemini/OpenAI AI Vision evaluation on a listing."""
    photo_url = body.photo_url.strip()
    collection_name = body.collection_name.strip()
    number = body.number
    attributes = body.attributes
    price = body.price
    fair_value = body.fair_value

    if not photo_url and body.listing_id:
        listings = await analytics_engine.get_analyzed_listings(limit=60)
        matched = next((x for x in listings if x.id == body.listing_id or x.tg_id == body.listing_id), None)
        if matched:
            photo_url = matched.photo_url
            collection_name = collection_name or matched.collection_name
            number = number or matched.number
            attributes = attributes or [a.model_dump() for a in matched.attributes]
            price = price if price is not None else matched.price
            fair_value = fair_value if fair_value is not None else matched.fair_value

    if not photo_url and not attributes:
        raise HTTPException(status_code=400, detail="Вкажіть photo_url або listing_id для візуальної оцінки")

    result = await visual_analyzer.evaluate_with_ai_vision(
        photo_url=photo_url,
        collection_name=collection_name,
        number=number,
        attributes=attributes,
        price=price,
        fair_value=fair_value,
    )
    return {
        "ok": True,
        "listing_id": body.listing_id,
        "photo_url": photo_url,
        **result,
    }


@app.post("/api/telegram/webhook")
async def post_telegram_webhook(request: Request) -> dict[str, Any]:
    """Receive Telegram Bot API webhook updates for 24/7 Vercel Serverless mode."""
    try:
        update_data = await request.json()
    except Exception:
        return {"ok": False, "error": "invalid_json"}
    processed = await telegram_bot_service.process_webhook_update(update_data)
    return {"ok": True, "processed": processed}


# ==============================================================================
# 4. SNIPER RULES & OFFERS
# ==============================================================================


@app.get("/api/sniper/rules")
async def get_sniper_rules() -> dict[str, Any]:
    rules = await db.list_sniper_rules()
    return {"rules": rules}


@app.post("/api/sniper/rules")
async def create_sniper_rule(body: SniperRuleCreate) -> dict[str, Any]:
    return await db.create_sniper_rule(body.model_dump())


@app.patch("/api/sniper/rules/{rule_id}")
async def update_sniper_rule(rule_id: int, body: SniperRuleUpdate) -> dict[str, Any]:
    updated = await db.update_sniper_rule(rule_id, body.model_dump(exclude_none=True))
    if not updated:
        raise HTTPException(status_code=404, detail="Правило снайпера не знайдено")
    return updated


@app.delete("/api/sniper/rules/{rule_id}")
async def delete_sniper_rule(rule_id: int) -> dict[str, Any]:
    deleted = await db.delete_sniper_rule(rule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Правило снайпера не знайдено")
    return {"deleted": True, "id": rule_id}


@app.get("/api/sniper/alerts")
async def get_sniper_alerts(limit: int = Query(default=30, ge=1, le=100)) -> dict[str, Any]:
    alerts = await db.list_alert_logs(limit=limit)
    return {"alerts": alerts}


@app.post("/api/sniper/test-alert")
async def post_sniper_test_alert() -> dict[str, Any]:
    try:
        return await sniper_engine.trigger_test_alert()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/offers")
async def get_offers() -> dict[str, Any]:
    offers, radar, cols = await asyncio.gather(
        db.list_offers(),
        analytics_engine.get_offer_radar(limit=12),
        analytics_engine.get_collections_summary(limit=100),
    )
    col_by_short = {c.short_name: c for c in cols}
    enriched_offers: list[dict[str, Any]] = []
    for o in offers:
        col = col_by_short.get(o["collection_short_name"])
        floor = col.floor_price if col else round(o["bid_price"] * 1.2, 2)
        best_market_offer = col.best_offer if col else round(o["bid_price"] - 0.1, 2)
        enriched_offers.append(
            {
                **o,
                "photo_url": col.photo_url if col else f"https://nft.fragment.com/collection/{o['collection_short_name']}.webp",
                "current_floor": floor,
                "best_market_offer": best_market_offer,
                "is_top_offer": o["bid_price"] >= best_market_offer,
                "est_profit_ton": round(floor * 0.95 - o["bid_price"], 2),
            }
        )
    return {"offers": enriched_offers, "radar": radar}


@app.post("/api/offers")
async def create_offer(body: UserOfferCreate) -> dict[str, Any]:
    return await db.create_offer(body.model_dump())


@app.post("/api/offers/{offer_id}/outbid")
async def outbid_offer(
    offer_id: int,
    body: OfferOutbidRequest | None = Body(default=None),
) -> dict[str, Any]:
    step = body.step if body else 0.1
    updated = await db.bump_offer(offer_id, step=step)
    if not updated:
        raise HTTPException(status_code=404, detail="Офер не знайдено")
    return updated


@app.delete("/api/offers/{offer_id}")
async def delete_offer(offer_id: int) -> dict[str, Any]:
    deleted = await db.delete_offer(offer_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Офер не знайдено")
    return {"deleted": True, "id": offer_id}


# ==============================================================================
# 5. PORTFOLIO & SMART AUTO-UNDERCUT
# ==============================================================================


@app.get("/api/portfolio")
async def get_portfolio() -> dict[str, Any]:
    return await undercut_engine.build_enriched_portfolio()


@app.post("/api/portfolio")
async def create_portfolio_item(body: PortfolioCreate) -> dict[str, Any]:
    created = await db.create_portfolio_item(body.model_dump())
    enriched = await undercut_engine.get_enriched_item(created["id"])
    return enriched or created


@app.patch("/api/portfolio/{item_id}")
async def update_portfolio_item(item_id: int, body: PortfolioUpdate) -> dict[str, Any]:
    updated = await db.update_portfolio_item(item_id, body.model_dump(exclude_none=True))
    if not updated:
        raise HTTPException(status_code=404, detail="Позицію в портфелі не знайдено")
    enriched = await undercut_engine.get_enriched_item(item_id)
    return enriched or updated


@app.post("/api/portfolio/{item_id}/apply-undercut")
async def apply_portfolio_undercut(item_id: int) -> dict[str, Any]:
    try:
        return await undercut_engine.apply_undercut(item_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/portfolio/{item_id}/simulate-competitor")
async def simulate_competitor(
    item_id: int,
    body: SimulateCompetitorRequest | None = Body(default=None),
) -> dict[str, Any]:
    drop = body.drop_ton if body else 0.1
    try:
        return await undercut_engine.simulate_competitor_undercut(item_id, drop_ton=drop)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/api/portfolio/{item_id}")
async def delete_portfolio_item(item_id: int) -> dict[str, Any]:
    deleted = await db.delete_portfolio_item(item_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Позицію в портфелі не знайдено")
    return {"deleted": True, "id": item_id}


# ==============================================================================
# 6. MARKETS, BOT, RISK SETTINGS & TRADE EXECUTION
# ==============================================================================


@app.get("/api/settings")
async def get_settings() -> dict[str, Any]:
    data = runtime_config.as_public_dict(
        bot_connected=telegram_bot_service.is_connected,
        live_markets=multi_market.get_live_markets(),
    )
    data["bot_username"] = telegram_bot_service.bot_username
    data["today_spent_ton"] = round(await db.get_today_spent_ton(), 2)
    return data


@app.patch("/api/settings")
async def patch_settings(body: SettingsUpdate) -> dict[str, Any]:
    updates = body.model_dump(exclude_none=True)
    old_token = runtime_config.tg_bot_token
    await db.save_settings(updates)

    # Restart Telegram bot if token changed (in Vercel mode just reset cached bot for webhook)
    if "tg_bot_token" in updates and runtime_config.tg_bot_token != old_token:
        if IS_VERCEL:
            await telegram_bot_service.stop()
        else:
            await telegram_bot_service.restart()

    # Refresh caches if marketplace credentials changed
    if any(k in updates for k in ("getgems_api_key", "portals_init_data", "mrkt_init_data", "tonnel_init_data")):
        analytics_engine.clear_caches()

    return await get_settings()


@app.post("/api/settings/test-telegram")
async def test_telegram() -> dict[str, Any]:
    return await telegram_bot_service.send_test_message()


@app.post("/api/trade/execute")
async def execute_trade(body: TradeExecuteRequest) -> dict[str, Any]:
    price = round(float(body.price), 2)
    today_spent = await db.get_today_spent_ton()

    if price > runtime_config.max_single_buy_ton:
        raise HTTPException(
            status_code=400,
            detail=f"Ціна {price} TON перевищує ліміт однієї угоди ({runtime_config.max_single_buy_ton} TON). Змініть ліміт у Налаштуваннях.",
        )
    if today_spent + price > runtime_config.daily_limit_ton:
        raise HTTPException(
            status_code=400,
            detail=f"Перевищено денний ліміт витрат ({today_spent:.1f} + {price} > {runtime_config.daily_limit_ton} TON).",
        )

    is_dry = runtime_config.dry_run
    mode = "DRY_RUN" if is_dry else "LIVE"

    await db.record_trade(body.listing_id, body.short_name, price, is_dry)
    target_list = body.auto_list_price or round(
        max((body.fair_value or price * 1.18) * 0.97, price * 1.15), 2
    )
    created = await db.create_portfolio_item(
        {
            "tg_id": body.tg_id or f"{body.collection_name.replace(' ', '')}-{body.number}",
            "collection_name": body.collection_name,
            "short_name": body.short_name,
            "number": body.number,
            "photo_url": body.photo_url,
            "buy_price": price,
            "listed_price": target_list,
            "market": body.market,
            "auto_undercut_enabled": True,
            "undercut_mode": "notify",
            "min_price_guard": round(price * 1.07, 2),
            "undercut_step": 0.05,
            "status": "listed",
        }
    )
    enriched = await undercut_engine.get_enriched_item(created["id"]) or created

    msg = (
        f"[DRY RUN] Симуляція купівлі {body.collection_name} #{body.number} за {price} TON успішна. Додано в портфель."
        if is_dry
        else f"[LIVE] Ордер на купівлю {body.collection_name} #{body.number} за {price} TON виконано. Додано в портфель."
    )
    await db.add_alert_log(
        alert_type="trade",
        listing_id=body.listing_id,
        title=f"Купівля [{mode}]: {body.collection_name} #{body.number}",
        summary=msg,
        payload=enriched,
    )
    await ws_manager.broadcast("trade_executed", {"mode": mode, "item": enriched, "message": msg})

    return {
        "ok": True,
        "dry_run": is_dry,
        "mode": mode,
        "message": msg,
        "portfolio_item": enriched,
    }


# ==============================================================================
# 7. WEBSOCKET /ws/live
# ==============================================================================


@app.websocket("/ws/live")
async def websocket_live(ws: WebSocket) -> None:
    await ws_manager.connect(ws)
    try:
        await ws.send_json(
            {
                "type": "connected",
                "data": {
                    "app": "TON Gift Terminal Pro",
                    "live_markets": multi_market.get_live_markets(),
                    "dry_run": runtime_config.dry_run,
                },
                "timestamp": utc_now_iso(),
            }
        )
        while True:
            text = await ws.receive_text()
            if text.strip().lower() == "ping":
                await ws.send_json({"type": "pong", "timestamp": utc_now_iso()})
    except WebSocketDisconnect:
        await ws_manager.disconnect(ws)
    except Exception:
        await ws_manager.disconnect(ws)


# ==============================================================================
# 8. STATIC FRONTEND SERVING (if frontend/dist is built)
# ==============================================================================

_FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _FRONTEND_DIST.exists() and (_FRONTEND_DIST / "index.html").exists():
    assets_dir = _FRONTEND_DIST / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api/") or full_path.startswith("ws/"):
            raise HTTPException(status_code=404, detail="Not Found")
        candidate = _FRONTEND_DIST / full_path
        if full_path and candidate.exists() and candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(_FRONTEND_DIST / "index.html"))
