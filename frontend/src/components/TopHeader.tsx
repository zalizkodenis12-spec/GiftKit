import React, { useEffect, useState } from 'react';
import {
  BarChart3,
  Briefcase,
  Crosshair,
  Diamond,
  Download,
  Flame,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Zap,
} from 'lucide-react';
import type { BeforeInstallPromptEvent, OverviewResponse, TabKey } from '../types/api';
import { formatPercent, haptic } from '../utils/format';

interface TopHeaderProps {
  overview: OverviewResponse | null;
  wsConnected: boolean;
  activeTab: TabKey;
  undercutCount: number;
  onChangeTab: (tab: TabKey) => void;
  onOpenXRay: () => void;
  onOpenMarkets: () => void;
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

function isIosSafari(): boolean {
  if (typeof navigator === 'undefined') return false;
  const ua = navigator.userAgent;
  const isIOS = /iPad|iPhone|iPod/.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  return isIOS;
}

function isStandaloneMode(): boolean {
  if (typeof window === 'undefined') return false;
  const nav = navigator as Navigator & { standalone?: boolean };
  return (
    window.matchMedia?.('(display-mode: standalone)')?.matches === true ||
    nav.standalone === true
  );
}

export const TopHeader: React.FC<TopHeaderProps> = ({
  overview,
  wsConnected,
  activeTab,
  undercutCount,
  onChangeTab,
  onOpenXRay,
  onOpenMarkets,
  onNotify,
}) => {
  const [deferredPrompt, setDeferredPrompt] = useState<BeforeInstallPromptEvent | null>(null);
  const [installed, setInstalled] = useState<boolean>(() => isStandaloneMode());

  useEffect(() => {
    const handleBeforeInstall = (e: Event) => {
      e.preventDefault();
      setDeferredPrompt(e as BeforeInstallPromptEvent);
    };

    const handleAppInstalled = () => {
      setInstalled(true);
      setDeferredPrompt(null);
      onNotify('GiftKit встановлено', 'Додаток доступний з головного екрану', 'success');
    };

    window.addEventListener('beforeinstallprompt', handleBeforeInstall);
    window.addEventListener('appinstalled', handleAppInstalled);
    return () => {
      window.removeEventListener('beforeinstallprompt', handleBeforeInstall);
      window.removeEventListener('appinstalled', handleAppInstalled);
    };
  }, [onNotify]);

  const handleInstallClick = async () => {
    haptic('light');
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

    if (isIosSafari()) {
      onNotify(
        'Встановлення на iOS',
        'Натисніть «Поділитися» -> «На екран «Домой»»',
        'info',
      );
      return;
    }

    onNotify(
      'Встановлення GiftKit',
      'Відкрийте меню браузера або іконку встановлення в адресному рядку',
      'info',
    );
  };

  const tonUsd = overview?.ton_usd ?? null;
  const tonChange = overview?.ton_change_24h ?? null;
  const isUp = (tonChange ?? 0) >= 0;
  const isDryRun = overview?.dry_run ?? true;
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
          <div className="relative flex items-center justify-center w-9 h-9 rounded-xl overflow-hidden bg-[#0098EA] shadow-sm shrink-0 border border-[#BAE3FC]">
            <img
              src="/giftkit-logo.png"
              alt="GiftKit"
              className="w-full h-full object-cover"
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
          className="hidden lg:flex items-center gap-1 bg-[#F4F7FB] p-1 rounded-2xl border border-[#E2E8F0]"
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

        {/* Right Controls */}
        <div className="flex items-center gap-1.5 shrink-0">
          {!installed && (
            <button
              type="button"
              onClick={handleInstallClick}
              title="Встановити GiftKit як додаток (PWA)"
              className="flex items-center gap-1.5 h-8 px-2.5 rounded-xl bg-[#F8FAFC] hover:bg-[#E8F5FE] text-[#0B1120] hover:text-[#0077C8] text-[11px] font-bold transition-colors cursor-pointer border border-[#E2E8F0] hover:border-[#BAE3FC]"
            >
              <Download className="w-3.5 h-3.5 text-[#0098EA]" />
              <span className="hidden xs:inline sm:inline">Встановити</span>
            </button>
          )}

          <button
            type="button"
            onClick={onOpenXRay}
            title="Швидкий X-Ray аналіз NFT"
            className="flex items-center gap-1.5 h-8 px-2.5 rounded-xl bg-[#E8F5FE] hover:bg-[#D4ECFD] text-[#0077C8] text-[11px] font-bold transition-colors cursor-pointer border border-[#BAE3FC]"
          >
            <Search className="w-3.5 h-3.5" />
            <span>X-Ray</span>
          </button>

          <button
            type="button"
            onClick={onOpenMarkets}
            title={isDryRun ? 'Безпечний DRY-RUN режим' : 'Бойовий LIVE режим'}
            className={`flex items-center gap-1 h-8 px-2.5 rounded-xl text-[11px] font-bold border transition-colors cursor-pointer ${
              isDryRun
                ? 'bg-[#F8FAFC] text-[#0B1120] border-[#CBD5E1] hover:border-[#94A3B8]'
                : 'bg-[#0098EA] text-white border-[#0098EA] hover:bg-[#0077C8]'
            }`}
          >
            {isDryRun ? (
              <>
                <ShieldCheck className="w-3.5 h-3.5 text-[#0098EA]" />
                <span>DRY</span>
              </>
            ) : (
              <>
                <Zap className="w-3.5 h-3.5 fill-current" />
                <span>LIVE</span>
              </>
            )}
          </button>
        </div>
      </div>
    </header>
  );
};
