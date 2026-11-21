import { useEffect, useRef, useState } from 'react';
import type {
  AddPortfolioPayload,
  AlertLog,
  AnalyticsCollectionsResponse,
  AppSettings,
  CollectionChartResponse,
  CreateSniperRulePayload,
  LiveSocketEvent,
  OffersResponse,
  OverviewResponse,
  PortfolioItem,
  PortfolioResponse,
  ScannerArbitrageResponse,
  ScannerListingsResponse,
  SniperRule,
  TestAlertResponse,
  TradeExecutePayload,
  TradeExecuteResponse,
  TrendsResponse,
  UserOffer,
  UserProfile,
  VisionScorePayload,
  VisionScoreResponse,
  WhalesResponse,
  XRayResponse,
} from '../types/api';

const API_BASE = '/api';
const SESSION_TOKEN_KEY = 'giftkit_session_token';
const STATE_ENVELOPE_KEY = 'giftkit_state_envelope';
const USER_PROFILE_KEY = 'giftkit_user_profile';
const USER_SETTINGS_KEY = 'giftkit_user_settings_v1';
const CLOUD_STATE_KEY = 'gk_state_v1';
const CLOUD_CHUNK_META = 'gk_st2_n';
const CLOUD_CHUNK_PREFIX = 'gk_st2_';
const CLOUD_SETTINGS_KEY = 'gk_prefs_v1';
const CLOUD_CHUNK_SIZE = 3600;
const MAX_CLOUD_CHUNKS = 60;

export function getStoredUserProfile(): UserProfile | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = localStorage.getItem(USER_PROFILE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as UserProfile;
  } catch {
    return null;
  }
}

export function saveStoredUserProfile(profile?: UserProfile | null): void {
  if (!profile || typeof window === 'undefined') return;
  try {
    localStorage.setItem(USER_PROFILE_KEY, JSON.stringify(profile));
  } catch {
    // ignore storage quota errors
  }
}

let capturedUrlTgAuth: string | undefined;

function extractInitialUrlAuth(): void {
  if (typeof window === 'undefined') return;
  try {
    const url = new URL(window.location.href);
    const tgAuth = url.searchParams.get('tg_auth');
    if (tgAuth) {
      capturedUrlTgAuth = tgAuth;
      localStorage.setItem(SESSION_TOKEN_KEY, tgAuth);
      url.searchParams.delete('tg_auth');
      const nextSearch = url.searchParams.toString();
      const nextUrl = `${url.pathname}${nextSearch ? `?${nextSearch}` : ''}${url.hash}`;
      window.history.replaceState({}, '', nextUrl);
    }
  } catch {
    // ignore URL parse issues
  }
}

extractInitialUrlAuth();

export function getCapturedTgAuth(): string | undefined {
  return capturedUrlTgAuth;
}

export function getSessionToken(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    return localStorage.getItem(SESSION_TOKEN_KEY);
  } catch {
    return null;
  }
}

export function saveSessionToken(token?: string | null): void {
  if (!token || typeof window === 'undefined') return;
  try {
    localStorage.setItem(SESSION_TOKEN_KEY, token);
  } catch {
    // ignore storage errors
  }
}

export function getStoredStateEnvelope(): unknown | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = localStorage.getItem(STATE_ENVELOPE_KEY);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function cloudGetItem(key: string, timeoutMs = 1100): Promise<string | null> {
  if (typeof window === 'undefined') return Promise.resolve(null);
  const cloud = window.Telegram?.WebApp?.CloudStorage;
  if (!cloud || typeof cloud.getItem !== 'function') return Promise.resolve(null);
  return new Promise((resolve) => {
    let settled = false;
    const timer = window.setTimeout(() => {
      if (!settled) {
        settled = true;
        resolve(null);
      }
    }, timeoutMs);
    try {
      cloud.getItem(key, (err, val) => {
        if (settled) return;
        settled = true;
        window.clearTimeout(timer);
        resolve(!err && typeof val === 'string' && val.length > 0 ? val : null);
      });
    } catch {
      if (!settled) {
        settled = true;
        window.clearTimeout(timer);
        resolve(null);
      }
    }
  });
}

function envelopeRank(env: unknown): number {
  if (!env || typeof env !== 'object') return -1;
  const obj = env as {
    state_version?: number;
    updated_at?: number;
    portfolio?: unknown[];
    rules?: unknown[];
    offers?: unknown[];
  };
  const ver = Number(obj.state_version || 0);
  if (ver > 0) return ver;
  const ts = Number(obj.updated_at || 0);
  if (ts > 0) return ts;
  return (
    (Array.isArray(obj.portfolio) ? obj.portfolio.length : 0) +
    (Array.isArray(obj.rules) ? obj.rules.length : 0) +
    (Array.isArray(obj.offers) ? obj.offers.length : 0)
  );
}

export function saveStateEnvelope(envelope: unknown): void {
  if (!envelope || typeof window === 'undefined') return;
  try {
    const serialized =
      typeof envelope === 'string' ? envelope : JSON.stringify(envelope);
    localStorage.setItem(STATE_ENVELOPE_KEY, serialized);
    const cloud = window.Telegram?.WebApp?.CloudStorage;
    if (cloud && typeof cloud.setItem === 'function') {
      const totalChunks = Math.min(
        MAX_CLOUD_CHUNKS,
        Math.ceil(serialized.length / CLOUD_CHUNK_SIZE),
      );
      if (totalChunks * CLOUD_CHUNK_SIZE >= serialized.length) {
        for (let i = 0; i < totalChunks; i += 1) {
          const chunk = serialized.slice(i * CLOUD_CHUNK_SIZE, (i + 1) * CLOUD_CHUNK_SIZE);
          cloud.setItem(`${CLOUD_CHUNK_PREFIX}${i}`, chunk, () => {});
        }
        cloud.setItem(CLOUD_CHUNK_META, String(totalChunks), () => {});
      }
      if (serialized.length <= 3900) {
        cloud.setItem(CLOUD_STATE_KEY, serialized, () => {});
      }
    }
  } catch {
    // ignore CloudStorage / localStorage errors
  }
}

export async function resolveInitialStateEnvelope(): Promise<unknown | null> {
  const localEnv = getStoredStateEnvelope();
  if (typeof window === 'undefined') return localEnv;
  try {
    let cloudRaw: string | null = null;
    const countRaw = await cloudGetItem(CLOUD_CHUNK_META, 900);
    const chunkCount = countRaw ? Number.parseInt(countRaw, 10) : 0;
    if (Number.isFinite(chunkCount) && chunkCount > 0 && chunkCount <= MAX_CLOUD_CHUNKS) {
      const parts = await Promise.all(
        Array.from({ length: chunkCount }, (_, i) =>
          cloudGetItem(`${CLOUD_CHUNK_PREFIX}${i}`, 1100),
        ),
      );
      if (parts.every((p) => typeof p === 'string')) {
        cloudRaw = parts.join('');
      }
    }
    if (!cloudRaw) {
      cloudRaw = await cloudGetItem(CLOUD_STATE_KEY, 900);
    }
    if (cloudRaw) {
      try {
        const parsed = JSON.parse(cloudRaw);
        if (!localEnv || envelopeRank(parsed) > envelopeRank(localEnv)) {
          localStorage.setItem(STATE_ENVELOPE_KEY, cloudRaw);
          return parsed;
        }
      } catch {
        // ignore malformed cloud state
      }
    }
  } catch {
    // ignore CloudStorage errors
  }
  return localEnv;
}

export type PersistedUserPrefs = Partial<
  Pick<
    AppSettings,
    | 'dry_run'
    | 'daily_limit_ton'
    | 'max_single_buy_ton'
    | 'stop_loss_percent'
    | 'wallet_address'
    | 'wallet_balance_ton'
  >
>;

export function savePersistedUserPrefs(prefs: PersistedUserPrefs): void {
  if (typeof window === 'undefined') return;
  try {
    const clean: PersistedUserPrefs = {
      dry_run: prefs.dry_run,
      daily_limit_ton: prefs.daily_limit_ton,
      max_single_buy_ton: prefs.max_single_buy_ton,
      stop_loss_percent: prefs.stop_loss_percent,
      wallet_address: prefs.wallet_address,
      wallet_balance_ton: prefs.wallet_balance_ton,
    };
    const serialized = JSON.stringify(clean);
    localStorage.setItem(USER_SETTINGS_KEY, serialized);
    const cloud = window.Telegram?.WebApp?.CloudStorage;
    if (cloud && typeof cloud.setItem === 'function' && serialized.length <= 3900) {
      cloud.setItem(CLOUD_SETTINGS_KEY, serialized, () => {});
    }
  } catch {
    // ignore storage errors
  }
}

export async function loadPersistedUserPrefs(): Promise<PersistedUserPrefs | null> {
  if (typeof window === 'undefined') return null;
  let localPrefs: PersistedUserPrefs | null = null;
  try {
    const raw = localStorage.getItem(USER_SETTINGS_KEY);
    if (raw) localPrefs = JSON.parse(raw) as PersistedUserPrefs;
  } catch {
    localPrefs = null;
  }
  try {
    const cloudRaw = await cloudGetItem(CLOUD_SETTINGS_KEY, 900);
    if (cloudRaw) {
      const parsed = JSON.parse(cloudRaw) as PersistedUserPrefs;
      if (!localPrefs) {
        localStorage.setItem(USER_SETTINGS_KEY, cloudRaw);
        return parsed;
      }
      return { ...parsed, ...localPrefs };
    }
  } catch {
    // ignore cloud errors
  }
  return localPrefs;
}

function toAsciiJsonHeader(value: unknown): string {
  const json = typeof value === 'string' ? value : JSON.stringify(value);
  return json.replace(/[\u007F-\uFFFF]/g, (chr) => {
    return '\\u' + ('0000' + chr.charCodeAt(0).toString(16)).slice(-4);
  });
}

function shouldAttachStateHeader(path: string): boolean {
  return (
    path.startsWith('/sniper') ||
    path.startsWith('/offers') ||
    path.startsWith('/portfolio') ||
    path.startsWith('/auth') ||
    path.startsWith('/trade') ||
    path.startsWith('/overview')
  );
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...((init?.headers as Record<string, string>) || {}),
  };

  const sessionToken = getSessionToken();
  if (sessionToken) {
    headers['Authorization'] = `Bearer ${sessionToken}`;
  }

  try {
    const tgInitData = window.Telegram?.WebApp?.initData;
    if (tgInitData) {
      headers['X-Telegram-Init-Data'] = tgInitData;
    }
  } catch {
    // ignore outside Telegram
  }

  if (shouldAttachStateHeader(path)) {
    const env = getStoredStateEnvelope();
    if (env) {
      try {
        const encoded = toAsciiJsonHeader(env);
        if (encoded.length <= 10500) {
          headers['X-GiftKit-State'] = encoded;
        }
      } catch {
        // ignore serialization error
      }
    }
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
  });

  if (!res.ok) {
    let detail = `Помилка сервера (${res.status})`;
    try {
      const errBody = await res.json();
      if (typeof errBody?.detail === 'string') {
        detail = errBody.detail;
      } else if (typeof errBody?.message === 'string') {
        detail = errBody.message;
      }
    } catch {
      // ignore json parse error
    }
    throw new Error(detail);
  }

  const resData = await res.json();
  if (resData && typeof resData === 'object') {
    if ('state_envelope' in resData && resData.state_envelope) {
      saveStateEnvelope(resData.state_envelope);
    }
    if ('session_token' in resData && typeof resData.session_token === 'string') {
      saveSessionToken(resData.session_token);
    }
    if ('user' in resData && resData.user && typeof resData.user === 'object') {
      saveStoredUserProfile(resData.user as UserProfile);
    }
  }

  return resData as T;
}

function toQuery(params: Record<string, string | number | boolean | undefined | null>): string {
  const sp = new URLSearchParams();
  Object.entries(params).forEach(([key, val]) => {
    if (val !== undefined && val !== null && val !== '') {
      sp.set(key, String(val));
    }
  });
  const str = sp.toString();
  return str ? `?${str}` : '';
}

export const api = {
  // 0. Multi-User Telegram Auth & Cloud State Sync
  initAuthSession: (payload: {
    init_data?: string;
    tg_auth?: string;
    state_envelope?: unknown;
  }) =>
    request<{
      ok: boolean;
      authenticated: boolean;
      user: UserProfile;
      session_token?: string;
      state_envelope?: unknown;
    }>('/auth/session', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  createLoginCode: () =>
    request<{ ok: boolean; nonce: string; bot_login_url: string }>('/auth/login-code', {
      method: 'POST',
    }),

  pollLoginCode: (nonce: string) =>
    request<{
      ok: boolean;
      ready: boolean;
      user?: UserProfile;
      session_token?: string;
      state_envelope?: unknown;
    }>(`/auth/poll-login?nonce=${encodeURIComponent(nonce)}`),

  updateProfile: (payload: {
    first_name: string;
    username: string;
    photo_url: string;
  }) =>
    request<{
      ok: boolean;
      user: UserProfile;
      session_token?: string;
      state_envelope?: unknown;
    }>('/auth/profile', {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),

  // 1. System & Overview
  getOverview: () => request<OverviewResponse>('/overview'),

  // 2. Scanner & Listings
  getScannerListings: (params?: {
    collection?: string;
    market?: string;
    search?: string;
    min_discount?: number;
    min_price?: number;
    max_price?: number;
    rare_combo_only?: boolean;
    visual_top_only?: boolean;
    nice_number_only?: boolean;
    sort?:
      | 'discount_desc'
      | 'price_asc'
      | 'price_desc'
      | 'newest'
      | 'profit_desc'
      | 'visual_desc';
    limit?: number;
    page?: number;
  }) => request<ScannerListingsResponse>(`/scanner/listings${toQuery(params || {})}`),

  getScannerArbitrage: () => request<ScannerArbitrageResponse>('/scanner/arbitrage'),

  refreshScanner: () =>
    request<{ ok?: boolean; refreshed?: boolean; message?: string; count?: number }>(
      '/scanner/refresh',
      { method: 'POST' },
    ),

  // 3. Analytics & X-Ray
  getCollections: (params?: {
    search?: string;
    sort?:
      | 'volume_desc'
      | 'floor_desc'
      | 'floor_asc'
      | 'change_desc'
      | 'liquidity_desc'
      | 'spread_desc';
    limit?: number;
  }) => request<AnalyticsCollectionsResponse>(`/analytics/collections${toQuery(params || {})}`),

  getCollectionChart: (shortName: string, timeframe: '24h' | '7d' | '30d' = '7d') =>
    request<CollectionChartResponse>(
      `/analytics/collections/${encodeURIComponent(shortName)}/chart${toQuery({ timeframe })}`,
    ),

  runXRay: (query: string) =>
    request<XRayResponse>(`/analytics/xray${toQuery({ query })}`),

  getWhales: () => request<WhalesResponse>('/analytics/whales'),

  getTrends: (collection?: string) =>
    request<TrendsResponse>(`/analytics/trends${toQuery({ collection })}`),

  inspectCollectionModel: (short_name: string, model_name: string) =>
    request<XRayResponse>(`/analytics/model-preview${toQuery({ short_name, model_name })}`),

  getPixelColors: (params: {
    photo_url: string;
    model?: string;
    backdrop?: string;
    symbol?: string;
  }) =>
    request<{
      ok: boolean;
      color_swatches: string[];
      visual_score?: number;
      visual_tag?: string;
      is_monochrome?: boolean;
      harmony_label?: string | null;
      ai_vision_comment?: string | null;
      source?: string;
    }>(`/analytics/pixel-colors${toQuery(params)}`),

  runVisionScore: (payload: VisionScorePayload) =>
    request<VisionScoreResponse>('/analytics/vision-score', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  // 4. Sniper Rules & Offers
  getSniperRules: () => request<{ rules: SniperRule[] }>('/sniper/rules'),

  createSniperRule: (payload: CreateSniperRulePayload) =>
    request<{ rule?: SniperRule } & Partial<SniperRule>>('/sniper/rules', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  updateSniperRule: (id: number | string, payload: Partial<SniperRule>) =>
    request<{ rule?: SniperRule } & Partial<SniperRule>>(`/sniper/rules/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),

  deleteSniperRule: (id: number | string) =>
    request<{ ok: boolean }>(`/sniper/rules/${id}`, { method: 'DELETE' }),

  getSniperAlerts: () => request<{ alerts: AlertLog[] }>('/sniper/alerts'),

  triggerTestAlert: () =>
    request<TestAlertResponse>('/sniper/test-alert', { method: 'POST' }),

  getOffers: () => request<OffersResponse>('/offers'),

  createOffer: (payload: {
    collection_short_name: string;
    collection_name: string;
    market: string;
    bid_price: number;
    max_bid: number;
    auto_outbid: boolean;
  }) =>
    request<{ offer?: UserOffer } & Partial<UserOffer>>('/offers', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  outbidOffer: (id: number | string, step = 0.1) =>
    request<{ offer?: UserOffer; message?: string }>(`/offers/${id}/outbid`, {
      method: 'POST',
      body: JSON.stringify({ step }),
    }),

  deleteOffer: (id: number | string) =>
    request<{ ok: boolean }>(`/offers/${id}`, { method: 'DELETE' }),

  // 5. Portfolio & Smart Auto-Undercut
  getPortfolio: () => request<PortfolioResponse>('/portfolio'),

  addPortfolioItem: (payload: AddPortfolioPayload) =>
    request<{ item?: PortfolioItem } & Partial<PortfolioItem>>('/portfolio', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  updatePortfolioItem: (
    id: number,
    payload: Partial<{
      listed_price: number | null;
      auto_undercut_enabled: boolean;
      undercut_mode: 'auto' | 'notify';
      min_price_guard: number;
      undercut_step: number;
      status: 'listed' | 'holding' | 'sold';
      market: string;
    }>,
  ) =>
    request<{ item?: PortfolioItem } & Partial<PortfolioItem>>(`/portfolio/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),

  applyUndercut: (id: number) =>
    request<{ ok?: boolean; item?: PortfolioItem; message?: string; new_price?: number }>(
      `/portfolio/${id}/apply-undercut`,
      { method: 'POST' },
    ),

  simulateCompetitor: (id: number) =>
    request<{ ok?: boolean; item?: PortfolioItem; message?: string }>(
      `/portfolio/${id}/simulate-competitor`,
      { method: 'POST' },
    ),

  deletePortfolioItem: (id: number) =>
    request<{ ok: boolean }>(`/portfolio/${id}`, { method: 'DELETE' }),

  // 6. Settings & Trade Execution
  getSettings: () => request<AppSettings>('/settings'),

  updateSettings: (payload: Partial<AppSettings>) =>
    request<AppSettings>('/settings', {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),

  testTelegram: () =>
    request<{ ok: boolean; message?: string; detail?: string }>('/settings/test-telegram', {
      method: 'POST',
    }),

  executeTrade: (payload: TradeExecutePayload) =>
    request<TradeExecuteResponse>('/trade/execute', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
};

export function useLiveSocket(onEvent: (event: LiveSocketEvent) => void) {
  const [connected, setConnected] = useState(false);
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  useEffect(() => {
    let ws: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    let disposed = false;

    const connect = () => {
      if (disposed) return;
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const url = `${protocol}//${window.location.host}/ws/live`;

      try {
        ws = new WebSocket(url);

        ws.onopen = () => {
          if (!disposed) setConnected(true);
        };

        ws.onmessage = (msg) => {
          try {
            const parsed = JSON.parse(msg.data) as LiveSocketEvent;
            if (parsed && typeof parsed === 'object') {
              onEventRef.current(parsed);
            }
          } catch {
            // ignore non-json heartbeat
          }
        };

        ws.onclose = () => {
          if (!disposed) {
            setConnected(false);
            reconnectTimer = window.setTimeout(connect, 3500);
          }
        };

        ws.onerror = () => {
          ws?.close();
        };
      } catch {
        setConnected(false);
        reconnectTimer = window.setTimeout(connect, 4500);
      }
    };

    connect();

    return () => {
      disposed = true;
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
      if (ws) {
        ws.onclose = null;
        ws.close();
      }
    };
  }, []);

  return { connected };
}
