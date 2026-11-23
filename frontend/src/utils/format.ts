import type { VerdictType } from '../types/api';

export function formatTon(value: number | null | undefined, decimals = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '0.00';
  const abs = Math.abs(value);
  if (abs >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}M`;
  if (abs >= 10_000) return `${(value / 1_000).toFixed(1)}K`;
  if (abs >= 100) return value.toFixed(1);
  return value.toFixed(decimals);
}

export function formatUsd(ton: number | null | undefined, tonUsd = 1.03): string {
  if (ton === null || ton === undefined || Number.isNaN(ton)) return '$0.00';
  const usd = ton * tonUsd;
  if (Math.abs(usd) >= 1_000_000) return `$${(usd / 1_000_000).toFixed(2)}M`;
  if (Math.abs(usd) >= 10_000) return `$${(usd / 1_000).toFixed(1)}K`;
  return `$${usd.toFixed(2)}`;
}

export function formatPercent(value: number | null | undefined, signed = true): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '0%';
  const prefix = signed && value > 0 ? '+' : '';
  return `${prefix}${value.toFixed(1)}%`;
}

export function formatTimeAgo(iso?: string | null): string {
  if (!iso) return 'щойно';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const diffSec = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
  if (diffSec < 45) return 'щойно';
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin} хв тому`;
  const diffHours = Math.floor(diffMin / 60);
  if (diffHours < 24) return `${diffHours} год тому`;
  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays} дн тому`;
}

export interface MarketBadgeMeta {
  label: string;
  bg: string;
  text: string;
  border: string;
  dot: string;
}

export function getMarketMeta(market?: string): MarketBadgeMeta {
  const key = (market || '').toLowerCase();
  const labelMap: Record<string, string> = {
    portals: 'Portals',
    getgems: 'Getgems',
    mrkt: 'MRKT',
    tonnel: 'Tonnel',
    fragment: 'Fragment',
  };
  return {
    label: labelMap[key] || (market ? market.toUpperCase() : 'TON'),
    bg: 'bg-[#F8FAFC]',
    text: 'text-[#0B1120]',
    border: 'border-[#E2E8F0]',
    dot: 'bg-[#0098EA]',
  };
}

export function getVerdictStyle(verdict: VerdictType | string) {
  switch (verdict) {
    case 'STRONG_BUY':
      return {
        label: 'Супер фліп',
        badge: 'bg-[#0098EA] text-white border-[#0098EA]',
        solid: 'bg-[#0098EA] text-white',
      };
    case 'GOOD_DEAL':
      return {
        label: 'Вигідно',
        badge: 'bg-[#E8F5FE] text-[#0077C8] border-[#BAE3FC]',
        solid: 'bg-[#0077C8] text-white',
      };
    case 'OVERPRICED':
      return {
        label: 'Оверпрайс',
        badge: 'bg-[#F1F5F9] text-[#475569] border-[#CBD5E1]',
        solid: 'bg-[#475569] text-white',
      };
    default:
      return {
        label: 'Ринок',
        badge: 'bg-[#F8FAFC] text-[#334155] border-[#CBD5E1]',
        solid: 'bg-[#334155] text-white',
      };
  }
}

export function getLiquidityColor(score: number): string {
  if (score >= 75) return 'bg-[#0098EA]';
  if (score >= 45) return 'bg-[#38BDF8]';
  return 'bg-[#64748B]';
}

export function haptic(style: 'light' | 'medium' | 'success' | 'warning' = 'light') {
  try {
    const h = window.Telegram?.WebApp?.HapticFeedback;
    if (!h) return;
    if (style === 'success' || style === 'warning') {
      h.notificationOccurred?.(style);
    } else {
      h.impactOccurred?.(style);
    }
  } catch {
    // ignore outside Telegram
  }
}

export function openExternalLink(url?: string | null): void {
  if (!url) return;
  try {
    const wa = window.Telegram?.WebApp as
      | { openTelegramLink?: (u: string) => void; openLink?: (u: string) => void }
      | undefined;
    if ((url.startsWith('https://t.me/') || url.startsWith('tg://')) && typeof wa?.openTelegramLink === 'function') {
      wa.openTelegramLink(url);
      return;
    }
    if ((url.startsWith('https://') || url.startsWith('http://')) && typeof wa?.openLink === 'function') {
      wa.openLink(url);
      return;
    }
  } catch {
    // fallback to window.open
  }
  window.open(url, '_blank', 'noopener,noreferrer');
}
