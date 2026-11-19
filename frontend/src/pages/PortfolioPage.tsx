import React, { useState } from 'react';
import {
  AlertTriangle,
  Bell,
  Briefcase,
  Check,
  Flame,
  Plus,
  ShieldCheck,
  Trash2,
  TrendingUp,
  X,
  Zap,
} from 'lucide-react';
import { api } from '../api/client';
import type {
  CollectionSummary,
  PortfolioItem,
  PortfolioResponse,
} from '../types/api';
import {
  formatPercent,
  formatTon,
  formatUsd,
  getMarketMeta,
  haptic,
} from '../utils/format';
import { NftImage } from '../components/NftImage';

interface PortfolioPageProps {
  portfolio: PortfolioResponse | null;
  collections: CollectionSummary[];
  tonUsd: number;
  loading: boolean;
  onReload: () => Promise<void>;
  onNotify: (title: string, message?: string, variant?: 'info' | 'success' | 'warning' | 'error') => void;
}

interface ItemDraft {
  min_price_guard: string;
  undercut_step: string;
  listed_price: string;
}

export const PortfolioPage: React.FC<PortfolioPageProps> = ({
  portfolio,
  collections,
  tonUsd,
  loading,
  onReload,
  onNotify,
}) => {
  const [drafts, setDrafts] = useState<Record<number, ItemDraft>>({});
  const [busyId, setBusyId] = useState<number | null>(null);

  // Add NFT Modal
  const [showAddModal, setShowAddModal] = useState(false);
  const [savingNew, setSavingNew] = useState(false);
  const [newCollection, setNewCollection] = useState(collections[0]?.short_name || 'eternalrose');
  const [newNumber, setNewNumber] = useState('1245');
  const [newBuyPrice, setNewBuyPrice] = useState('25');
  const [newListedPrice, setNewListedPrice] = useState('31');
  const [newMarket, setNewMarket] = useState('portals');
  const [newMinGuard, setNewMinGuard] = useState('28');

  const summary = portfolio?.summary;
  const items = portfolio?.items || [];

  const getDraft = (item: PortfolioItem): ItemDraft =>
    drafts[item.id] ?? {
      min_price_guard: String(item.min_price_guard ?? ''),
      undercut_step: String(item.undercut_step ?? 0.05),
      listed_price: item.listed_price !== null ? String(item.listed_price) : '',
    };

  const updateDraft = (id: number, patch: Partial<ItemDraft>, item: PortfolioItem) => {
    const cur = getDraft(item);
    setDrafts((prev) => ({ ...prev, [id]: { ...cur, ...patch } }));
  };

  const handleToggleUndercut = async (item: PortfolioItem) => {
    haptic('light');
    setBusyId(item.id);
    try {
      await api.updatePortfolioItem(item.id, {
        auto_undercut_enabled: !item.auto_undercut_enabled,
      });
      await onReload();
      onNotify(
        !item.auto_undercut_enabled ? 'Auto-Undercut увімкнено' : 'Auto-Undercut вимкнено',
        `${item.collection_name} #${item.number}`,
        'info',
      );
    } catch (err) {
      onNotify('Помилка оновлення', err instanceof Error ? err.message : '', 'error');
    } finally {
      setBusyId(null);
    }
  };

  const handleModeChange = async (item: PortfolioItem, mode: 'auto' | 'notify') => {
    haptic('light');
    setBusyId(item.id);
    try {
      await api.updatePortfolioItem(item.id, { undercut_mode: mode });
      await onReload();
    } catch (err) {
      onNotify('Помилка зміни режиму', err instanceof Error ? err.message : '', 'error');
    } finally {
      setBusyId(null);
    }
  };

  const handleSaveGuard = async (item: PortfolioItem) => {
    haptic('medium');
    const draft = getDraft(item);
    setBusyId(item.id);
    try {
      await api.updatePortfolioItem(item.id, {
        min_price_guard: Number(draft.min_price_guard),
        undercut_step: Number(draft.undercut_step),
        listed_price: draft.listed_price ? Number(draft.listed_price) : item.listed_price,
      });
      await onReload();
      onNotify('Захист збережено', `${item.collection_name} #${item.number}`, 'success');
    } catch (err) {
      onNotify('Помилка збереження', err instanceof Error ? err.message : '', 'error');
    } finally {
      setBusyId(null);
    }
  };

  const handleApplyUndercut = async (item: PortfolioItem) => {
    haptic('success');
    setBusyId(item.id);
    try {
      const res = await api.applyUndercut(item.id);
      await onReload();
      onNotify(
        'Ціну знижено під конкурента!',
        res.message ||
          `Нова ціна: ${formatTon(res.new_price ?? item.suggested_price ?? item.listed_price)} TON`,
        'success',
      );
    } catch (err) {
      onNotify('Не вдалося застосувати undercut', err instanceof Error ? err.message : '', 'error');
    } finally {
      setBusyId(null);
    }
  };

  const handleDelete = async (item: PortfolioItem) => {
    haptic('light');
    try {
      await api.deletePortfolioItem(item.id);
      await onReload();
      onNotify('Позицію видалено', `${item.collection_name} #${item.number}`, 'info');
    } catch (err) {
      onNotify('Помилка видалення', err instanceof Error ? err.message : '', 'error');
    }
  };

  const handleAddItem = async (e: React.FormEvent) => {
    e.preventDefault();
    setSavingNew(true);
    try {
      const found = collections.find((c) => c.short_name === newCollection);
      const colName = found?.name || newCollection;
      await api.addPortfolioItem({
        collection_name: colName,
        short_name: newCollection,
        number: Number(newNumber) || 1,
        photo_url: found?.photo_url,
        buy_price: Number(newBuyPrice),
        listed_price: newListedPrice ? Number(newListedPrice) : null,
        market: newMarket,
        auto_undercut_enabled: true,
        undercut_mode: 'notify',
        min_price_guard: Number(newMinGuard) || Number(newBuyPrice),
        undercut_step: 0.05,
        status: newListedPrice ? 'listed' : 'holding',
      });
      setShowAddModal(false);
      await onReload();
      onNotify('NFT додано до портфеля', `${colName} #${newNumber}`, 'success');
    } catch (err) {
      onNotify('Помилка додавання', err instanceof Error ? err.message : '', 'error');
    } finally {
      setSavingNew(false);
    }
  };

  const pnlPositive = (summary?.unrealized_pnl_ton ?? 0) >= 0;

  return (
    <div className="space-y-4 pb-4">
      {/* Blue Gradient Portfolio Summary Card */}
      <section className="ton-gradient-banner rounded-[24px] p-4 sm:p-5 text-white relative overflow-hidden">
        <div className="absolute -right-8 -top-8 w-36 h-36 rounded-full bg-white/10 pointer-events-none" />
        <div className="absolute -left-6 -bottom-10 w-32 h-32 rounded-full bg-white/10 pointer-events-none" />

        <div className="relative z-10 flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
          <div className="flex items-start justify-between gap-3 lg:block">
            <div>
              <p className="text-[11px] font-semibold text-white/80">
                Оцінка моїх NFT
              </p>
              <div className="flex items-baseline gap-2 mt-0.5 tabular-nums">
                <h2 className="font-display text-[26px] sm:text-[30px] font-extrabold tracking-tight">
                  {formatTon(summary?.current_value_ton ?? 0)}{' '}
                  <span className="text-base font-bold text-white/90">TON</span>
                </h2>
                <span className="text-xs font-semibold text-white/80">
                  {formatUsd(summary?.current_value_ton ?? 0, tonUsd)}
                </span>
              </div>
            </div>

            <button
              type="button"
              onClick={() => {
                haptic('light');
                setShowAddModal(true);
              }}
              className="lg:hidden h-9 px-3 rounded-xl bg-white/20 hover:bg-white/30 backdrop-blur-md text-white text-xs font-bold inline-flex items-center gap-1 border border-white/25 cursor-pointer"
            >
              <Plus className="w-4 h-4" />
              <span>Додати NFT</span>
            </button>
          </div>

          <div className="grid grid-cols-3 gap-3 lg:gap-8 pt-3 lg:pt-0 border-t lg:border-t-0 border-white/20 tabular-nums items-center">
            <div>
              <p className="text-[10.5px] text-white/75 font-medium">Куплено за</p>
              <p className="text-[14px] sm:text-[15px] font-extrabold">
                {formatTon(summary?.total_invested_ton ?? 0)} TON
              </p>
            </div>
            <div>
              <p className="text-[10.5px] text-white/75 font-medium">Різниця</p>
              <p
                className={`text-[14px] sm:text-[15px] font-extrabold ${
                  pnlPositive ? 'text-white' : 'text-white/80'
                }`}
              >
                {pnlPositive ? '+' : ''}
                {formatTon(summary?.unrealized_pnl_ton ?? 0)} (
                {formatPercent(summary?.unrealized_pnl_percent ?? 0)})
              </p>
            </div>
            <div className="text-right lg:text-left">
              <p className="text-[10.5px] text-white/75 font-medium">Під контролем</p>
              <p className="text-[14px] sm:text-[15px] font-extrabold">
                {summary?.undercut_active_count ?? 0} з {items.length} NFT
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={() => {
              haptic('light');
              setShowAddModal(true);
            }}
            className="hidden lg:inline-flex h-10 px-4 rounded-xl bg-white/20 hover:bg-white/30 backdrop-blur-md text-white text-xs font-bold items-center gap-1.5 border border-white/25 cursor-pointer shrink-0"
          >
            <Plus className="w-4 h-4" />
            <span>Додати NFT</span>
          </button>
        </div>
      </section>

      {/* Holdings Grid */}
      {loading && items.length === 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="ton-card rounded-2xl p-4 h-56 animate-pulse" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="ton-card rounded-2xl p-8 text-center max-w-md mx-auto">
          <div className="w-12 h-12 rounded-2xl bg-[#E8F5FE] border border-[#BAE3FC] flex items-center justify-center mx-auto mb-2.5">
            <Briefcase className="w-5 h-5 text-[#0098EA]" />
          </div>
          <p className="text-sm font-bold text-[#0B1120]">Портфель порожній</p>
          <p className="text-xs text-[#64748B] mt-1">
            Купіть NFT зі Сканера або додайте свої подарунки вручну для Auto-Undercut моніторингу.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3 items-start">
          {items.map((item) => {
            const marketMeta = getMarketMeta(item.market);
            const bestSellMeta = getMarketMeta(item.best_sell_market);
            const draft = getDraft(item);
            const isBusy = busyId === item.id;
            const pnlUp = item.pnl_ton >= 0;

            return (
              <div
                key={item.id}
                className={`ton-card rounded-2xl p-3.5 space-y-3 ${
                  item.is_undercut_by_competitor ? 'border-[#0098EA] ring-1 ring-[#BAE3FC]' : ''
                }`}
              >
                {/* Top Info Row */}
                <div className="flex items-start gap-3">
                  <div className="w-14 h-14 rounded-2xl overflow-hidden bg-[#F4F7FB] border border-[#E2E8F0] shrink-0">
                    <NftImage
                      src={item.photo_url}
                      alt={item.collection_name}
                      className="w-full h-full object-cover"
                    />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2">
                      <h3 className="text-[14px] font-extrabold text-[#0B1120] truncate">
                        {item.collection_name}{' '}
                        <span className="text-[#0098EA] tabular-nums">#{item.number}</span>
                      </h3>
                      <button
                        type="button"
                        onClick={() => handleDelete(item)}
                        className="text-[#64748B] hover:text-[#DC2626] p-1 cursor-pointer"
                        title="Видалити з портфеля"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>

                    <div className="flex items-center gap-1.5 mt-1 flex-wrap">
                      <span
                        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-bold border ${marketMeta.bg} ${marketMeta.text} ${marketMeta.border}`}
                      >
                        <span className={`w-1.5 h-1.5 rounded-full ${marketMeta.dot}`} />
                        {marketMeta.label}
                      </span>
                      <span
                        className={`px-2 py-0.5 rounded-md text-[10px] font-extrabold tabular-nums ${
                          pnlUp
                            ? 'bg-[#E8F5FE] text-[#0077C8]'
                            : 'bg-[#F1F5F9] text-[#334155]'
                        }`}
                      >
                        PnL {pnlUp ? '+' : ''}
                        {formatTon(item.pnl_ton)} TON ({formatPercent(item.pnl_percent)})
                      </span>
                    </div>
                  </div>
                </div>

                {/* Prices Comparison */}
                <div className="grid grid-cols-3 gap-1.5 text-center tabular-nums">
                  <div className="rounded-xl bg-[#F8FAFC] border border-[#E2E8F0] py-2 px-1">
                    <p className="text-[10px] text-[#64748B] font-semibold">Куплено</p>
                    <p className="text-[13px] font-extrabold text-[#0B1120]">
                      {formatTon(item.buy_price)} TON
                    </p>
                  </div>
                  <div className="rounded-xl bg-[#E8F5FE]/70 border border-[#BAE3FC] py-2 px-1">
                    <p className="text-[10px] text-[#0077C8] font-semibold">Ваш лістинг</p>
                    <p className="text-[13px] font-extrabold text-[#0098EA]">
                      {item.listed_price ? `${formatTon(item.listed_price)} TON` : 'Холд'}
                    </p>
                  </div>
                  <div className="rounded-xl bg-[#F8FAFC] border border-[#E2E8F0] py-2 px-1">
                    <p className="text-[10px] text-[#64748B] font-semibold">Живий флор</p>
                    <p className="text-[13px] font-extrabold text-[#0B1120]">
                      {formatTon(item.current_floor)} TON
                    </p>
                  </div>
                </div>

                {/* Protective Floor Guard Active Banner */}
                {!item.is_undercut_by_competitor && item.hit_min_guard && (
                  <div className="rounded-2xl p-3 bg-[#E8F5FE] border border-[#BAE3FC] flex items-start gap-2.5">
                    <ShieldCheck className="w-4.5 h-4.5 text-[#0098EA] shrink-0 mt-0.5" />
                    <div className="text-[11.5px] leading-snug">
                      <p className="font-extrabold text-[#0B1120]">
                        Захист мін. ціни спрацював ({formatTon(item.min_price_guard)} TON)
                      </p>
                      <p className="text-[#334155] mt-0.5 tabular-nums">
                        Конкурент нижче вашого ліміту ({formatTon(item.competitor_price ?? item.current_floor)} TON) — продаж у мінус заблоковано.
                      </p>
                    </div>
                  </div>
                )}

                {/* Competitor Undercut Alert */}
                {item.is_undercut_by_competitor && (
                  <div className="rounded-2xl p-3 bg-[#E8F5FE] border border-[#BAE3FC] space-y-2">
                    <div className="flex items-start gap-2">
                      <AlertTriangle className="w-4 h-4 text-[#0098EA] shrink-0 mt-0.5" />
                      <div className="text-[11.5px] leading-snug">
                        <p className="font-extrabold text-[#0B1120]">
                          Конкурент перебив вашу ціну:{' '}
                          <span className="tabular-nums text-[#0077C8]">
                            {formatTon(item.competitor_price ?? item.current_floor)} TON
                          </span>
                          !
                        </p>
                        <p className="text-[#334155] mt-0.5 tabular-nums">
                          Рекомендовано знизити до{' '}
                          <strong className="text-[#0B1120]">
                            {formatTon(
                              item.suggested_price ??
                                Math.max(
                                  item.min_price_guard,
                                  (item.competitor_price ?? item.current_floor) - item.undercut_step,
                                ),
                            )}{' '}
                            TON
                          </strong>
                        </p>
                      </div>
                    </div>

                    <button
                      type="button"
                      disabled={isBusy}
                      onClick={() => handleApplyUndercut(item)}
                      className="w-full h-9 rounded-xl ton-btn-primary text-xs font-extrabold flex items-center justify-center gap-1.5 cursor-pointer disabled:opacity-60"
                    >
                      <Zap className="w-3.5 h-3.5 fill-current" />
                      <span className="tabular-nums">
                        Знизити до{' '}
                        {formatTon(
                          item.suggested_price ??
                            Math.max(
                              item.min_price_guard,
                              (item.competitor_price ?? item.current_floor) - item.undercut_step,
                            ),
                        )}{' '}
                        TON
                      </span>
                    </button>
                  </div>
                )}

                {/* Thin Floor Protection Warning */}
                {item.thin_floor_warning && (
                  <div className="rounded-xl px-3 py-2 bg-[#F8FAFC] border border-[#E2E8F0] flex items-start gap-2">
                    <Flame className="w-4 h-4 text-[#0098EA] shrink-0 mt-0.5" />
                    <p className="text-[11px] font-semibold text-[#0B1120] leading-snug">
                      {item.thin_floor_warning}
                    </p>
                  </div>
                )}

                {/* Best Market to Sell Advisor */}
                {item.best_sell_market && item.best_sell_price > 0 && (
                  <div className="rounded-xl px-3 py-2 bg-[#E8F5FE]/70 border border-[#BAE3FC] flex items-center justify-between text-[11px]">
                    <span className="font-bold text-[#0B1120] inline-flex items-center gap-1.5">
                      <TrendingUp className="w-3.5 h-3.5 text-[#0098EA]" />
                      Вигідніше продати на {bestSellMeta.label}
                    </span>
                    <span className="font-extrabold text-[#0077C8] tabular-nums">
                      ~{formatTon(item.best_sell_price)} TON
                    </span>
                  </div>
                )}

                {/* Smart Auto-Undercut Control Box */}
                <div className="rounded-2xl p-3 bg-[#F4F7FB] border border-[#E2E8F0] space-y-2.5">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5">
                      <ShieldCheck className="w-4 h-4 text-[#0098EA]" />
                      <span className="text-xs font-extrabold text-[#0B1120]">
                        Smart Auto-Undercut
                      </span>
                    </div>

                    <button
                      type="button"
                      disabled={isBusy}
                      onClick={() => handleToggleUndercut(item)}
                      className={`w-10 h-5.5 rounded-full p-0.5 transition-colors cursor-pointer ${
                        item.auto_undercut_enabled ? 'bg-[#0098EA]' : 'bg-[#CBD5E1]'
                      }`}
                    >
                      <span
                        className={`block w-4.5 h-4.5 rounded-full bg-white shadow-sm transition-transform ${
                          item.auto_undercut_enabled ? 'translate-x-4.5' : 'translate-x-0'
                        }`}
                      />
                    </button>
                  </div>

                  {/* Mode Selector */}
                  <div className="grid grid-cols-2 gap-1.5">
                    <button
                      type="button"
                      disabled={isBusy}
                      onClick={() => handleModeChange(item, 'auto')}
                      className={`py-1.5 rounded-xl text-[11px] font-bold border inline-flex items-center justify-center gap-1 cursor-pointer transition-colors ${
                        item.undercut_mode === 'auto'
                          ? 'bg-[#0098EA] text-white border-[#0098EA]'
                          : 'bg-white text-[#0B1120] border-[#E2E8F0]'
                      }`}
                    >
                      <Zap className="w-3 h-3" />
                      <span>Авто (-{item.undercut_step})</span>
                    </button>
                    <button
                      type="button"
                      disabled={isBusy}
                      onClick={() => handleModeChange(item, 'notify')}
                      className={`py-1.5 rounded-xl text-[11px] font-bold border inline-flex items-center justify-center gap-1 cursor-pointer transition-colors ${
                        item.undercut_mode === 'notify'
                          ? 'bg-[#0077C8] text-white border-[#0077C8]'
                          : 'bg-white text-[#0B1120] border-[#E2E8F0]'
                      }`}
                    >
                      <Bell className="w-3 h-3" />
                      <span>Сповіщати в ТГ</span>
                    </button>
                  </div>

                  {/* Guard & Step Inputs */}
                  <div className="grid grid-cols-12 gap-1.5 items-end text-[10.5px]">
                    <div className="col-span-5">
                      <label className="block font-bold text-[#64748B] mb-0.5">
                        Мін. ціна (Захист)
                      </label>
                      <input
                        type="number"
                        step="0.1"
                        value={draft.min_price_guard}
                        onChange={(e) =>
                          updateDraft(item.id, { min_price_guard: e.target.value }, item)
                        }
                        className="w-full h-8 px-2 rounded-lg bg-white border border-[#E2E8F0] font-bold text-[#0B1120] tabular-nums focus:outline-none focus:border-[#0098EA]"
                      />
                    </div>
                    <div className="col-span-4">
                      <label className="block font-bold text-[#64748B] mb-0.5">Крок (TON)</label>
                      <input
                        type="number"
                        step="0.01"
                        value={draft.undercut_step}
                        onChange={(e) =>
                          updateDraft(item.id, { undercut_step: e.target.value }, item)
                        }
                        className="w-full h-8 px-2 rounded-lg bg-white border border-[#E2E8F0] font-bold text-[#0B1120] tabular-nums focus:outline-none focus:border-[#0098EA]"
                      />
                    </div>
                    <div className="col-span-3">
                      <button
                        type="button"
                        disabled={isBusy}
                        onClick={() => handleSaveGuard(item)}
                        className="w-full h-8 rounded-lg bg-[#E8F5FE] hover:bg-[#D4ECFD] border border-[#BAE3FC] text-[#0077C8] font-extrabold inline-flex items-center justify-center gap-0.5 cursor-pointer"
                      >
                        <Check className="w-3.5 h-3.5" />
                        <span>Ок</span>
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* ADD NFT MODAL */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-end md:items-center justify-center md:p-6 bg-[#0B1120]/45 backdrop-blur-[2px] animate-fade-in">
          <div className="absolute inset-0" onClick={() => setShowAddModal(false)} />
          <form
            onSubmit={handleAddItem}
            className="relative z-10 w-full md:max-w-[500px] bg-white rounded-t-[28px] md:rounded-3xl p-4 sm:p-5 space-y-3 animate-sheet-up shadow-2xl border border-[#E2E8F0]"
          >
            <div className="flex items-center justify-between">
              <h3 className="font-display text-base font-extrabold text-[#0B1120]">
                Додати NFT в портфель
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
                  className="w-full h-10 px-3 rounded-xl bg-[#F4F7FB] border border-[#E2E8F0] font-bold focus:outline-none focus:border-[#0098EA]"
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
                    value={newNumber}
                    onChange={(e) => setNewNumber(e.target.value)}
                    className="w-full h-10 px-3 rounded-xl bg-[#F4F7FB] border border-[#E2E8F0] font-bold tabular-nums focus:outline-none focus:border-[#0098EA]"
                  />
                </div>
                <div>
                  <label className="block font-bold text-[#334155] mb-1">Маркет</label>
                  <select
                    value={newMarket}
                    onChange={(e) => setNewMarket(e.target.value)}
                    className="w-full h-10 px-3 rounded-xl bg-[#F4F7FB] border border-[#E2E8F0] font-bold focus:outline-none focus:border-[#0098EA]"
                  >
                    <option value="portals">Portals</option>
                    <option value="getgems">Getgems</option>
                    <option value="mrkt">MRKT</option>
                    <option value="tonnel">Tonnel</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-3 gap-2">
                <div>
                  <label className="block font-bold text-[#334155] mb-1">Купівля (TON)</label>
                  <input
                    type="number"
                    step="0.1"
                    required
                    value={newBuyPrice}
                    onChange={(e) => setNewBuyPrice(e.target.value)}
                    className="w-full h-10 px-2.5 rounded-xl bg-[#F4F7FB] border border-[#E2E8F0] font-bold tabular-nums focus:outline-none focus:border-[#0098EA]"
                  />
                </div>
                <div>
                  <label className="block font-bold text-[#334155] mb-1">Лістинг (TON)</label>
                  <input
                    type="number"
                    step="0.1"
                    value={newListedPrice}
                    onChange={(e) => setNewListedPrice(e.target.value)}
                    className="w-full h-10 px-2.5 rounded-xl bg-[#F4F7FB] border border-[#E2E8F0] font-bold tabular-nums focus:outline-none focus:border-[#0098EA]"
                  />
                </div>
                <div>
                  <label className="block font-bold text-[#334155] mb-1">Захист (TON)</label>
                  <input
                    type="number"
                    step="0.1"
                    value={newMinGuard}
                    onChange={(e) => setNewMinGuard(e.target.value)}
                    className="w-full h-10 px-2.5 rounded-xl bg-[#F4F7FB] border border-[#E2E8F0] font-bold tabular-nums focus:outline-none focus:border-[#0098EA]"
                  />
                </div>
              </div>
            </div>

            <button
              type="submit"
              disabled={savingNew}
              className="w-full ton-btn-primary h-11 rounded-xl font-bold text-sm cursor-pointer disabled:opacity-60"
            >
              {savingNew ? 'Додавання...' : 'Додати в портфель'}
            </button>
          </form>
        </div>
      )}
    </div>
  );
};
