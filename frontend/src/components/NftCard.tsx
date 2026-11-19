import React from 'react';
import { AlertTriangle, Eye, Flame, Hash, Sparkles, TrendingUp } from 'lucide-react';
import type { AnalyzedListing } from '../types/api';
import { formatTon, getMarketMeta, haptic } from '../utils/format';
import { NftImage } from './NftImage';

interface NftCardProps {
  item: AnalyzedListing;
  tonUsd: number;
  onSelect: (item: AnalyzedListing) => void;
}

export const NftCard: React.FC<NftCardProps> = ({ item, tonUsd, onSelect }) => {
  const marketMeta = getMarketMeta(item.market);
  const modelAttr = item.attributes?.find((a) => a.type === 'model');
  const hasGoodDiscount = item.discount_percent >= 5;
  const isProfitable = item.net_profit_ton > 0;
  const visualScore = typeof item.visual_score === 'number' ? item.visual_score : null;
  const hasHighVisual = visualScore !== null && visualScore >= 7.8;
  const swatches = (item.color_swatches || []).filter(Boolean).slice(0, 3);
  const highlightTag =
    item.harmony_label ||
    item.number_pattern ||
    item.symbol_badge ||
    item.trend_label ||
    null;

  return (
    <button
      type="button"
      onClick={() => {
        haptic('light');
        onSelect(item);
      }}
      className="group text-left ton-card ton-card-hover rounded-2xl overflow-hidden flex flex-col cursor-pointer focus:outline-none focus:ring-2 focus:ring-[#0098EA]/40"
    >
      {/* Square NFT Preview */}
      <div className="relative aspect-square w-full bg-[#F4F7FB] overflow-hidden">
        <NftImage
          src={item.photo_url}
          alt={`${item.collection_name} #${item.number}`}
          fallbackText={item.collection_name}
          className="w-full h-full object-cover group-hover:scale-[1.03] transition-transform duration-300"
        />

        {/* Top-Left Market Pill */}
        <span
          className={`absolute top-2 left-2 inline-flex items-center gap-1 px-2 py-0.5 rounded-lg text-[10px] font-bold border backdrop-blur-md bg-white/94 shadow-xs ${marketMeta.text} ${marketMeta.border}`}
        >
          <span className={`w-1.5 h-1.5 rounded-full ${marketMeta.dot}`} />
          {marketMeta.label}
        </span>

        {/* Top-Right Discount, Visual Score & Combo Pills */}
        <div className="absolute top-2 right-2 flex flex-col items-end gap-1">
          {hasGoodDiscount && (
            <span className="px-2 py-0.5 rounded-lg text-[10px] font-extrabold tabular-nums bg-[#0098EA] text-white shadow-sm">
              -{Math.round(item.discount_percent)}%
            </span>
          )}
          {hasHighVisual && (
            <span
              title="Візуальна оцінка Очі GiftKit"
              className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-lg text-[10px] font-extrabold tabular-nums bg-[#0098EA] text-white border border-[#BAE3FC]/50 shadow-xs"
            >
              <Eye className="w-2.5 h-2.5 text-white" />
              {visualScore.toFixed(1)}
            </span>
          )}
          {item.is_rare_combo && (
            <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-lg text-[10px] font-extrabold bg-[#0077C8] text-white border border-[#BAE3FC]/40 backdrop-blur-sm shadow-xs">
              <Sparkles className="w-2.5 h-2.5 text-white" />
              Комбо
            </span>
          )}
        </div>

        {/* Bottom-Left Number Pill */}
        <span className="absolute bottom-2 left-2 px-2 py-0.5 rounded-lg text-[10px] font-bold tabular-nums bg-white/94 text-[#0B1120] border border-[#E2E8F0] backdrop-blur-md">
          #{item.number}
        </span>

        {/* Bottom-Right Special Badge (Wash Risk / Number Badge) */}
        {item.wash_trade_risk ? (
          <span
            title="Ризик накрутки об'ємів"
            className="absolute bottom-2 right-2 inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-lg text-[9px] font-bold bg-[#F8FAFC]/95 text-[#334155] border border-[#CBD5E1]"
          >
            <AlertTriangle className="w-2.5 h-2.5 text-[#0098EA]" />
            Wash
          </span>
        ) : item.number_badge ? (
          <span className="absolute bottom-2 right-2 px-1.5 py-0.5 rounded-lg text-[9px] font-bold bg-[#E8F5FE]/95 text-[#0077C8] border border-[#BAE3FC]">
            {item.number_badge}
          </span>
        ) : null}
      </div>

      {/* Card Body */}
      <div className="p-2.5 flex-1 flex flex-col justify-between gap-1.5 bg-white">
        <div className="space-y-1">
          <h3 className="text-[12.5px] font-bold text-[#0B1120] leading-tight truncate">
            {item.collection_name}
          </h3>

          {/* Model Name + 3 Real Pixel Color Swatches */}
          <div className="flex items-center justify-between gap-1.5">
            <p className="text-[11px] text-[#64748B] truncate min-w-0">
              {modelAttr ? (
                <>
                  <span className="font-medium text-[#334155]">{modelAttr.value}</span>
                  <span className="text-[#64748B] tabular-nums">
                    {' '}
                    · {modelAttr.rarity_percent.toFixed(1)}%
                  </span>
                </>
              ) : (
                <span>Лікв. {item.liquidity_score}/100</span>
              )}
            </p>

            {swatches.length > 0 && (
              <div
                className="flex items-center -space-x-1 shrink-0"
                title={`Палітра пікселів: ${swatches.join(', ')}`}
              >
                {swatches.map((hex, idx) => (
                  <span
                    key={`${hex}-${idx}`}
                    className="w-[10px] h-[10px] rounded-full ring-[1.5px] ring-white border border-[#0B1120]/15 shadow-2xs"
                    style={{ backgroundColor: hex }}
                  />
                ))}
              </div>
            )}
          </div>

          {/* Harmony / Trend / Nice Number Tag */}
          {highlightTag && (
            <div className="pt-0.5">
              <span className="inline-flex items-center gap-1 max-w-full px-1.5 py-0.5 rounded-md bg-[#E8F5FE] text-[#0077C8] border border-[#BAE3FC] text-[9.5px] font-bold truncate">
                {item.harmony_label ? (
                  <Sparkles className="w-2.5 h-2.5 shrink-0 text-[#0098EA]" />
                ) : item.trend_label ? (
                  <Flame className="w-2.5 h-2.5 shrink-0 text-[#0098EA]" />
                ) : (
                  <Hash className="w-2.5 h-2.5 shrink-0 text-[#0098EA]" />
                )}
                <span className="truncate">{highlightTag}</span>
              </span>
            </div>
          )}
        </div>

        {/* Price Row */}
        <div className="pt-1.5 border-t border-[#F1F5F9]">
          <div className="flex items-baseline justify-between gap-1">
            <div className="flex items-baseline gap-1 tabular-nums">
              <span className="text-[15px] font-extrabold text-[#0B1120]">
                {formatTon(item.price)}
              </span>
              <span className="text-[11px] font-bold text-[#0098EA]">TON</span>
            </div>
            <span className="text-[10px] font-medium text-[#64748B] tabular-nums">
              ≈${(item.price * tonUsd).toFixed(1)}
            </span>
          </div>

          {/* Floor vs Fair Value */}
          <div className="flex items-center justify-between text-[10px] text-[#64748B] mt-1 tabular-nums">
            <span>Флор: {formatTon(item.collection_floor, 1)}</span>
            <span className="text-[#0077C8] font-bold">
              Оцінка: {formatTon(item.fair_value, 1)}
            </span>
          </div>

          {/* Net Profit Pill */}
          <div className="mt-1.5 flex items-center justify-between gap-1">
            <span
              className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-lg text-[10.5px] font-bold tabular-nums ${
                isProfitable
                  ? 'bg-[#E8F5FE] text-[#0077C8]'
                  : 'bg-[#F8FAFC] text-[#64748B]'
              }`}
            >
              {isProfitable && <TrendingUp className="w-3 h-3" />}
              {isProfitable ? '+' : ''}
              {formatTon(item.net_profit_ton)} TON
            </span>
            <span className="text-[10px] font-semibold text-[#64748B] tabular-nums">
              {item.sales_24h} пр/24г
            </span>
          </div>
        </div>
      </div>
    </button>
  );
};
