"""FastAPI entrypoint for TON Gift Terminal Pro."""

from __future__ import annotations

import asyncio
import base64
import json
import sys
import types
import urllib.parse
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

# Support BOTH local launch (`uvicorn backend.main:app` from repo root)
# AND Vercel Services (`root: "backend/"`, `entrypoint: "main:app"` where files live in /var/task/).
_BACKEND_DIR = Path(__file__).resolve().parent
if _BACKEND_DIR.name == "backend":
    _PROJECT_ROOT = str(_BACKEND_DIR.parent)
    if _PROJECT_ROOT not in sys.path:
        sys.path.insert(0, _PROJECT_ROOT)
else:
    if str(_BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(_BACKEND_DIR))
    if "backend" not in sys.modules:
        _pkg = types.ModuleType("backend")
        _pkg.__path__ = [str(_BACKEND_DIR)]
        _pkg.__package__ = "backend"
        sys.modules["backend"] = _pkg

from fastapi import Body, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from loguru import logger

from backend.config import IS_VERCEL, SECRET_KEYS, base_settings, runtime_config
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
from backend.services import auth_service
from backend.services.analytics_engine import analytics_engine
from backend.services.auth_service import DEFAULT_ADMIN_USER_ID
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
    version="1.2.0",
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
# 0. AUTHENTICATION & CROSS-DEVICE STATE HYDRATION
# ==============================================================================


def _decode_state_header(raw_header: str) -> dict[str, Any] | None:
    """Decode X-GiftKit-State header supporting raw JSON, URL-encoded JSON, or base64 JSON."""
    text = (raw_header or "").strip()
    if not text:
        return None
    # 1. Raw JSON
    if text.startswith("{"):
        try:
            obj = json.loads(text)
            return obj if isinstance(obj, dict) else None
        except Exception:
            pass
    # 2. URL-encoded JSON
    if "%7B" in text or "%22" in text:
        try:
            unquoted = urllib.parse.unquote(text)
            obj = json.loads(unquoted)
            return obj if isinstance(obj, dict) else None
        except Exception:
            pass
    # 3. Base64 / Base64URL JSON
    try:
        padded = text + "=" * ((4 - len(text) % 4) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        obj = json.loads(decoded)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _public_user_fields(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "tg_user_id": str(user.get("tg_user_id") or DEFAULT_ADMIN_USER_ID),
        "username": str(user.get("username") or ""),
        "first_name": str(user.get("first_name") or ""),
        "last_name": str(user.get("last_name") or ""),
        "photo_url": str(user.get("photo_url") or ""),
    }


async def get_request_user(request: Request) -> dict[str, Any]:
    """Authenticate request via Bearer token, X-Telegram-Init-Data, or X-GiftKit-Auth & hydrate state."""
    verified_user: dict[str, Any] | None = None

    auth_header = (request.headers.get("Authorization") or "").strip()
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
        verified_user = auth_service.verify_signed_token(token)

    if verified_user is None:
        gk_auth = (request.headers.get("X-GiftKit-Auth") or "").strip()
        if gk_auth:
            verified_user = auth_service.verify_signed_token(gk_auth)

    if verified_user is None:
        init_data_hdr = (request.headers.get("X-Telegram-Init-Data") or "").strip()
        if init_data_hdr:
            verified_user = auth_service.verify_telegram_init_data(init_data_hdr)

    if verified_user is None:
        q_auth = (request.query_params.get("tg_auth") or "").strip()
        if q_auth:
            verified_user = auth_service.verify_signed_token(q_auth)

    state_header_raw = (request.headers.get("X-GiftKit-State") or "").strip()
    parsed_state_env = _decode_state_header(state_header_raw) if state_header_raw else None

    if verified_user is None and isinstance(parsed_state_env, dict):
        env_uid = str(parsed_state_env.get("user_id") or "").strip()
        if env_uid and auth_service.verify_state_envelope(env_uid, parsed_state_env):
            existing_u = await db.get_user(env_uid)
            verified_user = existing_u or {"tg_user_id": env_uid}

    if verified_user is not None:
        user = await db.upsert_user(verified_user)
        authenticated = True
    else:
        default_id = (
            runtime_config.tg_admin_chat_id.strip()
            or base_settings.TG_ADMIN_CHAT_ID.strip()
            or DEFAULT_ADMIN_USER_ID
        )
        user = await db.get_user(default_id)
        if not user:
            user = await telegram_bot_service.resolve_chat_profile(default_id)
        authenticated = False

    if isinstance(parsed_state_env, dict):
        try:
            await db.import_user_state(user["tg_user_id"], parsed_state_env)
        except Exception as exc:
            logger.debug(f"X-GiftKit-State import skipped: {exc}")

    return {
        **user,
        "authenticated": authenticated,
    }


@app.post("/api/auth/session")
async def post_auth_session(
    request: Request,
    body: dict[str, Any] | None = Body(default=None),
) -> dict[str, Any]:
    """Authenticate Telegram Mini App / Bot deep-link / Bearer token and synchronize state envelope."""
    payload = body or {}
    init_data = str(payload.get("init_data") or "").strip()
    tg_auth = str(payload.get("tg_auth") or "").strip()
    incoming_envelope = payload.get("state_envelope")

    verified_user: dict[str, Any] | None = None

    if init_data:
        verified_user = auth_service.verify_telegram_init_data(init_data)
        if verified_user is None:
            raise HTTPException(status_code=401, detail="Недійсний підпис Telegram initData")
    elif tg_auth:
        verified_user = auth_service.verify_signed_token(tg_auth)
        if verified_user is None:
            raise HTTPException(status_code=401, detail="Недійсний токен авторизації tg_auth")
    else:
        # Check request headers
        auth_header = (request.headers.get("Authorization") or "").strip()
        if auth_header.lower().startswith("bearer "):
            verified_user = auth_service.verify_signed_token(auth_header[7:].strip())
        if verified_user is None:
            gk_auth = (request.headers.get("X-GiftKit-Auth") or "").strip()
            if gk_auth:
                verified_user = auth_service.verify_signed_token(gk_auth)
        if verified_user is None:
            init_hdr = (request.headers.get("X-Telegram-Init-Data") or "").strip()
            if init_hdr:
                verified_user = auth_service.verify_telegram_init_data(init_hdr)

    if verified_user is None and isinstance(incoming_envelope, dict):
        env_uid = str(incoming_envelope.get("user_id") or "").strip()
        if env_uid and auth_service.verify_state_envelope(env_uid, incoming_envelope):
            verified_user = (await db.get_user(env_uid)) or {"tg_user_id": env_uid}

    if verified_user is not None:
        user = await db.upsert_user(verified_user)
    else:
        default_id = (
            runtime_config.tg_admin_chat_id.strip()
            or base_settings.TG_ADMIN_CHAT_ID.strip()
            or DEFAULT_ADMIN_USER_ID
        )
        user = await telegram_bot_service.resolve_chat_profile(default_id)

    uid = user["tg_user_id"]

    # Hydrate from header or body state_envelope if newer
    state_header_raw = (request.headers.get("X-GiftKit-State") or "").strip()
    header_env = _decode_state_header(state_header_raw) if state_header_raw else None
    if isinstance(header_env, dict):
        await db.import_user_state(uid, header_env)
    if isinstance(incoming_envelope, dict):
        await db.import_user_state(uid, incoming_envelope)

    session_token = auth_service.create_signed_token(user)
    state_envelope = await db.export_user_state(uid)

    return {
        "ok": True,
        "authenticated": True,
        "user": _public_user_fields(user),
        "session_token": session_token,
        "state_envelope": state_envelope,
    }


@app.get("/api/auth/me")
async def get_auth_me(request: Request) -> dict[str, Any]:
    """Return current authenticated user profile and signed state envelope."""
    user = await get_request_user(request)
    uid = user["tg_user_id"]
    state_envelope = await db.export_user_state(uid)
    return {
        "ok": True,
        "authenticated": bool(user.get("authenticated")),
        "user": _public_user_fields(user),
        "state_envelope": state_envelope,
    }


@app.post("/api/auth/login-code")
async def post_auth_login_code() -> dict[str, Any]:
    """Generate a one-time nonce and @GiftKit_bot deep-link for 1-click browser/PWA login."""
    nonce = auth_service.create_login_nonce()
    bot_username = (telegram_bot_service.bot_username or "GiftKit_bot").strip().lstrip("@") or "GiftKit_bot"
    return {
        "ok": True,
        "nonce": nonce,
        "bot_username": bot_username,
        "bot_login_url": f"https://t.me/{bot_username}?start=login_{nonce}",
    }


@app.get("/api/auth/poll-login")
async def get_auth_poll_login(nonce: str = Query(..., min_length=4)) -> dict[str, Any]:
    """Poll login nonce status; returns session_token, user, and state_envelope once approved in @GiftKit_bot."""
    approved_user = auth_service.poll_login_nonce(nonce)
    if not approved_user:
        return {"ok": True, "ready": False}

    user = await db.upsert_user(approved_user)
    uid = user["tg_user_id"]
    session_token = auth_service.create_signed_token(user)
    state_envelope = await db.export_user_state(uid)
    return {
        "ok": True,
        "ready": True,
        "authenticated": True,
        "session_token": session_token,
        "user": _public_user_fields(user),
        "state_envelope": state_envelope,
    }


@app.get("/api/auth/avatar/{tg_user_id}")
async def get_user_avatar(tg_user_id: str) -> Response:
    """Resolve user's Telegram avatar without exposing TG_BOT_TOKEN."""
    user = await db.get_user(tg_user_id)
    if user and user.get("username"):
        return RedirectResponse(f"https://t.me/i/userpic/320/{user['username']}.jpg")
    return Response(status_code=204)


@app.get("/api/internal/bot-sync")
async def get_internal_bot_sync(
    request: Request,
    user_id: str = Query(default=DEFAULT_ADMIN_USER_ID),
) -> dict[str, Any]:
    """Internal endpoint for local @GiftKit_bot process to pull latest user rules from Vercel."""
    sig = (request.headers.get("X-Bot-Sync-Signature") or "").strip()
    if not auth_service.verify_bot_sync_signature(sig):
        raise HTTPException(status_code=403, detail="Forbidden")
    uid = str(user_id or DEFAULT_ADMIN_USER_ID).strip()
    return {
        "ok": True,
        "user_id": uid,
        "state_envelope": await db.export_user_state(uid),
        "rules": await db.list_sniper_rules(user_id=uid),
    }


@app.post("/api/internal/bot-sync")
async def post_internal_bot_sync(
    request: Request,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Internal endpoint for local @GiftKit_bot process to push state & triggered alerts to Vercel."""
    sig = (request.headers.get("X-Bot-Sync-Signature") or "").strip()
    if not auth_service.verify_bot_sync_signature(sig):
        raise HTTPException(status_code=403, detail="Forbidden")

    uid = str(body.get("user_id") or DEFAULT_ADMIN_USER_ID).strip()
    envelope = body.get("state_envelope")
    if isinstance(envelope, dict):
        await db.import_user_state(uid, envelope)

    alerts = body.get("alerts")
    if isinstance(alerts, list):
        existing = await db.list_alert_logs(limit=30, user_id=uid)
        existing_keys = {(a.get("listing_id"), a.get("rule_id")) for a in existing}
        for al in alerts:
            if not isinstance(al, dict):
                continue
            key = (al.get("listing_id"), al.get("rule_id"))
            if key in existing_keys:
                continue
            await db.add_alert_log(
                alert_type=str(al.get("alert_type") or "sniper"),
                rule_id=al.get("rule_id"),
                rule_name=str(al.get("rule_name") or ""),
                listing_id=str(al.get("listing_id") or ""),
                title=str(al.get("title") or "Снайпер-сигнал"),
                summary=str(al.get("summary") or ""),
                payload=al.get("payload") if isinstance(al.get("payload"), dict) else {},
                telegram_html=str(al.get("telegram_html") or ""),
                telegram_sent=bool(al.get("telegram_sent", True)),
                user_id=uid,
            )

    return {
        "ok": True,
        "user_id": uid,
        "state_envelope": await db.export_user_state(uid),
    }


# ==============================================================================
# 1. SYSTEM & OVERVIEW
# ==============================================================================


@app.get("/api/health")
async def get_health() -> dict[str, Any]:
    return {
        "status": "ok",
        "vercel": IS_VERCEL,
        "live_markets": multi_market.get_live_markets(),
        "bot_connected": telegram_bot_service.is_connected,
        "timestamp": utc_now_iso(),
    }


@app.get("/api/overview")
async def get_overview(request: Request) -> dict[str, Any]:
    user = await get_request_user(request)
    uid = user["tg_user_id"]
    (ton_usd, ton_change), cols, rules, portfolio, arb = await asyncio.gather(
        getgems_client.get_ton_rate(),
        analytics_engine.get_collections_summary(limit=250),
        db.list_sniper_rules(user_id=uid),
        undercut_engine.build_enriched_portfolio(user_id=uid),
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
async def get_sniper_rules(request: Request) -> dict[str, Any]:
    user = await get_request_user(request)
    uid = user["tg_user_id"]
    rules = await db.list_sniper_rules(user_id=uid)
    state_envelope = await db.export_user_state(uid)
    return {"rules": rules, "state_envelope": state_envelope}


@app.post("/api/sniper/rules")
async def create_sniper_rule(request: Request, body: SniperRuleCreate) -> dict[str, Any]:
    user = await get_request_user(request)
    uid = user["tg_user_id"]
    created = await db.create_sniper_rule(body.model_dump(), user_id=uid)
    state_envelope = await db.export_user_state(uid)
    return {**created, "rule": created, "state_envelope": state_envelope}


@app.patch("/api/sniper/rules/{rule_id}")
async def update_sniper_rule(
    rule_id: int,
    request: Request,
    body: SniperRuleUpdate,
) -> dict[str, Any]:
    user = await get_request_user(request)
    uid = user["tg_user_id"]
    updated = await db.update_sniper_rule(rule_id, body.model_dump(exclude_none=True), user_id=uid)
    if not updated:
        raise HTTPException(status_code=404, detail="Правило снайпера не знайдено")
    state_envelope = await db.export_user_state(uid)
    return {**updated, "rule": updated, "state_envelope": state_envelope}


@app.delete("/api/sniper/rules/{rule_id}")
async def delete_sniper_rule(rule_id: int, request: Request) -> dict[str, Any]:
    user = await get_request_user(request)
    uid = user["tg_user_id"]
    deleted = await db.delete_sniper_rule(rule_id, user_id=uid)
    if not deleted:
        raise HTTPException(status_code=404, detail="Правило снайпера не знайдено")
    state_envelope = await db.export_user_state(uid)
    return {"deleted": True, "id": rule_id, "state_envelope": state_envelope}


@app.get("/api/sniper/alerts")
async def get_sniper_alerts(
    request: Request,
    limit: int = Query(default=30, ge=1, le=100),
) -> dict[str, Any]:
    user = await get_request_user(request)
    uid = user["tg_user_id"]
    alerts = await db.list_alert_logs(limit=limit, user_id=uid)
    return {"alerts": alerts}


@app.post("/api/sniper/test-alert")
async def post_sniper_test_alert(request: Request) -> dict[str, Any]:
    user = await get_request_user(request)
    uid = user["tg_user_id"]
    try:
        return await sniper_engine.trigger_test_alert(user_id=uid)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/offers")
async def get_offers(request: Request) -> dict[str, Any]:
    user = await get_request_user(request)
    uid = user["tg_user_id"]
    offers, radar, cols = await asyncio.gather(
        db.list_offers(user_id=uid),
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
    state_envelope = await db.export_user_state(uid)
    return {"offers": enriched_offers, "radar": radar, "state_envelope": state_envelope}


@app.post("/api/offers")
async def create_offer(request: Request, body: UserOfferCreate) -> dict[str, Any]:
    user = await get_request_user(request)
    uid = user["tg_user_id"]
    created = await db.create_offer(body.model_dump(), user_id=uid)
    state_envelope = await db.export_user_state(uid)
    return {**created, "offer": created, "state_envelope": state_envelope}


@app.post("/api/offers/{offer_id}/outbid")
async def outbid_offer(
    offer_id: int,
    request: Request,
    body: OfferOutbidRequest | None = Body(default=None),
) -> dict[str, Any]:
    user = await get_request_user(request)
    uid = user["tg_user_id"]
    step = body.step if body else 0.1
    updated = await db.bump_offer(offer_id, step=step, user_id=uid)
    if not updated:
        raise HTTPException(status_code=404, detail="Офер не знайдено")
    state_envelope = await db.export_user_state(uid)
    return {**updated, "offer": updated, "state_envelope": state_envelope}


@app.delete("/api/offers/{offer_id}")
async def delete_offer(offer_id: int, request: Request) -> dict[str, Any]:
    user = await get_request_user(request)
    uid = user["tg_user_id"]
    deleted = await db.delete_offer(offer_id, user_id=uid)
    if not deleted:
        raise HTTPException(status_code=404, detail="Офер не знайдено")
    state_envelope = await db.export_user_state(uid)
    return {"deleted": True, "id": offer_id, "state_envelope": state_envelope}


# ==============================================================================
# 5. PORTFOLIO & SMART AUTO-UNDERCUT
# ==============================================================================


@app.get("/api/portfolio")
async def get_portfolio(request: Request) -> dict[str, Any]:
    user = await get_request_user(request)
    uid = user["tg_user_id"]
    pf = await undercut_engine.build_enriched_portfolio(user_id=uid)
    state_envelope = await db.export_user_state(uid)
    return {**pf, "state_envelope": state_envelope}


@app.post("/api/portfolio")
async def create_portfolio_item(request: Request, body: PortfolioCreate) -> dict[str, Any]:
    user = await get_request_user(request)
    uid = user["tg_user_id"]
    created = await db.create_portfolio_item(body.model_dump(), user_id=uid)
    enriched = await undercut_engine.get_enriched_item(created["id"], user_id=uid)
    state_envelope = await db.export_user_state(uid)
    base = enriched or created
    return {**base, "state_envelope": state_envelope}


@app.patch("/api/portfolio/{item_id}")
async def update_portfolio_item(
    item_id: int,
    request: Request,
    body: PortfolioUpdate,
) -> dict[str, Any]:
    user = await get_request_user(request)
    uid = user["tg_user_id"]
    updated = await db.update_portfolio_item(item_id, body.model_dump(exclude_none=True), user_id=uid)
    if not updated:
        raise HTTPException(status_code=404, detail="Позицію в портфелі не знайдено")
    enriched = await undercut_engine.get_enriched_item(item_id, user_id=uid)
    state_envelope = await db.export_user_state(uid)
    base = enriched or updated
    return {**base, "state_envelope": state_envelope}


@app.post("/api/portfolio/{item_id}/apply-undercut")
async def apply_portfolio_undercut(item_id: int, request: Request) -> dict[str, Any]:
    user = await get_request_user(request)
    uid = user["tg_user_id"]
    try:
        res = await undercut_engine.apply_undercut(item_id, user_id=uid)
        state_envelope = await db.export_user_state(uid)
        return {**res, "state_envelope": state_envelope}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/portfolio/{item_id}/simulate-competitor")
async def simulate_competitor(
    item_id: int,
    request: Request,
    body: SimulateCompetitorRequest | None = Body(default=None),
) -> dict[str, Any]:
    user = await get_request_user(request)
    uid = user["tg_user_id"]
    drop = body.drop_ton if body else 0.1
    try:
        res = await undercut_engine.simulate_competitor_undercut(item_id, drop_ton=drop, user_id=uid)
        state_envelope = await db.export_user_state(uid)
        return {**res, "state_envelope": state_envelope}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/api/portfolio/{item_id}")
async def delete_portfolio_item(item_id: int, request: Request) -> dict[str, Any]:
    user = await get_request_user(request)
    uid = user["tg_user_id"]
    deleted = await db.delete_portfolio_item(item_id, user_id=uid)
    if not deleted:
        raise HTTPException(status_code=404, detail="Позицію в портфелі не знайдено")
    state_envelope = await db.export_user_state(uid)
    return {"deleted": True, "id": item_id, "state_envelope": state_envelope}


# ==============================================================================
# 6. MARKETS, BOT, RISK SETTINGS & TRADE EXECUTION
# ==============================================================================


@app.get("/api/settings")
async def get_settings(request: Request) -> dict[str, Any]:
    user = await get_request_user(request)
    uid = user["tg_user_id"]
    data = runtime_config.as_public_dict(
        bot_connected=telegram_bot_service.is_connected,
        live_markets=multi_market.get_live_markets(),
    )
    data["bot_username"] = telegram_bot_service.bot_username
    data["today_spent_ton"] = round(await db.get_today_spent_ton(user_id=uid), 2)
    return data


@app.patch("/api/settings")
async def patch_settings(request: Request, body: SettingsUpdate) -> dict[str, Any]:
    updates = body.model_dump(exclude_none=True)
    if IS_VERCEL:
        for secret_k in SECRET_KEYS:
            updates.pop(secret_k, None)
    old_token = runtime_config.tg_bot_token
    await db.save_settings(updates)

    if "tg_bot_token" in updates and runtime_config.tg_bot_token != old_token:
        if IS_VERCEL:
            await telegram_bot_service.stop()
        else:
            await telegram_bot_service.restart()

    if any(k in updates for k in ("getgems_api_key", "portals_init_data", "mrkt_init_data", "tonnel_init_data")):
        analytics_engine.clear_caches()

    return await get_settings(request)


@app.post("/api/settings/test-telegram")
async def test_telegram() -> dict[str, Any]:
    return await telegram_bot_service.send_test_message()


@app.post("/api/trade/execute")
async def execute_trade(request: Request, body: TradeExecuteRequest) -> dict[str, Any]:
    user = await get_request_user(request)
    uid = user["tg_user_id"]
    price = round(float(body.price), 2)
    today_spent = await db.get_today_spent_ton(user_id=uid)

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

    await db.record_trade(body.listing_id, body.short_name, price, is_dry, user_id=uid)
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
        },
        user_id=uid,
    )
    enriched = await undercut_engine.get_enriched_item(created["id"], user_id=uid) or created
    state_envelope = await db.export_user_state(uid)

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
        user_id=uid,
    )
    await ws_manager.broadcast("trade_executed", {"mode": mode, "item": enriched, "message": msg})

    return {
        "ok": True,
        "dry_run": is_dry,
        "mode": mode,
        "message": msg,
        "portfolio_item": enriched,
        "state_envelope": state_envelope,
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
