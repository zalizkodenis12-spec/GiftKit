import React, { useCallback, useEffect, useState } from 'react';
import {
  ArrowRight,
  ArrowUpDown,
  Eye,
  Flame,
  Hash,
  RefreshCw,
  Search,
  SlidersHorizontal,
  Sparkles,
  TrendingUp,
} from 'lucide-react';
import { api } from '../api/client';
import type {
  AnalyzedListing,
  ArbitrageOpportunity,
  CollectionSummary,
} from '../types/api';
import { formatTon, getMarketMeta, haptic } from '../utils/format';
import { NftCard } from '../components/NftCard';
import { NftImage } from '../components/NftImage';

interface ScannerPageProps {
  collections: CollectionSummary[];
  tonUsd: number;
  refreshTick: number;
  onSelectListing: (item: AnalyzedListing) => void;
  onNotify: (title: string, message?: string, variant?: 'info' | 'success' | 'warning' | 'error') => void;
}

const MARKET_FILTERS = [
  { key: 'all', label: 'Всі' },
  { key: 'portals', label: 'Portals' },
  { key: 'getgems', label: 'Getgems' },
  { key: 'mrkt', label: 'MRKT' },
  { key: 'tonnel', label: 'Tonnel' },
];

const DISCOUNT_FILTERS = [
  { value: -100, label: 'Всі' },
  { value: 5, label: '>5%' },
  { value: 15, label: '>15%' },
  { value: 25, label: '>25%' },
];

type SortOption = 'discount_desc' | 'profit_desc' | 'visual_desc' | 'price_asc' | 'newest';

export const ScannerPage: React.FC<ScannerPageProps> = ({
  collections,
  tonUsd,
  refreshTick,
  onSelectListing,
  onNotify,
}) => {
  const [items, setItems] = useState<AnalyzedListing[]>([]);
  const [arbitrage, setArbitrage] = useState<ArbitrageOpportunity[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  // Filters
  const [searchText, setSearchText] = useState('');
  const [collection, setCollection] = useState('');
  const [market, setMarket] = useState('all');
  const [minDiscount, setMinDiscount] = useState(-100);
  const [rareComboOnly, setRareComboOnly] = useState(false);
  const [visualTopOnly, setVisualTopOnly] = useState(false);
  const [niceNumberOnly, setNiceNumberOnly] = useState(false);
  const [sort, setSort] = useState<SortOption>('discount_desc');

  const filteredItems = items.filter((item) => {
    if (searchText.trim()) {
      const q = searchText.trim().toLowerCase();
      const matchesText =
        item.collection_name.toLowerCase().includes(q) ||
        item.short_name.toLowerCase().includes(q) ||
        String(item.number).includes(q) ||
        (item.harmony_label || '').toLowerCase().includes(q) ||
        (item.symbol_badge || '').toLowerCase().includes(q) ||
        (item.trend_label || '').toLowerCase().includes(q) ||
        (item.number_pattern || '').toLowerCase().includes(q) ||
        (item.attributes || []).some((a) => a.value.toLowerCase().includes(q));
      if (!matchesText) return false;
    }
    return true;
  });

  const fetchListings = useCallback(async () => {
    setLoading(true);
    try {
      const [listRes, arbRes] = await Promise.all([
        api.getScannerListings({
          collection: collection || undefined,
          market: market === 'all' ? undefined : market,
          min_discount: minDiscount,
          rare_combo_only: rareComboOnly || undefined,
          visual_top_only: visualTopOnly || undefined,
          nice_number_only: niceNumberOnly || undefined,
          sort,
          limit: 60,
        }),
        api.getScannerArbitrage().catch(() => ({ opportunities: [] })),
      ]);

      setItems(listRes.items || []);
      setTotal(listRes.total ?? (listRes.items?.length || 0));
      const arbList =
        arbRes.opportunities && arbRes.opportunities.length > 0
          ? arbRes.opportunities
          : listRes.arbitrage_top || [];
      setArbitrage(arbList);
    } catch (err) {
      onNotify(
        'Не вдалося завантажити сканер',
        err instanceof Error ? err.message : 'Перевірте підключення до бекенду',
        'error',
      );
    } finally {
      setLoading(false);
    }
  }, [
    collection,
    market,
    minDiscount,
    rareComboOnly,
    visualTopOnly,
    niceNumberOnly,
    sort,
    onNotify,
  ]);

  useEffect(() => {
    fetchListings();
  }, [fetchListings, refreshTick]);

  const handleHardRefresh = async () => {
    haptic('light');
    setRefreshing(true);
    try {
      await api.refreshScanner();
      await fetchListings();
      onNotify('Дані оновлено', 'Отримано свіжі лоти з усіх маркетів', 'success');
    } catch (err) {
      onNotify(
        'Помилка оновлення',
        err instanceof Error ? err.message : 'Спробуйте ще раз',
        'error',
      );
    } finally {
      setRefreshing(false);
    }
  };

  const resetAllFilters = () => {
    setSearchText('');
    setCollection('');
    setMarket('all');
    setMinDiscount(-100);
    setRareComboOnly(false);
    setVisualTopOnly(false);
    setNiceNumberOnly(false);
    setSort('discount_desc');
  };

  return (
    <div className="space-y-4 pb-4">
      {/* Cross-Market Arbitrage Strip */}
      <section>
        <div className="flex items-center justify-between px-0.5 mb-2">
          <div className="flex items-center gap-1.5">
            <span className="w-6 h-6 rounded-lg bg-[#E8F5FE] border border-[#BAE3FC] flex items-center justify-center">
              <TrendingUp className="w-3.5 h-3.5 text-[#0098EA]" />
            </span>
            <h2 className="font-display text-[14px] font-extrabold text-[#0B1120]">
              Крос-маркет Арбітраж
            </h2>
          </div>
          <span className="text-[11px] font-bold text-[#0077C8] bg-[#E8F5FE] border border-[#BAE3FC] px-2.5 py-0.5 rounded-full tabular-nums">
            {arbitrage.length} зв&apos;язок
          </span>
        </div>

        {arbitrage.length === 0 && !loading ? (
          <div className="ton-card rounded-2xl p-3 text-xs text-[#64748B] text-center">
            Наразі спред між маркетами в межах комісій. Спробуйте оновити потік.
          </div>
        ) : (
          <div className="flex gap-2.5 overflow-x-auto no-scrollbar pb-1 -mx-3 px-3 sm:mx-0 sm:px-0">
            {arbitrage.slice(0, 10).map((opp) => {
              const buyMeta = getMarketMeta(opp.buy_market);
              const sellMeta = getMarketMeta(opp.sell_market);
              return (
                <button
                  key={opp.id}
                  type="button"
                  onClick={() => {
                    haptic('light');
                    setCollection(opp.short_name);
                  }}
                  className="shrink-0 w-[238px] sm:w-[252px] text-left ton-card ton-card-hover rounded-2xl p-3 cursor-pointer"
                >
                  <div className="flex items-center gap-2.5">
                    <div className="w-10 h-10 rounded-xl overflow-hidden bg-[#F4F7FB] border border-[#E2E8F0] shrink-0">
                      <NftImage
                        src={opp.photo_url}
                        alt={opp.collection_name}
                        className="w-full h-full object-cover"
                      />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-[12.5px] font-extrabold text-[#0B1120] truncate">
                        {opp.collection_name}
                      </p>
                      <span className="inline-block text-[10px] font-bold px-1.5 py-0.5 rounded bg-[#E8F5FE] text-[#0077C8] mt-0.5">
                        {opp.type === 'instant_offer' ? 'Миттєвий офер' : 'Флор-спред'}
                      </span>
                    </div>
                  </div>

                  {/* Route */}
                  <div className="mt-2.5 flex items-center justify-between gap-1 bg-[#F8FAFC] border border-[#E2E8F0] rounded-xl px-2.5 py-1.5 text-[11px] tabular-nums">
                    <div>
                      <span className={`inline-flex items-center gap-1 font-bold ${buyMeta.text}`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${buyMeta.dot}`} />
                        {buyMeta.label}
                      </span>
                      <p className="font-extrabold text-[#0B1120]">
                        {formatTon(opp.buy_price)} TON
                      </p>
                    </div>
                    <ArrowRight className="w-3.5 h-3.5 text-[#64748B] shrink-0" />
                    <div className="text-right">
                      <span className={`inline-flex items-center gap-1 font-bold ${sellMeta.text}`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${sellMeta.dot}`} />
                        {sellMeta.label}
                      </span>
                      <p className="font-extrabold text-[#0B1120]">
                        {formatTon(opp.sell_price)} TON
                      </p>
                    </div>
                  </div>

                  {/* Net Profit */}
                  <div className="mt-2 flex items-center justify-between tabular-nums">
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-lg bg-[#E8F5FE] text-[#0077C8] text-[11px] font-extrabold">
                      +{formatTon(opp.net_profit_ton)} TON
                    </span>
                    <span className="text-[11px] font-extrabold text-[#0098EA]">
                      ROI +{opp.roi_percent.toFixed(1)}%
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </section>

      {/* Responsive Filter Toolbar (Stacked on Mobile, Sleek Horizontal on Desktop) */}
      <section className="ton-card rounded-2xl p-3 sm:p-3.5 space-y-2.5">
        {/* Row 1: Search + Collection Select + Market Pills + Refresh */}
        <div className="flex flex-col lg:flex-row lg:items-center gap-2">
          {/* Instant Search Input */}
          <div className="relative flex-1 min-w-0">
            <Search className="w-3.5 h-3.5 text-[#64748B] absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
            <input
              type="text"
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              placeholder="Пошук: колекція, модель, фон, монохром або #номер..."
              className="w-full h-9 pl-8 pr-3 rounded-xl bg-[#F4F7FB] border border-[#E2E8F0] text-xs font-semibold text-[#0B1120] placeholder:text-[#64748B] focus:outline-none focus:border-[#0098EA] focus:bg-white transition-colors"
            />
          </div>

          {/* Collection Select + Refresh */}
          <div className="flex items-center gap-2 lg:w-auto">
            <select
              value={collection}
              onChange={(e) => setCollection(e.target.value)}
              className="flex-1 lg:w-[220px] h-9 pl-3 pr-7 rounded-xl bg-[#F4F7FB] border border-[#E2E8F0] text-xs font-bold text-[#0B1120] focus:outline-none focus:border-[#0098EA]"
            >
              <option value="">
                {collections.length > 0 ? `Всі колекції (${collections.length})` : 'Всі колекції'}
              </option>
              {collections.map((c) => (
                <option key={c.short_name} value={c.short_name}>
                  {c.name} — {formatTon(c.floor_price)} TON
                </option>
              ))}
            </select>

            <button
              type="button"
              disabled={refreshing}
              onClick={handleHardRefresh}
              className="h-9 px-3 rounded-xl bg-[#E8F5FE] hover:bg-[#D4ECFD] border border-[#BAE3FC] text-[#0077C8] text-xs font-bold inline-flex items-center gap-1.5 transition-colors cursor-pointer shrink-0 disabled:opacity-60"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
              <span>Оновити</span>
            </button>
          </div>
        </div>

        {/* Row 2: Market Pills + Discount + Visual/Combo/NiceNumber Quick Filters */}
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-2">
          {/* Market Pills */}
          <div className="flex items-center gap-1.5 overflow-x-auto no-scrollbar">
            {MARKET_FILTERS.map((m) => {
              const active = market === m.key;
              return (
                <button
                  key={m.key}
                  type="button"
                  onClick={() => {
                    haptic('light');
                    setMarket(m.key);
                  }}
                  className={`shrink-0 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-[11px] font-bold border transition-all cursor-pointer ${
                    active
                      ? 'bg-[#0098EA] text-white border-[#0098EA] shadow-xs'
                      : 'bg-[#F8FAFC] text-[#0B1120] border-[#E2E8F0] hover:border-[#BAE3FC] hover:bg-[#E8F5FE]/60'
                  }`}
                >
                  {m.key !== 'all' && (
                    <span
                      className={`w-1.5 h-1.5 rounded-full ${
                        active ? 'bg-white' : 'bg-[#0098EA]'
                      }`}
                    />
                  )}
                  <span>{m.label}</span>
                </button>
              );
            })}
          </div>

          {/* Discount + Quick Visual/Combo/NiceNumber Toggles */}
          <div className="flex flex-wrap items-center gap-1.5">
            <div className="flex items-center gap-1">
              {DISCOUNT_FILTERS.map((d) => {
                const active = minDiscount === d.value;
                return (
                  <button
                    key={d.value}
                    type="button"
                    onClick={() => setMinDiscount(d.value)}
                    className={`px-2 py-1 rounded-lg text-[10.5px] font-bold tabular-nums cursor-pointer border transition-colors ${
                      active
                        ? 'bg-[#0098EA] text-white border-[#0098EA]'
                        : 'bg-[#F8FAFC] border-[#E2E8F0] text-[#334155] hover:border-[#BAE3FC]'
                    }`}
                  >
                    {d.label}
                  </button>
                );
              })}
            </div>

            <button
              type="button"
              onClick={() => {
                haptic('light');
                setRareComboOnly((v) => !v);
              }}
              className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-[10.5px] font-bold border transition-all cursor-pointer ${
                rareComboOnly
                  ? 'bg-[#0098EA] text-white border-[#0098EA] shadow-xs'
                  : 'bg-[#F8FAFC] text-[#334155] border-[#E2E8F0] hover:border-[#BAE3FC]'
              }`}
            >
              <Sparkles className="w-3 h-3" />
              <span>Тільки Комбо</span>
            </button>

            <button
              type="button"
              onClick={() => {
                haptic('light');
                setVisualTopOnly((v) => !v);
              }}
              className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-[10.5px] font-bold border transition-all cursor-pointer ${
                visualTopOnly
                  ? 'bg-[#0098EA] text-white border-[#0098EA] shadow-xs'
                  : 'bg-[#F8FAFC] text-[#334155] border-[#E2E8F0] hover:border-[#BAE3FC]'
              }`}
            >
              <Eye className="w-3 h-3" />
              <span>Топ візуал (8+)</span>
            </button>

            <button
              type="button"
              onClick={() => {
                haptic('light');
                setNiceNumberOnly((v) => !v);
              }}
              className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-[10.5px] font-bold border transition-all cursor-pointer ${
                niceNumberOnly
                  ? 'bg-[#0098EA] text-white border-[#0098EA] shadow-xs'
                  : 'bg-[#F8FAFC] text-[#334155] border-[#E2E8F0] hover:border-[#BAE3FC]'
              }`}
            >
              <Hash className="w-3 h-3" />
              <span>Красиві номери</span>
            </button>
          </div>
        </div>

        {/* Row 3: Counter & Sort */}
        <div className="flex items-center justify-between pt-2 border-t border-[#F1F5F9]">
          <div className="flex items-center gap-1.5 text-[11px] text-[#64748B] font-semibold">
            <Flame className="w-3.5 h-3.5 text-[#0098EA]" />
            <span>
              Знайдено:{' '}
              <strong className="text-[#0B1120] tabular-nums">
                {searchText.trim() ? filteredItems.length : total}
              </strong>{' '}
              лотів
            </span>
          </div>

          <div className="flex items-center gap-1.5">
            <ArrowUpDown className="w-3.5 h-3.5 text-[#64748B]" />
            <select
              value={sort}
              onChange={(e) => setSort(e.target.value as SortOption)}
              className="text-[11.5px] font-bold text-[#0077C8] bg-[#E8F5FE] border border-[#BAE3FC] px-2.5 py-1 rounded-lg focus:outline-none cursor-pointer"
            >
              <option value="discount_desc">Вигода ↓</option>
              <option value="profit_desc">Профіт ↓</option>
              <option value="visual_desc">Топ візуал ↓</option>
              <option value="price_asc">Ціна ↑</option>
              <option value="newest">Нові</option>
            </select>
          </div>
        </div>
      </section>

      {/* Responsive Marketplace Grid (2 phone -> 3 sm -> 4 md -> 5 lg -> 6 xl) */}
      {loading ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3">
          {Array.from({ length: 12 }).map((_, idx) => (
            <div
              key={idx}
              className="ton-card rounded-2xl overflow-hidden animate-pulse"
            >
              <div className="aspect-square bg-[#E8F5FE]" />
              <div className="p-2.5 space-y-2">
                <div className="h-3.5 bg-[#E2E8F0] rounded w-3/4" />
                <div className="h-3 bg-[#F1F5F9] rounded w-1/2" />
                <div className="h-5 bg-[#E8F5FE] rounded w-2/3" />
              </div>
            </div>
          ))}
        </div>
      ) : filteredItems.length === 0 ? (
        <div className="ton-card rounded-2xl p-8 text-center max-w-md mx-auto">
          <div className="w-12 h-12 rounded-2xl bg-[#E8F5FE] border border-[#BAE3FC] flex items-center justify-center mx-auto mb-2.5">
            <SlidersHorizontal className="w-5 h-5 text-[#0098EA]" />
          </div>
          <p className="text-sm font-bold text-[#0B1120]">Лотів за фільтром не знайдено</p>
          <p className="text-xs text-[#64748B] mt-1">
            Спробуйте змінити критерії візуалу, дисконту або обрати всі колекції.
          </p>
          <button
            type="button"
            onClick={resetAllFilters}
            className="mt-3 px-4 py-2 rounded-xl bg-[#E8F5FE] hover:bg-[#D4ECFD] border border-[#BAE3FC] text-[#0077C8] text-xs font-bold cursor-pointer transition-colors"
          >
            Скинути фільтри
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3">
          {filteredItems.map((item) => (
            <NftCard
              key={item.id}
              item={item}
              tonUsd={tonUsd}
              onSelect={onSelectListing}
            />
          ))}
        </div>
      )}
    </div>
  );
};
