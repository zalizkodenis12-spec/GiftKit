import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  Eye,
  Flame,
  Layers,
  Palette,
  Search,
  Sparkles,
  TrendingDown,
  TrendingUp,
  Waves,
} from 'lucide-react';
import { api } from '../api/client';
import type {
  AnalyzedListing,
  CollectionChartResponse,
  CollectionSummary,
  TrendingBackdrop,
  WhaleEvent,
  XRayResponse,
} from '../types/api';
import {
  formatPercent,
  formatTimeAgo,
  formatTon,
  getLiquidityColor,
  haptic,
} from '../utils/format';
import { PriceChart } from '../components/PriceChart';
import { NftImage } from '../components/NftImage';
import { NftCard } from '../components/NftCard';

interface AnalyticsPageProps {
  collections: CollectionSummary[];
  tonUsd: number;
  focusXRayTrigger: number;
  onXRayResult: (res: XRayResponse) => void;
  onSelectListing: (item: AnalyzedListing) => void;
  onNotify: (title: string, message?: string, variant?: 'info' | 'success' | 'warning' | 'error') => void;
}

type SortKey =
  | 'volume_desc'
  | 'floor_desc'
  | 'change_desc'
  | 'liquidity_desc'
  | 'spread_desc';

type AnalyticsSubTab = 'charts' | 'trends' | 'rating' | 'whales';

const QUICK_XRAY_CHIPS = [
  'Eternal Rose #18718',
  'Plush Pepe #42',
  'Durov Cap #108',
  'Astral Shard #777',
];

export const AnalyticsPage: React.FC<AnalyticsPageProps> = ({
  collections: initialCollections,
  tonUsd,
  focusXRayTrigger,
  onXRayResult,
  onSelectListing,
  onNotify,
}) => {
  const xrayInputRef = useRef<HTMLInputElement | null>(null);

  // X-Ray
  const [xrayQuery, setXrayQuery] = useState('');
  const [xrayLoading, setXrayLoading] = useState(false);

  // Chart & selected collection
  const [selectedShortName, setSelectedShortName] = useState<string>(
    initialCollections[0]?.short_name || 'eternalrose',
  );
  const [timeframe, setTimeframe] = useState<'24h' | '7d' | '30d'>('7d');
  const [chartData, setChartData] = useState<CollectionChartResponse | null>(null);
  const [chartLoading, setChartLoading] = useState(true);
  const [traitTab, setTraitTab] = useState<'models' | 'backdrops' | 'symbols'>('models');

  // Collections table & heatmap
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState<SortKey>('volume_desc');
  const [collections, setCollections] = useState<CollectionSummary[]>(initialCollections);
  const [heatmap, setHeatmap] = useState<CollectionSummary[]>(initialCollections.slice(0, 12));
  const [subTab, setSubTab] = useState<AnalyticsSubTab>('charts');

  // Whales
  const [whales, setWhales] = useState<WhaleEvent[]>([]);

  // 24h Trends & Visual Top Picks
  const [trendingBackdrops, setTrendingBackdrops] = useState<TrendingBackdrop[]>([]);
  const [topVisualFinds, setTopVisualFinds] = useState<AnalyzedListing[]>([]);
  const [trendsLoading, setTrendsLoading] = useState(true);

  useEffect(() => {
    if (focusXRayTrigger > 0) {
      xrayInputRef.current?.focus();
      xrayInputRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [focusXRayTrigger]);

  useEffect(() => {
    if (initialCollections.length > 0 && !selectedShortName) {
      setSelectedShortName(initialCollections[0].short_name);
    }
  }, [initialCollections, selectedShortName]);

  const fetchCollectionsAndWhales = useCallback(async () => {
    try {
      const [colRes, whaleRes] = await Promise.all([
        api.getCollections({ search: search || undefined, sort, limit: 250 }),
        api.getWhales().catch(() => ({ events: [] })),
      ]);
      const cols = colRes.collections || [];
      setCollections(cols);
      setHeatmap(colRes.heatmap && colRes.heatmap.length > 0 ? colRes.heatmap : cols.slice(0, 12));
      setWhales(whaleRes.events || []);

      if (cols.length > 0 && !cols.some((c) => c.short_name === selectedShortName) && !search) {
        setSelectedShortName(cols[0].short_name);
      }
    } catch {
      // handled silently if initialCollections already present
    }
  }, [search, sort, selectedShortName]);

  const fetchTrends = useCallback(async () => {
    setTrendsLoading(true);
    try {
      const trendsRes = await api.getTrends().catch(() => null);
      if (trendsRes) {
        setTrendingBackdrops(trendsRes.trending_backdrops || []);
        const picks =
          trendsRes.top_visual_picks ||
          trendsRes.top_visual_finds ||
          trendsRes.top_visual_listings ||
          [];
        if (picks.length > 0) {
          setTopVisualFinds(picks);
          return;
        }
      }
      // Graceful fallback for top visual picks from scanner visual_desc
      const visualRes = await api
        .getScannerListings({ sort: 'visual_desc', visual_top_only: true, limit: 12 })
        .catch(() => ({ items: [] }));
      setTopVisualFinds(visualRes.items || []);
    } finally {
      setTrendsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchCollectionsAndWhales();
  }, [fetchCollectionsAndWhales]);

  useEffect(() => {
    fetchTrends();
  }, [fetchTrends]);

  useEffect(() => {
    if (!selectedShortName) return;
    let active = true;
    setChartLoading(true);
    api
      .getCollectionChart(selectedShortName, timeframe)
      .then((res) => {
        if (active) setChartData(res);
      })
      .catch(() => {
        if (active) setChartData(null);
      })
      .finally(() => {
        if (active) setChartLoading(false);
      });
    return () => {
      active = false;
    };
  }, [selectedShortName, timeframe]);

  const handleRunXRay = async (queryOverride?: string) => {
    const q = (queryOverride ?? xrayQuery).trim();
    if (!q) {
      onNotify('Введіть назву або посилання NFT', 'Наприклад: Eternal Rose #18718', 'warning');
      return;
    }
    haptic('medium');
    setXrayQuery(q);
    setXrayLoading(true);
    try {
      const res = await api.runXRay(q);
      onXRayResult(res);
    } catch (err) {
      onNotify(
        'X-Ray не знайшов цей подарунок',
        err instanceof Error ? err.message : 'Спробуйте інший запит',
        'error',
      );
    } finally {
      setXrayLoading(false);
    }
  };

  const activeCol = chartData?.collection;
  const activeTraits = chartData?.traits?.[traitTab] || [];
  const depthList = chartData?.orderbook_depth || [];
  const maxDepthCount = Math.max(1, ...depthList.map((d) => d.count));

  return (
    <div className="space-y-4 pb-4">
      {/* Top Row: X-Ray Instant Valuator + Sub-navigation */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-3.5 items-stretch">
        <section className="lg:col-span-7 ton-card rounded-2xl p-3.5 bg-gradient-to-br from-white via-white to-[#F0F8FF] border-[#BAE3FC]">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-7 h-7 rounded-xl ton-btn-primary flex items-center justify-center shrink-0">
              <Sparkles className="w-3.5 h-3.5 text-white" />
            </div>
            <div>
              <h2 className="font-display text-[13.5px] font-extrabold text-[#0B1120] leading-tight">
                X-Ray Оцінювач NFT
              </h2>
              <p className="text-[10.5px] text-[#64748B]">
                Вставте назву, #номер або посилання t.me/nft/...
              </p>
            </div>
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleRunXRay();
            }}
            className="flex gap-2"
          >
            <div className="relative flex-1">
              <Search className="w-4 h-4 text-[#64748B] absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                ref={xrayInputRef}
                type="text"
                value={xrayQuery}
                onChange={(e) => setXrayQuery(e.target.value)}
                placeholder="Eternal Rose #18718..."
                className="w-full h-10 pl-9 pr-3 rounded-xl bg-white border border-[#BAE3FC] text-xs font-semibold text-[#0B1120] placeholder:text-[#64748B] focus:outline-none focus:border-[#0098EA] focus:ring-2 focus:ring-[#0098EA]/15"
              />
            </div>
            <button
              type="submit"
              disabled={xrayLoading}
              className="ton-btn-primary h-10 px-4 rounded-xl text-xs font-bold shrink-0 cursor-pointer disabled:opacity-60"
            >
              {xrayLoading ? '...' : 'Перевірити'}
            </button>
          </form>

          <div className="flex items-center gap-1.5 overflow-x-auto no-scrollbar mt-2">
            {QUICK_XRAY_CHIPS.map((chip) => (
              <button
                key={chip}
                type="button"
                onClick={() => handleRunXRay(chip)}
                className="shrink-0 px-2.5 py-1 rounded-lg bg-[#E8F5FE] hover:bg-[#D4ECFD] border border-[#BAE3FC] text-[#0077C8] text-[10.5px] font-bold transition-colors cursor-pointer"
              >
                {chip}
              </button>
            ))}
          </div>
        </section>

        {/* Sub-navigation inside Analytics (4 clean tabs) */}
        <section className="lg:col-span-5 ton-card rounded-2xl p-2 flex flex-col justify-center">
          <p className="hidden lg:block text-[10.5px] font-bold text-[#64748B] px-2 mb-1.5">
            Розділи аналітики ринку
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-2 gap-1.5">
            {(
              [
                ['charts', 'Графік', Activity],
                ['trends', 'Тренди 24г', Flame],
                ['rating', `Усі (${collections.length || 124})`, Layers],
                ['whales', `Кити (${whales.length})`, Waves],
              ] as const
            ).map(([k, label, Icon]) => {
              const active = subTab === k;
              return (
                <button
                  key={k}
                  type="button"
                  onClick={() => {
                    haptic('light');
                    setSubTab(k);
                  }}
                  className={`py-2.5 px-2 rounded-xl text-[11.5px] font-extrabold transition-all flex items-center justify-center gap-1.5 cursor-pointer ${
                    active
                      ? 'ton-btn-primary text-white'
                      : 'bg-[#F8FAFC] text-[#0B1120] border border-[#E2E8F0] hover:border-[#BAE3FC] hover:bg-[#E8F5FE]/60'
                  }`}
                >
                  <Icon className="w-3.5 h-3.5 shrink-0" />
                  <span className="truncate">{label}</span>
                </button>
              );
            })}
          </div>
        </section>
      </div>

      {/* TAB 1: CHARTS & HEATMAP (2-Column Desktop Dashboard) */}
      {subTab === 'charts' && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
          {/* Left Column: Chart + Trait Floors + Orderbook */}
          <section className="lg:col-span-7 ton-card rounded-2xl p-3.5 sm:p-4 space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <select
                value={selectedShortName}
                onChange={(e) => setSelectedShortName(e.target.value)}
                className="flex-1 min-w-[180px] h-9 px-2.5 rounded-xl bg-[#F4F7FB] border border-[#E2E8F0] text-xs font-extrabold text-[#0B1120] focus:outline-none focus:border-[#0098EA]"
              >
                {collections.map((c) => (
                  <option key={c.short_name} value={c.short_name}>
                    {c.name} ({formatTon(c.floor_price)} TON)
                  </option>
                ))}
              </select>

              <div className="flex bg-[#F4F7FB] p-0.5 rounded-xl border border-[#E2E8F0] shrink-0">
                {(['24h', '7d', '30d'] as const).map((tf) => (
                  <button
                    key={tf}
                    type="button"
                    onClick={() => setTimeframe(tf)}
                    className={`px-2.5 py-1 rounded-lg text-[10.5px] font-extrabold transition-all cursor-pointer ${
                      timeframe === tf
                        ? 'bg-[#0098EA] text-white shadow-xs'
                        : 'text-[#64748B] hover:text-[#0B1120]'
                    }`}
                  >
                    {tf}
                  </button>
                ))}
              </div>
            </div>

            {/* Key Stats Strip */}
            {activeCol && (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                <div className="rounded-xl bg-[#F8FAFC] border border-[#E2E8F0] p-2.5">
                  <p className="text-[10px] font-semibold text-[#64748B]">Флор</p>
                  <p className="text-[14px] font-extrabold text-[#0B1120] tabular-nums">
                    {formatTon(activeCol.floor_price)}
                  </p>
                  <p
                    className={`text-[10.5px] font-bold tabular-nums ${
                      activeCol.change_24h_percent >= 0 ? 'text-[#0098EA]' : 'text-[#334155]'
                    }`}
                  >
                    {formatPercent(activeCol.change_24h_percent)}
                  </p>
                </div>
                <div className="rounded-xl bg-[#F8FAFC] border border-[#E2E8F0] p-2.5">
                  <p className="text-[10px] font-semibold text-[#64748B]">Об&apos;єм 24г</p>
                  <p className="text-[14px] font-extrabold text-[#0B1120] tabular-nums">
                    {formatTon(activeCol.day_volume, 0)}
                  </p>
                  <p className="text-[10.5px] text-[#0098EA] font-bold">TON</p>
                </div>
                <div className="rounded-xl bg-[#F8FAFC] border border-[#E2E8F0] p-2.5">
                  <p className="text-[10px] font-semibold text-[#64748B]">Продажі</p>
                  <p className="text-[14px] font-extrabold text-[#0B1120] tabular-nums">
                    {activeCol.sales_24h}
                  </p>
                  <p className="text-[10.5px] text-[#64748B]">за 24г</p>
                </div>
                <div className="rounded-xl bg-[#F8FAFC] border border-[#E2E8F0] p-2.5">
                  <p className="text-[10px] font-semibold text-[#64748B]">Ліквідн.</p>
                  <p className="text-[14px] font-extrabold text-[#0098EA] tabular-nums">
                    {activeCol.liquidity_score}
                    <span className="text-[10px] text-[#64748B]">/100</span>
                  </p>
                  <div className="h-1 bg-[#E2E8F0] rounded-full mt-1 overflow-hidden">
                    <div
                      className={`h-full ${getLiquidityColor(activeCol.liquidity_score)}`}
                      style={{ width: `${activeCol.liquidity_score}%` }}
                    />
                  </div>
                </div>
              </div>
            )}

            {/* Thin Floor Badge */}
            {activeCol && activeCol.thin_floor_gap_percent >= 8 && (
              <div className="rounded-xl px-3 py-2 bg-[#E8F5FE] border border-[#BAE3FC] flex items-center justify-between text-[11px]">
                <span className="inline-flex items-center gap-1.5 font-bold text-[#0B1120]">
                  <Flame className="w-3.5 h-3.5 text-[#0098EA]" />
                  Тонкий стакан: {activeCol.thin_floor_count} лотів до +
                  {activeCol.thin_floor_gap_percent.toFixed(1)}%
                </span>
                <span className="font-extrabold text-[#0077C8] tabular-nums">
                  Спред {activeCol.bid_ask_spread_percent.toFixed(1)}%
                </span>
              </div>
            )}

            {/* TradingView Lightweight Chart */}
            {chartLoading ? (
              <div className="h-[240px] rounded-xl bg-[#F4F7FB] animate-pulse flex items-center justify-center text-xs font-semibold text-[#64748B]">
                Завантаження графіка...
              </div>
            ) : chartData && chartData.points.length > 0 ? (
              <PriceChart points={chartData.points} height={240} />
            ) : (
              <div className="h-[200px] rounded-xl bg-[#F8FAFC] border border-[#E2E8F0] flex items-center justify-center text-xs text-[#64748B]">
                Немає історичних точок для цієї колекції
              </div>
            )}

            {/* Trait Floor Table */}
            {chartData && (
              <div className="pt-2 border-t border-[#F1F5F9]">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-xs font-extrabold text-[#0B1120] flex items-center gap-1.5">
                    <Layers className="w-3.5 h-3.5 text-[#0098EA]" />
                    Флор по трейтах
                  </h3>
                  <div className="flex gap-1 bg-[#F4F7FB] p-0.5 rounded-lg border border-[#E2E8F0]">
                    {(
                      [
                        ['models', 'Моделі'],
                        ['backdrops', 'Фони'],
                        ['symbols', 'Символи'],
                      ] as const
                    ).map(([key, label]) => (
                      <button
                        key={key}
                        type="button"
                        onClick={() => setTraitTab(key)}
                        className={`px-2 py-0.5 rounded-md text-[10px] font-bold cursor-pointer ${
                          traitTab === key
                            ? 'bg-white text-[#0098EA] shadow-xs'
                            : 'text-[#64748B]'
                        }`}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="space-y-1.5">
                  {activeTraits.slice(0, 5).map((t, idx) => (
                    <div
                      key={`${t.name}-${idx}`}
                      className="flex items-center justify-between px-2.5 py-1.5 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0] text-xs"
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="font-bold text-[#0B1120] truncate">{t.name}</span>
                        <span className="px-1.5 py-0.5 rounded bg-[#E8F5FE] text-[#0077C8] text-[10px] font-bold tabular-nums">
                          {t.rarity_percent.toFixed(1)}%
                        </span>
                      </div>
                      <div className="text-right shrink-0 tabular-nums">
                        <span className="font-extrabold text-[#0B1120]">
                          {formatTon(t.floor_price)} TON
                        </span>
                        <span className="text-[10px] text-[#64748B] ml-1.5">
                          ({t.supply} шт)
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Orderbook Depth */}
            {depthList.length > 0 && (
              <div className="pt-2 border-t border-[#F1F5F9]">
                <h3 className="text-xs font-extrabold text-[#0B1120] mb-2">
                  Глибина стакана (Orderbook)
                </h3>
                <div className="space-y-1.5">
                  {depthList.slice(0, 5).map((lvl, idx) => {
                    const widthPct = Math.max(12, Math.round((lvl.count / maxDepthCount) * 100));
                    return (
                      <div
                        key={`${lvl.price}-${idx}`}
                        className="flex items-center gap-2 text-[11px] tabular-nums"
                      >
                        <span className="w-16 font-bold text-[#0B1120] shrink-0">
                          {formatTon(lvl.price)} TON
                        </span>
                        <div className="flex-1 h-4 bg-[#F1F5F9] rounded-lg overflow-hidden relative">
                          <div
                            className="h-full bg-gradient-to-r from-[#0098EA]/80 to-[#0077C8] rounded-lg"
                            style={{ width: `${widthPct}%` }}
                          />
                        </div>
                        <span className="w-10 text-right font-bold text-[#334155] shrink-0">
                          {lvl.count} шт
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </section>

          {/* Right Column: Market Heatmap + Compact Trends & Whales Summary */}
          <div className="lg:col-span-5 space-y-4">
            <section className="ton-card rounded-2xl p-3.5 sm:p-4">
              <div className="flex items-center justify-between mb-2.5">
                <h2 className="font-display text-[13.5px] font-extrabold text-[#0B1120] flex items-center gap-1.5">
                  <Activity className="w-4 h-4 text-[#0098EA]" />
                  Теплова карта ринку (24г)
                </h2>
                <span className="text-[10.5px] font-semibold text-[#64748B]">
                  Натисніть для графіка
                </span>
              </div>

              <div className="grid grid-cols-3 gap-1.5">
                {heatmap.slice(0, 9).map((c) => {
                  const pct = c.change_24h_percent;
                  const tileStyle =
                    pct >= 0
                      ? 'bg-[#E8F5FE] border-[#BAE3FC] text-[#0077C8]'
                      : 'bg-[#F8FAFC] border-[#CBD5E1] text-[#0B1120]';

                  const isSelected = c.short_name === selectedShortName;

                  return (
                    <button
                      key={c.short_name}
                      type="button"
                      onClick={() => {
                        haptic('light');
                        setSelectedShortName(c.short_name);
                      }}
                      className={`p-2 rounded-xl border text-left transition-all cursor-pointer ${tileStyle} ${
                        isSelected ? 'ring-2 ring-[#0098EA]' : ''
                      }`}
                    >
                      <p className="text-[11px] font-extrabold truncate">{c.name}</p>
                      <p className="text-[12px] font-extrabold tabular-nums mt-0.5">
                        {formatTon(c.floor_price, 1)} TON
                      </p>
                      <p className="text-[10.5px] font-bold tabular-nums flex items-center gap-0.5">
                        {pct >= 0 ? (
                          <TrendingUp className="w-3 h-3" />
                        ) : (
                          <TrendingDown className="w-3 h-3" />
                        )}
                        {formatPercent(pct)}
                      </p>
                    </button>
                  );
                })}
              </div>
            </section>

            {/* Quick 24h Trending Backdrops Preview */}
            {trendingBackdrops.length > 0 && (
              <section className="ton-card rounded-2xl p-3.5 sm:p-4">
                <div className="flex items-center justify-between mb-2.5">
                  <h3 className="font-display text-[13px] font-extrabold text-[#0B1120] flex items-center gap-1.5">
                    <Flame className="w-4 h-4 text-[#0098EA]" />
                    Топ фони за 24г
                  </h3>
                  <button
                    type="button"
                    onClick={() => setSubTab('trends')}
                    className="text-[11px] font-bold text-[#0077C8] hover:text-[#0098EA] cursor-pointer"
                  >
                    Всі тренди →
                  </button>
                </div>
                <div className="space-y-1.5">
                  {trendingBackdrops.slice(0, 4).map((tb, idx) => {
                    const label = tb.name || tb.backdrop || 'Backdrop';
                    const color = tb.color_hex || tb.hex || '#0098EA';
                    const boost = tb.fair_value_boost_percent ?? tb.boost_percent ?? 0;
                    return (
                      <div
                        key={`${label}-${idx}`}
                        className="flex items-center justify-between gap-2 px-2.5 py-2 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0] text-xs tabular-nums"
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          <span
                            className="w-3.5 h-3.5 rounded-full border border-[#0B1120]/15 shrink-0"
                            style={{ backgroundColor: color }}
                          />
                          <span className="font-bold text-[#0B1120] truncate">{label}</span>
                        </div>
                        <div className="flex items-center gap-1.5 shrink-0">
                          <span className="font-extrabold text-[#0077C8]">
                            +{tb.avg_premium_percent.toFixed(0)}%
                          </span>
                          {boost > 0 && (
                            <span className="px-1.5 py-0.5 rounded bg-[#E8F5FE] text-[#0098EA] text-[10px] font-extrabold">
                              FV +{boost.toFixed(0)}%
                            </span>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </section>
            )}

            {/* Quick Whale Signals Preview on Desktop */}
            {whales.length > 0 && (
              <section className="hidden lg:block ton-card rounded-2xl p-4">
                <div className="flex items-center justify-between mb-2.5">
                  <h3 className="font-display text-[13px] font-extrabold text-[#0B1120] flex items-center gap-1.5">
                    <Waves className="w-4 h-4 text-[#0098EA]" />
                    Останні угоди Китів
                  </h3>
                  <button
                    type="button"
                    onClick={() => setSubTab('whales')}
                    className="text-[11px] font-bold text-[#0077C8] hover:text-[#0098EA] cursor-pointer"
                  >
                    Всі ({whales.length}) →
                  </button>
                </div>
                <div className="space-y-1.5">
                  {whales.slice(0, 3).map((ev) => (
                    <div
                      key={ev.id}
                      className="flex items-center justify-between gap-2 px-2.5 py-2 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0] text-xs"
                    >
                      <div className="min-w-0">
                        <p className="font-bold text-[#0B1120] truncate">
                          {ev.collection_name} · {ev.count} шт
                        </p>
                        <p className="text-[10.5px] text-[#64748B] truncate">{ev.signal}</p>
                      </div>
                      <span className="font-extrabold text-[#0077C8] tabular-nums shrink-0">
                        {formatTon(ev.total_ton, 1)} TON
                      </span>
                    </div>
                  ))}
                </div>
              </section>
            )}
          </div>
        </div>
      )}

      {/* TAB 2: 24H TRENDS & TOP VISUAL FINDS */}
      {subTab === 'trends' && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
          {/* Left: Trending Backdrops Today */}
          <section className="lg:col-span-5 ton-card rounded-2xl p-3.5 sm:p-4 space-y-3">
            <div className="flex items-start justify-between gap-2">
              <div>
                <h2 className="font-display text-[14px] font-extrabold text-[#0B1120] flex items-center gap-1.5">
                  <Palette className="w-4 h-4 text-[#0098EA]" />
                  Популярні фони сьогодні
                </h2>
                <p className="text-[11px] text-[#64748B] mt-0.5">
                  Фони, що торгуються вище флора на +15–40% за останні 24 години
                </p>
              </div>
              <span className="px-2 py-0.5 rounded-full bg-[#E8F5FE] text-[#0077C8] border border-[#BAE3FC] text-[10px] font-extrabold shrink-0">
                LIVE 24г
              </span>
            </div>

            {trendsLoading ? (
              <div className="space-y-2">
                {[1, 2, 3, 4].map((i) => (
                  <div
                    key={i}
                    className="h-16 rounded-xl bg-[#F4F7FB] border border-[#E2E8F0] animate-pulse"
                  />
                ))}
              </div>
            ) : trendingBackdrops.length === 0 ? (
              <div className="rounded-xl p-5 bg-[#F8FAFC] border border-[#E2E8F0] text-center text-xs text-[#64748B]">
                Збираємо статистику премій по фонах за останні 24 години...
              </div>
            ) : (
              <div className="space-y-2">
                {trendingBackdrops.map((tb, idx) => {
                  const name = tb.name || tb.backdrop || 'Backdrop';
                  const swatch = tb.swatch_hex || tb.color_hex || tb.hex || '#0098EA';
                  const colCount = tb.collections_count ?? tb.collection_count ?? 0;
                  const boost =
                    tb.fair_value_boost_percent ??
                    tb.boost_percent ??
                    Math.min(18, Math.round(tb.avg_premium_percent * 0.45));

                  return (
                    <div
                      key={`${name}-${idx}`}
                      className="p-3 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0] hover:border-[#BAE3FC] transition-colors flex items-center justify-between gap-3"
                    >
                      <div className="flex items-center gap-2.5 min-w-0">
                        <div className="w-9 h-9 rounded-xl bg-white border border-[#E2E8F0] flex items-center justify-center shrink-0">
                          <span
                            className="w-5 h-5 rounded-full border border-[#0B1120]/20 shadow-2xs"
                            style={{ backgroundColor: swatch }}
                          />
                        </div>
                        <div className="min-w-0">
                          <p className="text-[13px] font-extrabold text-[#0B1120] truncate">
                            {name}
                          </p>
                          <p className="text-[10.5px] text-[#64748B] tabular-nums">
                            {colCount} колекцій
                            {tb.sample_collections && tb.sample_collections.length > 0
                              ? ` · ${tb.sample_collections.slice(0, 2).join(', ')}`
                              : ''}
                          </p>
                        </div>
                      </div>

                      <div className="text-right shrink-0 tabular-nums space-y-1">
                        <p className="text-[13px] font-extrabold text-[#0077C8]">
                          +{tb.avg_premium_percent.toFixed(1)}% до флора
                        </p>
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-[#E8F5FE] text-[#0098EA] border border-[#BAE3FC] text-[10px] font-extrabold">
                          <Sparkles className="w-2.5 h-2.5" />
                          Fair Value +{boost}%
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </section>

          {/* Right: Top Visual Finds (8+/10 near/below floor) */}
          <section className="lg:col-span-7 ton-card rounded-2xl p-3.5 sm:p-4 space-y-3">
            <div className="flex items-start justify-between gap-2">
              <div>
                <h2 className="font-display text-[14px] font-extrabold text-[#0B1120] flex items-center gap-1.5">
                  <Eye className="w-4 h-4 text-[#0098EA]" />
                  Топ візуальні знахідки (8+/10 нижче/біля флора)
                </h2>
                <p className="text-[11px] text-[#64748B] mt-0.5">
                  Монохром, сильний контраст, трендові фони та красиві номери — натисніть для X-Ray
                </p>
              </div>
              <span className="px-2 py-0.5 rounded-full bg-[#E8F5FE] text-[#0077C8] border border-[#BAE3FC] text-[10px] font-extrabold tabular-nums shrink-0">
                {topVisualFinds.length} NFT
              </span>
            </div>

            {trendsLoading ? (
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {[1, 2, 3, 4, 5, 6].map((i) => (
                  <div
                    key={i}
                    className="rounded-2xl overflow-hidden border border-[#E2E8F0] animate-pulse"
                  >
                    <div className="aspect-square bg-[#E8F5FE]" />
                    <div className="p-2.5 space-y-2 bg-white">
                      <div className="h-3 bg-[#E2E8F0] rounded w-3/4" />
                      <div className="h-4 bg-[#E8F5FE] rounded w-1/2" />
                    </div>
                  </div>
                ))}
              </div>
            ) : topVisualFinds.length === 0 ? (
              <div className="rounded-xl p-6 bg-[#F8FAFC] border border-[#E2E8F0] text-center text-xs text-[#64748B]">
                Наразі скануємо візуальну естетику свіжих лотів. Перевірте через кілька секунд.
              </div>
            ) : (
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {topVisualFinds.slice(0, 9).map((item) => (
                  <NftCard
                    key={item.id}
                    item={item}
                    tonUsd={tonUsd}
                    onSelect={onSelectListing}
                  />
                ))}
              </div>
            )}
          </section>
        </div>
      )}

      {/* TAB 3: SORTABLE COLLECTIONS TABLE */}
      {subTab === 'rating' && (
        <section className="ton-card rounded-2xl p-3.5 sm:p-4 space-y-3">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <h2 className="font-display text-[14px] font-extrabold text-[#0B1120]">
              Усі колекції ({collections.length})
            </h2>
            <div className="flex items-center gap-2">
              <div className="relative flex-1 sm:w-64">
                <Search className="w-3.5 h-3.5 text-[#64748B] absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Пошук серед усіх 124+ колекцій..."
                  className="w-full h-9 pl-8 pr-3 rounded-xl bg-[#F4F7FB] border border-[#E2E8F0] text-xs font-medium text-[#0B1120] focus:outline-none focus:border-[#0098EA]"
                />
              </div>
              <select
                value={sort}
                onChange={(e) => setSort(e.target.value as SortKey)}
                className="h-9 text-[11px] font-bold text-[#0077C8] bg-[#E8F5FE] border border-[#BAE3FC] px-2.5 rounded-xl focus:outline-none cursor-pointer shrink-0"
              >
                <option value="volume_desc">Об&apos;єм ↓</option>
                <option value="floor_desc">Флор ↓</option>
                <option value="change_desc">Зріст 24г ↓</option>
                <option value="liquidity_desc">Ліквідність ↓</option>
                <option value="spread_desc">Bid-Ask Спред ↓</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2 max-h-[600px] overflow-y-auto pr-0.5">
            {collections.map((col) => {
              const up = col.change_24h_percent >= 0;
              return (
                <button
                  key={col.short_name}
                  type="button"
                  onClick={() => {
                    haptic('light');
                    setSelectedShortName(col.short_name);
                    setSubTab('charts');
                  }}
                  className={`w-full text-left flex items-center justify-between gap-2 p-2.5 rounded-xl border transition-colors cursor-pointer ${
                    col.short_name === selectedShortName
                      ? 'bg-[#E8F5FE]/70 border-[#0098EA]'
                      : 'bg-[#F8FAFC] border-[#E2E8F0] hover:border-[#BAE3FC]'
                  }`}
                >
                  <div className="flex items-center gap-2.5 min-w-0">
                    <div className="w-9 h-9 rounded-xl overflow-hidden bg-white border border-[#E2E8F0] shrink-0">
                      <NftImage
                        src={col.photo_url}
                        alt={col.name}
                        className="w-full h-full object-cover"
                      />
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-1">
                        <p className="text-xs font-extrabold text-[#0B1120] truncate">
                          {col.name}
                        </p>
                        {col.wash_trade_flag && (
                          <AlertTriangle
                            className="w-3 h-3 text-[#0098EA] shrink-0"
                            aria-label="Wash-trade ризик"
                          />
                        )}
                      </div>
                      <div className="flex items-center gap-1.5 mt-0.5 text-[10px] text-[#64748B] tabular-nums">
                        <span>Лікв. {col.liquidity_score}</span>
                        <span>·</span>
                        <span>Bid-Ask {col.bid_ask_spread_percent.toFixed(1)}%</span>
                        {col.arbitrage_spread_percent > 3 && (
                          <span className="text-[#0077C8] font-bold">
                            Арб +{col.arbitrage_spread_percent.toFixed(1)}%
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="text-right shrink-0 tabular-nums">
                    <p className="text-[12.5px] font-extrabold text-[#0B1120]">
                      {formatTon(col.floor_price)} TON
                    </p>
                    <p
                      className={`text-[10.5px] font-bold ${
                        up ? 'text-[#0098EA]' : 'text-[#64748B]'
                      }`}
                    >
                      {formatPercent(col.change_24h_percent)}
                    </p>
                  </div>
                </button>
              );
            })}
          </div>
        </section>
      )}

      {/* TAB 4: WHALE ACTIVITY FEED */}
      {subTab === 'whales' && (
        <section className="ton-card rounded-2xl p-3.5 sm:p-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-display text-[14px] font-extrabold text-[#0B1120] flex items-center gap-1.5">
              <Waves className="w-4 h-4 text-[#0098EA]" />
              Активність Китів (Smart Money)
            </h2>
            <span className="text-[10.5px] font-bold text-[#0077C8] bg-[#E8F5FE] border border-[#BAE3FC] px-2.5 py-0.5 rounded-full">
              LIVE
            </span>
          </div>

          {whales.length === 0 ? (
            <p className="text-xs text-[#64748B] text-center py-6">
              Очікуємо великі транзакції китів...
            </p>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
              {whales.slice(0, 12).map((ev) => {
                const badgeStyle =
                  ev.action === 'SWEEP'
                    ? 'bg-[#E8F5FE] text-[#0077C8] border-[#BAE3FC]'
                    : ev.action === 'RARE_BUY'
                      ? 'bg-[#0098EA] text-white border-[#0098EA]'
                      : 'bg-[#F1F5F9] text-[#334155] border-[#CBD5E1]';
                const actionLabel =
                  ev.action === 'SWEEP'
                    ? 'ВИКУП ФЛОРА'
                    : ev.action === 'RARE_BUY'
                      ? 'РІДКІСНА ПОКУПКА'
                      : 'ЛІСТИНГ';

                return (
                  <div
                    key={ev.id}
                    className="p-3 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0] flex items-center gap-3"
                  >
                    <div className="w-11 h-11 rounded-xl overflow-hidden bg-white border border-[#E2E8F0] shrink-0">
                      <NftImage
                        src={ev.photo_url}
                        alt={ev.collection_name}
                        className="w-full h-full object-cover"
                      />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span
                          className={`px-1.5 py-0.5 rounded-md text-[9.5px] font-extrabold border ${badgeStyle}`}
                        >
                          {actionLabel}
                        </span>
                        <span className="text-[11px] font-bold text-[#0B1120] truncate">
                          {ev.wallet_label || ev.wallet}
                        </span>
                      </div>
                      <p className="text-[11.5px] font-semibold text-[#334155] mt-0.5 truncate">
                        {ev.collection_name} · {ev.count} шт ·{' '}
                        <span className="text-[#0077C8]">{ev.signal}</span>
                      </p>
                    </div>
                    <div className="text-right shrink-0 tabular-nums">
                      <p className="text-[13px] font-extrabold text-[#0B1120]">
                        {formatTon(ev.total_ton, 1)} TON
                      </p>
                      <p className="text-[10px] text-[#64748B]">
                        {formatTimeAgo(ev.timestamp)}
                      </p>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>
      )}
    </div>
  );
};
