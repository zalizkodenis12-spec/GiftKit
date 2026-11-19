# TON Gift & NFT Sniper Pro — Architecture & Master Strategy

## Vision
An institutional-grade Telegram Bot + Telegram Mini App (White & Blue TON-native aesthetic) for Telegram Gifts & TON NFTs across **Getgems, Portals, MRKT, Tonnel, and Fragment**.

## Core Modules
1. **Multi-Market Data Engine (Backend - Python FastAPI)**
   - Real live connectors for Getgems GraphQL API, Portals API (`portal-market.com`), TonAPI, Fragment scraping, plus resilient live-calibrated fallback/hybrid simulator when off-chain private APIs (MRKT/Tonnel `initData`) are not configured yet, clearly labeled with data source status (`LIVE` vs `DEMO/FALLBACK`).
   - Fair Value & Real Sales Analyzer (median/trimmed mean of actual sales, wash-trade filter, Liquidity Score 0-100, Thin Floor detector, Rare Combo detector: Monochrome, Gold-on-Black, Low-Mint, Palindromes).
   - Cross-Market Arbitrage Scanner (detecting price spreads & instant-offer arbitrage across Getgems / Portals / MRKT / Tonnel accounting for exact platform fees & royalties).
   - Sniper & Auto-Buy Engine (rule-based monitoring, alert dispatcher, DRY-RUN / LIVE auto-buy guardrails, risk limits).
   - Smart Auto-Undercut & Portfolio Manager (competitor price tracking, automatic or 1-click -0.05 TON undercut above user floor limit, Thin Floor protection warning, Whale/Smart-Money tracker).
   - Offer / Bid War Manager (find largest Bid-Ask spreads, suggest optimal +0.1 TON top bids, batch offer management).

2. **Interactive Telegram Bot (`aiogram 3.x`)**
   - Rich alert cards with NFT preview photo/card, Title + #Number, Model/Backdrop/Symbol rarities & Rare Combo badges, Listing Price vs Floor vs Model Floor vs Fair Value, Recent Real Sales History, Net Profit calculator after fees.
   - Inline action buttons: `[🛒 Купити / Деталі]`, `[⚡ Поставити офер]`, `[📊 Історія продажів]`, `[📱 Відкрити в Mini App]`.
   - Instant Auto-Undercut notifications with 1-click `[✅ Знизити на -0.05 TON]` / `[❌ Залишити]`.
   - X-Ray command / link paste: paste any NFT link or name/number to get full valuation & sales history directly in chat.
   - WebApp launch button opening the White & Blue Telegram Mini App.

3. **Telegram Mini App (Frontend - React + Vite + Tailwind CSS + Lightweight Charts)**
   - **White & Blue TON/Telegram Premium Aesthetic** (`#F4F7FB` canvas, `#FFFFFF` elevated cards, `#0088CC` / `#1D6FF2` TON Blue accents, crisp typography, native Telegram WebApp SDK integration).
   - **5 Core Bottom-Nav Tabs + Deep Drill-down Modals/Drawers:**
     1. **Сканер (Live Feed & Arbitrage)**: Multi-market live listings, instant filters (Market, Collection, Min Discount %, Rare Combos, Liquidity, Max Price), Arbitrage Opportunities banner, quick-inspect drawer with full sales history & profit breakdown.
     2. **Аналітика (GiftChart + X-Ray)**: Interactive TradingView Lightweight Charts (Floor Price, Sales Volume, Liquidity Index), Collection Market Cap & Heatmap (Top Gainers/Losers, Thin Floor badges, Wash-Trade warnings), X-Ray NFT Valuator (paste link/ID or search any gift to calculate exact Fair Value, Trait Rarity Multiplier, Best Market to Sell), Whale Activity feed.
     3. **Снайпер (Rules, Auto-Buy & Offer Radar)**: Create/edit/toggle custom Sniper Rules (Collection, Model, Backdrop, Max Price, Min Discount %, Mode: Telegram Alert / Auto-Buy), Bid-Ask Spread Offer Radar (find best collections for lowball offers & 1-click outbid +0.1 TON), Live Trigger Log.
     4. **Портфель (My Assets & Auto-Undercut)**: Holdings PnL dashboard, active listings, **Smart Auto-Undercut** controls per item (min floor price guard, step `-0.05 TON`, Auto vs Notify mode, Competitor undercut simulator/monitor), Thin Floor hold warnings, Best Market to Relist advisor.
     5. **Маркети (Connections, Bot & Risk)**: TON Connect wallet integration UI, Market connectors status (Getgems GraphQL, Portals API, MRKT initData, Tonnel initData, Fragment), Telegram Bot config & live test-alert button, Risk Guardrails (Daily Spend Limit, Max Single Buy, Stop-Loss, Dry-Run Toggle).
