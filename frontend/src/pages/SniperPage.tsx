import React, { useCallback, useEffect, useState } from 'react';
import {
  Bell,
  Crosshair,
  Eye,
  ExternalLink,
  Plus,
  RefreshCw,
  Send,
  ShoppingCart,
  Sparkles,
  Trash2,
  X,
  Zap,
} from 'lucide-react';
import { api } from '../api/client';
import type {
  AlertLog,
  AnalyzedListing,
  CollectionSummary,
  CreateSniperRulePayload,
  OfferRadarItem,
  SniperRule,
  TestAlertResponse,
  UserOffer,
} from '../types/api';
import { formatTimeAgo, formatTon, getMarketMeta, haptic } from '../utils/format';
import { NftImage } from '../components/NftImage';

interface SniperPageProps {
  collections: CollectionSummary[];
  refreshTick: number;
  onSelectListing: (item: AnalyzedListing) => void;
  onNotify: (title: string, message?: string, variant?: 'info' | 'success' | 'warning' | 'error') => void;
}

type SubTab = 'rules' | 'offers' | 'alerts';

const ALL_MARKETS = ['portals', 'getgems', 'mrkt', 'tonnel'];

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
    return 'https://t.me/mrkt';
  }
  if (m === 'tonnel') {
    return 'https://t.me/tonnel_network_bot';
  }
  return 'https://portal-market.com';
}

export const SniperPage: React.FC<SniperPageProps> = ({
  collections,
  refreshTick,
  onSelectListing,
  onNotify,
}) => {
  const [subTab, setSubTab] = useState<SubTab>('rules');

  // Data
  const [rules, setRules] = useState<SniperRule[]>([]);
  const [offers, setOffers] = useState<UserOffer[]>([]);
  const [radar, setRadar] = useState<OfferRadarItem[]>([]);
  const [alerts, setAlerts] = useState<AlertLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshingRadar, setRefreshingRadar] = useState(false);

  // Test TG Preview
  const [testingAlert, setTestingAlert] = useState(false);
  const [tgPreview, setTgPreview] = useState<TestAlertResponse | null>(null);

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
      const [rulesRes, offersRes, alertsRes] = await Promise.all([
        api.getSniperRules().catch(() => ({ rules: [] })),
        api.getOffers().catch(() => ({ offers: [], radar: [] })),
        api.getSniperAlerts().catch(() => ({ alerts: [] })),
      ]);
      setRules(rulesRes.rules || []);
      setOffers(offersRes.offers || []);
      setRadar(offersRes.radar || []);
      setAlerts(alertsRes.alerts || []);
    } finally {
      setLoading(false);
    }
  }, []);

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

  const handleSelectAlertCard = async (al: AlertLog) => {
    haptic('light');
    if (al.listing) {
      onSelectListing(al.listing);
      return;
    }
    const query = al.listing_id || al.title || al.rule_name;
    if (!query) return;
    try {
      const res = await api.runXRay(String(query));
      if (res?.item) {
        onSelectListing(res.item);
      }
    } catch {
      onNotify('Не вдалося відкрити NFT', String(query), 'warning');
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

  const handleTestAlert = async () => {
    haptic('medium');
    setTestingAlert(true);
    try {
      const res = await api.triggerTestAlert();
      setTgPreview(res);
      await loadAll();
      const sent = res.sent_to_telegram ?? res.telegram_sent;
      onNotify(
        sent ? 'Тест-картку надіслано в Telegram!' : 'Прев’ю ТГ-картки згенеровано',
        sent
          ? 'Перевірте ваш чат з ботом'
          : 'Додайте TG_BOT_TOKEN у вкладці «Маркети» для реальної відправки',
        sent ? 'success' : 'info',
      );
    } catch (err) {
      onNotify('Помилка тест-алерту', err instanceof Error ? err.message : '', 'error');
    } finally {
      setTestingAlert(false);
    }
  };

  const rawPreview = tgPreview?.listing || tgPreview?.alert?.listing || alerts[0]?.listing;
  const previewListing =
    rawPreview && typeof rawPreview.price === 'number' && rawPreview.collection_name
      ? rawPreview
      : null;

  return (
    <div className="space-y-4 pb-4">
      {/* Segmented Sub-tabs */}
      <div className="ton-card rounded-2xl p-1 grid grid-cols-3 gap-1 max-w-xl">
        {(
          [
            ['rules', 'Правила', rules.filter((r) => r.enabled).length, Crosshair],
            ['offers', 'Офери', offers.length, Zap],
            ['alerts', 'Алерти', alerts.length, Bell],
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
                        <a
                          href={marketUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="h-9 px-2.5 rounded-xl bg-[#F8FAFC] hover:bg-[#E8F5FE] border border-[#E2E8F0] hover:border-[#BAE3FC] text-[#0B1120] hover:text-[#0077C8] text-[11px] font-bold inline-flex items-center gap-1 transition-colors"
                        >
                          <span>На маркет</span>
                          <ExternalLink className="w-3 h-3" />
                        </a>
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
                          className="w-full h-full object-cover"
                        />
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="text-[12.5px] font-extrabold text-[#0B1120] truncate">
                          {item.collection_name}
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

      {/* TAB 3: ALERT LOG & TELEGRAM CARD PREVIEW */}
      {subTab === 'alerts' && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
          {/* Left: Test Alert + Telegram Preview */}
          <div className="lg:col-span-5 space-y-3">
            <div className="ton-card rounded-2xl p-3.5 bg-gradient-to-br from-white to-[#F0F8FF] border-[#BAE3FC] flex items-center justify-between gap-3">
              <div>
                <h2 className="font-display text-[13.5px] font-extrabold text-[#0B1120]">
                  Прев&apos;ю картки в Telegram
                </h2>
                <p className="text-[11px] text-[#334155] mt-0.5">
                  Перевірте, як бот надсилає знахідки снайпера з фото та кнопками
                </p>
              </div>
              <button
                type="button"
                disabled={testingAlert}
                onClick={handleTestAlert}
                className="ton-btn-primary h-10 px-3.5 rounded-xl text-xs font-bold inline-flex items-center gap-1.5 shrink-0 cursor-pointer disabled:opacity-60"
              >
                <Send className="w-3.5 h-3.5" />
                <span>{testingAlert ? '...' : 'Тест ТГ-картки'}</span>
              </button>
            </div>

            {(tgPreview || previewListing) && (
              <div className="rounded-2xl p-3 bg-[#E8F5FE] border border-[#BAE3FC] space-y-1.5">
                <div className="flex items-center justify-between px-1">
                  <span className="text-[10.5px] font-extrabold text-[#0077C8] flex items-center gap-1">
                    <Send className="w-3 h-3" />
                    Telegram Bot · GiftKit
                  </span>
                  <span className="text-[10px] font-semibold text-[#334155]">
                    {tgPreview?.sent_to_telegram ? 'Надіслано в чат' : 'Живе прев’ю'}
                  </span>
                </div>

                <div className="bg-white rounded-2xl rounded-tl-md shadow-sm border border-[#BAE3FC] overflow-hidden">
                  {previewListing && (
                    <div className="relative h-44 w-full bg-[#F4F7FB] overflow-hidden">
                      <NftImage
                        src={previewListing.photo_url}
                        alt={previewListing.collection_name}
                        className="w-full h-full object-cover"
                      />
                      <span className="absolute top-2.5 left-2.5 px-2.5 py-1 rounded-xl bg-[#0098EA] text-white text-[11px] font-extrabold shadow-sm tabular-nums">
                        -{Math.round(previewListing.discount_percent)}% · {previewListing.verdict_label}
                      </span>
                    </div>
                  )}

                  <div className="p-3 text-[12px] text-[#0B1120] space-y-1.5 leading-relaxed">
                    {previewListing ? (
                      <>
                        <p className="font-extrabold text-[13.5px]">
                          {previewListing.collection_name} #{previewListing.number}
                        </p>
                        <div className="grid grid-cols-2 gap-1.5 text-[11.5px] bg-[#F8FAFC] rounded-xl p-2 border border-[#E2E8F0] tabular-nums">
                          <div>
                            Ціна: <strong>{formatTon(previewListing.price)} TON</strong>
                          </div>
                          <div>
                            Флор: <strong>{formatTon(previewListing.collection_floor)} TON</strong>
                          </div>
                          <div>
                            Fair Value:{' '}
                            <strong className="text-[#0077C8]">
                              {formatTon(previewListing.fair_value)} TON
                            </strong>
                          </div>
                          <div>
                            Профіт:{' '}
                            <strong
                              className={
                                previewListing.net_profit_ton >= 0
                                  ? 'text-[#0077C8]'
                                  : 'text-[#0B1120]'
                              }
                            >
                              {previewListing.net_profit_ton >= 0 ? '+' : ''}
                              {formatTon(previewListing.net_profit_ton)} TON
                            </strong>
                          </div>
                          {previewListing.model_floor ? (
                            <div className="col-span-2 pt-1 border-t border-[#E2E8F0] text-[11px] text-[#334155]">
                              Флор моделі:{' '}
                              <strong className="text-[#0B1120]">
                                {formatTon(previewListing.model_floor)} TON
                              </strong>
                              {' · '}Ліквідність:{' '}
                              <strong className="text-[#0077C8]">
                                {previewListing.liquidity_score}/100
                              </strong>
                            </div>
                          ) : null}
                        </div>
                        {previewListing.attributes && previewListing.attributes.length > 0 && (
                          <div className="flex flex-wrap gap-1 pt-0.5">
                            {previewListing.attributes.slice(0, 3).map((attr, idx) => (
                              <span
                                key={`${attr.type}-${idx}`}
                                className="px-2 py-0.5 rounded-lg bg-[#E8F5FE] text-[#0077C8] text-[10px] font-bold"
                              >
                                {attr.value} ({attr.rarity_percent.toFixed(1)}%)
                              </span>
                            ))}
                          </div>
                        )}
                      </>
                    ) : (
                      <p className="whitespace-pre-line text-xs text-[#334155]">
                        {tgPreview?.message || tgPreview?.caption || 'Тестовий алерт сформовано.'}
                      </p>
                    )}
                  </div>

                  {/* Inline Telegram Buttons */}
                  <div className="px-2.5 pb-2.5 grid grid-cols-2 gap-1.5">
                    <button
                      type="button"
                      onClick={() => previewListing && onSelectListing(previewListing)}
                      className="py-2 rounded-xl bg-[#E8F5FE] hover:bg-[#D4ECFD] text-[#0077C8] text-[11px] font-bold inline-flex items-center justify-center gap-1 cursor-pointer"
                    >
                      <ShoppingCart className="w-3 h-3" />
                      <span>Купити / Деталі</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => setSubTab('offers')}
                      className="py-2 rounded-xl bg-[#E8F5FE] hover:bg-[#D4ECFD] text-[#0077C8] text-[11px] font-bold inline-flex items-center justify-center gap-1 cursor-pointer"
                    >
                      <Zap className="w-3 h-3" />
                      <span>Поставити офер</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => previewListing && onSelectListing(previewListing)}
                      className="col-span-2 py-2 rounded-xl bg-[#0098EA] hover:bg-[#0077C8] text-white text-[11px] font-bold inline-flex items-center justify-center gap-1 cursor-pointer"
                    >
                      <span>Відкрити в GiftKit</span>
                      <ExternalLink className="w-3 h-3" />
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Right: Alert History List — Rich Mini NFT Cards */}
          <div className="lg:col-span-7 space-y-2.5">
            <h3 className="font-display text-[14px] font-extrabold text-[#0B1120] px-0.5 flex items-center gap-1.5">
              <Bell className="w-4 h-4 text-[#0098EA]" />
              Журнал спрацювань ({alerts.length})
            </h3>
            {alerts.length === 0 ? (
              <div className="ton-card rounded-2xl p-6 text-center text-xs text-[#64748B]">
                Журнал порожній. Натисніть «Тест ТГ-картки», щоб перевірити алерти.
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-2.5">
                {alerts.map((al) => {
                  const lst = al.listing;
                  const titleText = lst
                    ? `${lst.collection_name} #${lst.number}`
                    : al.title || al.rule_name || 'Спрацювання снайпера';
                  const marketUrl = lst
                    ? lst.market_url ||
                      getMarketCollectionUrl(lst.market, lst.short_name, lst.collection_name)
                    : 'https://portal-market.com';
                  const tgNftUrl = lst?.tg_id
                    ? `https://t.me/nft/${lst.tg_id}`
                    : 'https://t.me/GiftKit_bot';

                  return (
                    <div
                      key={al.id}
                      onClick={() => handleSelectAlertCard(al)}
                      role="button"
                      tabIndex={0}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          handleSelectAlertCard(al);
                        }
                      }}
                      className="w-full text-left ton-card ton-card-hover rounded-2xl p-3 flex flex-col gap-2.5 cursor-pointer"
                    >
                      <div className="flex items-start gap-3">
                        {/* Left: Square NFT thumbnail */}
                        <div className="w-16 h-16 rounded-xl overflow-hidden bg-[#F4F7FB] border border-[#E2E8F0] shrink-0">
                          <NftImage
                            src={lst?.photo_url}
                            alt={titleText}
                            className="w-full h-full object-cover"
                          />
                        </div>

                        {/* Center: Title, Valuation & Badges */}
                        <div className="flex-1 min-w-0 space-y-1">
                          <div className="flex items-center justify-between gap-2">
                            <p className="text-[13px] font-extrabold text-[#0B1120] truncate">
                              {titleText}
                            </p>
                            <span className="text-[10.5px] font-semibold text-[#64748B] shrink-0">
                              {formatTimeAgo(al.created_at)}
                            </span>
                          </div>

                          {lst ? (
                            <>
                              {/* Price & Valuation Row */}
                              <div className="flex items-center gap-1.5 flex-wrap text-[11px] text-[#334155] tabular-nums">
                                <span>
                                  Ціна: <strong className="text-[#0B1120]">{formatTon(lst.price)} TON</strong>
                                </span>
                                <span>·</span>
                                <span>Флор: {formatTon(lst.collection_floor)} TON</span>
                                <span>·</span>
                                <span>
                                  Fair: <strong className="text-[#0077C8]">{formatTon(lst.fair_value)} TON</strong>
                                </span>
                                <span className="px-1.5 py-0.5 rounded-md bg-[#0098EA] text-white text-[10px] font-extrabold">
                                  -{Math.round(lst.discount_percent)}%
                                </span>
                              </div>

                              {/* Visual / Nice Number / Symbol Badges Row */}
                              <div className="flex items-center gap-1.5 flex-wrap pt-0.5">
                                {typeof lst.visual_score === 'number' && (
                                  <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-[#E8F5FE] text-[#0077C8] border border-[#BAE3FC] text-[10px] font-bold tabular-nums">
                                    <Eye className="w-2.5 h-2.5" />
                                    Візуал {lst.visual_score.toFixed(1)}/10
                                  </span>
                                )}
                                {lst.harmony_label && (
                                  <span className="px-1.5 py-0.5 rounded-md bg-[#F0F8FF] text-[#0098EA] border border-[#BAE3FC] text-[10px] font-bold">
                                    {lst.harmony_label}
                                  </span>
                                )}
                                {(lst.number_pattern || lst.number_badge) && (
                                  <span className="px-1.5 py-0.5 rounded-md bg-[#E8F5FE] text-[#0077C8] border border-[#BAE3FC] text-[10px] font-bold">
                                    {lst.number_pattern || lst.number_badge}
                                  </span>
                                )}
                                {lst.symbol_badge && (
                                  <span className="px-1.5 py-0.5 rounded-md bg-[#F8FAFC] text-[#334155] border border-[#E2E8F0] text-[10px] font-bold">
                                    {lst.symbol_badge}
                                  </span>
                                )}
                              </div>
                            </>
                          ) : (
                            <p className="text-[11px] text-[#334155] line-clamp-2">
                              {al.message || 'Новий сигнал снайпера — натисніть для відкриття NFT'}
                            </p>
                          )}
                        </div>
                      </div>

                      {/* Direct Action Links Row */}
                      <div className="flex items-center gap-1.5 pt-2 border-t border-[#F1F5F9]">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleSelectAlertCard(al);
                          }}
                          className="flex-1 h-8 px-2.5 rounded-xl bg-[#0098EA] hover:bg-[#0077C8] text-white text-[11px] font-extrabold inline-flex items-center justify-center gap-1 cursor-pointer transition-colors"
                        >
                          <span>Відкрити NFT</span>
                        </button>
                        <a
                          href={marketUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="h-8 px-2.5 rounded-xl bg-[#E8F5FE] hover:bg-[#D4ECFD] border border-[#BAE3FC] text-[#0077C8] text-[11px] font-bold inline-flex items-center justify-center gap-1 transition-colors"
                        >
                          <span>На маркеті</span>
                          <ExternalLink className="w-3 h-3" />
                        </a>
                        <a
                          href={tgNftUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="h-8 px-2.5 rounded-xl bg-[#F8FAFC] hover:bg-[#E8F5FE] border border-[#E2E8F0] hover:border-[#BAE3FC] text-[#0B1120] hover:text-[#0077C8] text-[11px] font-bold inline-flex items-center justify-center gap-1 transition-colors"
                        >
                          <span>Власник в ТГ</span>
                          <ExternalLink className="w-3 h-3" />
                        </a>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
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
              type="submit"
              disabled={savingOffer}
              className="w-full ton-btn-primary h-11 rounded-xl font-bold text-sm cursor-pointer disabled:opacity-60"
            >
              {savingOffer ? 'Розміщення...' : 'Поставити офер'}
            </button>

            <a
              href={getMarketCollectionUrl(
                offerMarket,
                offerTarget.collection_short_name || offerTarget.short_name,
                offerTarget.collection_name,
                offerTarget.market_url,
              )}
              target="_blank"
              rel="noopener noreferrer"
              className="w-full h-10 rounded-xl bg-[#E8F5FE] hover:bg-[#D4ECFD] border border-[#BAE3FC] text-[#0077C8] text-xs font-extrabold inline-flex items-center justify-center gap-1.5 transition-colors"
            >
              <span>Відкрити колекцію на маркеті</span>
              <ExternalLink className="w-3.5 h-3.5" />
            </a>
          </form>
        </div>
      )}
    </div>
  );
};
