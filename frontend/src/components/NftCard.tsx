import React from 'react';
import { TrendingDown, TrendingUp } from 'lucide-react';
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
  const backdropAttr = item.attributes?.find((a) => a.type === 'backdrop');
  const symbolAttr = item.attributes?.find((a) => a.type === 'symbol');
  const isProfitable = item.net_profit_ton >= 0;

  return (
    <button
      type="button"
      onClick={() => {
        haptic('light');
        onSelect(item);
      }}
      className="group text-left ton-card ton-card-hover rounded-2xl overflow-hidden flex flex-col cursor-pointer focus:outline-none focus:ring-2 focus:ring-[#0098EA]/40"
    >
      {/* Square NFT Preview — ONLY Market Source (top-left) & Number (bottom-left) */}
      <div className="relative aspect-square w-full bg-[#F4F7FB] overflow-hidden">
        <NftImage
          src={item.photo_url}
          alt={`${item.collection_name} #${item.number}`}
          fallbackText={item.collection_name}
          collectionName={item.collection_name}
          shortName={item.short_name}
          modelName={modelAttr?.value}
          backdropName={backdropAttr?.value}
          symbolName={symbolAttr?.value}
          className="w-full h-full object-cover group-hover:scale-[1.03] transition-transform duration-300"
        />

        {/* Top-Left Market Pill */}
        <span
          className={`absolute top-2 left-2 inline-flex items-center gap-1 px-2 py-0.5 rounded-lg text-[10px] font-bold border backdrop-blur-md bg-white/94 shadow-xs ${marketMeta.text} ${marketMeta.border}`}
        >
          <span className={`w-1.5 h-1.5 rounded-full ${marketMeta.dot}`} />
          {marketMeta.label}
        </span>

        {/* Optional Top-Right 1:1 Visual Similarity Pill (shown in Visual Twins mode) */}
        {typeof item.similarity_percent === 'number' && (
          <span className="absolute top-2 right-2 px-2 py-0.5 rounded-lg text-[10px] font-extrabold tabular-nums bg-[#0098EA] text-white shadow-xs">
            {item.similarity_percent}%
          </span>
        )}

        {/* Bottom-Left Number Pill */}
        <span className="absolute bottom-2 left-2 px-2 py-0.5 rounded-lg text-[10px] font-bold tabular-nums bg-white/94 text-[#0B1120] border border-[#E2E8F0] backdrop-blur-md">
          #{item.number}
        </span>
      </div>

      {/* Card Body — Clean & Minimal */}
      <div className="p-2.5 flex-1 flex flex-col justify-between gap-2 bg-white">
        <div className="space-y-0.5">
          <h3 className="text-[13px] font-extrabold text-[#0B1120] leading-tight truncate">
            {item.collection_name}
          </h3>

          <p className="text-[11px] text-[#64748B] truncate">
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
        </div>

        {/* Price & Valuation */}
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

          {/* Full-Width Profit / Delta Pill */}
          <div className="mt-2">
            <span
              className={`w-full inline-flex items-center justify-center gap-1 px-2.5 py-1.5 rounded-xl text-[11px] font-extrabold tabular-nums ${
                isProfitable
                  ? 'bg-[#E8F5FE] text-[#0077C8]'
                  : 'bg-[#F4F7FB] text-[#64748B]'
              }`}
            >
              {isProfitable ? (
                <TrendingUp className="w-3.5 h-3.5 shrink-0" />
              ) : (
                <TrendingDown className="w-3.5 h-3.5 shrink-0" />
              )}
              <span>
                {isProfitable ? '+' : ''}
                {formatTon(item.net_profit_ton)} TON
              </span>
            </span>
          </div>
        </div>
      </div>
    </button>
  );
};
