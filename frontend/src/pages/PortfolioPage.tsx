import React, { useState } from 'react';
import {
  Briefcase,
  ExternalLink,
  Eye,
  Plus,
  Trash2,
  X,
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
  collections,
  tonUsd,
  loading,
  onSelectListing,
  onReload,
  onNotify,
}) => {
  const [openingId, setOpeningId] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  // Add Saved NFT Modal
  const [showAddModal, setShowAddModal] = useState(false);
  const [savingNew, setSavingNew] = useState(false);
  const [newCollection, setNewCollection] = useState(collections[0]?.short_name || 'eternalrose');
  const [newNumber, setNewNumber] = useState('');
  const [newBuyPrice, setNewBuyPrice] = useState('');
  const [newMarket, setNewMarket] = useState('portals');

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
      // Fallback preview so user can always open saved item cleanly
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

  const handleAddNew = async (e: React.FormEvent) => {
    e.preventDefault();
    const col = collections.find((c) => c.short_name === newCollection) || collections[0];
    const num = Math.max(1, Number(newNumber) || 1);
    const price = Number(newBuyPrice) || col?.floor_price || 10;
    const colName = col?.name || newCollection;
    const shortName = col?.short_name || newCollection;
    const tgId = `${colName.replace(/[^A-Za-z0-9]/g, '')}-${num}`;

    setSavingNew(true);
    try {
      let xrayListing: AnalyzedListing | undefined;
      try {
        const xr = await api.runXRay(`${colName} #${num}`);
        xrayListing = xr.item;
      } catch {
        // optional enrichment
      }

      await api.addPortfolioItem({
        tg_id: xrayListing?.tg_id || tgId,
        collection_name: xrayListing?.collection_name || colName,
        short_name: xrayListing?.short_name || shortName,
        number: num,
        photo_url:
          xrayListing?.photo_url ||
          `https://nft.fragment.com/gift/${shortName}-${num}.large.jpg`,
        buy_price: price,
        listed_price: xrayListing?.fair_value || price,
        market: newMarket,
        auto_undercut_enabled: false,
        undercut_mode: 'notify',
        min_price_guard: price,
        undercut_step: 0.05,
        status: 'holding',
        listing: xrayListing || null,
      });
      setShowAddModal(false);
      setNewNumber('');
      setNewBuyPrice('');
      await onReload();
      onNotify('Збережено в портфель', `${colName} #${num}`, 'success');
    } catch (err) {
      onNotify('Помилка збереження', err instanceof Error ? err.message : '', 'error');
    } finally {
      setSavingNew(false);
    }
  };

  return (
    <div className="space-y-4 pb-4">
      {/* Header Summary Card */}
      <section className="rounded-3xl p-4 sm:p-5 bg-gradient-to-br from-[#0098EA] via-[#0086D6] to-[#0070B8] text-white shadow-lg shadow-[#0098EA]/20 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
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
          <p className="text-[11.5px] text-white/80 mt-1">
            Ваша особиста колекція цікавих NFT — зберігаються без сповіщень, натисніть на картку для повного перегляду
          </p>
        </div>

        <button
          type="button"
          onClick={() => {
            haptic('light');
            setShowAddModal(true);
          }}
          className="h-10 px-4 rounded-xl bg-white/18 hover:bg-white/28 border border-white/30 text-white text-xs font-extrabold inline-flex items-center justify-center gap-1.5 backdrop-blur-sm cursor-pointer shrink-0 transition-colors"
        >
          <Plus className="w-4 h-4" />
          <span>Додати NFT</span>
        </button>
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
          <p className="text-xs text-[#64748B] mt-1 leading-relaxed">
            Зберігайте сюди будь-які цікаві NFT зі Сканера, Аналітики чи Снайпера — вони лежатимуть тут без зайвих сповіщень, і ви зможете відкрити будь-який у повний екран у будь-який момент.
          </p>
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

      {/* ADD SAVED NFT MODAL */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-end md:items-center justify-center md:p-6 bg-[#0B1120]/45 backdrop-blur-[2px] animate-fade-in">
          <div className="absolute inset-0" onClick={() => setShowAddModal(false)} />
          <form
            onSubmit={handleAddNew}
            className="relative z-10 w-full md:max-w-[460px] bg-white rounded-t-[28px] md:rounded-3xl p-4 sm:p-5 space-y-3 animate-sheet-up shadow-2xl border border-[#E2E8F0]"
          >
            <div className="flex items-center justify-between">
              <h3 className="font-display text-base font-extrabold text-[#0B1120]">
                Зберегти NFT в портфель
              </h3>
              <button
                type="button"
                onClick={() => setShowAddModal(false)}
                className="w-8 h-8 rounded-full bg-[#F8FAFC] border border-[#E2E8F0] flex items-center justify-center text-[#334155] cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-2.5 text-xs">
              <div>
                <label className="block font-bold text-[#334155] mb-1">Колекція</label>
                <select
                  value={newCollection}
                  onChange={(e) => setNewCollection(e.target.value)}
                  className="w-full h-10 px-3 rounded-xl bg-[#F4F7FB] border border-[#E2E8F0] font-bold text-[#0B1120] focus:outline-none focus:border-[#0098EA]"
                >
                  {collections.map((c) => (
                    <option key={c.short_name} value={c.short_name}>
                      {c.name} (Флор {formatTon(c.floor_price)} TON)
                    </option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block font-bold text-[#334155] mb-1">Номер #</label>
                  <input
                    type="number"
                    required
                    min="1"
                    value={newNumber}
                    onChange={(e) => setNewNumber(e.target.value)}
                    placeholder="18718"
                    className="w-full h-10 px-3 rounded-xl bg-[#F4F7FB] border border-[#E2E8F0] font-bold tabular-nums focus:outline-none focus:border-[#0098EA]"
                  />
                </div>
                <div>
                  <label className="block font-bold text-[#334155] mb-1">Ціна (TON)</label>
                  <input
                    type="number"
                    step="0.01"
                    value={newBuyPrice}
                    onChange={(e) => setNewBuyPrice(e.target.value)}
                    placeholder="Флор авто"
                    className="w-full h-10 px-3 rounded-xl bg-[#F4F7FB] border border-[#E2E8F0] font-bold tabular-nums focus:outline-none focus:border-[#0098EA]"
                  />
                </div>
              </div>

              <div>
                <label className="block font-bold text-[#334155] mb-1">Маркет</label>
                <select
                  value={newMarket}
                  onChange={(e) => setNewMarket(e.target.value)}
                  className="w-full h-10 px-3 rounded-xl bg-[#F4F7FB] border border-[#E2E8F0] font-bold text-[#0B1120] focus:outline-none focus:border-[#0098EA]"
                >
                  <option value="portals">Portals</option>
                  <option value="getgems">Getgems</option>
                  <option value="mrkt">MRKT</option>
                  <option value="tonnel">Tonnel</option>
                  <option value="fragment">Fragment</option>
                </select>
              </div>
            </div>

            <button
              type="submit"
              disabled={savingNew}
              className="w-full h-11 rounded-full ton-btn-primary text-white text-sm font-extrabold cursor-pointer disabled:opacity-60"
            >
              {savingNew ? 'Збереження...' : 'Зберегти в портфель'}
            </button>
          </form>
        </div>
      )}
    </div>
  );
};
