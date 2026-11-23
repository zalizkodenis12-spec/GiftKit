import React, { useEffect, useState } from 'react';
import {
  BarChart3,
  Briefcase,
  Crosshair,
  Diamond,
  Download,
  Flame,
  PlusSquare,
  Share,
  SlidersHorizontal,
  X,
} from 'lucide-react';
import { getSessionToken } from '../api/client';
import type {
  BeforeInstallPromptEvent,
  OverviewResponse,
  TabKey,
  UserProfile,
} from '../types/api';
import { formatPercent, haptic, openExternalLink } from '../utils/format';

interface TopHeaderProps {
  overview: OverviewResponse | null;
  userProfile?: UserProfile | null;
  wsConnected: boolean;
  activeTab: TabKey;
  undercutCount: number;
  onChangeTab: (tab: TabKey) => void;
  onOpenXRay?: () => void;
  onOpenMarkets?: () => void;
  onOpenProfile?: () => void;
  onNotify: (
    title: string,
    message?: string,
    variant?: 'info' | 'success' | 'warning' | 'error',
  ) => void;
}

const DESKTOP_TABS: {
  key: TabKey;
  label: string;
  icon: React.FC<{ className?: string }>;
}[] = [
  { key: 'scanner', label: 'Сканер', icon: Flame },
  { key: 'analytics', label: 'Аналітика', icon: BarChart3 },
  { key: 'sniper', label: 'Снайпер', icon: Crosshair },
  { key: 'portfolio', label: 'Портфель', icon: Briefcase },
  { key: 'markets', label: 'Маркети', icon: SlidersHorizontal },
];

function isIosDevice(): boolean {
  if (typeof navigator === 'undefined') return false;
  const ua = navigator.userAgent;
  return (
    /iPad|iPhone|iPod/.test(ua) ||
    (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)
  );
}

function isInsideTelegramMiniApp(): boolean {
  if (typeof window === 'undefined') return false;
  const wa = window.Telegram?.WebApp as { initData?: string; platform?: string } | undefined;
  return Boolean(wa && (wa.initData || (wa.platform && wa.platform !== 'unknown')));
}

function isStandaloneMode(): boolean {
  if (typeof window === 'undefined') return false;
  const nav = navigator as Navigator & { standalone?: boolean };
  return (
    nav.standalone === true ||
    window.matchMedia?.('(display-mode: standalone)')?.matches === true ||
    window.matchMedia?.('(display-mode: minimal-ui)')?.matches === true ||
    window.matchMedia?.('(display-mode: window-controls-overlay)')?.matches === true ||
    window.matchMedia?.('(display-mode: fullscreen)')?.matches === true
  );
}

export const TopHeader: React.FC<TopHeaderProps> = ({
  overview,
  wsConnected,
  activeTab,
  undercutCount,
  onChangeTab,
  onNotify,
}) => {
  const [deferredPrompt, setDeferredPrompt] = useState<BeforeInstallPromptEvent | null>(null);
  const [installed, setInstalled] = useState<boolean>(() => isStandaloneMode());
  const [showIosGuide, setShowIosGuide] = useState<boolean>(false);

  useEffect(() => {
    const syncStandalone = () => {
      if (isStandaloneMode()) {
        setInstalled(true);
      }
    };
    syncStandalone();

    const handleBeforeInstall = (e: Event) => {
      e.preventDefault();
      setDeferredPrompt(e as BeforeInstallPromptEvent);
    };

    const handleAppInstalled = () => {
      setInstalled(true);
      setDeferredPrompt(null);
      setShowIosGuide(false);
      onNotify('GiftKit встановлено', 'Додаток доступний з головного екрану', 'success');
    };

    // If opened from Telegram Mini App with ?install=1 in Safari/Chrome, show install guide immediately
    try {
      const url = new URL(window.location.href);
      if (url.searchParams.get('install') === '1' && !isStandaloneMode() && !isInsideTelegramMiniApp()) {
        url.searchParams.delete('install');
        const cleanSearch = url.searchParams.toString();
        window.history.replaceState(
          {},
          '',
          `${url.pathname}${cleanSearch ? `?${cleanSearch}` : ''}${url.hash}`,
        );
        if (isIosDevice()) {
          setShowIosGuide(true);
        }
      }
    } catch {
      // ignore URL error
    }

    const mq = window.matchMedia?.('(display-mode: standalone)');
    mq?.addEventListener?.('change', syncStandalone);
    window.addEventListener('beforeinstallprompt', handleBeforeInstall);
    window.addEventListener('appinstalled', handleAppInstalled);
    return () => {
      mq?.removeEventListener?.('change', syncStandalone);
      window.removeEventListener('beforeinstallprompt', handleBeforeInstall);
      window.removeEventListener('appinstalled', handleAppInstalled);
    };
  }, [onNotify]);

  const handleInstallClick = async () => {
    haptic('light');

    // Inside Telegram Mini App: open GiftKit website directly in Safari/Chrome with user session
    // so iOS/Android installs the real GiftKit PWA (NOT t.me/GiftKit_bot!)
    if (isInsideTelegramMiniApp()) {
      const token = getSessionToken();
      const origin =
        typeof window !== 'undefined' && window.location.origin.startsWith('https://')
          ? window.location.origin
          : 'https://giftkit-ten.vercel.app';
      const params = new URLSearchParams({ install: '1' });
      if (token) params.set('tg_auth', token);
      const browserUrl = `${origin}/?${params.toString()}`;
      openExternalLink(browserUrl);
      return;
    }

    if (deferredPrompt) {
      try {
        await deferredPrompt.prompt();
        const choice = await deferredPrompt.userChoice;
        if (choice.outcome === 'accepted') {
          setInstalled(true);
        }
        setDeferredPrompt(null);
      } catch {
        // user dismissed or prompt unavailable
      }
      return;
    }

    if (isIosDevice()) {
      setShowIosGuide(true);
      return;
    }

    onNotify(
      'Встановлення GiftKit',
      'Натисніть меню браузера (три крапки) -> «Встановити додаток»',
      'info',
    );
  };

  const tonUsd = overview?.ton_usd ?? null;
  const tonChange = overview?.ton_change_24h ?? null;
  const isUp = (tonChange ?? 0) >= 0;
  const isLiveConnected = wsConnected || Boolean(overview);

  return (
    <header className="sticky top-0 z-30 w-full backdrop-blur-md bg-white/94 border-b border-[#E2E8F0]">
      <div className="w-full max-w-[1440px] mx-auto px-3 sm:px-5 lg:px-6 h-14 flex items-center justify-between gap-2 sm:gap-4">
        {/* Brand */}
        <button
          type="button"
          onClick={() => {
            haptic('light');
            onChangeTab('scanner');
          }}
          className="flex items-center gap-2.5 min-w-0 text-left cursor-pointer shrink-0"
        >
          <div className="relative flex items-center justify-center w-9 h-9 rounded-full overflow-hidden bg-[#0098EA] shadow-sm shrink-0 border border-[#BAE3FC]">
            <img
              src="/giftkit-logo.png"
              alt="GiftKit"
              className="w-full h-full object-cover rounded-full"
              onError={(e) => {
                (e.currentTarget as HTMLImageElement).style.display = 'none';
              }}
            />
            <Diamond className="w-4.5 h-4.5 text-white fill-white/25 -z-10 absolute" />
            <span
              title={isLiveConnected ? 'LIVE підключено' : 'Підключення до сервера...'}
              className={`absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full border-2 border-white ${
                isLiveConnected ? 'bg-[#0098EA]' : 'bg-[#64748B] animate-pulse'
              }`}
            />
          </div>
          <div className="min-w-0 leading-tight">
            <div className="flex items-center gap-1.5">
              <span className="font-display font-extrabold text-[15px] tracking-tight text-[#0B1120] truncate">
                GiftKit
              </span>
              <span className="hidden sm:inline-block text-[10px] font-bold px-1.5 py-0.5 rounded-md bg-[#E8F5FE] text-[#0077C8] border border-[#BAE3FC]">
                TON
              </span>
            </div>
            <div className="flex items-center gap-1.5 mt-0.5">
              <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-[#64748B] tabular-nums">
                <span className="text-[#0098EA] font-bold">TON</span>
                {tonUsd !== null ? (
                  <>
                    <span className="text-[#0B1120] font-bold">${tonUsd.toFixed(2)}</span>
                    <span
                      className={`font-bold ${
                        isUp ? 'text-[#0098EA]' : 'text-[#334155]'
                      }`}
                    >
                      {formatPercent(tonChange ?? 0)}
                    </span>
                  </>
                ) : (
                  <span className="text-[#64748B] font-semibold">синхронізація...</span>
                )}
              </span>
            </div>
          </div>
        </button>

        {/* Desktop Horizontal Navigation */}
        <nav
          aria-label="Основна навігація"
          className="hidden md:flex items-center gap-1 bg-[#F4F7FB] p-1 rounded-2xl border border-[#E2E8F0]"
        >
          {DESKTOP_TABS.map(({ key, label, icon: Icon }) => {
            const isActive = activeTab === key;
            return (
              <button
                key={key}
                type="button"
                onClick={() => {
                  haptic('light');
                  onChangeTab(key);
                }}
                className={`relative flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-[12.5px] font-bold transition-all cursor-pointer ${
                  isActive
                    ? 'bg-white text-[#0098EA] shadow-xs border border-[#BAE3FC]'
                    : 'text-[#64748B] hover:text-[#0B1120] hover:bg-white/60 border border-transparent'
                }`}
              >
                <Icon className={`w-4 h-4 ${isActive ? 'stroke-[2.3]' : 'stroke-[1.9]'}`} />
                <span>{label}</span>
                {key === 'portfolio' && undercutCount > 0 && (
                  <span className="min-w-[18px] h-[18px] px-1 flex items-center justify-center rounded-full bg-[#0098EA] text-white text-[10px] font-extrabold tabular-nums">
                    {undercutCount}
                  </span>
                )}
              </button>
            );
          })}
        </nav>

        {/* Right Controls — Install PWA (hidden automatically when running inside installed app) */}
        <div className="flex items-center gap-1.5 shrink-0">
          {!installed && (
            <button
              type="button"
              onClick={handleInstallClick}
              title="Встановити GiftKit як додаток"
              className="flex items-center gap-1.5 h-8 px-3 rounded-xl bg-[#F8FAFC] hover:bg-[#E8F5FE] text-[#0B1120] hover:text-[#0077C8] text-[11.5px] font-bold transition-colors cursor-pointer border border-[#E2E8F0] hover:border-[#BAE3FC]"
            >
              <Download className="w-3.5 h-3.5 text-[#0098EA]" />
              <span>Встановити</span>
            </button>
          )}
        </div>
      </div>

      {/* Clean iOS Safari Install Sheet */}
      {showIosGuide && !installed && (
        <div
          className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-[#0B1120]/45 backdrop-blur-xs p-3"
          onClick={() => setShowIosGuide(false)}
        >
          <div
            className="w-full max-w-sm bg-white rounded-3xl border border-[#E2E8F0] shadow-2xl p-5 space-y-4"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2.5">
                <img
                  src="/giftkit-logo.png"
                  alt="GiftKit"
                  className="w-10 h-10 rounded-2xl object-cover border border-[#BAE3FC]"
                />
                <div>
                  <h3 className="font-display text-[15px] font-extrabold text-[#0B1120]">
                    Встановити GiftKit
                  </h3>
                  <p className="text-[11px] font-medium text-[#64748B]">
                    На Початковий екран iPhone / iPad
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setShowIosGuide(false)}
                className="w-8 h-8 rounded-full bg-[#F4F7FB] flex items-center justify-center text-[#334155] cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-2.5 text-xs text-[#0B1120]">
              <div className="flex items-center gap-2.5 p-2.5 rounded-2xl bg-[#F4F7FB] border border-[#E2E8F0]">
                <span className="w-7 h-7 rounded-xl bg-white border border-[#BAE3FC] flex items-center justify-center shrink-0">
                  <Share className="w-3.5 h-3.5 text-[#0098EA]" />
                </span>
                <p className="font-semibold leading-snug">
                  1. Натисніть кнопку <b>«Поділитися»</b> у нижній панелі Safari
                </p>
              </div>
              <div className="flex items-center gap-2.5 p-2.5 rounded-2xl bg-[#F4F7FB] border border-[#E2E8F0]">
                <span className="w-7 h-7 rounded-xl bg-white border border-[#BAE3FC] flex items-center justify-center shrink-0">
                  <PlusSquare className="w-3.5 h-3.5 text-[#0098EA]" />
                </span>
                <p className="font-semibold leading-snug">
                  2. Оберіть <b>«На Початковий екран»</b> і натисніть <b>«Додати»</b>
                </p>
              </div>
            </div>

            <button
              type="button"
              onClick={() => setShowIosGuide(false)}
              className="w-full h-10 rounded-2xl ton-btn-primary text-xs font-extrabold cursor-pointer"
            >
              Зрозуміло
            </button>
          </div>
        </div>
      )}
    </header>
  );
};
