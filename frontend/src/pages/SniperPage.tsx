import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Bell,
  Copy,
  Crosshair,
  ExternalLink,
  Loader2,
  Plus,
  RefreshCw,
  Search,
  Sparkles,
  Trash2,
  TrendingUp,
  X,
  Zap,
} from 'lucide-react';
import { api } from '../api/client';
import type {
  AnalyzedListing,
  CollectionSummary,
  CreateSniperRulePayload,
  OfferRadarItem,
  SniperRule,
  UserOffer,
  VisualTwinsResponse,
} from '../types/api';
import {
  formatTon,
  getMarketMeta,
  haptic,
  openExternalLink,
} from '../utils/format';
import { NftCard } from '../components/NftCard';
import { NftImage } from '../components/NftImage';

export interface TwinsSeed {
  query: string;
  collection?: string;
  model?: string;
  backdrop?: string;
  symbol?: string;
  nonce: number;
}

interface SniperPageProps {
  collections: CollectionSummary[];
  tonUsd: number;
  refreshTick: number;
  initialTwinsSeed?: TwinsSeed | null;
  onSelectListing: (item: AnalyzedListing) => void;
  onNotify: (title: string, message?: string, variant?: 'info' | 'success' | 'warning' | 'error') => void;
}

type SubTab = 'rules' | 'offers' | 'twins';
type TwinsSort = 'similarity' | 'price_asc' | 'discount_desc';

const ALL_MARKETS = ['portals', 'getgems', 'mrkt', 'tonnel'];
const TWINS_MARKETS = [
  { key: 'all', label: 'Всі' },
  { key: 'portals', label: 'Portals' },
  { key: 'mrkt', label: 'MRKT' },
  { key: 'tonnel', label: 'Tonnel' },
  { key: 'getgems', label: 'Getgems' },
  { key: 'fragment', label: 'Fragment' },
];
const QUICK_TWINS_EXAMPLES = [
  'Eternal Rose #3497',
  'Plush Pepe',
  'Homemade Cake Sweet Bite',
  'B-Day Candle Neon Lights',
];

function getMarketCollectionUrl(
  market?: string,
  shortName?: string,
  collectionName?: string,
  explicitUrl?: string,
): string {
  if (explicitUrl) return explicitUrl;
  const m = (market || 'portals').toLowerCase();
  const query = encodeURIComponent(collectionName || shortName || '');
  if (m === 'getgems') {
    return `https://getgems.io/search?q=${query}`;
  }
  if (m === 'mrkt') {
    return 'https://t.me/mrkt/app';
  }
  if (m === 'tonnel') {
    return 'https://t.me/tonnel_network_bot/gift';
  }
  if (m === 'fragment') {
    return `https://fragment.com/gifts?query=${query}`;
  }
  return 'https://t.me/portals_market_bot/market';
}

export const SniperPage: React.FC<SniperPageProps> = ({
  collections,
  tonUsd,
  refreshTick,
  initialTwinsSeed,
  onSelectListing,
  onNotify,
}) => {
  const [subTab, setSubTab] = useState<SubTab>(() => (initialTwinsSeed ? 'twins' : 'rules'));

  // Data
  const [rules, setRules] = useState<SniperRule[]>([]);
  const [offers, setOffers] = useState<UserOffer[]>([]);
  const [radar, setRadar] = useState<OfferRadarItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshingRadar, setRefreshingRadar] = useState(false);

  // Visual 1:1 Twins Finder
  const [twinsQuery, setTwinsQuery] = useState<string>('');
  const [twinsSort, setTwinsSort] = useState<TwinsSort>('similarity');
  const [twinsMarket, setTwinsMarket] = useState<string>('all');
  const [twinsLoading, setTwinsLoading] = useState<boolean>(false);
  const [twinsError, setTwinsError] = useState<string>('');
  const [twinsResult, setTwinsResult] = useState<VisualTwinsResponse | null>(null);
  const [lastTwinsParams, setLastTwinsParams] = useState<{
    query?: string;
    collection?: string;
    model?: string;
    backdrop?: string;
    symbol?: string;
  } | null>(null);

  // Create Rule Modal
  const [showRuleModal, setShowRuleModal] = useState(false);
  const [savingRule, setSavingRule] = useState(false);
  const [ruleForm, setRuleForm] = useState<CreateSniperRulePayload>({
    name: '',
    collection_short_name: '',
    collection_name: 'Всі колекції',
    model_filter: '',
    backdrop_filter: '',
    max_price: 50,
    min_discount_percent: 15,
    rare_combo_only: false,
    markets: ['portals', 'getgems', 'mrkt', 'tonnel'],
    mode: 'alert',
    enabled: true,
  });

  // Create Offer Modal
  const [offerTarget, setOfferTarget] = useState<OfferRadarItem | null>(null);
  const [offerBid, setOfferBid] = useState('25');
  const [offerMaxBid, setOfferMaxBid] = useState('28');
  const [offerMarket, setOfferMarket] = useState('portals');
  const [offerAutoOutbid, setOfferAutoOutbid] = useState(true);
  const [savingOffer, setSavingOffer] = useState(false);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [rulesRes, offersRes] = await Promise.all([
        api.getSniperRules().catch(() => ({ rules: [] })),
        api.getOffers().catch(() => ({ offers: [], radar: [] })),
      ]);
      setRules(rulesRes.rules || []);
      setOffers(offersRes.offers || []);
      setRadar(offersRes.radar || []);
    } finally {
      setLoading(false);
    }
  }, []);

  const runTwinsSearch = useCallback(
    async (
      params: {
        query?: string;
        collection?: string;
        model?: string;
        backdrop?: string;
        symbol?: string;
      },
      sortOverride?: TwinsSort,
    ) => {
      const q = (params.query || '').trim();
      if (!q && !params.collection && !params.model) {
        onNotify('Введіть подарунок для пошуку', 'Посилання, назва + номер або модель', 'warning');
        return;
      }
      setTwinsLoading(true);
      setTwinsError('');
      setLastTwinsParams(params);
      try {
        const res = await api.searchVisualTwins({
          ...params,
          query: q,
          sort: sortOverride || twinsSort,
          limit: 60,
        });
        setTwinsResult(res);
        setTwinsMarket('all');
      } catch (err) {
        const msg =
          err instanceof Error
            ? err.message
            : 'Не вдалося знайти подарунок або двійників. Спробуйте інший запит.';
        setTwinsError(msg);
        setTwinsResult(null);
      } finally {
        setTwinsLoading(false);
      }
    },
    [onNotify, twinsSort],
  );

  useEffect(() => {
    if (!initialTwinsSeed) return;
    setSubTab('twins');
    setTwinsQuery(initialTwinsSeed.query);
    runTwinsSearch(
      {
        query: initialTwinsSeed.query,
        collection: initialTwinsSeed.collection,
        model: initialTwinsSeed.model,
        backdrop: initialTwinsSeed.backdrop,
        symbol: initialTwinsSeed.symbol,
      },
      'similarity',
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialTwinsSeed?.nonce]);

  useEffect(() => {
    loadAll();
  }, [loadAll, refreshTick]);

  const handleToggleRule = async (rule: SniperRule) => {
    haptic('light');
    const next = !rule.enabled;
    setRules((prev) =>
      prev.map((r) => (String(r.id) === String(rule.id) ? { ...r, enabled: next } : r)),
    );
    try {
      const res = await api.updateSniperRule(rule.id, { enabled: next });
      const serverRule =
        res?.rule || (res && 'id' in res && res.id !== undefined ? (res as SniperRule) : null);
      setRules((prev) =>
        prev.map((r) =>
          String(r.id) === String(rule.id)
            ? serverRule
              ? { ...r, ...serverRule, enabled: next }
              : { ...r, enabled: next }
            : r,
        ),
      );
      onNotify(
        next ? 'Правило активовано' : 'Правило призупинено',
        rule.name,
        next ? 'success' : 'info',
      );
    } catch {
      setRules((prev) =>
        prev.map((r) => (String(r.id) === String(rule.id) ? { ...r, enabled: !next } : r)),
      );
      onNotify('Помилка оновлення правила', undefined, 'error');
    }
  };

  const handleDeleteRule = async (rule: SniperRule) => {
    haptic('warning');
    try {
      await api.deleteSniperRule(rule.id);
      setRules((prev) => prev.filter((r) => String(r.id) !== String(rule.id)));
      onNotify('Правило видалено', rule.name, 'info');
    } catch (err) {
      onNotify('Не вдалося видалити правило', err instanceof Error ? err.message : '', 'error');
    }
  };

  const handleCreateRule = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ruleForm.name.trim()) {
      onNotify('Вкажіть назву правила', undefined, 'warning');
      return;
    }
    setSavingRule(true);
    try {
      const res = await api.createSniperRule(ruleForm);
      const createdRule =
        res?.rule || (res && 'id' in res && res.id !== undefined ? (res as SniperRule) : null);
      if (createdRule && createdRule.id !== undefined) {
        setRules((prev) => [
          createdRule,
          ...prev.filter((r) => String(r.id) !== String(createdRule.id)),
        ]);
      } else {
        const fresh = await api.getSniperRules().catch(() => ({ rules: [] }));
        setRules(fresh.rules || []);
      }
      setShowRuleModal(false);
      setRuleForm({
        name: '',
        collection_short_name: '',
        collection_name: 'Всі колекції',
        model_filter: '',
        backdrop_filter: '',
        max_price: 50,
        min_discount_percent: 15,
        rare_combo_only: false,
        markets: ['portals', 'getgems', 'mrkt', 'tonnel'],
        mode: 'alert',
        enabled: true,
      });
      onNotify('Нове правило створено', 'Снайпер почав моніторинг маркетів', 'success');
    } catch (err) {
      onNotify('Помилка створення правила', err instanceof Error ? err.message : '', 'error');
    } finally {
      setSavingRule(false);
    }
  };

  const toggleRuleMarket = (m: string) => {
    setRuleForm((prev) => {
      const exists = prev.markets.includes(m);
      const next = exists
        ? prev.markets.filter((x) => x !== m)
        : [...prev.markets, m];
      return { ...prev, markets: next.length > 0 ? next : [m] };
    });
  };

  const handleRefreshRadar = async () => {
    haptic('light');
    setRefreshingRadar(true);
    try {
      const offersRes = await api.getOffers();
      setOffers(offersRes.offers || []);
      setRadar(offersRes.radar || []);
      onNotify('Радар оферів оновлено', 'Актуальні Bid-Ask спреди завантажено', 'info');
    } catch {
      onNotify('Не вдалося оновити радар', undefined, 'error');
    } finally {
      setRefreshingRadar(false);
    }
  };

  const handleSelectRadarItem = async (item: OfferRadarItem) => {
    haptic('light');
    if (item.sample_listing) {
      onSelectListing(item.sample_listing);
      return;
    }
    try {
      const query = item.collection_name || item.collection_short_name || item.short_name || '';
      const res = await api.runXRay(query);
      if (res?.item) {
        onSelectListing(res.item);
      }
    } catch {
      onNotify('Не вдалося завантажити деталі лота', item.collection_name, 'warning');
    }
  };

  const openOfferModal = (item: OfferRadarItem) => {
    haptic('light');
    const suggestedBid =
      item.suggested_offer ??
      item.recommended_bid ??
      Number(((item.best_offer || item.floor_price * 0.85 || 1) + 0.1).toFixed(2));
    setOfferTarget(item);
    setOfferBid(suggestedBid.toFixed(2));
    setOfferMaxBid((suggestedBid * 1.1).toFixed(2));
    setOfferMarket(item.market || 'portals');
    setOfferAutoOutbid(true);
  };

  const handleCreateOffer = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!offerTarget) return;
    setSavingOffer(true);
    const shortName =
      offerTarget.collection_short_name ||
      offerTarget.short_name ||
      offerTarget.collection_name.toLowerCase().replace(/[^a-z0-9]/g, '');
    try {
      await api.createOffer({
        collection_short_name: shortName,
        collection_name: offerTarget.collection_name,
        market: offerMarket,
        bid_price: Number(offerBid),
        max_bid: Number(offerMaxBid),
        auto_outbid: offerAutoOutbid,
      });
      setOfferTarget(null);
      await loadAll();
      onNotify(
        'Офер розміщено!',
        `${offerTarget.collection_name} · ${offerBid} TON`,
        'success',
      );
    } catch (err) {
      onNotify('Помилка розміщення офера', err instanceof Error ? err.message : '', 'error');
    } finally {
      setSavingOffer(false);
    }
  };

  const handleOutbid = async (offer: UserOffer) => {
    haptic('medium');
    try {
      const res = await api.outbidOffer(offer.id, 0.1);
      await loadAll();
      onNotify(
        'Ставку підвищено на +0.1 TON',
        res.message || `${offer.collection_name}`,
        'success',
      );
    } catch (err) {
      onNotify('Не вдалося перебити офер', err instanceof Error ? err.message : '', 'error');
    }
  };

  const handleDeleteOffer = async (offer: UserOffer) => {
    haptic('light');
    try {
      await api.deleteOffer(offer.id);
      setOffers((prev) => prev.filter((o) => o.id !== offer.id));
      onNotify('Офер скасовано', offer.collection_name, 'info');
    } catch (err) {
      onNotify('Помилка скасування', err instanceof Error ? err.message : '', 'error');
    }
  };

  const filteredTwins = useMemo(() => {
    const list = twinsResult?.items || [];
    const byMarket =
      twinsMarket === 'all'
        ? list
        : list.filter((it) => (it.market || '').toLowerCase() === twinsMarket);
    const copy = [...byMarket];
    if (twinsSort === 'price_asc') {
      copy.sort((a, b) => a.price - b.price || (b.similarity_percent ?? 0) - (a.similarity_percent ?? 0));
    } else if (twinsSort === 'discount_desc') {
      copy.sort(
        (a, b) =>
          b.discount_percent - a.discount_percent ||
          (b.similarity_percent ?? 0) - (a.similarity_percent ?? 0),
      );
    } else {
      copy.sort((a, b) => (b.similarity_percent ?? 0) - (a.similarity_percent ?? 0) || a.price - b.price);
    }
    return copy;
  }, [twinsResult, twinsMarket, twinsSort]);

  return (
    <div className="space-y-4 pb-4">
      {/* Segmented Sub-tabs */}
      <div className="ton-card rounded-2xl p-1 grid grid-cols-3 gap-1 max-w-xl">
        {(
          [
            ['rules', 'Правила', rules.filter((r) => r.enabled).length, Crosshair],
            ['offers', 'Офери', offers.length, Zap],
            ['twins', 'Двійники', twinsResult?.total ?? 0, Copy],
          ] as const
        ).map(([key, label, count, Icon]) => {
          const active = subTab === key;
          return (
            <button
              key={key}
              type="button"
              onClick={() => {
                haptic('light');
                setSubTab(key);
              }}
              className={`py-2 px-2 rounded-xl text-[11.5px] font-extrabold transition-all flex items-center justify-center gap-1.5 cursor-pointer ${
                active
                  ? 'ton-btn-primary text-white'
                  : 'text-[#0B1120] hover:bg-[#F4F7FB]'
              }`}
            >
              <Icon className="w-3.5 h-3.5 shrink-0" />
              <span>{label}</span>
              {count > 0 && (
                <span
                  className={`px-1.5 py-0.2 rounded-full text-[10px] tabular-nums ${
                    active ? 'bg-white/25 text-white' : 'bg-[#E8F5FE] text-[#0077C8]'
                  }`}
                >
                  {count}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* TAB 1: SNIPER RULES */}
      {subTab === 'rules' && (
        <div className="space-y-3">
          <div className="flex items-center justify-between px-0.5">
            <div>
              <h2 className="font-display text-[15px] font-extrabold text-[#0B1120]">
                Правила Снайпера
              </h2>
              <p className="text-[11px] text-[#64748B]">
                Миттєвий пошук недооцінених лотів, візуальних комбо та автобай
              </p>
            </div>
            <button
              type="button"
              onClick={() => {
                haptic('light');
                setShowRuleModal(true);
              }}
              className="ton-btn-primary h-9 px-3.5 rounded-xl text-xs font-bold inline-flex items-center gap-1 cursor-pointer shrink-0"
            >
              <Plus className="w-4 h-4" />
              <span>Нове правило</span>
            </button>
          </div>

          {loading ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="ton-card rounded-2xl p-4 h-32 animate-pulse bg-white" />
              ))}
            </div>
          ) : rules.length === 0 ? (
            <div className="ton-card rounded-2xl p-8 text-center max-w-md mx-auto">
              <div className="w-11 h-11 rounded-2xl bg-[#E8F5FE] border border-[#BAE3FC] flex items-center justify-center mx-auto mb-2">
                <Crosshair className="w-5 h-5 text-[#0098EA]" />
              </div>
              <p className="text-sm font-bold text-[#0B1120]">Ще немає правил снайпера</p>
              <p className="text-xs text-[#64748B] mt-1">
                Створіть правило, щоб отримувати миттєві картки в Telegram або активувати Автобай.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {rules.map((rule) => (
                <div
                  key={rule.id}
                  className={`ton-card rounded-2xl p-3.5 flex flex-col justify-between transition-opacity ${
                    rule.enabled ? 'opacity-100' : 'opacity-65'
                  }`}
                >
                  <div>
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <h3 className="text-[13.5px] font-extrabold text-[#0B1120] truncate">
                            {rule.name}
                          </h3>
                          <span
                            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-lg text-[10px] font-extrabold border ${
                              rule.mode === 'autobuy'
                                ? 'bg-[#0077C8] text-white border-[#0077C8]'
                                : 'bg-[#E8F5FE] text-[#0077C8] border-[#BAE3FC]'
                            }`}
                          >
                            {rule.mode === 'autobuy' ? (
                              <>
                                <Zap className="w-2.5 h-2.5" />
                                Автобай
                              </>
                            ) : (
                              <>
                                <Bell className="w-2.5 h-2.5" />
                                Алерт в ТГ
                              </>
                            )}
                          </span>
                        </div>
                        <p className="text-[11.5px] font-semibold text-[#334155] mt-1">
                          {rule.collection_name || 'Всі колекції'}
                          {rule.model_filter ? ` · Модель: ${rule.model_filter}` : ''}
                          {rule.backdrop_filter ? ` · Фон: ${rule.backdrop_filter}` : ''}
                        </p>
                      </div>

                      {/* ON/OFF Switch */}
                      <button
                        type="button"
                        onClick={() => handleToggleRule(rule)}
                        className={`w-11 h-6 rounded-full p-0.5 transition-colors cursor-pointer shrink-0 ${
                          rule.enabled ? 'bg-[#0098EA]' : 'bg-[#CBD5E1]'
                        }`}
                      >
                        <span
                          className={`block w-5 h-5 rounded-full bg-white shadow-sm transition-transform ${
                            rule.enabled ? 'translate-x-5' : 'translate-x-0'
                          }`}
                        />
                      </button>
                    </div>

                    {/* Conditions Row */}
                    <div className="flex flex-wrap items-center gap-1.5 mt-2.5 text-[10.5px] tabular-nums">
                      <span className="px-2 py-0.5 rounded-lg bg-[#E8F5FE] text-[#0077C8] border border-[#BAE3FC] font-bold">
                        Дисконт ≥ {rule.min_discount_percent}%
                      </span>
                      {rule.max_price && (
                        <span className="px-2 py-0.5 rounded-lg bg-[#F8FAFC] text-[#0B1120] font-bold border border-[#E2E8F0]">
                          До {formatTon(rule.max_price, 1)} TON
                        </span>
                      )}
                      {rule.rare_combo_only && (
                        <span className="inline-flex items-center gap-0.5 px-2 py-0.5 rounded-lg bg-[#E8F5FE] text-[#0077C8] font-bold border border-[#BAE3FC]">
                          <Sparkles className="w-3 h-3" />
                          Тільки Комбо
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Markets + Delete */}
                  <div className="flex items-center justify-between mt-3 pt-2.5 border-t border-[#F1F5F9]">
                    <div className="flex items-center gap-1 flex-wrap">
                      {(rule.markets || []).map((m) => {
                        const meta = getMarketMeta(m);
                        return (
                          <span
                            key={m}
                            className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded border text-[9.5px] font-bold ${meta.bg} ${meta.text} ${meta.border}`}
                          >
                            <span className={`w-1.5 h-1.5 rounded-full ${meta.dot}`} />
                            {meta.label}
                          </span>
                        );
                      })}
                    </div>

                    <button
                      type="button"
                      onClick={() => handleDeleteRule(rule)}
                      className="p-1.5 rounded-lg text-[#64748B] hover:text-[#DC2626] hover:bg-[#FEF2F2] transition-colors cursor-pointer"
                      title="Видалити правило"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* TAB 2: OFFER RADAR & MY OFFERS */}
      {subTab === 'offers' && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
          {/* Active User Offers */}
          <section className="lg:col-span-5 space-y-2.5">
            <h2 className="font-display text-[14px] font-extrabold text-[#0B1120] px-0.5">
              Мої активні офери ({offers.length})
            </h2>
            {offers.length === 0 ? (
              <div className="ton-card rounded-2xl p-5 text-center text-xs text-[#64748B]">
                У вас поки немає активних оферів. Оберіть колекцію з найширшим Bid-Ask спредом у Радарі Оферів.
              </div>
            ) : (
              <div className="space-y-2.5">
                {offers.map((offer) => {
                  const mMeta = getMarketMeta(offer.market);
                  const marketUrl = getMarketCollectionUrl(
                    offer.market,
                    offer.collection_short_name,
                    offer.collection_name,
                    offer.market_url,
                  );
                  return (
                    <div key={offer.id} className="ton-card rounded-2xl p-3 space-y-2.5">
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-2.5 min-w-0">
                          <div className="w-10 h-10 rounded-xl overflow-hidden bg-[#F4F7FB] border border-[#E2E8F0] shrink-0">
                            <NftImage
                              src={offer.photo_url}
                              alt={offer.collection_name}
                              collectionName={offer.collection_name}
                              shortName={offer.collection_short_name}
                              className="w-full h-full object-cover"
                            />
                          </div>
                          <div className="min-w-0">
                            <div className="flex items-center gap-1.5">
                              <p className="text-[13px] font-extrabold text-[#0B1120] truncate">
                                {offer.collection_name}
                              </p>
                              <span
                                className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded border text-[9.5px] font-bold ${mMeta.bg} ${mMeta.text} ${mMeta.border}`}
                              >
                                <span className={`w-1.5 h-1.5 rounded-full ${mMeta.dot}`} />
                                {mMeta.label}
                              </span>
                            </div>
                            <p className="text-[11px] text-[#64748B] tabular-nums">
                              Ваш офер:{' '}
                              <strong className="text-[#0098EA]">
                                {formatTon(offer.bid_price)} TON
                              </strong>{' '}
                              · Макс: {formatTon(offer.max_bid)} TON
                            </p>
                          </div>
                        </div>
                        <span
                          className={`px-2 py-0.5 rounded-lg text-[10px] font-bold shrink-0 border ${
                            offer.status === 'outbid'
                              ? 'bg-[#FEF2F2] text-[#DC2626] border-[#FECACA]'
                              : 'bg-[#E8F5FE] text-[#0077C8] border-[#BAE3FC]'
                          }`}
                        >
                          {offer.status === 'outbid' ? 'Перебито' : 'Топ-1'}
                        </span>
                      </div>

                      <div className="flex items-center gap-1.5">
                        <button
                          type="button"
                          onClick={() => handleOutbid(offer)}
                          className="flex-1 h-9 rounded-xl bg-[#E8F5FE] hover:bg-[#D4ECFD] border border-[#BAE3FC] text-[#0077C8] text-[11px] font-extrabold inline-flex items-center justify-center gap-1 cursor-pointer"
                        >
                          <Zap className="w-3.5 h-3.5" />
                          <span>Перебити +0.1 TON</span>
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            haptic('light');
                            openExternalLink(marketUrl);
                          }}
                          className="h-9 px-2.5 rounded-xl bg-[#F8FAFC] hover:bg-[#E8F5FE] border border-[#E2E8F0] hover:border-[#BAE3FC] text-[#0B1120] hover:text-[#0077C8] text-[11px] font-bold inline-flex items-center gap-1 transition-colors cursor-pointer"
                        >
                          <span>На маркет</span>
                          <ExternalLink className="w-3 h-3" />
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDeleteOffer(offer)}
                          className="h-9 px-2.5 rounded-xl bg-[#F8FAFC] hover:bg-[#FEF2F2] border border-[#E2E8F0] hover:border-[#FECACA] text-[#334155] hover:text-[#DC2626] text-[11px] font-bold cursor-pointer transition-colors"
                        >
                          Скасувати
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </section>

          {/* Bid-Ask Spread Offer Radar */}
          <section className="lg:col-span-7 space-y-2.5">
            <div className="flex items-center justify-between gap-2 px-0.5">
              <div>
                <h2 className="font-display text-[14px] font-extrabold text-[#0B1120]">
                  Радар Оферів (Найкращі Bid-Ask Спреди)
                </h2>
                <p className="text-[11px] text-[#64748B]">
                  Натисніть на колекцію для X-Ray аналізу NFT або кнопку «Офер» для виставлення біду
                </p>
              </div>
              <button
                type="button"
                disabled={refreshingRadar}
                onClick={handleRefreshRadar}
                className="h-8 px-2.5 rounded-xl bg-[#E8F5FE] hover:bg-[#D4ECFD] border border-[#BAE3FC] text-[#0077C8] text-[11px] font-bold inline-flex items-center gap-1.5 shrink-0 cursor-pointer disabled:opacity-60"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${refreshingRadar ? 'animate-spin' : ''}`} />
                <span>Оновити радар</span>
              </button>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
              {radar.map((item) => {
                const shortName = item.collection_short_name || item.short_name || item.collection_name;
                const suggestedBid =
                  item.suggested_offer ??
                  item.recommended_bid ??
                  Number(((item.best_offer || 0) + 0.1).toFixed(2));
                const spreadPct = Number(item.bid_ask_spread_percent ?? 0);
                const estProfit = item.est_net_profit_ton ?? item.est_profit_ton;

                return (
                  <div
                    key={shortName}
                    onClick={() => handleSelectRadarItem(item)}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        handleSelectRadarItem(item);
                      }
                    }}
                    className="ton-card ton-card-hover rounded-2xl p-3 flex items-center justify-between gap-2.5 cursor-pointer text-left"
                  >
                    <div className="flex items-center gap-2.5 min-w-0 flex-1">
                      <div className="w-11 h-11 rounded-xl overflow-hidden bg-[#F4F7FB] border border-[#E2E8F0] shrink-0">
                        <NftImage
                          src={item.photo_url || item.sample_listing?.photo_url}
                          alt={item.collection_name}
                          collectionName={item.collection_name}
                          shortName={shortName}
                          modelName={item.sample_listing?.attributes?.find((a) => a.type === 'model')?.value}
                          backdropName={item.sample_listing?.attributes?.find((a) => a.type === 'backdrop')?.value}
                          symbolName={item.sample_listing?.attributes?.find((a) => a.type === 'symbol')?.value}
                          className="w-full h-full object-cover"
                        />
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="text-[12.5px] font-extrabold text-[#0B1120] truncate">
                          {item.collection_name}
                          {item.sample_listing?.number ? (
                            <span className="text-[#64748B] font-bold">
                              {' '}#{item.sample_listing.number}
                            </span>
                          ) : null}
                        </p>
                        <div className="flex items-center gap-1.5 text-[10.5px] text-[#64748B] tabular-nums mt-0.5 flex-wrap">
                          <span>Флор: {formatTon(item.floor_price)}</span>
                          <span>·</span>
                          <span>Офер: {formatTon(item.best_offer)}</span>
                          <span>·</span>
                          <span className="text-[#0077C8] font-bold">
                            Рек: {formatTon(suggestedBid)}
                          </span>
                        </div>
                        <div className="flex items-center gap-1 mt-1 flex-wrap">
                          <span className="inline-block px-1.5 py-0.5 rounded bg-[#E8F5FE] text-[#0077C8] border border-[#BAE3FC] text-[10px] font-extrabold tabular-nums">
                            Спред {spreadPct.toFixed(1)}% · Лікв. {item.liquidity_score}
                          </span>
                          {typeof estProfit === 'number' && estProfit > 0 && (
                            <span className="inline-block px-1.5 py-0.5 rounded bg-[#F0F8FF] text-[#0098EA] border border-[#BAE3FC] text-[10px] font-extrabold tabular-nums">
                              +{formatTon(estProfit)} TON
                            </span>
                          )}
                        </div>
                      </div>
                    </div>

                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        openOfferModal(item);
                      }}
                      className="ton-btn-primary h-9 px-3 rounded-xl text-[11px] font-bold shrink-0 cursor-pointer"
                    >
                      Офер
                    </button>
                  </div>
                );
              })}
            </div>
          </section>
        </div>
      )}

      {/* TAB 3: VISUAL 1:1 TWINS FINDER (SAME CARD GRID & DRAWER AS SCANNER) */}
      {subTab === 'twins' && (
        <div className="space-y-3.5">
          {/* Universal Gift Input Card */}
          <section className="ton-card rounded-2xl p-3.5 sm:p-4 space-y-3">
            <div>
              <h2 className="font-display text-[15px] font-extrabold text-[#0B1120] flex items-center gap-1.5">
                <Copy className="w-4 h-4 text-[#0098EA]" />
                Пошук двійників 1:1 по вигляду
              </h2>
              <p className="text-[11.5px] text-[#64748B] mt-0.5">
                Вставте посилання (t.me/nft/..., Fragment, Getgems), назву + номер або модель — знайдемо сам подарунок і всіх його візуальних двійників на всіх 5 маркетах
              </p>
            </div>

            <form
              onSubmit={(e) => {
                e.preventDefault();
                haptic('light');
                runTwinsSearch({ query: twinsQuery });
              }}
              className="flex items-center gap-2"
            >
              <div className="relative flex-1 min-w-0">
                <Search className="w-4 h-4 text-[#64748B] absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
                <input
                  type="text"
                  value={twinsQuery}
                  onChange={(e) => setTwinsQuery(e.target.value)}
                  placeholder="Напр.: t.me/nft/EternalRose-3497 або Plush Pepe #123..."
                  className="w-full h-10 pl-9 pr-8 rounded-xl bg-[#F4F7FB] border border-[#E2E8F0] focus:border-[#0098EA] focus:bg-white text-xs font-semibold text-[#0B1120] placeholder:text-[#94A3B8] focus:outline-none transition-colors"
                />
                {twinsQuery && (
                  <button
                    type="button"
                    onClick={() => setTwinsQuery('')}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[#94A3B8] hover:text-[#334155] cursor-pointer"
                    aria-label="Очистити"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
              <button
                type="submit"
                disabled={twinsLoading}
                className="ton-btn-primary h-10 px-4 rounded-xl text-xs font-extrabold inline-flex items-center gap-1.5 shrink-0 cursor-pointer disabled:opacity-60"
              >
                {twinsLoading ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>Пошук...</span>
                  </>
                ) : (
                  <>
                    <Search className="w-3.5 h-3.5" />
                    <span>Знайти</span>
                  </>
                )}
              </button>
            </form>

            {/* Quick Example Chips */}
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="text-[10.5px] font-bold text-[#64748B]">Приклади:</span>
              {QUICK_TWINS_EXAMPLES.map((ex) => (
                <button
                  key={ex}
                  type="button"
                  onClick={() => {
                    haptic('light');
                    setTwinsQuery(ex);
                    runTwinsSearch({ query: ex });
                  }}
                  className="px-2.5 py-1 rounded-lg bg-[#F4F7FB] hover:bg-[#E8F5FE] border border-[#E2E8F0] hover:border-[#BAE3FC] text-[10.5px] font-bold text-[#334155] hover:text-[#0077C8] transition-colors cursor-pointer"
                >
                  {ex}
                </button>
              ))}
            </div>
          </section>

          {/* Error Banner */}
          {twinsError && (
            <div className="ton-card rounded-2xl p-4 border-[#FECACA] bg-[#FEF2F2]/60 text-xs font-bold text-[#B91C1C]">
              {twinsError}
            </div>
          )}

          {/* Loading Skeleton — Matches Scanner Grid */}
          {twinsLoading && (
            <div className="space-y-3">
              <div className="ton-card rounded-2xl p-4 animate-pulse space-y-2">
                <div className="h-4 bg-[#E2E8F0] rounded w-1/3" />
                <div className="h-3 bg-[#F1F5F9] rounded w-2/3" />
              </div>
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
            </div>
          )}

          {/* Empty State before first search */}
          {!twinsLoading && !twinsResult && !twinsError && (
            <div className="ton-card rounded-2xl p-7 text-center max-w-lg mx-auto space-y-2">
              <div className="w-12 h-12 rounded-2xl bg-[#E8F5FE] border border-[#BAE3FC] flex items-center justify-center mx-auto">
                <Copy className="w-5 h-5 text-[#0098EA]" />
              </div>
              <p className="text-sm font-extrabold text-[#0B1120]">
                Знайдіть двійників будь-якого подарунка 1 в 1
              </p>
              <p className="text-xs text-[#64748B] leading-relaxed">
                Введіть назву, номер, модель або посилання на NFT вище — GiftKit просканує Portals, MRKT, Tonnel, Getgems і Fragment, покаже попит та всі найсхожіші лоти по вигляду.
              </p>
            </div>
          )}

          {/* Results: Target Gift + Demand Pulse + Scanner-Identical Twins Grid */}
          {!twinsLoading && twinsResult && (
            <div className="space-y-3.5">
              {/* Target NFT + Demand Pulse Row */}
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-3">
                {/* Resolved Target Gift Card (clickable -> opens exact same NftDetailDrawer!) */}
                <button
                  type="button"
                  onClick={() => {
                    haptic('light');
                    onSelectListing(twinsResult.target);
                  }}
                  className="lg:col-span-5 ton-card ton-card-hover rounded-2xl p-3 flex items-center gap-3 text-left cursor-pointer border-[#BAE3FC] bg-gradient-to-br from-white to-[#F4F9FF]"
                >
                  <div className="w-20 h-20 rounded-2xl overflow-hidden bg-[#F4F7FB] border border-[#E2E8F0] shrink-0">
                    <NftImage
                      src={twinsResult.target.photo_url}
                      alt={`${twinsResult.target.collection_name} #${twinsResult.target.number}`}
                      collectionName={twinsResult.target.collection_name}
                      shortName={twinsResult.target.short_name}
                      modelName={twinsResult.target_traits.model}
                      backdropName={twinsResult.target_traits.backdrop}
                      symbolName={twinsResult.target_traits.symbol}
                      className="w-full h-full object-cover"
                    />
                  </div>
                  <div className="min-w-0 flex-1 space-y-1">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className="px-1.5 py-0.5 rounded-md bg-[#0098EA] text-white text-[9.5px] font-extrabold">
                        ОРИГІНАЛ
                      </span>
                      <span className="text-[10.5px] font-bold text-[#64748B] tabular-nums">
                        {formatTon(twinsResult.target.price)} TON
                      </span>
                    </div>
                    <h3 className="font-display text-[15px] font-extrabold text-[#0B1120] truncate">
                      {twinsResult.target.collection_name}{' '}
                      <span className="text-[#0098EA] tabular-nums">
                        #{twinsResult.target.number}
                      </span>
                    </h3>
                    <div className="flex items-center gap-1 flex-wrap">
                      {twinsResult.target_traits.model && (
                        <span className="px-1.5 py-0.5 rounded-md bg-[#E8F5FE] text-[#0077C8] text-[10px] font-bold truncate max-w-full">
                          {twinsResult.target_traits.model}
                        </span>
                      )}
                      {twinsResult.target_traits.backdrop && (
                        <span className="px-1.5 py-0.5 rounded-md bg-[#F4F7FB] border border-[#E2E8F0] text-[#334155] text-[10px] font-bold truncate max-w-full">
                          {twinsResult.target_traits.backdrop}
                        </span>
                      )}
                      {twinsResult.target_traits.symbol && (
                        <span className="px-1.5 py-0.5 rounded-md bg-[#F4F7FB] border border-[#E2E8F0] text-[#64748B] text-[10px] font-semibold truncate max-w-full">
                          {twinsResult.target_traits.symbol}
                        </span>
                      )}
                    </div>
                  </div>
                </button>

                {/* Demand & Pricing Summary */}
                <div className="lg:col-span-7 ton-card rounded-2xl p-3.5 flex flex-col justify-between gap-2.5">
                  <div className="flex items-center justify-between gap-2 flex-wrap">
                    <span className="text-xs font-extrabold text-[#0B1120] inline-flex items-center gap-1.5">
                      <TrendingUp className="w-3.5 h-3.5 text-[#0098EA]" />
                      Попит на цей вигляд
                    </span>
                    <div className="flex items-center gap-1.5">
                      <span className="px-2 py-0.5 rounded-lg bg-[#E8F5FE] text-[#0077C8] border border-[#BAE3FC] text-[10.5px] font-extrabold">
                        {twinsResult.demand.demand_label}
                      </span>
                      <span className="px-2 py-0.5 rounded-lg bg-[#F8FAFC] border border-[#E2E8F0] text-[#334155] text-[10.5px] font-bold tabular-nums">
                        {twinsResult.demand.sales_24h} прод/24г
                      </span>
                    </div>
                  </div>

                  <div className="grid grid-cols-4 gap-1.5 tabular-nums">
                    <div className="rounded-xl bg-[#F8FAFC] border border-[#E2E8F0] px-2.5 py-1.5">
                      <p className="text-[9.5px] font-bold text-[#64748B]">Двійників</p>
                      <p className="text-[13px] font-extrabold text-[#0B1120]">
                        {twinsResult.demand.total_twins}
                      </p>
                    </div>
                    <div className="rounded-xl bg-[#F8FAFC] border border-[#E2E8F0] px-2.5 py-1.5">
                      <p className="text-[9.5px] font-bold text-[#64748B]">Від (мін)</p>
                      <p className="text-[13px] font-extrabold text-[#0098EA]">
                        {formatTon(twinsResult.demand.min_price, 1)} TON
                      </p>
                    </div>
                    <div className="rounded-xl bg-[#F8FAFC] border border-[#E2E8F0] px-2.5 py-1.5">
                      <p className="text-[9.5px] font-bold text-[#64748B]">Медіана</p>
                      <p className="text-[13px] font-extrabold text-[#0B1120]">
                        {formatTon(twinsResult.demand.median_price, 1)} TON
                      </p>
                    </div>
                    <div className="rounded-xl bg-[#E8F5FE]/65 border border-[#BAE3FC] px-2.5 py-1.5">
                      <p className="text-[9.5px] font-bold text-[#0077C8]">Швидк. ціна</p>
                      <p className="text-[13px] font-extrabold text-[#0077C8]">
                        {formatTon(twinsResult.demand.recommended_sell, 1)} TON
                      </p>
                    </div>
                  </div>

                  <p className="text-[11px] font-medium text-[#334155] leading-snug">
                    {twinsResult.demand.demand_summary}
                  </p>
                </div>
              </div>

              {/* Filter & Sort Bar (Same Feel as Scanner) */}
              <div className="ton-card rounded-2xl p-2.5 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <div className="flex items-center gap-1 overflow-x-auto no-scrollbar">
                  {TWINS_MARKETS.map((m) => {
                    const active = twinsMarket === m.key;
                    const mCount =
                      m.key === 'all'
                        ? twinsResult.items.length
                        : twinsResult.items.filter(
                            (it) => (it.market || '').toLowerCase() === m.key,
                          ).length;
                    if (m.key !== 'all' && mCount === 0) return null;
                    return (
                      <button
                        key={m.key}
                        type="button"
                        onClick={() => {
                          haptic('light');
                          setTwinsMarket(m.key);
                        }}
                        className={`px-2.5 py-1.5 rounded-xl text-[11px] font-bold shrink-0 transition-colors cursor-pointer ${
                          active
                            ? 'ton-btn-primary text-white'
                            : 'bg-[#F4F7FB] text-[#334155] hover:bg-[#E8F5FE] hover:text-[#0077C8]'
                        }`}
                      >
                        {m.label}{' '}
                        <span className={active ? 'text-white/85' : 'text-[#64748B]'}>
                          ({mCount})
                        </span>
                      </button>
                    );
                  })}
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <span className="text-[11px] font-extrabold text-[#0B1120] tabular-nums">
                    {filteredTwins.length} лотів
                  </span>
                  <select
                    value={twinsSort}
                    onChange={(e) => {
                      const nextSort = e.target.value as TwinsSort;
                      setTwinsSort(nextSort);
                      if (lastTwinsParams) {
                        runTwinsSearch(lastTwinsParams, nextSort);
                      }
                    }}
                    className="h-8 px-2.5 rounded-xl bg-[#F4F7FB] border border-[#E2E8F0] text-[#0B1120] text-[11px] font-bold focus:outline-none focus:border-[#0098EA] cursor-pointer"
                  >
                    <option value="similarity">Схожість 1:1</option>
                    <option value="price_asc">Дешевші</option>
                    <option value="discount_desc">Вигода</option>
                  </select>
                </div>
              </div>

              {/* Exact Scanner NFT Grid — Same Cards & Same Full-Screen Drawer */}
              {filteredTwins.length === 0 ? (
                <div className="ton-card rounded-2xl p-8 text-center max-w-md mx-auto">
                  <p className="text-sm font-bold text-[#0B1120]">
                    Двійників у продажу зараз не знайдено
                  </p>
                  <p className="text-xs text-[#64748B] mt-1">
                    Це рідкісний вигляд або спробуйте обрати вкладку «Всі» маркети.
                  </p>
                </div>
              ) : (
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3">
                  {filteredTwins.map((item) => (
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
          )}
        </div>
      )}

      {/* CREATE RULE MODAL */}
      {showRuleModal && (
        <div className="fixed inset-0 z-50 flex items-end md:items-center justify-center md:p-6 bg-[#0B1120]/45 backdrop-blur-[2px] animate-fade-in">
          <div className="absolute inset-0" onClick={() => setShowRuleModal(false)} />
          <form
            onSubmit={handleCreateRule}
            className="relative z-10 w-full md:max-w-[520px] max-h-[90vh] overflow-y-auto bg-white rounded-t-[28px] md:rounded-3xl p-4 sm:p-5 space-y-3 animate-sheet-up shadow-2xl border border-[#E2E8F0]"
          >
            <div className="flex items-center justify-between">
              <h3 className="font-display text-base font-extrabold text-[#0B1120]">
                Нове правило Снайпера
              </h3>
              <button
                type="button"
                onClick={() => setShowRuleModal(false)}
                className="w-8 h-8 rounded-full bg-[#F8FAFC] border border-[#E2E8F0] flex items-center justify-center text-[#334155] cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-2.5 text-xs">
              <div>
                <label className="block font-bold text-[#334155] mb-1">Назва правила</label>
                <input
                  type="text"
                  required
                  value={ruleForm.name}
                  onChange={(e) => setRuleForm({ ...ruleForm, name: e.target.value })}
                  placeholder="Напр.: Троянди -20% або Рідкісний Пепе"
                  className="w-full h-10 px-3 rounded-xl bg-[#F4F7FB] border border-[#E2E8F0] font-semibold focus:outline-none focus:border-[#0098EA]"
                />
              </div>

              <div>
                <label className="block font-bold text-[#334155] mb-1">Колекція</label>
                <select
                  value={ruleForm.collection_short_name}
                  onChange={(e) => {
                    const short = e.target.value;
                    const found = collections.find((c) => c.short_name === short);
                    setRuleForm({
                      ...ruleForm,
                      collection_short_name: short,
                      collection_name: found ? found.name : 'Всі колекції',
                    });
                  }}
                  className="w-full h-10 px-3 rounded-xl bg-[#F4F7FB] border border-[#E2E8F0] font-semibold focus:outline-none focus:border-[#0098EA]"
                >
                  <option value="">Всі колекції</option>
                  {collections.map((c) => (
                    <option key={c.short_name} value={c.short_name}>
                      {c.name} (Флор {formatTon(c.floor_price)} TON)
                    </option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block font-bold text-[#334155] mb-1">Модель (опц.)</label>
                  <input
                    type="text"
                    value={ruleForm.model_filter}
                    onChange={(e) => setRuleForm({ ...ruleForm, model_filter: e.target.value })}
                    placeholder="Gold, Quantum..."
                    className="w-full h-10 px-3 rounded-xl bg-[#F4F7FB] border border-[#E2E8F0] font-semibold focus:outline-none focus:border-[#0098EA]"
                  />
                </div>
                <div>
                  <label className="block font-bold text-[#334155] mb-1">Фон (опц.)</label>
                  <input
                    type="text"
                    value={ruleForm.backdrop_filter}
                    onChange={(e) =>
                      setRuleForm({ ...ruleForm, backdrop_filter: e.target.value })
                    }
                    placeholder="Black, Onyx..."
                    className="w-full h-10 px-3 rounded-xl bg-[#F4F7FB] border border-[#E2E8F0] font-semibold focus:outline-none focus:border-[#0098EA]"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block font-bold text-[#334155] mb-1">Макс. ціна (TON)</label>
                  <input
                    type="number"
                    step="0.1"
                    value={ruleForm.max_price ?? ''}
                    onChange={(e) =>
                      setRuleForm({
                        ...ruleForm,
                        max_price: e.target.value ? Number(e.target.value) : null,
                      })
                    }
                    className="w-full h-10 px-3 rounded-xl bg-[#F4F7FB] border border-[#E2E8F0] font-bold tabular-nums focus:outline-none focus:border-[#0098EA]"
                  />
                </div>
                <div>
                  <label className="block font-bold text-[#334155] mb-1">Мін. дисконт (%)</label>
                  <input
                    type="number"
                    step="1"
                    value={ruleForm.min_discount_percent}
                    onChange={(e) =>
                      setRuleForm({
                        ...ruleForm,
                        min_discount_percent: Number(e.target.value),
                      })
                    }
                    className="w-full h-10 px-3 rounded-xl bg-[#F4F7FB] border border-[#E2E8F0] font-bold tabular-nums focus:outline-none focus:border-[#0098EA]"
                  />
                </div>
              </div>

              {/* Mode */}
              <div>
                <label className="block font-bold text-[#334155] mb-1">Режим реакції</label>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => setRuleForm({ ...ruleForm, mode: 'alert' })}
                    className={`h-10 rounded-xl font-bold border inline-flex items-center justify-center gap-1.5 cursor-pointer ${
                      ruleForm.mode === 'alert'
                        ? 'bg-[#E8F5FE] border-[#0098EA] text-[#0077C8]'
                        : 'bg-[#F8FAFC] border-[#E2E8F0] text-[#334155]'
                    }`}
                  >
                    <Bell className="w-3.5 h-3.5" />
                    <span>Алерт в Telegram</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setRuleForm({ ...ruleForm, mode: 'autobuy' })}
                    className={`h-10 rounded-xl font-bold border inline-flex items-center justify-center gap-1.5 cursor-pointer ${
                      ruleForm.mode === 'autobuy'
                        ? 'bg-[#0098EA] border-[#0098EA] text-white'
                        : 'bg-[#F8FAFC] border-[#E2E8F0] text-[#334155]'
                    }`}
                  >
                    <Zap className="w-3.5 h-3.5" />
                    <span>Автобай</span>
                  </button>
                </div>
              </div>

              {/* Markets */}
              <div>
                <label className="block font-bold text-[#334155] mb-1">Маркети</label>
                <div className="grid grid-cols-4 gap-1.5">
                  {ALL_MARKETS.map((m) => {
                    const checked = ruleForm.markets.includes(m);
                    return (
                      <button
                        key={m}
                        type="button"
                        onClick={() => toggleRuleMarket(m)}
                        className={`py-2 rounded-xl text-[11px] font-bold border cursor-pointer ${
                          checked
                            ? 'bg-[#0098EA] text-white border-[#0098EA]'
                            : 'bg-[#F8FAFC] text-[#64748B] border-[#E2E8F0]'
                        }`}
                      >
                        {getMarketMeta(m).label}
                      </button>
                    );
                  })}
                </div>
              </div>

              <label className="flex items-center justify-between p-3 rounded-xl bg-[#E8F5FE] border border-[#BAE3FC] cursor-pointer">
                <span className="font-bold text-[#0B1120] flex items-center gap-1.5">
                  <Sparkles className="w-4 h-4 text-[#0098EA]" />
                  Тільки рідкісні комбо (Monochrome / Gold)
                </span>
                <input
                  type="checkbox"
                  checked={ruleForm.rare_combo_only}
                  onChange={(e) =>
                    setRuleForm({ ...ruleForm, rare_combo_only: e.target.checked })
                  }
                  className="w-4 h-4 accent-[#0098EA]"
                />
              </label>
            </div>

            <button
              type="submit"
              disabled={savingRule}
              className="w-full ton-btn-primary h-11 rounded-xl font-bold text-sm cursor-pointer disabled:opacity-60"
            >
              {savingRule ? 'Збереження...' : 'Створити правило'}
            </button>
          </form>
        </div>
      )}

      {/* CREATE OFFER MODAL */}
      {offerTarget && (
        <div className="fixed inset-0 z-50 flex items-end md:items-center justify-center md:p-6 bg-[#0B1120]/45 backdrop-blur-[2px] animate-fade-in">
          <div className="absolute inset-0" onClick={() => setOfferTarget(null)} />
          <form
            onSubmit={handleCreateOffer}
            className="relative z-10 w-full md:max-w-[500px] bg-white rounded-t-[28px] md:rounded-3xl p-4 sm:p-5 space-y-3 animate-sheet-up shadow-2xl border border-[#E2E8F0]"
          >
            <div className="flex items-center justify-between">
              <h3 className="font-display text-base font-extrabold text-[#0B1120]">
                Новий офер · {offerTarget.collection_name}
              </h3>
              <button
                type="button"
                onClick={() => setOfferTarget(null)}
                className="w-8 h-8 rounded-full bg-[#F8FAFC] border border-[#E2E8F0] flex items-center justify-center text-[#334155] cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="rounded-xl p-2.5 bg-[#E8F5FE] border border-[#BAE3FC] text-[#0077C8] text-xs font-semibold tabular-nums flex justify-between">
              <span>Поточний флор: {formatTon(offerTarget.floor_price)} TON</span>
              <span>Топ офер: {formatTon(offerTarget.best_offer)} TON</span>
            </div>

            <div className="grid grid-cols-2 gap-2 text-xs">
              <div>
                <label className="block font-bold text-[#334155] mb-1">Ваша ставка (TON)</label>
                <input
                  type="number"
                  step="0.05"
                  required
                  value={offerBid}
                  onChange={(e) => setOfferBid(e.target.value)}
                  className="w-full h-10 px-3 rounded-xl bg-[#F4F7FB] border border-[#E2E8F0] font-bold tabular-nums focus:outline-none focus:border-[#0098EA]"
                />
              </div>
              <div>
                <label className="block font-bold text-[#334155] mb-1">Макс. ліміт (TON)</label>
                <input
                  type="number"
                  step="0.05"
                  required
                  value={offerMaxBid}
                  onChange={(e) => setOfferMaxBid(e.target.value)}
                  className="w-full h-10 px-3 rounded-xl bg-[#F4F7FB] border border-[#E2E8F0] font-bold tabular-nums focus:outline-none focus:border-[#0098EA]"
                />
              </div>
            </div>

            <div className="text-xs">
              <label className="block font-bold text-[#334155] mb-1">Маркет</label>
              <select
                value={offerMarket}
                onChange={(e) => setOfferMarket(e.target.value)}
                className="w-full h-10 px-3 rounded-xl bg-[#F4F7FB] border border-[#E2E8F0] font-bold focus:outline-none focus:border-[#0098EA]"
              >
                {ALL_MARKETS.map((m) => (
                  <option key={m} value={m}>
                    {getMarketMeta(m).label}
                  </option>
                ))}
              </select>
            </div>

            <label className="flex items-center justify-between p-3 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0] text-xs cursor-pointer">
              <span className="font-bold text-[#0B1120]">
                Авто-перебиття конкурентів (+0.1 TON до ліміту)
              </span>
              <input
                type="checkbox"
                checked={offerAutoOutbid}
                onChange={(e) => setOfferAutoOutbid(e.target.checked)}
                className="w-4 h-4 accent-[#0098EA]"
              />
            </label>

            <button
              type="button"
              onClick={() => {
                haptic('medium');
                openExternalLink(
                  offerTarget.sample_listing?.market_url ||
                    offerTarget.market_url ||
                    getMarketCollectionUrl(
                      offerMarket,
                      offerTarget.collection_short_name || offerTarget.short_name,
                      offerTarget.collection_name,
                      offerTarget.market_url,
                    ),
                );
              }}
              className="w-full ton-btn-primary h-11 rounded-xl font-bold text-sm inline-flex items-center justify-center gap-1.5 cursor-pointer"
            >
              <span>Зробити реальний офер на маркеті</span>
              <ExternalLink className="w-4 h-4" />
            </button>

            <button
              type="submit"
              disabled={savingOffer}
              className="w-full h-10 rounded-xl bg-[#E8F5FE] hover:bg-[#D4ECFD] border border-[#BAE3FC] text-[#0077C8] text-xs font-extrabold cursor-pointer disabled:opacity-60 transition-colors"
            >
              {savingOffer ? 'Збереження...' : 'Зберегти офер у трекері GiftKit'}
            </button>
          </form>
        </div>
      )}
    </div>
  );
};
