import React, { useCallback, useEffect, useState } from 'react';
import {
  ArrowRight,
  Check,
  ChevronDown,
  RefreshCw,
  Search,
  SlidersHorizontal,
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

const MARKET_OPTIONS = [
  { key: 'portals', label: 'Portals' },
  { key: 'getgems', label: 'Getgems' },
  { key: 'mrkt', label: 'MRKT' },
  { key: 'tonnel', label: 'Tonnel' },
  { key: 'fragment', label: 'Fragment' },
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
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  // Filters
  const [searchText, setSearchText] = useState('');
  const [collection, setCollection] = useState('');
  const [selectedMarkets, setSelectedMarkets] = useState<string[]>([]);
  const [showMarketMenu, setShowMarketMenu] = useState(false);
  const [sort, setSort] = useState<SortOption>('discount_desc');

  const filteredItems = items.filter((item) => {
    if (selectedMarkets.length > 0 && selectedMarkets.length < MARKET_OPTIONS.length) {
      if (!selectedMarkets.includes(String(item.market).toLowerCase())) {
        return false;
      }
    }
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

  const marketParam =
    selectedMarkets.length > 0 && selectedMarkets.length < MARKET_OPTIONS.length
      ? selectedMarkets.join(',')
      : undefined;

  const fetchListings = useCallback(async () => {
    setLoading(true);
    try {
      const [listRes, arbRes] = await Promise.all([
        api.getScannerListings({
          collection: collection || undefined,
          market: marketParam,
          min_discount: -100,
          sort,
          limit: 60,
        }),
        api.getScannerArbitrage().catch(() => ({ opportunities: [] })),
      ]);

      setItems(listRes.items || []);
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
  }, [collection, marketParam, sort, onNotify]);

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
    setSelectedMarkets([]);
    setShowMarketMenu(false);
    setSort('discount_desc');
  };

  const toggleMarketChoice = (key: string) => {
    haptic('light');
    setSelectedMarkets((prev) => {
      if (prev.includes(key)) {
        return prev.filter((k) => k !== key);
      }
      const next = [...prev, key];
      return next.length === MARKET_OPTIONS.length ? [] : next;
    });
  };

  const marketButtonLabel = (() => {
    if (selectedMarkets.length === 0 || selectedMarkets.length === MARKET_OPTIONS.length) {
      return 'Маркет: Всі';
    }
    if (selectedMarkets.length <= 2) {
      const labels = selectedMarkets.map(
        (k) => MARKET_OPTIONS.find((m) => m.key === k)?.label || k,
      );
      return `Маркет: ${labels.join(', ')}`;
    }
    return `Маркет: ${selectedMarkets.length} обрано`;
  })();

  const handleClickArbitrage = async (opp: ArbitrageOpportunity) => {
    haptic('light');
    if (opp.listing) {
      onSelectListing(opp.listing);
      return;
    }
    try {
      const query =
        opp.tg_id ||
        (opp.number ? `${opp.collection_name} #${opp.number}` : opp.collection_name);
      const res = await api.runXRay(query);
      if (res?.item) {
        onSelectListing(res.item);
      }
    } catch {
      setCollection(opp.short_name);
    }
  };

  return (
    <div className="space-y-4 pb-4">
      {/* Cross-Market Arbitrage Strip (Real Specific NFTs) */}
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
              const nftNumber = opp.number ?? opp.listing?.number;
              const nftPhoto = opp.photo_url || opp.listing?.photo_url;
              return (
                <button
                  key={opp.id}
                  type="button"
                  onClick={() => handleClickArbitrage(opp)}
                  className="shrink-0 w-[244px] sm:w-[258px] text-left ton-card ton-card-hover rounded-2xl p-3 cursor-pointer"
                >
                  <div className="flex items-center gap-2.5">
                    <div className="w-10 h-10 rounded-xl overflow-hidden bg-[#F4F7FB] border border-[#E2E8F0] shrink-0">
                      <NftImage
                        src={nftPhoto}
                        alt={opp.collection_name}
                        className="w-full h-full object-cover"
                      />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-[12.5px] font-extrabold text-[#0B1120] truncate">
                        {opp.collection_name}
                        {nftNumber ? ` #${nftNumber}` : ''}
                      </p>
                      <span className="inline-block text-[10px] font-bold px-1.5 py-0.5 rounded bg-[#E8F5FE] text-[#0077C8] mt-0.5 truncate max-w-full">
                        {opp.model_name
                          ? opp.model_name
                          : opp.type === 'instant_offer'
                            ? 'Миттєвий офер'
                            : 'Реальний лот'}
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

      {/* Filter Toolbar — Exact 4-Row User Layout */}
      <section className="ton-card rounded-2xl p-3 sm:p-3.5 space-y-2.5">
        {/* Row 1: Instant Search Input */}
        <div className="relative w-full">
          <Search className="w-3.5 h-3.5 text-[#64748B] absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
          <input
            type="text"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            placeholder="Пошук: колекція, модель, фон або #номер..."
            className="w-full h-10 pl-8 pr-3 rounded-xl bg-[#F4F7FB] border border-[#E2E8F0] text-xs font-semibold text-[#0B1120] placeholder:text-[#64748B] focus:outline-none focus:border-[#0098EA] focus:bg-white transition-colors"
          />
        </div>

        {/* Row 2: 50/50 Collection Select + BLACK Оновити Button */}
        <div className="grid grid-cols-2 gap-2 w-full">
          <select
            value={collection}
            onChange={(e) => setCollection(e.target.value)}
            className="h-10 w-full px-3 rounded-xl bg-[#F4F7FB] border border-[#E2E8F0] text-xs font-bold text-[#0B1120] focus:outline-none focus:border-[#0098EA]"
          >
            <option value="">
              {collections.length > 0 ? `Всі колекції (${collections.length})` : 'Всі колекції (124)'}
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
            className="h-10 w-full rounded-xl bg-[#F4F7FB] hover:bg-[#E8F5FE] border border-[#E2E8F0] text-[#0B1120] text-xs font-bold inline-flex items-center justify-center gap-1.5 cursor-pointer disabled:opacity-60 transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 text-[#0B1120] ${refreshing ? 'animate-spin' : ''}`} />
            <span>Оновити</span>
          </button>
        </div>

        {/* Row 3: Full-Width Light-Grey Multi-Select "Маркет" Button */}
        <div className="w-full relative">
          <button
            type="button"
            onClick={() => {
              haptic('light');
              setShowMarketMenu((v) => !v);
            }}
            className="h-10 w-full rounded-xl bg-[#F4F7FB] hover:bg-[#E8F5FE] border border-[#E2E8F0] text-[#0B1120] text-xs font-bold flex items-center justify-between px-3.5 cursor-pointer transition-colors"
          >
            <span>{marketButtonLabel}</span>
            <ChevronDown
              className={`w-4 h-4 text-[#0B1120] transition-transform ${showMarketMenu ? 'rotate-180' : ''}`}
            />
          </button>

          {showMarketMenu && (
            <div className="w-full mt-1.5 p-2 rounded-xl bg-white border border-[#E2E8F0] shadow-lg grid grid-cols-2 sm:grid-cols-3 gap-1.5">
              <button
                type="button"
                onClick={() => {
                  haptic('light');
                  setSelectedMarkets([]);
                }}
                className={`h-9 px-2.5 rounded-lg text-xs font-bold border flex items-center justify-between cursor-pointer transition-colors ${
                  selectedMarkets.length === 0
                    ? 'bg-[#E8F5FE] text-[#0077C8] border-[#0098EA]'
                    : 'bg-[#F4F7FB] text-[#0B1120] border-[#E2E8F0] hover:border-[#BAE3FC]'
                }`}
              >
                <span>Всі</span>
                {selectedMarkets.length === 0 && <Check className="w-3.5 h-3.5 text-[#0098EA]" />}
              </button>

              {MARKET_OPTIONS.map((m) => {
                const isSelected = selectedMarkets.includes(m.key);
                return (
                  <button
                    key={m.key}
                    type="button"
                    onClick={() => toggleMarketChoice(m.key)}
                    className={`h-9 px-2.5 rounded-lg text-xs font-bold border flex items-center justify-between cursor-pointer transition-colors ${
                      isSelected
                        ? 'bg-[#E8F5FE] text-[#0077C8] border-[#0098EA]'
                        : 'bg-[#F4F7FB] text-[#0B1120] border-[#E2E8F0] hover:border-[#BAE3FC]'
                    }`}
                  >
                    <span>{m.label}</span>
                    {isSelected && <Check className="w-3.5 h-3.5 text-[#0098EA]" />}
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Row 4: 50/50 Count + Vertical Divider + Light-Grey Sort Selector */}
        <div className="grid grid-cols-2 items-center pt-2.5 border-t border-[#E2E8F0] divide-x divide-[#CBD5E1]">
          <div className="pr-3 flex items-center justify-center">
            <span className="text-xs font-extrabold text-[#0B1120] tabular-nums">
              {filteredItems.length} лотів
            </span>
          </div>

          <div className="pl-3">
            <select
              value={sort}
              onChange={(e) => setSort(e.target.value as SortOption)}
              className="h-9 w-full px-3 rounded-xl bg-[#F4F7FB] hover:bg-[#E8F5FE] border border-[#E2E8F0] text-[#0B1120] text-xs font-bold focus:outline-none focus:border-[#0098EA] cursor-pointer transition-colors"
            >
              <option value="discount_desc">Вигода</option>
              <option value="visual_desc">Топ візуал</option>
              <option value="profit_desc">Профіт TON</option>
              <option value="price_asc">Дешевші</option>
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
