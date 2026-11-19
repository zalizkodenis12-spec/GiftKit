# API Contract — TON Gift Terminal Pro

Base URL: `/api` (proxied to `http://127.0.0.1:8000/api`)
WebSocket URL: `/ws/live`

## Common Types

### MarketName
`"portals" | "getgems" | "mrkt" | "tonnel" | "fragment"`

### MarketPricePoint
```json
{
  "market": "portals",
  "floor_price": 30.99,
  "fee_percent": 5.0,
  "is_live": true,
  "url": "https://portal-market.com/..."
}
```

### TraitAttribute
```json
{
  "type": "model" | "backdrop" | "symbol",
  "value": "Golden Shine",
  "rarity_percent": 1.9,
  "trait_floor": 48.5,
  "supply": 42
}
```

### SaleRecord
```json
{
  "price": 32.5,
  "market": "portals",
  "timestamp": "2026-11-19T16:40:00Z",
  "buyer": "UQ...8f2a",
  "tx_type": "sale" | "offer_accepted"
}
```

### AnalyzedListing
```json
{
  "id": "uuid-or-id",
  "tg_id": "EternalRose-18718",
  "collection_id": "uuid",
  "collection_name": "Eternal Rose",
  "short_name": "eternalrose",
  "number": 18718,
  "photo_url": "https://...",
  "market": "portals",
  "market_url": "https://t.me/portals/market?startapp=...",
  "price": 24.5,
  "collection_floor": 30.8,
  "model_floor": 42.0,
  "backdrop_floor": 35.0,
  "fair_value": 36.4,
  "discount_percent": 32.7,
  "net_profit_ton": 9.8,
  "net_profit_percent": 40.0,
  "fee_percent": 5.0,
  "liquidity_score": 84,
  "sales_24h": 142,
  "is_rare_combo": true,
  "combo_label": "Gold & Classic Match",
  "number_badge": "Low Mint" | "Palindrome" | "Repeating" | null,
  "thin_floor_warning": "До +19% залишилось 2 лоти",
  "wash_trade_risk": false,
  "best_sell_market": "getgems",
  "best_sell_price": 35.2,
  "verdict": "STRONG_BUY" | "GOOD_DEAL" | "FAIR" | "OVERPRICED",
  "verdict_label": "Супер фліп (+40%)",
  "listed_at": "2026-11-19T17:58:00Z",
  "attributes": [ /* TraitAttribute[] */ ],
  "market_prices": [ /* MarketPricePoint[] */ ],
  "recent_sales": [ /* SaleRecord[] */ ],
  "is_live": true
}
```

### CollectionSummary
```json
{
  "id": "uuid",
  "name": "Eternal Rose",
  "short_name": "eternalrose",
  "photo_url": "https://...",
  "floor_price": 30.8,
  "change_24h_percent": 6.4,
  "day_volume": 12450.5,
  "total_volume": 912822.9,
  "supply": 38400,
  "listed_count": 1120,
  "sales_24h": 142,
  "market_cap": 1182720.0,
  "liquidity_score": 88,
  "best_offer": 25.4,
  "bid_ask_spread_percent": 17.5,
  "thin_floor_gap_percent": 14.2,
  "thin_floor_count": 3,
  "wash_trade_flag": false,
  "market_floors": {
    "portals": 30.8,
    "getgems": 31.4,
    "mrkt": 32.1,
    "tonnel": 30.2
  },
  "arbitrage_spread_percent": 6.3,
  "is_live": true
}
```

---

## Endpoints

### 1. System & Overview
- `GET /api/overview`
  Returns:
  ```json
  {
    "ton_usd": 1.03,
    "ton_change_24h": 0.87,
    "total_collections": 100,
    "active_rules": 3,
    "portfolio_count": 4,
    "portfolio_pnl_ton": 18.4,
    "arbitrage_opportunities_count": 12,
    "live_markets": ["portals", "getgems"],
    "bot_connected": false,
    "dry_run": true,
    "last_sync": "2026-11-19T18:00:00Z"
  }
  ```

### 2. Scanner & Listings
- `GET /api/scanner/listings`
  Query params:
  - `collection`: optional short_name
  - `market`: optional (`all` | `portals` | `getgems` | `mrkt` | `tonnel`)
  - `min_discount`: float (default -100)
  - `max_price`: optional float
  - `rare_combo_only`: bool (default false)
  - `sort`: `"discount_desc" | "price_asc" | "price_desc" | "newest" | "profit_desc"`
  - `limit`: int (default 40)
  Returns: `{ "items": AnalyzedListing[], "arbitrage_top": ArbitrageOpportunity[], "total": int }`

- `GET /api/scanner/arbitrage`
  Returns:
  ```json
  {
    "opportunities": [
      {
        "id": "...",
        "collection_name": "Eternal Rose",
        "short_name": "eternalrose",
        "photo_url": "...",
        "buy_market": "tonnel",
        "buy_price": 28.5,
        "sell_market": "getgems",
        "sell_price": 33.4,
        "net_profit_ton": 3.23,
        "roi_percent": 11.3,
        "liquidity_score": 86,
        "type": "instant_offer" | "floor_spread"
      }
    ]
  }
  ```

- `POST /api/scanner/refresh` -> triggers immediate fresh fetch from live APIs.

### 3. Analytics & X-Ray
- `GET /api/analytics/collections`
  Query params: `search`, `sort` (`volume_desc` | `floor_desc` | `floor_asc` | `change_desc` | `liquidity_desc` | `spread_desc`), `limit` (default 50)
  Returns: `{ "collections": CollectionSummary[], "heatmap": CollectionSummary[] }`

- `GET /api/analytics/collections/{short_name}/chart`
  Query params: `timeframe` (`24h` | `7d` | `30d`)
  Returns:
  ```json
  {
    "collection": CollectionSummary,
    "points": [
      { "time": 1763500800, "floor": 30.2, "avg_sale": 31.5, "volume": 420.5 }
    ],
    "traits": {
      "models": [{ "name": "Quantum", "rarity_percent": 0.8, "floor_price": 49.95, "supply": 15 }],
      "backdrops": [{ "name": "Black", "rarity_percent": 1.1, "floor_price": 45.0, "supply": 22 }],
      "symbols": [{ "name": "Crown", "rarity_percent": 0.5, "floor_price": 39.0, "supply": 10 }]
    },
    "orderbook_depth": [
      { "price": 30.8, "count": 2 },
      { "price": 31.2, "count": 3 }
    ]
  }
  ```

- `GET /api/analytics/xray`
  Query params: `query` (e.g., `"Eternal Rose #18718"`, `"eternalrose-18718"`, `"https://t.me/nft/EternalRose-18718"`, or item UUID)
  Returns: `{ "item": AnalyzedListing, "comparable_sales": SaleRecord[], "recommendation": string }`

- `GET /api/analytics/whales`
  Returns:
  ```json
  {
    "events": [
      {
        "id": "...",
        "wallet": "UQ...9a4f",
        "wallet_label": "Кит #1 (TON Gifts Whale)",
        "action": "SWEEP" | "RARE_BUY" | "LIST",
        "collection_name": "Plush Pepe",
        "short_name": "plushpepe",
        "photo_url": "...",
        "count": 4,
        "total_ton": 1820.5,
        "avg_price": 455.1,
        "timestamp": "2026-11-19T17:52:00Z",
        "signal": "Агресивний викуп флора"
      }
    ]
  }
  ```

### 4. Sniper Rules & Offers
- `GET /api/sniper/rules` -> `{ "rules": SniperRule[] }`
- `POST /api/sniper/rules` -> creates rule:
  ```json
  {
    "name": "Троянди -20%",
    "collection_short_name": "eternalrose",
    "collection_name": "Eternal Rose",
    "model_filter": "",
    "backdrop_filter": "",
    "max_price": 35.0,
    "min_discount_percent": 15.0,
    "rare_combo_only": false,
    "markets": ["portals", "getgems", "mrkt", "tonnel"],
    "mode": "alert" | "autobuy",
    "enabled": true
  }
  ```
- `PATCH /api/sniper/rules/{id}` -> updates rule (toggle enabled, edit thresholds)
- `DELETE /api/sniper/rules/{id}` -> deletes rule
- `GET /api/sniper/alerts` -> `{ "alerts": AlertLog[] }` (latest triggered cards with full listing payload!)
- `POST /api/sniper/test-alert` -> triggers a real formatted alert (sends to Telegram if configured + pushes via WebSocket + returns Telegram HTML preview!)

- `GET /api/offers` -> `{ "offers": UserOffer[], "radar": OfferRadarItem[] }`
- `POST /api/offers` -> creates new offer `{ "collection_short_name", "collection_name", "market", "bid_price", "max_bid", "auto_outbid" }`
- `POST /api/offers/{id}/outbid` -> bumps offer by `+0.1 TON` (or custom `step`)
- `DELETE /api/offers/{id}` -> cancels offer

### 5. Portfolio & Smart Auto-Undercut
- `GET /api/portfolio`
  Returns:
  ```json
  {
    "summary": {
      "total_invested_ton": 112.5,
      "current_value_ton": 134.8,
      "unrealized_pnl_ton": 22.3,
      "unrealized_pnl_percent": 19.8,
      "active_listings": 3,
      "undercut_active_count": 2
    },
    "items": [
      {
        "id": 1,
        "tg_id": "EternalRose-18718",
        "collection_name": "Eternal Rose",
        "short_name": "eternalrose",
        "number": 18718,
        "photo_url": "...",
        "buy_price": 26.5,
        "listed_price": 31.2,
        "market": "portals",
        "current_floor": 30.8,
        "competitor_price": 30.8,
        "fair_value": 34.5,
        "best_sell_market": "mrkt",
        "best_sell_price": 33.0,
        "auto_undercut_enabled": true,
        "undercut_mode": "auto" | "notify",
        "min_price_guard": 29.0,
        "undercut_step": 0.05,
        "thin_floor_warning": "Тонкий стакан: 2 лоти до 35 TON — краще не демпінгувати!",
        "status": "listed" | "holding" | "sold",
        "is_undercut_by_competitor": true,
        "suggested_price": 30.75,
        "pnl_ton": 4.7,
        "pnl_percent": 17.7,
        "last_undercut_at": "..."
      }
    ]
  }
  ```
- `POST /api/portfolio` -> adds NFT to portfolio (or quick buy from Scanner!)
- `PATCH /api/portfolio/{id}` -> updates listing price, `auto_undercut_enabled`, `undercut_mode`, `min_price_guard`, `undercut_step`, `status`
- `POST /api/portfolio/{id}/apply-undercut` -> executes `-0.05 TON` (or configured step) below competitor price (respecting `min_price_guard`!), logs alert, sends TG message
- `POST /api/portfolio/{id}/simulate-competitor` -> simulates a competitor undercutting your listing by 0.1 TON to verify Auto-Undercut reaction live!
- `DELETE /api/portfolio/{id}` -> removes item

### 6. Markets, Bot & Risk Settings
- `GET /api/settings`
- `PATCH /api/settings` -> saves `dry_run`, `daily_limit_ton`, `max_single_buy_ton`, `stop_loss_percent`, `wallet_address`, `tg_bot_token` (masked on GET), `tg_admin_chat_id`, `webapp_url`, `getgems_api_key`, `portals_init_data`, `mrkt_init_data`, `tonnel_init_data`
- `POST /api/settings/test-telegram` -> sends live test message to configured Telegram chat (or returns diagnostic status)
- `POST /api/trade/execute` -> executes (or DRY_RUN simulates) quick buy from Scanner / Bot and adds to Portfolio!
