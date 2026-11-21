import React, { useState } from 'react';
import {
  Briefcase,
  ExternalLink,
  Eye,
  Trash2,
} from 'lucide-react';
import { api } from '../api/client';
import type {
  AnalyzedListing,
  CollectionSummary,
  PortfolioItem,
  PortfolioResponse,
} from '../types/api';
import {
  formatTon,
  formatUsd,
  getMarketMeta,
  haptic,
  openExternalLink,
} from '../utils/format';
import { NftImage } from '../components/NftImage';

interface PortfolioPageProps {
  portfolio: PortfolioResponse | null;
  collections: CollectionSummary[];
  tonUsd: number;
  loading: boolean;
  onSelectListing: (item: AnalyzedListing) => void;
  onReload: () => Promise<void>;
  onNotify: (title: string, message?: string, variant?: 'info' | 'success' | 'warning' | 'error') => void;
}

export const PortfolioPage: React.FC<PortfolioPageProps> = ({
  portfolio,
  tonUsd,
  loading,
  onSelectListing,
  onReload,
  onNotify,
}) => {
  const [openingId, setOpeningId] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const items = portfolio?.items || [];
  const totalValueTon = items.reduce(
    (sum, it) => sum + Number(it.current_floor || it.buy_price || 0),
    0,
  );

  const handleOpenFullscreen = async (item: PortfolioItem) => {
    haptic('light');
    if (item.listing && typeof item.listing.price === 'number') {
      onSelectListing(item.listing);
      return;
    }
    setOpeningId(item.id);
    try {
      const query = item.tg_id || `${item.collection_name} #${item.number}`;
      const res = await api.runXRay(query);
      onSelectListing(res.item);
    } catch {
      onSelectListing({
        id: String(item.id),
        tg_id: item.tg_id,
        collection_id: item.short_name,
        collection_name: item.collection_name,
        short_name: item.short_name,
        number: item.number,
        photo_url: item.photo_url,
        market: item.market,
        market_url: item.market_url || `https://t.me/nft/${item.tg_id}`,
        price: item.buy_price,
        collection_floor: item.current_floor,
        fair_value: item.fair_value,
        discount_percent: 0,
        net_profit_ton: item.pnl_ton,
        net_profit_percent: item.pnl_percent,
        fee_percent: 5,
        liquidity_score: 75,
        sales_24h: 0,
        is_rare_combo: false,
        wash_trade_risk: false,
        best_sell_market: item.best_sell_market,
        best_sell_price: item.best_sell_price,
        verdict: 'FAIR',
        verdict_label: 'Збережено в портфелі',
        listed_at: new Date().toISOString(),
        attributes: [],
        market_prices: [],
        recent_sales: [],
        is_live: true,
      });
    } finally {
      setOpeningId(null);
    }
  };

  const handleDelete = async (e: React.MouseEvent, item: PortfolioItem) => {
    e.stopPropagation();
    haptic('light');
    setDeletingId(item.id);
    try {
      await api.deletePortfolioItem(item.id);
      await onReload();
      onNotify('Видалено з портфеля', `${item.collection_name} #${item.number}`, 'info');
    } catch (err) {
      onNotify('Помилка видалення', err instanceof Error ? err.message : '', 'error');
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="space-y-4 pb-4">
      {/* Compact Header Summary Card */}
      <section className="rounded-3xl p-4 sm:p-5 bg-gradient-to-br from-[#0098EA] via-[#0086D6] to-[#0070B8] text-white shadow-lg shadow-[#0098EA]/20">
        <p className="text-[11px] font-bold uppercase tracking-wider text-white/80">
          Портфель · Збережені NFT
        </p>
        <div className="flex items-baseline gap-2.5 mt-1 tabular-nums">
          <span className="font-display text-2xl sm:text-3xl font-extrabold">
            {items.length} NFT
          </span>
          {totalValueTon > 0 && (
            <span className="text-sm font-bold text-white/85">
              ≈ {formatTon(totalValueTon)} TON ({formatUsd(totalValueTon * tonUsd)})
            </span>
          )}
        </div>
      </section>

      {/* Saved NFTs Grid */}
      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="ton-card rounded-2xl p-4 h-44 animate-pulse bg-white" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="ton-card rounded-2xl p-8 text-center max-w-md mx-auto">
          <div className="w-12 h-12 rounded-2xl bg-[#E8F5FE] border border-[#BAE3FC] flex items-center justify-center mx-auto mb-2.5">
            <Briefcase className="w-5 h-5 text-[#0098EA]" />
          </div>
          <p className="text-sm font-extrabold text-[#0B1120]">Портфель порожній</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {items.map((item) => {
            const mMeta = getMarketMeta(item.market);
            const isOpening = openingId === item.id;
            const isDeleting = deletingId === item.id;
            const tgNftUrl = item.tg_id ? `https://t.me/nft/${item.tg_id}` : '';

            return (
              <div
                key={item.id}
                onClick={() => handleOpenFullscreen(item)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    handleOpenFullscreen(item);
                  }
                }}
                className="ton-card ton-card-hover rounded-2xl p-3.5 flex flex-col justify-between gap-3 cursor-pointer text-left"
              >
                <div className="flex items-start gap-3">
                  <div className="w-16 h-16 rounded-2xl overflow-hidden bg-[#F4F7FB] border border-[#E2E8F0] shrink-0">
                    <NftImage
                      src={item.photo_url || item.listing?.photo_url}
                      alt={`${item.collection_name} #${item.number}`}
                      fallbackText={item.collection_name}
                      collectionName={item.collection_name}
                      shortName={item.short_name}
                      modelName={item.listing?.attributes?.find((a) => a.type === 'model')?.value}
                      backdropName={item.listing?.attributes?.find((a) => a.type === 'backdrop')?.value}
                      className="w-full h-full object-cover"
                    />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-start justify-between gap-1.5">
                      <h3 className="text-[13.5px] font-extrabold text-[#0B1120] leading-tight truncate">
                        {item.collection_name}{' '}
                        <span className="text-[#64748B] font-bold">#{item.number}</span>
                      </h3>
                      <button
                        type="button"
                        disabled={isDeleting}
                        onClick={(e) => handleDelete(e, item)}
                        className="p-1.5 rounded-lg text-[#64748B] hover:text-[#DC2626] hover:bg-[#FEF2F2] transition-colors cursor-pointer shrink-0 disabled:opacity-50"
                        title="Видалити з портфеля"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>

                    <div className="flex items-center gap-1.5 mt-1 flex-wrap">
                      <span
                        className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded border text-[9.5px] font-bold ${mMeta.bg} ${mMeta.text} ${mMeta.border}`}
                      >
                        <span className={`w-1.5 h-1.5 rounded-full ${mMeta.dot}`} />
                        {mMeta.label}
                      </span>
                      {item.listing?.harmony_label && (
                        <span className="px-1.5 py-0.5 rounded bg-[#E8F5FE] text-[#0077C8] border border-[#BAE3FC] text-[9.5px] font-bold">
                          {item.listing.harmony_label}
                        </span>
                      )}
                    </div>

                    <div className="grid grid-cols-2 gap-1.5 mt-2 text-[11px] tabular-nums">
                      <div className="rounded-lg bg-[#F8FAFC] border border-[#E2E8F0] px-2 py-1">
                        <span className="block text-[9.5px] text-[#64748B] font-semibold">
                          Ціна збереження
                        </span>
                        <span className="font-extrabold text-[#0B1120]">
                          {formatTon(item.buy_price)} TON
                        </span>
                      </div>
                      <div className="rounded-lg bg-[#F0F8FF] border border-[#BAE3FC] px-2 py-1">
                        <span className="block text-[9.5px] text-[#0077C8] font-semibold">
                          Живий флор
                        </span>
                        <span className="font-extrabold text-[#0077C8]">
                          {formatTon(item.current_floor)} TON
                        </span>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-1.5 pt-1 border-t border-[#F1F5F9]">
                  <button
                    type="button"
                    disabled={isOpening}
                    onClick={(e) => {
                      e.stopPropagation();
                      handleOpenFullscreen(item);
                    }}
                    className="flex-1 h-9 rounded-xl ton-btn-primary text-white text-[11px] font-extrabold inline-flex items-center justify-center gap-1.5 cursor-pointer disabled:opacity-60"
                  >
                    <Eye className="w-3.5 h-3.5" />
                    <span>{isOpening ? 'Відкриття...' : 'Відкрити на весь екран'}</span>
                  </button>
                  {tgNftUrl && (
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        haptic('light');
                        openExternalLink(tgNftUrl);
                      }}
                      className="h-9 px-3 rounded-xl bg-[#F8FAFC] hover:bg-[#E8F5FE] border border-[#E2E8F0] hover:border-[#BAE3FC] text-[#0B1120] hover:text-[#0077C8] text-[11px] font-bold inline-flex items-center gap-1 cursor-pointer transition-colors"
                    >
                      <span>TG</span>
                      <ExternalLink className="w-3 h-3" />
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
