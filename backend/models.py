"""Pydantic schemas adhering strictly to API_CONTRACT.md."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

MarketName = Literal["portals", "getgems", "mrkt", "tonnel", "fragment"]
VerdictType = Literal["STRONG_BUY", "GOOD_DEAL", "FAIR", "OVERPRICED"]


class MarketPricePoint(BaseModel):
    market: MarketName
    floor_price: float
    fee_percent: float
    is_live: bool
    url: str


class TraitAttribute(BaseModel):
    type: Literal["model", "backdrop", "symbol"]
    value: str
    rarity_percent: float
    trait_floor: float
    supply: int = 0


class SaleRecord(BaseModel):
    price: float
    market: MarketName
    timestamp: str
    buyer: str
    tx_type: Literal["sale", "offer_accepted"] = "sale"


class AnalyzedListing(BaseModel):
    id: str
    tg_id: str
    collection_id: str
    collection_name: str
    short_name: str
    number: int
    photo_url: str
    market: MarketName
    market_url: str
    price: float
    collection_floor: float
    model_floor: float
    backdrop_floor: float
    fair_value: float
    discount_percent: float
    net_profit_ton: float
    net_profit_percent: float
    fee_percent: float = 5.0
    liquidity_score: int
    sales_24h: int
    is_rare_combo: bool = False
    combo_label: str | None = None
    number_badge: str | None = None
    visual_score: float = 6.5
    visual_tag: str = "Стандарт"
    is_monochrome: bool = False
    harmony_label: str | None = None
    color_swatches: list[str] = Field(default_factory=list)
    number_pattern: str | None = None
    number_bonus_percent: float = 0.0
    trend_boost_percent: float = 0.0
    trend_label: str | None = None
    ai_vision_comment: str | None = None
    thin_floor_warning: str | None = None
    wash_trade_risk: bool = False
    best_sell_market: MarketName = "portals"
    best_sell_price: float = 0.0
    verdict: VerdictType = "FAIR"
    verdict_label: str = "Ринкова ціна"
    listed_at: str
    attributes: list[TraitAttribute] = Field(default_factory=list)
    market_prices: list[MarketPricePoint] = Field(default_factory=list)
    recent_sales: list[SaleRecord] = Field(default_factory=list)
    is_live: bool = True


class CollectionSummary(BaseModel):
    id: str
    name: str
    short_name: str
    photo_url: str
    floor_price: float
    change_24h_percent: float
    day_volume: float
    total_volume: float
    supply: int
    listed_count: int
    sales_24h: int
    market_cap: float
    liquidity_score: int
    best_offer: float
    bid_ask_spread_percent: float
    thin_floor_gap_percent: float
    thin_floor_count: int
    wash_trade_flag: bool = False
    market_floors: dict[str, float] = Field(default_factory=dict)
    arbitrage_spread_percent: float = 0.0
    is_live: bool = True


class ArbitrageOpportunity(BaseModel):
    id: str
    collection_name: str
    short_name: str
    photo_url: str
    buy_market: MarketName
    buy_price: float
    sell_market: MarketName
    sell_price: float
    net_profit_ton: float
    roi_percent: float
    liquidity_score: int
    type: Literal["instant_offer", "floor_spread"]


class WhaleEvent(BaseModel):
    id: str
    wallet: str
    wallet_label: str
    action: Literal["SWEEP", "RARE_BUY", "LIST"]
    collection_name: str
    short_name: str
    photo_url: str
    count: int
    total_ton: float
    avg_price: float
    timestamp: str
    signal: str


# --- Sniper Rules ---

class SniperRuleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    collection_short_name: str = ""
    collection_name: str = "Усі колекції"
    model_filter: str = ""
    backdrop_filter: str = ""
    max_price: float = Field(default=500.0, gt=0)
    min_discount_percent: float = Field(default=15.0, ge=-50, le=95)
    rare_combo_only: bool = False
    markets: list[str] = Field(default_factory=lambda: ["portals", "getgems", "mrkt", "tonnel"])
    mode: Literal["alert", "autobuy"] = "alert"
    enabled: bool = True


class SniperRuleUpdate(BaseModel):
    name: str | None = None
    collection_short_name: str | None = None
    collection_name: str | None = None
    model_filter: str | None = None
    backdrop_filter: str | None = None
    max_price: float | None = None
    min_discount_percent: float | None = None
    rare_combo_only: bool | None = None
    markets: list[str] | None = None
    mode: Literal["alert", "autobuy"] | None = None
    enabled: bool | None = None


class SniperRuleOut(SniperRuleCreate):
    id: int
    hits_count: int = 0
    created_at: str


# --- Offers ---

class UserOfferCreate(BaseModel):
    collection_short_name: str
    collection_name: str
    market: MarketName = "portals"
    bid_price: float = Field(..., gt=0)
    max_bid: float = Field(..., gt=0)
    auto_outbid: bool = True


class OfferOutbidRequest(BaseModel):
    step: float = Field(default=0.1, gt=0, le=100)


# --- Portfolio & Auto-Undercut ---

class PortfolioCreate(BaseModel):
    tg_id: str = ""
    collection_name: str
    short_name: str
    number: int = 1
    photo_url: str = ""
    buy_price: float = Field(..., gt=0)
    listed_price: float | None = None
    market: MarketName = "portals"
    auto_undercut_enabled: bool = True
    undercut_mode: Literal["auto", "notify"] = "notify"
    min_price_guard: float | None = None
    undercut_step: float = Field(default=0.05, gt=0, le=50)
    status: Literal["listed", "holding", "sold"] = "listed"


class PortfolioUpdate(BaseModel):
    listed_price: float | None = None
    market: MarketName | None = None
    auto_undercut_enabled: bool | None = None
    undercut_mode: Literal["auto", "notify"] | None = None
    min_price_guard: float | None = None
    undercut_step: float | None = None
    status: Literal["listed", "holding", "sold"] | None = None


class SimulateCompetitorRequest(BaseModel):
    drop_ton: float = Field(default=0.1, gt=0, le=50)


# --- Settings & Trade ---

class SettingsUpdate(BaseModel):
    dry_run: bool | None = None
    daily_limit_ton: float | None = None
    max_single_buy_ton: float | None = None
    stop_loss_percent: float | None = None
    wallet_address: str | None = None
    tg_bot_token: str | None = None
    tg_admin_chat_id: str | None = None
    webapp_url: str | None = None
    getgems_api_key: str | None = None
    portals_init_data: str | None = None
    mrkt_init_data: str | None = None
    tonnel_init_data: str | None = None
    gemini_api_key: str | None = None
    openai_api_key: str | None = None


class VisionScoreRequest(BaseModel):
    listing_id: str = ""
    photo_url: str = ""
    collection_name: str = ""
    short_name: str = ""
    number: int = 0
    price: float | None = None
    fair_value: float | None = None
    attributes: list[dict[str, Any]] = Field(default_factory=list)


class TradeExecuteRequest(BaseModel):
    listing_id: str = ""
    tg_id: str = ""
    collection_name: str
    short_name: str
    number: int = 1
    photo_url: str = ""
    price: float = Field(..., gt=0)
    market: MarketName = "portals"
    fair_value: float | None = None
    collection_floor: float | None = None
    auto_list_price: float | None = None
    extra: dict[str, Any] = Field(default_factory=dict)
