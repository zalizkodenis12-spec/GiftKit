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
  VisionScorePayload,
  VisionScoreResponse,
  WhalesResponse,
  XRayResponse,
} from '../types/api';

const API_BASE = '/api';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {}),
    },
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

  return res.json() as Promise<T>;
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
  // 1. System & Overview
  getOverview: () => request<OverviewResponse>('/overview'),

  // 2. Scanner & Listings
  getScannerListings: (params?: {
    collection?: string;
    market?: string;
    min_discount?: number;
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

  getTrends: () => request<TrendsResponse>('/analytics/trends'),

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
