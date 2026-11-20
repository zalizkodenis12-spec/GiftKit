import React, { useEffect, useState } from 'react';
import {
  Briefcase,
  Calculator,
  CheckCircle2,
  ExternalLink,
  Eye,
  Flame,
  Layers,
  Loader2,
  Palette,
  ShieldAlert,
  ShoppingCart,
  Sparkles,
  TrendingUp,
  X,
  Zap,
} from 'lucide-react';
import { api } from '../api/client';
import type { AnalyzedListing, SaleRecord } from '../types/api';
import {
  formatPercent,
  formatTimeAgo,
  formatTon,
  formatUsd,
  getLiquidityColor,
  getMarketMeta,
  getVerdictStyle,
  haptic,
  openExternalLink,
} from '../utils/format';
import { NftImage } from './NftImage';

interface NftDetailDrawerProps {
  item: AnalyzedListing | null;
  recommendation?: string;
  comparableSales?: SaleRecord[];
  tonUsd: number;
  dryRun: boolean;
  onClose: () => void;
  onUpdateItem?: (item: AnalyzedListing) => void;
  onBuy: (item: AnalyzedListing) => Promise<void>;
  onMakeOffer: (item: AnalyzedListing) => Promise<void>;
  onAddPortfolio: (item: AnalyzedListing) => Promise<void>;
  onNotify?: (
    title: string,
    message?: string,
    variant?: 'info' | 'success' | 'warning' | 'error',
  ) => void;
}

const TRAIT_LABELS: Record<string, string> = {
  model: 'Модель',
  backdrop: 'Фон',
  symbol: 'Символ',
};

export const NftDetailDrawer: React.FC<NftDetailDrawerProps> = ({
  item,
  recommendation,
  comparableSales,
  tonUsd,
  dryRun,
  onClose,
  onUpdateItem,
  onBuy,
  onMakeOffer,
  onAddPortfolio,
  onNotify,
}) => {
  const [busyAction, setBusyAction] = useState<'buy' | 'offer' | 'portfolio' | null>(null);
  const [targetSell, setTargetSell] = useState<string>('');
  const [visionLoading, setVisionLoading] = useState(false);
  const [visionProvider, setVisionProvider] = useState<string | null>(null);
  const [liveSwatches, setLiveSwatches] = useState<string[]>([]);

  useEffect(() => {
    if (!item) return;
    setTargetSell(item.fair_value.toFixed(2));
    setVisionProvider(null);
    setLiveSwatches((item.color_swatches || []).filter(Boolean).slice(0, 4));
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);

    // Always verify/extract REAL pixel colors from the actual NFT image when opened
    let cancelled = false;
    if (item.photo_url && item.photo_url.startsWith('http')) {
      const modelAttr = item.attributes?.find((a) => a.type === 'model')?.value || '';
      const backdropAttr = item.attributes?.find((a) => a.type === 'backdrop')?.value || '';
      const symbolAttr = item.attributes?.find((a) => a.type === 'symbol')?.value || '';
      api
        .getPixelColors({
          photo_url: item.photo_url,
          model: modelAttr || undefined,
          backdrop: backdropAttr || undefined,
          symbol: symbolAttr || undefined,
        })
        .then((res) => {
          if (cancelled) return;
          if (res.color_swatches && res.color_swatches.length > 0) {
            setLiveSwatches(res.color_swatches.slice(0, 4));
          }
        })
        .catch(() => {
          // keep existing swatches if network fails
        });
    }

    return () => {
      cancelled = true;
      window.removeEventListener('keydown', onKeyDown);
    };
  }, [item?.id, item?.photo_url, onClose]);

  if (!item) return null;

  const parsedTargetSell = Number(targetSell) || item.fair_value;
  const calcFeeTon = parsedTargetSell * (item.fee_percent / 100);
  const calcNetProfit = parsedTargetSell - calcFeeTon - item.price;
  const calcRoi = item.price > 0 ? (calcNetProfit / item.price) * 100 : 0;

  const marketMeta = getMarketMeta(item.market);
  const bestSellMeta = getMarketMeta(item.best_sell_market);
  const verdict = getVerdictStyle(item.verdict);
  const salesList =
    comparableSales && comparableSales.length > 0 ? comparableSales : item.recent_sales || [];

  const visualScore = typeof item.visual_score === 'number' ? item.visual_score : null;
  const visualScorePct = visualScore !== null ? Math.min(100, Math.max(6, visualScore * 10)) : 0;
  const visualTag =
    item.visual_tag ||
    (visualScore !== null
      ? visualScore >= 8.2
        ? 'Топ візуал'
        : visualScore >= 7.0
          ? 'Стильний'
          : 'Стандарт'
      : 'Аналіз пікселів');
  const swatches = (
    liveSwatches.length > 0 ? liveSwatches : item.color_swatches || []
  )
    .filter(Boolean)
    .slice(0, 4);

  const handleAction = async (
    type: 'buy' | 'offer' | 'portfolio',
    fn: (listing: AnalyzedListing) => Promise<void>,
  ) => {
    setBusyAction(type);
    haptic('medium');
    try {
      await fn(item);
    } finally {
      setBusyAction(null);
    }
  };

  const handleRunVisionScore = async () => {
    haptic('light');
    setVisionLoading(true);
    try {
      const modelAttr = item.attributes?.find((a) => a.type === 'model')?.value;
      const backdropAttr = item.attributes?.find((a) => a.type === 'backdrop')?.value;
      const symbolAttr = item.attributes?.find((a) => a.type === 'symbol')?.value;

      const res = await api.runVisionScore({
        listing_id: item.id,
        tg_id: item.tg_id,
        photo_url: item.photo_url,
        collection_name: item.collection_name,
        short_name: item.short_name,
        number: item.number,
        model: modelAttr,
        backdrop: backdropAttr,
        symbol: symbolAttr,
      });

      const updated: AnalyzedListing = {
        ...item,
        visual_score: typeof res.visual_score === 'number' ? res.visual_score : item.visual_score,
        visual_tag: res.visual_tag ?? item.visual_tag,
        is_monochrome: res.is_monochrome ?? item.is_monochrome,
        harmony_label: res.harmony_label ?? item.harmony_label,
        color_swatches:
          res.color_swatches && res.color_swatches.length > 0
            ? res.color_swatches
            : item.color_swatches,
        number_pattern: res.number_pattern ?? item.number_pattern,
        number_bonus_percent: res.number_bonus_percent ?? item.number_bonus_percent,
        ai_vision_comment: res.ai_vision_comment || res.comment || item.ai_vision_comment,
      };

      setVisionProvider(res.provider || null);
      onUpdateItem?.(updated);
      onNotify?.(
        'AI Vision оцінку оновлено',
        `Оцінка естетики: ${(updated.visual_score ?? 0).toFixed(1)} / 10`,
        'success',
      );
    } catch (err) {
      onNotify?.(
        'Не вдалося виконати AI Vision',
        err instanceof Error ? err.message : 'Спробуйте ще раз трохи пізніше',
        'error',
      );
    } finally {
      setVisionLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-end md:items-center justify-center md:p-6 bg-[#0B1120]/45 backdrop-blur-[2px] animate-fade-in">
      {/* Backdrop click */}
      <div className="absolute inset-0" onClick={onClose} />

      {/* Mobile Bottom Sheet -> Desktop Centered Modal */}
      <div className="relative z-10 w-full md:max-w-[580px] max-h-[92vh] md:max-h-[88vh] bg-[#F4F7FB] rounded-t-[28px] md:rounded-3xl shadow-[0_-12px_40px_rgba(11,17,32,0.22)] md:shadow-[0_24px_64px_rgba(11,17,32,0.24)] border border-transparent md:border-[#E2E8F0] flex flex-col overflow-hidden animate-sheet-up">
        {/* Grab handle & Top Bar */}
        <div className="bg-white border-b border-[#E2E8F0] px-4 pt-2.5 md:pt-3.5 pb-3 shrink-0">
          <div className="w-10 h-1 bg-[#CBD5E1] rounded-full mx-auto mb-2.5 md:hidden" />
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 min-w-0">
              <span
                className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-lg text-[11px] font-bold border ${marketMeta.bg} ${marketMeta.text} ${marketMeta.border}`}
              >
                <span className={`w-1.5 h-1.5 rounded-full ${marketMeta.dot}`} />
                {marketMeta.label}
              </span>
              <span
                className={`px-2 py-0.5 rounded-lg text-[11px] font-bold border ${verdict.badge}`}
              >
                {item.verdict_label || verdict.label}
              </span>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="w-8 h-8 rounded-full bg-[#F8FAFC] hover:bg-[#E8F5FE] border border-[#E2E8F0] flex items-center justify-center text-[#334155] hover:text-[#0077C8] cursor-pointer transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Scrollable Content */}
        <div className="overflow-y-auto px-3.5 sm:px-4 py-3.5 space-y-3">
          {/* Hero Card */}
          <div className="ton-card rounded-2xl p-3 flex gap-3 items-center">
            <div className="w-24 h-24 rounded-2xl overflow-hidden bg-[#F4F7FB] border border-[#E2E8F0] shrink-0 relative">
              <NftImage
                src={item.photo_url}
                alt={item.collection_name}
                className="w-full h-full object-cover"
              />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-[11px] font-semibold text-[#64748B] truncate">
                {item.tg_id}
              </p>
              <h2 className="font-display text-[17px] font-extrabold text-[#0B1120] leading-tight truncate">
                {item.collection_name}{' '}
                <span className="text-[#0098EA] tabular-nums">#{item.number}</span>
              </h2>

              <div className="flex flex-wrap items-center gap-1.5 mt-2">
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-lg bg-[#E8F5FE] text-[#0077C8] border border-[#BAE3FC] text-[10.5px] font-bold tabular-nums">
                  Ліквідність {item.liquidity_score}/100
                </span>
                <span className="px-2 py-0.5 rounded-lg bg-[#F8FAFC] border border-[#E2E8F0] text-[#334155] text-[10.5px] font-semibold tabular-nums">
                  {item.sales_24h} прод/24г
                </span>
              </div>

              <div className="mt-2 w-full h-1.5 rounded-full bg-[#E8F5FE] overflow-hidden">
                <div
                  className={`h-full rounded-full ${getLiquidityColor(item.liquidity_score)}`}
                  style={{ width: `${Math.min(100, Math.max(8, item.liquidity_score))}%` }}
                />
              </div>
            </div>
          </div>

          {/* Dedicated Visual AI ("Очі GiftKit") Card */}
          <div className="ton-card rounded-2xl p-3.5 border-[#BAE3FC] bg-gradient-to-br from-white via-white to-[#F2F9FF] space-y-2.5">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 min-w-0">
                <div className="w-7 h-7 rounded-xl bg-[#E8F5FE] border border-[#BAE3FC] flex items-center justify-center shrink-0">
                  <Eye className="w-4 h-4 text-[#0098EA]" />
                </div>
                <div className="min-w-0">
                  <h3 className="text-xs font-extrabold text-[#0B1120] truncate">
                    Візуальна оцінка (Очі GiftKit)
                  </h3>
                  {visionProvider && (
                    <p className="text-[10px] font-semibold text-[#64748B]">
                      Джерело: {visionProvider}
                    </p>
                  )}
                </div>
              </div>
              <span
                className={`px-2 py-0.5 rounded-lg text-[10.5px] font-extrabold border shrink-0 ${
                  visualScore !== null && visualScore >= 8.0
                    ? 'bg-[#0098EA] text-white border-[#0098EA]'
                    : 'bg-[#E8F5FE] text-[#0077C8] border-[#BAE3FC]'
                }`}
              >
                {visualTag}
              </span>
            </div>

            {/* Score Bar */}
            <div className="space-y-1">
              <div className="flex items-baseline justify-between text-[11px] tabular-nums">
                <span className="font-semibold text-[#64748B]">Індекс естетики та гармонії</span>
                <span className="font-extrabold text-[#0B1120]">
                  {visualScore !== null ? (
                    <>
                      <span className="text-[15px] text-[#0098EA]">
                        {visualScore.toFixed(1)}
                      </span>
                      <span className="text-[#64748B]"> / 10</span>
                    </>
                  ) : (
                    <span className="text-[#64748B]">Не оцінено</span>
                  )}
                </span>
              </div>
              <div className="w-full h-2 rounded-full bg-[#E8F5FE] overflow-hidden border border-[#BAE3FC]/60">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-[#0098EA] to-[#0077C8] transition-all duration-300"
                  style={{ width: `${visualScorePct}%` }}
                />
              </div>
            </div>

            {/* Extracted Pixel Color Swatches + Harmony Label */}
            {(swatches.length > 0 || item.harmony_label || item.is_monochrome) && (
              <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
                {swatches.length > 0 && (
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Palette className="w-3.5 h-3.5 text-[#0098EA] shrink-0" />
                    {swatches.map((hex, idx) => (
                      <span
                        key={`${hex}-${idx}`}
                        className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-lg bg-white border border-[#E2E8F0] text-[10px] font-bold text-[#334155] font-mono"
                      >
                        <span
                          className="w-2.5 h-2.5 rounded-full border border-[#0B1120]/15 shrink-0"
                          style={{ backgroundColor: hex }}
                        />
                        {hex.toUpperCase()}
                      </span>
                    ))}
                  </div>
                )}

                {(item.harmony_label || item.is_monochrome) && (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-lg bg-[#E8F5FE] text-[#0077C8] border border-[#BAE3FC] text-[10.5px] font-extrabold">
                    <Sparkles className="w-3 h-3 text-[#0098EA]" />
                    {item.harmony_label || 'Монохром'}
                  </span>
                )}
              </div>
            )}

            {/* 24h Trend Chip */}
            {item.trend_label && (
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="inline-flex items-center gap-1 px-2 py-1 rounded-xl bg-[#E8F5FE] border border-[#BAE3FC] text-[10.5px] font-bold text-[#0077C8] tabular-nums">
                  <Flame className="w-3 h-3 text-[#0098EA]" />
                  <span>{item.trend_label}</span>
                  {typeof item.trend_boost_percent === 'number' &&
                    item.trend_boost_percent > 0 && (
                      <span className="font-extrabold">
                        (+{item.trend_boost_percent}%)
                      </span>
                    )}
                </span>
              </div>
            )}

            {/* AI Vision Comment */}
            {item.ai_vision_comment && (
              <div className="rounded-xl p-2.5 bg-white border border-[#E2E8F0] text-[11.5px] text-[#334155] leading-snug">
                {item.ai_vision_comment}
              </div>
            )}

            {/* Deep AI Vision Check Button */}
            <button
              type="button"
              disabled={visionLoading}
              onClick={handleRunVisionScore}
              className="w-full h-9 rounded-xl bg-[#E8F5FE] hover:bg-[#D4ECFD] border border-[#BAE3FC] text-[#0077C8] text-[11.5px] font-extrabold flex items-center justify-center gap-1.5 transition-colors cursor-pointer disabled:opacity-60"
            >
              {visionLoading ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin text-[#0098EA]" />
                  <span>Аналізуємо композицію та палітру...</span>
                </>
              ) : (
                <>
                  <Eye className="w-3.5 h-3.5 text-[#0098EA]" />
                  <span>Перевірити через AI Vision</span>
                </>
              )}
            </button>
          </div>

          {/* X-Ray Recommendation */}
          {recommendation && (
            <div className="rounded-2xl p-3 bg-[#E8F5FE] border border-[#BAE3FC] flex items-start gap-2.5">
              <CheckCircle2 className="w-4 h-4 text-[#0098EA] shrink-0 mt-0.5" />
              <p className="text-[12px] font-semibold text-[#0B1120] leading-snug">
                {recommendation}
              </p>
            </div>
          )}

          {/* 4-Metric Valuation Grid */}
          <div className="grid grid-cols-2 gap-2">
            <div className="ton-card rounded-2xl p-3">
              <p className="text-[10.5px] font-semibold text-[#64748B]">Ціна зараз</p>
              <p className="text-[18px] font-extrabold text-[#0B1120] tabular-nums mt-0.5">
                {formatTon(item.price)}{' '}
                <span className="text-xs font-bold text-[#0098EA]">TON</span>
              </p>
              <p className="text-[10.5px] text-[#64748B] tabular-nums">
                {formatUsd(item.price, tonUsd)} · комісія {item.fee_percent}%
              </p>
            </div>

            <div className="ton-card rounded-2xl p-3">
              <p className="text-[10.5px] font-semibold text-[#64748B]">Флор колекції</p>
              <p className="text-[18px] font-extrabold text-[#0B1120] tabular-nums mt-0.5">
                {formatTon(item.collection_floor)}{' '}
                <span className="text-xs font-bold text-[#0098EA]">TON</span>
              </p>
              <p className="text-[10.5px] text-[#334155] tabular-nums">
                Дисконт:{' '}
                <span
                  className={
                    item.discount_percent > 0
                      ? 'font-bold text-[#0077C8]'
                      : 'font-bold text-[#64748B]'
                  }
                >
                  {formatPercent(item.discount_percent, false)}
                </span>
              </p>
            </div>

            <div className="ton-card rounded-2xl p-3 border-[#BAE3FC] bg-gradient-to-br from-white to-[#F2F9FF]">
              <p className="text-[10.5px] font-semibold text-[#0077C8]">
                Справедлива ціна (Fair Value)
              </p>
              <p className="text-[18px] font-extrabold text-[#0098EA] tabular-nums mt-0.5">
                {formatTon(item.fair_value)}{' '}
                <span className="text-xs font-bold">TON</span>
              </p>
              <p className="text-[10.5px] text-[#64748B] tabular-nums">
                {formatUsd(item.fair_value, tonUsd)}
              </p>
            </div>

            <div
              className={`ton-card rounded-2xl p-3 ${
                item.net_profit_ton > 0
                  ? 'border-[#BAE3FC] bg-gradient-to-br from-white to-[#E8F5FE]/65'
                  : 'border-[#E2E8F0] bg-[#F8FAFC]'
              }`}
            >
              <p className="text-[10.5px] font-semibold text-[#64748B]">
                Чистий профіт (після 5%)
              </p>
              <p
                className={`text-[18px] font-extrabold tabular-nums mt-0.5 ${
                  item.net_profit_ton > 0 ? 'text-[#0077C8]' : 'text-[#334155]'
                }`}
              >
                {item.net_profit_ton > 0 ? '+' : ''}
                {formatTon(item.net_profit_ton)}{' '}
                <span className="text-xs font-bold">TON</span>
              </p>
              <p
                className={`text-[10.5px] font-bold tabular-nums ${
                  item.net_profit_percent > 0 ? 'text-[#0098EA]' : 'text-[#64748B]'
                }`}
              >
                ROI {formatPercent(item.net_profit_percent)}
              </p>
            </div>
          </div>

          {/* Interactive Flip Profit Calculator */}
          <div className="ton-card rounded-2xl p-3 bg-gradient-to-r from-white to-[#F4F8FE] border-[#BAE3FC]">
            <div className="flex items-center justify-between gap-2 mb-2">
              <span className="text-[11.5px] font-extrabold text-[#0B1120] inline-flex items-center gap-1.5">
                <Calculator className="w-3.5 h-3.5 text-[#0098EA]" />
                Калькулятор фліпу
              </span>
              <span className="text-[10px] font-semibold text-[#64748B] tabular-nums">
                Комісія маркету {item.fee_percent}% (-{formatTon(calcFeeTon)} TON)
              </span>
            </div>
            <div className="flex items-center gap-2">
              <div className="flex-1">
                <label className="block text-[10px] font-bold text-[#64748B] mb-0.5">
                  Цільова ціна продажу (TON)
                </label>
                <input
                  type="number"
                  step="0.5"
                  min="0.1"
                  value={targetSell}
                  onChange={(e) => setTargetSell(e.target.value)}
                  className="w-full h-9 px-2.5 rounded-xl bg-white border border-[#BAE3FC] text-xs font-extrabold text-[#0B1120] tabular-nums focus:outline-none focus:border-[#0098EA]"
                />
              </div>
              <div className="text-right shrink-0 rounded-xl px-3 py-1.5 bg-white border border-[#E2E8F0] tabular-nums">
                <p className="text-[9.5px] font-bold text-[#64748B]">Чистий результат</p>
                <p
                  className={`text-[13.5px] font-extrabold ${
                    calcNetProfit >= 0 ? 'text-[#0077C8]' : 'text-[#0B1120]'
                  }`}
                >
                  {calcNetProfit >= 0 ? '+' : ''}
                  {formatTon(calcNetProfit)} TON ({calcRoi >= 0 ? '+' : ''}
                  {calcRoi.toFixed(1)}%)
                </p>
              </div>
            </div>
          </div>

          {/* Alerts: Rare Combo / Thin Floor / Wash Trade */}
          {item.is_rare_combo && (
            <div className="rounded-2xl p-3 bg-[#E8F5FE] border border-[#BAE3FC] flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-xl bg-[#0098EA] flex items-center justify-center shrink-0">
                <Sparkles className="w-4 h-4 text-white" />
              </div>
              <div>
                <p className="text-xs font-extrabold text-[#0B1120]">
                  Рідкісне Комбо виявлено
                </p>
                <p className="text-[11px] text-[#0077C8] font-medium">
                  {item.combo_label || 'Поєднання рідкісних атрибутів підвищує Fair Value'}
                </p>
              </div>
            </div>
          )}

          {item.thin_floor_warning && (
            <div className="rounded-2xl p-3 bg-[#F8FAFC] border border-[#CBD5E1] flex items-center gap-2.5">
              <Flame className="w-4 h-4 text-[#0098EA] shrink-0" />
              <p className="text-[11.5px] font-semibold text-[#0B1120]">
                Тонкий стакан: {item.thin_floor_warning}
              </p>
            </div>
          )}

          {item.wash_trade_risk && (
            <div className="rounded-2xl p-3 bg-[#F8FAFC] border border-[#CBD5E1] flex items-center gap-2.5">
              <ShieldAlert className="w-4 h-4 text-[#0098EA] shrink-0" />
              <p className="text-[11.5px] font-semibold text-[#0B1120]">
                Увага: виявлено ознаки штучних продажів (Wash-Trade Risk). Перевірте історію.
              </p>
            </div>
          )}

          {/* Traits Breakdown */}
          <div className="ton-card rounded-2xl p-3.5">
            <div className="flex items-center justify-between mb-2.5">
              <h3 className="text-xs font-extrabold text-[#0B1120] flex items-center gap-1.5">
                <Layers className="w-3.5 h-3.5 text-[#0098EA]" />
                Атрибути та флор кожного трейта
              </h3>
            </div>
            <div className="space-y-2">
              {(item.attributes || []).map((attr, idx) => (
                <div
                  key={`${attr.type}-${attr.value}-${idx}`}
                  className="flex items-center justify-between gap-2 px-3 py-2 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0]"
                >
                  <div className="min-w-0">
                    <span className="text-[10px] font-semibold uppercase tracking-wider text-[#64748B]">
                      {TRAIT_LABELS[attr.type] || attr.type}
                    </span>
                    <p className="text-[12.5px] font-bold text-[#0B1120] truncate">
                      {attr.value}
                    </p>
                  </div>
                  <div className="text-right shrink-0 tabular-nums">
                    <span className="inline-block px-1.5 py-0.5 rounded-md bg-[#E8F5FE] text-[#0077C8] text-[10px] font-extrabold">
                      {attr.rarity_percent.toFixed(1)}%
                    </span>
                    <p className="text-[11px] font-bold text-[#0B1120] mt-0.5">
                      Флор: {formatTon(attr.trait_floor)} TON
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Cross-Market Comparison */}
          <div className="ton-card rounded-2xl p-3.5">
            <div className="flex flex-wrap items-center justify-between gap-2 mb-2.5">
              <h3 className="text-xs font-extrabold text-[#0B1120]">
                Порівняння маркетів
              </h3>
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-lg bg-[#E8F5FE] text-[#0077C8] border border-[#BAE3FC] text-[10.5px] font-bold">
                <TrendingUp className="w-3 h-3" />
                Краще продати: {bestSellMeta.label} (~{formatTon(item.best_sell_price)} TON)
              </span>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {(item.market_prices || []).map((mp) => {
                const meta = getMarketMeta(mp.market);
                const isBest = mp.market === item.best_sell_market;
                const rowUrl =
                  mp.url ||
                  (mp.market === item.market && item.market_url ? item.market_url : null) ||
                  `https://t.me/nft/${item.tg_id}`;
                return (
                  <button
                    key={mp.market}
                    type="button"
                    onClick={() => {
                      haptic('light');
                      openExternalLink(rowUrl);
                    }}
                    className={`rounded-xl p-2.5 border text-left transition-colors cursor-pointer ${
                      isBest
                        ? 'bg-[#E8F5FE]/65 border-[#BAE3FC] hover:bg-[#D4ECFD]/60'
                        : 'bg-[#F8FAFC] border-[#E2E8F0] hover:border-[#BAE3FC]'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-1">
                      <span className={`inline-flex items-center gap-1 text-[11px] font-bold ${meta.text}`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${meta.dot}`} />
                        {meta.label}
                      </span>
                      <span
                        className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${
                          mp.is_live
                            ? 'bg-[#E8F5FE] text-[#0077C8]'
                            : 'bg-white text-[#64748B] border border-[#E2E8F0]'
                        }`}
                      >
                        {mp.is_live ? 'LIVE' : 'EST'}
                      </span>
                    </div>
                    <p className="text-[14px] font-extrabold text-[#0B1120] tabular-nums mt-1">
                      {formatTon(mp.floor_price)}{' '}
                      <span className="text-[10px] font-bold text-[#0098EA]">TON</span>
                    </p>
                    <p className="text-[10px] text-[#64748B] tabular-nums flex items-center justify-between">
                      <span>Комісія {mp.fee_percent}%</span>
                      <ExternalLink className="w-2.5 h-2.5 text-[#0098EA]" />
                    </p>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Recent Real Sales */}
          <div className="ton-card rounded-2xl p-3.5">
            <h3 className="text-xs font-extrabold text-[#0B1120] mb-2.5">
              Історія реальних продажів
            </h3>
            {salesList.length === 0 ? (
              <p className="text-xs text-[#64748B] text-center py-3">
                Немає нещодавніх угод
              </p>
            ) : (
              <div className="space-y-1.5">
                {salesList.slice(0, 6).map((sale, idx) => {
                  const sMeta = getMarketMeta(sale.market);
                  return (
                    <div
                      key={`${sale.timestamp}-${idx}`}
                      className="flex items-center justify-between px-2.5 py-2 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0] text-xs"
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        <span
                          className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md text-[10px] font-bold border ${sMeta.bg} ${sMeta.text} ${sMeta.border}`}
                        >
                          <span className={`w-1.5 h-1.5 rounded-full ${sMeta.dot}`} />
                          {sMeta.label}
                        </span>
                        <span className="text-[11px] text-[#64748B] truncate">
                          {sale.tx_type === 'offer_accepted' ? 'Прийнято офер' : 'Прямий продаж'}
                        </span>
                      </div>
                      <div className="text-right shrink-0 tabular-nums">
                        <span className="font-extrabold text-[#0B1120]">
                          {formatTon(sale.price)} TON
                        </span>
                        <span className="block text-[10px] text-[#64748B]">
                          {formatTimeAgo(sale.timestamp)}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* Sticky Bottom Action Bar */}
        <div className="bg-white border-t border-[#E2E8F0] px-3.5 sm:px-4 py-3 shrink-0 space-y-2">
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              disabled={busyAction !== null}
              onClick={() => handleAction('buy', onBuy)}
              className="ton-btn-primary h-11 rounded-xl font-bold text-[12.5px] flex items-center justify-center gap-1.5 cursor-pointer disabled:opacity-60"
            >
              <ShoppingCart className="w-4 h-4" />
              <span>
                {busyAction === 'buy'
                  ? 'Виконання...'
                  : `Купити (${dryRun ? 'DRY' : 'LIVE'})`}
              </span>
            </button>

            <button
              type="button"
              disabled={busyAction !== null}
              onClick={() => handleAction('offer', onMakeOffer)}
              className="h-11 rounded-xl bg-[#E8F5FE] hover:bg-[#D4ECFD] border border-[#BAE3FC] text-[#0077C8] font-bold text-[12.5px] flex items-center justify-center gap-1.5 transition-colors cursor-pointer disabled:opacity-60"
            >
              <Zap className="w-4 h-4" />
              <span>{busyAction === 'offer' ? 'Надсилаємо...' : 'Поставити офер'}</span>
            </button>
          </div>

          <div className="grid grid-cols-3 gap-2">
            <button
              type="button"
              onClick={() => {
                haptic('light');
                openExternalLink(`https://t.me/nft/${item.tg_id}`);
              }}
              className="h-9 rounded-xl bg-[#E8F5FE] hover:bg-[#D4ECFD] border border-[#BAE3FC] text-[#0077C8] font-bold text-[11px] flex items-center justify-center gap-1 cursor-pointer"
            >
              <ExternalLink className="w-3.5 h-3.5 text-[#0098EA] shrink-0" />
              <span className="truncate">Профіль</span>
            </button>

            <button
              type="button"
              onClick={() => {
                haptic('light');
                openExternalLink(item.market_url || `https://t.me/nft/${item.tg_id}`);
              }}
              className="h-9 rounded-xl bg-[#F8FAFC] hover:bg-[#E8F5FE] border border-[#E2E8F0] text-[#0B1120] font-bold text-[11px] flex items-center justify-center gap-1 cursor-pointer"
            >
              <ExternalLink className="w-3.5 h-3.5 text-[#0098EA] shrink-0" />
              <span className="truncate">Відкрити на маркеті</span>
            </button>

            <button
              type="button"
              disabled={busyAction !== null}
              onClick={() => handleAction('portfolio', onAddPortfolio)}
              className="h-9 rounded-xl bg-white hover:bg-[#F8FAFC] border border-[#E2E8F0] text-[#334155] font-bold text-[11px] flex items-center justify-center gap-1 cursor-pointer disabled:opacity-60"
            >
              <Briefcase className="w-3.5 h-3.5 text-[#0098EA] shrink-0" />
              <span className="truncate">У портфель</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
