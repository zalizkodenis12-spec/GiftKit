export type MarketName = 'portals' | 'getgems' | 'mrkt' | 'tonnel' | 'fragment';

export type TabKey = 'scanner' | 'analytics' | 'sniper' | 'portfolio' | 'markets';

export interface MarketPricePoint {
  market: MarketName | string;
  floor_price: number;
  fee_percent: number;
  is_live: boolean;
  url?: string;
}

export interface TraitAttribute {
  type: 'model' | 'backdrop' | 'symbol' | string;
  value: string;
  rarity_percent: number;
  trait_floor: number;
  supply?: number;
}

export interface SaleRecord {
  price: number;
  market: MarketName | string;
  timestamp: string;
  buyer?: string;
  tx_type: 'sale' | 'offer_accepted' | string;
}

export type VerdictType = 'STRONG_BUY' | 'GOOD_DEAL' | 'FAIR' | 'OVERPRICED';

export interface AnalyzedListing {
  id: string;
  tg_id: string;
  collection_id: string;
  collection_name: string;
  short_name: string;
  number: number;
  photo_url?: string;
  market: MarketName | string;
  market_url?: string;
  price: number;
  collection_floor: number;
  model_floor?: number | null;
  backdrop_floor?: number | null;
  fair_value: number;
  discount_percent: number;
  net_profit_ton: number;
  net_profit_percent: number;
  fee_percent: number;
  liquidity_score: number;
  sales_24h: number;
  is_rare_combo: boolean;
  combo_label?: string | null;
  number_badge?: 'Low Mint' | 'Palindrome' | 'Repeating' | string | null;
  symbol_badge?: string | null;
  symbol_bonus_percent?: number | null;
  thin_floor_warning?: string | null;
  wash_trade_risk: boolean;
  best_sell_market: MarketName | string;
  best_sell_price: number;
  verdict: VerdictType;
  verdict_label: string;
  listed_at: string;
  attributes: TraitAttribute[];
  market_prices: MarketPricePoint[];
  recent_sales: SaleRecord[];
  is_live: boolean;
  // Visual AI ("See With Your Eyes"), Nice Numbers & 24h Trends
  visual_score?: number;
  visual_tag?: string | null;
  is_monochrome?: boolean;
  harmony_label?: string | null;
  color_swatches?: string[];
  number_pattern?: string | null;
  number_bonus_percent?: number;
  trend_boost_percent?: number;
  trend_label?: string | null;
  ai_vision_comment?: string | null;
}

export interface TrendingBackdrop {
  name: string;
  backdrop?: string;
  swatch_hex?: string;
  color_hex?: string;
  hex?: string;
  avg_premium_percent: number;
  collections_count?: number;
  collection_count?: number;
  fair_value_boost_percent?: number;
  boost_percent?: number;
  sales_24h?: number;
  sample_collections?: string[];
}

export interface TrendsResponse {
  trending_backdrops: TrendingBackdrop[];
  top_visual_picks?: AnalyzedListing[];
  top_visual_finds?: AnalyzedListing[];
  top_visual_listings?: AnalyzedListing[];
  updated_at?: string;
}

export interface VisionScorePayload {
  listing_id?: string;
  tg_id?: string;
  photo_url?: string;
  collection_name: string;
  short_name?: string;
  number?: number;
  model?: string;
  backdrop?: string;
  symbol?: string;
}

export interface VisionScoreResponse {
  visual_score: number;
  visual_tag?: string | null;
  is_monochrome?: boolean;
  harmony_label?: string | null;
  color_swatches?: string[];
  number_pattern?: string | null;
  number_bonus_percent?: number;
  ai_vision_comment?: string;
  comment?: string;
  provider?: string;
}

export interface CollectionSummary {
  id: string;
  name: string;
  short_name: string;
  photo_url?: string;
  floor_price: number;
  change_24h_percent: number;
  day_volume: number;
  total_volume: number;
  supply: number;
  listed_count: number;
  sales_24h: number;
  market_cap: number;
  liquidity_score: number;
  best_offer: number;
  bid_ask_spread_percent: number;
  thin_floor_gap_percent: number;
  thin_floor_count: number;
  wash_trade_flag: boolean;
  market_floors: Record<string, number>;
  arbitrage_spread_percent: number;
  is_live: boolean;
}

export interface OverviewResponse {
  ton_usd: number;
  ton_change_24h: number;
  total_collections: number;
  active_rules: number;
  portfolio_count: number;
  portfolio_pnl_ton: number;
  arbitrage_opportunities_count: number;
  live_markets: string[];
  bot_connected: boolean;
  dry_run: boolean;
  last_sync: string;
}

export interface ArbitrageOpportunity {
  id: string;
  collection_name: string;
  short_name: string;
  photo_url?: string;
  buy_market: MarketName | string;
  buy_price: number;
  sell_market: MarketName | string;
  sell_price: number;
  net_profit_ton: number;
  roi_percent: number;
  liquidity_score: number;
  type: 'instant_offer' | 'floor_spread' | string;
}

export interface ScannerListingsResponse {
  items: AnalyzedListing[];
  arbitrage_top: ArbitrageOpportunity[];
  total: number;
}

export interface ScannerArbitrageResponse {
  opportunities: ArbitrageOpportunity[];
}

export interface AnalyticsCollectionsResponse {
  collections: CollectionSummary[];
  heatmap: CollectionSummary[];
}

export interface ChartPoint {
  time: number;
  floor: number;
  avg_sale: number;
  volume: number;
}

export interface TraitFloorItem {
  name: string;
  rarity_percent: number;
  floor_price: number;
  supply: number;
}

export interface OrderbookLevel {
  price: number;
  count: number;
}

export interface CollectionChartResponse {
  collection: CollectionSummary;
  points: ChartPoint[];
  traits: {
    models: TraitFloorItem[];
    backdrops: TraitFloorItem[];
    symbols: TraitFloorItem[];
  };
  orderbook_depth: OrderbookLevel[];
}

export interface XRayResponse {
  item: AnalyzedListing;
  comparable_sales: SaleRecord[];
  recommendation: string;
}

export interface WhaleEvent {
  id: string;
  wallet: string;
  wallet_label: string;
  action: 'SWEEP' | 'RARE_BUY' | 'LIST' | string;
  collection_name: string;
  short_name: string;
  photo_url?: string;
  count: number;
  total_ton: number;
  avg_price: number;
  timestamp: string;
  signal: string;
}

export interface WhalesResponse {
  events: WhaleEvent[];
}

export interface SniperRule {
  id: number | string;
  name: string;
  collection_short_name: string;
  collection_name: string;
  model_filter: string;
  backdrop_filter: string;
  max_price: number | null;
  min_discount_percent: number;
  rare_combo_only: boolean;
  markets: string[];
  mode: 'alert' | 'autobuy';
  enabled: boolean;
  triggers_count?: number;
  created_at?: string;
}

export interface CreateSniperRulePayload {
  name: string;
  collection_short_name: string;
  collection_name: string;
  model_filter: string;
  backdrop_filter: string;
  max_price: number | null;
  min_discount_percent: number;
  rare_combo_only: boolean;
  markets: string[];
  mode: 'alert' | 'autobuy';
  enabled: boolean;
}

export interface UserProfile {
  tg_user_id: string;
  username?: string;
  first_name?: string;
  last_name?: string;
  photo_url?: string;
}

export interface AlertLog {
  id: number | string;
  rule_id?: number | string | null;
  rule_name?: string;
  alert_type?: string;
  title?: string;
  message?: string;
  html_preview?: string;
  telegram_sent?: boolean;
  created_at: string;
  listing_id?: string | null;
  listing?: AnalyzedListing | null;
}

export interface TestAlertResponse {
  ok?: boolean;
  sent_to_telegram?: boolean;
  telegram_sent?: boolean;
  message?: string;
  html_preview?: string;
  caption?: string;
  listing?: AnalyzedListing | null;
  alert?: AlertLog | null;
}

export interface UserOffer {
  id: number | string;
  collection_short_name: string;
  collection_name: string;
  photo_url?: string;
  market: MarketName | string;
  market_url?: string;
  bid_price: number;
  max_bid: number;
  top_competitor_bid?: number;
  floor_price?: number;
  auto_outbid: boolean;
  status: 'active' | 'outbid' | 'accepted' | 'cancelled' | string;
  created_at?: string;
}

export interface OfferRadarItem {
  collection_short_name: string;
  short_name?: string;
  collection_name: string;
  photo_url?: string;
  floor_price: number;
  best_offer: number;
  suggested_offer?: number;
  recommended_bid?: number;
  bid_ask_spread_percent: number;
  est_profit_ton?: number;
  est_net_profit_ton?: number;
  est_roi_percent?: number;
  sales_24h?: number;
  liquidity_score: number;
  market?: MarketName | string;
  market_url?: string;
  sample_listing?: AnalyzedListing | null;
}

export interface OffersResponse {
  offers: UserOffer[];
  radar: OfferRadarItem[];
}

export interface PortfolioSummary {
  total_invested_ton: number;
  current_value_ton: number;
  unrealized_pnl_ton: number;
  unrealized_pnl_percent: number;
  active_listings: number;
  undercut_active_count: number;
}

export interface PortfolioItem {
  id: number;
  tg_id: string;
  collection_name: string;
  short_name: string;
  number: number;
  photo_url?: string;
  buy_price: number;
  listed_price: number | null;
  market: MarketName | string;
  current_floor: number;
  competitor_price: number | null;
  fair_value: number;
  best_sell_market: MarketName | string;
  best_sell_price: number;
  auto_undercut_enabled: boolean;
  undercut_mode: 'auto' | 'notify';
  min_price_guard: number;
  undercut_step: number;
  thin_floor_warning?: string | null;
  status: 'listed' | 'holding' | 'sold';
  is_undercut_by_competitor: boolean;
  hit_min_guard?: boolean;
  suggested_price: number | null;
  pnl_ton: number;
  pnl_percent: number;
  last_undercut_at?: string | null;
}

export interface PortfolioResponse {
  summary: PortfolioSummary;
  items: PortfolioItem[];
}

export interface AddPortfolioPayload {
  tg_id?: string;
  collection_name: string;
  short_name: string;
  number: number;
  photo_url?: string;
  buy_price: number;
  listed_price?: number | null;
  market: string;
  auto_undercut_enabled?: boolean;
  undercut_mode?: 'auto' | 'notify';
  min_price_guard?: number;
  undercut_step?: number;
  status?: 'listed' | 'holding' | 'sold';
}

export interface SettingsMarketStatus {
  market: string;
  name?: string;
  status: 'LIVE' | 'CONNECTED' | 'DEMO' | 'FALLBACK' | 'CONFIGURED' | string;
  is_live?: boolean;
  has_key?: boolean;
  fee_percent?: number;
  description?: string;
}

export interface AppSettings {
  dry_run: boolean;
  daily_limit_ton: number;
  daily_spent_ton?: number;
  max_single_buy_ton: number;
  stop_loss_percent: number;
  wallet_address: string;
  wallet_balance_ton?: number;
  tg_bot_token: string;
  tg_admin_chat_id: string;
  webapp_url: string;
  getgems_api_key: string;
  portals_init_data: string;
  mrkt_init_data: string;
  tonnel_init_data: string;
  gemini_api_key?: string;
  openai_api_key?: string;
  bot_connected?: boolean;
  markets_status?: SettingsMarketStatus[];
}

export interface TradeExecutePayload {
  listing_id?: string;
  tg_id: string;
  collection_name: string;
  short_name: string;
  number: number;
  price: number;
  market: string;
  photo_url?: string;
  fair_value?: number;
  collection_floor?: number;
}

export interface TradeExecuteResponse {
  ok: boolean;
  dry_run: boolean;
  message: string;
  portfolio_item?: PortfolioItem;
  tx_hash?: string;
}

export interface LiveSocketEvent {
  type: string;
  title?: string;
  message?: string;
  severity?: 'info' | 'success' | 'warning' | 'error';
  data?: unknown;
  timestamp?: string;
}

export interface ToastItem {
  id: string;
  title: string;
  message?: string;
  variant: 'info' | 'success' | 'warning' | 'error';
}

export interface BeforeInstallPromptEvent extends Event {
  readonly platforms: string[];
  readonly userChoice: Promise<{ outcome: 'accepted' | 'dismissed'; platform: string }>;
  prompt: () => Promise<void>;
}

declare global {
  interface Window {
    Telegram?: {
      WebApp?: {
        ready: () => void;
        expand: () => void;
        close?: () => void;
        initData?: string;
        openTelegramLink?: (url: string) => void;
        openLink?: (url: string) => void;
        setHeaderColor?: (color: string) => void;
        setBackgroundColor?: (color: string) => void;
        HapticFeedback?: {
          impactOccurred?: (style: 'light' | 'medium' | 'heavy' | 'rigid' | 'soft') => void;
          notificationOccurred?: (type: 'error' | 'success' | 'warning') => void;
          selectionChanged?: () => void;
        };
        CloudStorage?: {
          setItem: (
            key: string,
            value: string,
            callback?: (err: Error | null, stored?: boolean) => void,
          ) => void;
          getItem: (
            key: string,
            callback: (err: Error | null, value?: string) => void,
          ) => void;
        };
        initDataUnsafe?: {
          start_param?: string;
          user?: {
            id?: number;
            first_name?: string;
            last_name?: string;
            username?: string;
            photo_url?: string;
          };
        };
      };
    };
  }
}
