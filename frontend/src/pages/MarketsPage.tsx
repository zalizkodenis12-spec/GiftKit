import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Bot,
  ChevronDown,
  ChevronUp,
  Cloud,
  ExternalLink,
  Eye,
  Globe,
  KeyRound,
  Lock,
  Save,
  Send,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  UserCheck,
  Wallet,
} from 'lucide-react';
import { api } from '../api/client';
import type { AppSettings, OverviewResponse, UserProfile } from '../types/api';
import { formatTon, getMarketMeta, haptic } from '../utils/format';

interface MarketsPageProps {
  overview: OverviewResponse | null;
  userProfile: UserProfile | null;
  onUserSynced: (user: UserProfile) => void;
  onSettingsSaved: () => Promise<void>;
  onNotify: (title: string, message?: string, variant?: 'info' | 'success' | 'warning' | 'error') => void;
}

const DEFAULT_SETTINGS: AppSettings = {
  dry_run: true,
  daily_limit_ton: 150,
  daily_spent_ton: 0,
  max_single_buy_ton: 50,
  stop_loss_percent: 15,
  wallet_address: '',
  wallet_balance_ton: 0,
  tg_bot_token: '',
  tg_admin_chat_id: '',
  webapp_url: '',
  getgems_api_key: '',
  portals_init_data: '',
  mrkt_init_data: '',
  tonnel_init_data: '',
  gemini_api_key: '',
  openai_api_key: '',
};

const MARKET_DEFINITIONS = [
  {
    key: 'portals',
    name: 'Portals',
    field: 'portals_init_data' as const,
    fieldLabel: 'Portals initData (опц. для автопокупки)',
    fee: '5%',
    desc: 'Основний маркет Telegram Gifts з миттєвим API',
  },
  {
    key: 'getgems',
    name: 'Getgems',
    field: 'getgems_api_key' as const,
    fieldLabel: 'Getgems API Key (GraphQL)',
    fee: '5%',
    desc: 'Найбільший ончейн TON NFT маркетплейс',
  },
  {
    key: 'mrkt',
    name: 'MRKT',
    field: 'mrkt_init_data' as const,
    fieldLabel: 'MRKT Telegram initData',
    fee: '4%',
    desc: 'Офчейн-маркет з високою ліквідністю оферів',
  },
  {
    key: 'tonnel',
    name: 'Tonnel',
    field: 'tonnel_init_data' as const,
    fieldLabel: 'Tonnel Network initData',
    fee: '4%',
    desc: 'Часті арбітражні розбіжності по флору',
  },
  {
    key: 'fragment',
    name: 'Fragment',
    field: null,
    fieldLabel: '',
    fee: '5%',
    desc: 'Публічний моніторинг аукціонів та номерів',
  },
];

export const MarketsPage: React.FC<MarketsPageProps> = ({
  overview,
  userProfile,
  onUserSynced,
  onSettingsSaved,
  onNotify,
}) => {
  const [settings, setSettings] = useState<AppSettings>(DEFAULT_SETTINGS);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testingTg, setTestingTg] = useState(false);
  const [expandedMarket, setExpandedMarket] = useState<string | null>(null);
  const [linkingTg, setLinkingTg] = useState(false);
  const [avatarErr, setAvatarErr] = useState(false);
  const pollTimerRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (pollTimerRef.current !== null) {
        window.clearInterval(pollTimerRef.current);
      }
    };
  }, []);

  const handleLinkBrowserViaBot = async () => {
    haptic('medium');
    if (pollTimerRef.current !== null) {
      window.clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
    setLinkingTg(true);
    try {
      const codeRes = await api.createLoginCode();
      if (codeRes.bot_login_url) {
        window.open(codeRes.bot_login_url, '_blank', 'noopener,noreferrer');
      }
      onNotify(
        'Підтвердіть вхід у Telegram',
        'Натисніть Start у @GiftKit_bot — синхронізація відбудеться автоматично',
        'info',
      );

      let attempts = 0;
      pollTimerRef.current = window.setInterval(async () => {
        attempts += 1;
        if (attempts > 30) {
          if (pollTimerRef.current !== null) {
            window.clearInterval(pollTimerRef.current);
            pollTimerRef.current = null;
          }
          setLinkingTg(false);
          return;
        }
        try {
          const pollRes = await api.pollLoginCode(codeRes.nonce);
          if (pollRes.ready && pollRes.user) {
            if (pollTimerRef.current !== null) {
              window.clearInterval(pollTimerRef.current);
              pollTimerRef.current = null;
            }
            setLinkingTg(false);
            onUserSynced(pollRes.user);
            onNotify(
              'Telegram акаунт синхронізовано!',
              `${pollRes.user.first_name || ''} ${
                pollRes.user.username ? `(@${pollRes.user.username})` : ''
              } · правила та портфель завантажено`,
              'success',
            );
          }
        } catch {
          // continue polling
        }
      }, 2000);
    } catch (err) {
      setLinkingTg(false);
      onNotify(
        'Не вдалося створити код прив’язки',
        err instanceof Error ? err.message : '',
        'error',
      );
    }
  };

  const loadSettings = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.getSettings();
      setSettings({ ...DEFAULT_SETTINGS, ...data });
    } catch {
      // keep defaults if offline
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSettings();
  }, [loadSettings]);

  const handleSave = async () => {
    haptic('medium');
    setSaving(true);
    try {
      const updated = await api.updateSettings(settings);
      setSettings({ ...DEFAULT_SETTINGS, ...updated });
      await onSettingsSaved();
      onNotify(
        'Налаштування збережено',
        settings.dry_run
          ? 'Активний безпечний DRY-RUN режим'
          : 'Увага: LIVE-режим торгівлі активовано!',
        'success',
      );
    } catch (err) {
      onNotify('Помилка збереження', err instanceof Error ? err.message : '', 'error');
    } finally {
      setSaving(false);
    }
  };

  const handleTestTelegram = async () => {
    haptic('light');
    setTestingTg(true);
    try {
      const res = await api.testTelegram();
      onNotify(
        res.ok ? 'Telegram Бот на зв’язку!' : 'Telegram Бот не налаштований',
        res.message ||
          res.detail ||
          (res.ok ? 'Тестове повідомлення доставлено' : 'Перевірте токен і Chat ID'),
        res.ok ? 'success' : 'warning',
      );
    } catch (err) {
      onNotify('Помилка перевірки ТГ', err instanceof Error ? err.message : '', 'error');
    } finally {
      setTestingTg(false);
    }
  };

  const connectDemoWallet = () => {
    haptic('success');
    setSettings((prev) => ({
      ...prev,
      wallet_address: 'UQD9x7mK2pL8vN4qR6wT3yB5cF1hJ0sA8eG7uP2zX9kM4nW',
      wallet_balance_ton: prev.wallet_balance_ton || 248.6,
    }));
    onNotify('Демо-гаманець підключено', 'Натисніть «Зберегти налаштування» нижче', 'info');
  };

  const disconnectWallet = () => {
    haptic('light');
    setSettings((prev) => ({
      ...prev,
      wallet_address: '',
      wallet_balance_ton: 0,
    }));
  };

  const getMarketStatusBadge = (marketKey: string) => {
    const fromSettings = settings.markets_status?.find(
      (m) => m.market.toLowerCase() === marketKey,
    );
    const liveList = overview?.live_markets || ['portals', 'getgems'];
    const isLive =
      fromSettings?.is_live ??
      (fromSettings?.status === 'LIVE' || liveList.includes(marketKey));

    if (isLive) {
      return {
        label: 'LIVE',
        cls: 'bg-[#E8F5FE] text-[#0077C8] border-[#BAE3FC]',
      };
    }
    const keyField = MARKET_DEFINITIONS.find((m) => m.key === marketKey)?.field;
    const hasKey = Boolean(keyField && settings[keyField]);
    if (hasKey) {
      return {
        label: 'API OK',
        cls: 'bg-[#E8F5FE] text-[#0098EA] border-[#BAE3FC]',
      };
    }
    return {
      label: 'EST',
      cls: 'bg-[#F8FAFC] text-[#334155] border-[#CBD5E1]',
    };
  };

  if (loading) {
    return (
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 pb-4">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="ton-card rounded-2xl p-5 h-44 animate-pulse" />
        ))}
      </div>
    );
  }

  const isConnected = Boolean(settings.wallet_address?.trim());
  const hasVisionKey = Boolean(
    settings.gemini_api_key?.trim() || settings.openai_api_key?.trim(),
  );
  const displayUserId =
    userProfile?.tg_user_id || settings.tg_admin_chat_id || 'TG Auth';
  const displayFullName =
    [userProfile?.first_name, userProfile?.last_name].filter(Boolean).join(' ') ||
    'Власник GiftKit';
  const displayUsername = userProfile?.username ? `@${userProfile.username}` : '@GiftKit_Owner';
  const initials = (userProfile?.first_name || userProfile?.username || 'GK')
    .slice(0, 2)
    .toUpperCase();

  return (
    <div className="space-y-4 pb-6">
      {/* Telegram Profile & Cross-Device Cloud Sync Card */}
      <section className="ton-card rounded-2xl p-4 sm:p-5 border-[#BAE3FC] bg-gradient-to-br from-white via-white to-[#F0F8FF] space-y-3.5">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            {userProfile?.photo_url && !avatarErr ? (
              <img
                src={userProfile.photo_url}
                alt={displayFullName}
                onError={() => setAvatarErr(true)}
                className="w-12 h-12 rounded-2xl object-cover border-2 border-[#0098EA] shadow-xs shrink-0"
              />
            ) : (
              <div className="w-12 h-12 rounded-2xl bg-[#0098EA] text-white font-display font-extrabold text-base flex items-center justify-center border-2 border-[#BAE3FC] shadow-xs shrink-0">
                {initials}
              </div>
            )}

            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h2 className="font-display text-[15px] font-extrabold text-[#0B1120] truncate">
                  Профіль Telegram та Хмарна Синхронізація
                </h2>
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-lg bg-[#0098EA] text-white text-[10px] font-extrabold">
                  <Cloud className="w-3 h-3" />
                  Хмарна синхронізація активна (ПК + Телефон)
                </span>
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-lg bg-[#E8F5FE] text-[#0077C8] border border-[#BAE3FC] text-[10px] font-extrabold">
                  <Lock className="w-2.5 h-2.5" />
                  Захищено HMAC-SHA256
                </span>
              </div>

              <div className="flex items-center gap-2 flex-wrap mt-1 text-xs">
                <span className="font-extrabold text-[#0B1120]">{displayFullName}</span>
                <span className="text-[#0077C8] font-bold">{displayUsername}</span>
                <span className="px-2 py-0.5 rounded-md bg-[#F4F7FB] border border-[#E2E8F0] font-mono text-[11px] font-bold text-[#334155] tabular-nums">
                  ID: {displayUserId}
                </span>
              </div>
            </div>
          </div>

          <button
            type="button"
            disabled={linkingTg}
            onClick={handleLinkBrowserViaBot}
            className="ton-btn-primary h-10 px-3.5 rounded-xl text-xs font-extrabold inline-flex items-center justify-center gap-1.5 shrink-0 cursor-pointer disabled:opacity-60"
          >
            <UserCheck className="w-4 h-4" />
            <span>
              {linkingTg
                ? 'Очікуємо підтвердження в @GiftKit_bot...'
                : 'Прив’язати цей браузер / PWA через @GiftKit_bot'}
            </span>
            <ExternalLink className="w-3.5 h-3.5" />
          </button>
        </div>

        <p className="text-[11.5px] text-[#334155] leading-relaxed bg-[#F8FAFC] border border-[#E2E8F0] rounded-xl px-3 py-2">
          Ваш акаунт жорстко прив&apos;язаний до вашого Telegram ID. Усі правила снайпера, активні
          офери та портфель автоматично синхронізуються між телефоном та комп&apos;ютером. Доступ
          сторонніх осіб заблоковано криптографічним підписом.
        </p>
      </section>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-start">
        {/* Left Column: Wallet + Markets Status */}
        <div className="space-y-4">
          {/* TON Connect Wallet Card */}
          <section className="ton-card rounded-2xl p-4 space-y-3">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-xl ton-btn-primary flex items-center justify-center shrink-0">
                  <Wallet className="w-4 h-4 text-white" />
                </div>
                <div>
                  <h2 className="font-display text-[14px] font-extrabold text-[#0B1120]">
                    TON Connect Гаманець
                  </h2>
                  <p className="text-[10.5px] text-[#64748B]">
                    Для автопокупок, оферів та перевірки балансу
                  </p>
                </div>
              </div>
              <span
                className={`px-2 py-0.5 rounded-lg text-[10px] font-extrabold border ${
                  isConnected
                    ? 'bg-[#E8F5FE] text-[#0077C8] border-[#BAE3FC]'
                    : 'bg-[#F8FAFC] text-[#64748B] border-[#E2E8F0]'
                }`}
              >
                {isConnected ? 'Підключено' : 'Не підключено'}
              </span>
            </div>

            <div className="space-y-2 text-xs">
              <input
                type="text"
                value={settings.wallet_address}
                onChange={(e) => setSettings({ ...settings, wallet_address: e.target.value })}
                placeholder="Вставте TON-адресу (UQ... / EQ...)"
                className="w-full h-10 px-3 rounded-xl bg-[#F4F7FB] border border-[#E2E8F0] font-mono text-[11.5px] text-[#0B1120] focus:outline-none focus:border-[#0098EA]"
              />

              {isConnected ? (
                <div className="flex items-center justify-between px-3 py-2 rounded-xl bg-[#E8F5FE] border border-[#BAE3FC]">
                  <div className="tabular-nums">
                    <span className="text-[10.5px] text-[#0077C8] font-semibold">
                      Доступний баланс
                    </span>
                    <p className="text-sm font-extrabold text-[#0B1120]">
                      {formatTon(settings.wallet_balance_ton ?? 248.6)} TON
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={disconnectWallet}
                    className="px-3 py-1.5 rounded-xl bg-white text-[#DC2626] border border-[#FECACA] text-[11px] font-bold cursor-pointer"
                  >
                    Відключити
                  </button>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={connectDemoWallet}
                  className="w-full h-9 rounded-xl bg-[#E8F5FE] hover:bg-[#D4ECFD] text-[#0077C8] text-xs font-extrabold inline-flex items-center justify-center gap-1.5 cursor-pointer transition-colors border border-[#BAE3FC]"
                >
                  <Wallet className="w-3.5 h-3.5" />
                  <span>Підключити демо-гаманець Tonkeeper</span>
                </button>
              )}
            </div>
          </section>

          {/* Markets Status & API Keys */}
          <section className="ton-card rounded-2xl p-4 space-y-2.5">
            <div className="flex items-center justify-between">
              <h2 className="font-display text-[14px] font-extrabold text-[#0B1120] flex items-center gap-1.5">
                <Globe className="w-4 h-4 text-[#0098EA]" />
                Статус Маркетів (5)
              </h2>
              <span className="text-[10.5px] font-semibold text-[#64748B]">
                Натисніть для ключів
              </span>
            </div>

            <div className="space-y-2">
              {MARKET_DEFINITIONS.map((m) => {
                const meta = getMarketMeta(m.key);
                const badge = getMarketStatusBadge(m.key);
                const isOpen = expandedMarket === m.key;

                return (
                  <div
                    key={m.key}
                    className="rounded-xl border border-[#E2E8F0] bg-[#F8FAFC] overflow-hidden"
                  >
                    <button
                      type="button"
                      onClick={() => m.field && setExpandedMarket(isOpen ? null : m.key)}
                      className="w-full p-2.5 flex items-center justify-between gap-2 text-left cursor-pointer"
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        <span className={`w-2.5 h-2.5 rounded-full shrink-0 ${meta.dot}`} />
                        <div className="min-w-0">
                          <div className="flex items-center gap-1.5">
                            <span className="text-xs font-extrabold text-[#0B1120]">{m.name}</span>
                            <span className="text-[10px] text-[#64748B] font-semibold">
                              Комісія {m.fee}
                            </span>
                          </div>
                          <p className="text-[10.5px] text-[#64748B] truncate">{m.desc}</p>
                        </div>
                      </div>

                      <div className="flex items-center gap-1.5 shrink-0">
                        <span
                          className={`px-2 py-0.5 rounded-md text-[10px] font-extrabold border ${badge.cls}`}
                        >
                          {badge.label}
                        </span>
                        {m.field &&
                          (isOpen ? (
                            <ChevronUp className="w-4 h-4 text-[#64748B]" />
                          ) : (
                            <ChevronDown className="w-4 h-4 text-[#64748B]" />
                          ))}
                      </div>
                    </button>

                    {isOpen && m.field && (
                      <div className="px-2.5 pb-2.5 pt-1.5 border-t border-[#E2E8F0] bg-white">
                        <label className="text-[10.5px] font-bold text-[#334155] flex items-center gap-1 mb-1">
                          <KeyRound className="w-3 h-3 text-[#0098EA]" />
                          {m.fieldLabel}
                        </label>
                        <input
                          type="password"
                          value={settings[m.field]}
                          onChange={(e) =>
                            setSettings({ ...settings, [m.field]: e.target.value })
                          }
                          placeholder="Вставте ключ або initData..."
                          className="w-full h-9 px-2.5 rounded-lg bg-[#F4F7FB] border border-[#E2E8F0] text-xs font-mono focus:outline-none focus:border-[#0098EA]"
                        />
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </section>
        </div>

        {/* Right Column: AI Vision + Telegram Bot + Risk Management */}
        <div className="space-y-4">
          {/* AI Vision (Оцінка естетики) Card */}
          <section className="ton-card rounded-2xl p-4 space-y-2.5 border-[#BAE3FC]">
            <div className="flex items-center justify-between gap-2">
              <h2 className="font-display text-[14px] font-extrabold text-[#0B1120] flex items-center gap-1.5">
                <Eye className="w-4 h-4 text-[#0098EA]" />
                AI Vision (Оцінка естетики)
              </h2>
              <span
                className={`px-2 py-0.5 rounded-lg text-[10px] font-extrabold border ${
                  hasVisionKey
                    ? 'bg-[#0098EA] text-white border-[#0098EA]'
                    : 'bg-[#E8F5FE] text-[#0077C8] border-[#BAE3FC]'
                }`}
              >
                {hasVisionKey ? 'LLM + CV' : 'Базовий CV'}
              </span>
            </div>

            <div className="rounded-xl p-2.5 bg-[#E8F5FE] border border-[#BAE3FC] flex items-start gap-2">
              <Sparkles className="w-3.5 h-3.5 text-[#0098EA] shrink-0 mt-0.5" />
              <p className="text-[11px] font-medium text-[#0B1120] leading-snug">
                Базовий аналіз пікселів, монохрому та номерів працює безкоштовно без ключів. Ключ
                Gemini/OpenAI потрібен лише для глибокої LLM-оцінки.
              </p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
              <div>
                <label className="block font-bold text-[#334155] mb-1">GEMINI_API_KEY</label>
                <input
                  type="password"
                  value={settings.gemini_api_key || ''}
                  onChange={(e) =>
                    setSettings({ ...settings, gemini_api_key: e.target.value })
                  }
                  placeholder="AIzaSy... (опціонально)"
                  className="w-full h-9 px-3 rounded-xl bg-[#F4F7FB] border border-[#E2E8F0] font-mono text-[11.5px] focus:outline-none focus:border-[#0098EA]"
                />
              </div>
              <div>
                <label className="block font-bold text-[#334155] mb-1">OPENAI_API_KEY</label>
                <input
                  type="password"
                  value={settings.openai_api_key || ''}
                  onChange={(e) =>
                    setSettings({ ...settings, openai_api_key: e.target.value })
                  }
                  placeholder="sk-... (опціонально)"
                  className="w-full h-9 px-3 rounded-xl bg-[#F4F7FB] border border-[#E2E8F0] font-mono text-[11.5px] focus:outline-none focus:border-[#0098EA]"
                />
              </div>
            </div>
          </section>

          {/* Telegram Bot Configuration */}
          <section className="ton-card rounded-2xl p-4 space-y-2.5">
            <div className="flex items-center justify-between">
              <h2 className="font-display text-[14px] font-extrabold text-[#0B1120] flex items-center gap-1.5">
                <Bot className="w-4 h-4 text-[#0098EA]" />
                Telegram Бот та Алерти
              </h2>
              <span
                className={`px-2 py-0.5 rounded-lg text-[10px] font-extrabold border ${
                  overview?.bot_connected || settings.bot_connected
                    ? 'bg-[#E8F5FE] text-[#0077C8] border-[#BAE3FC]'
                    : 'bg-[#F8FAFC] text-[#334155] border-[#CBD5E1]'
                }`}
              >
                {overview?.bot_connected || settings.bot_connected ? 'Активний' : 'Очікує токен'}
              </span>
            </div>

            <div className="space-y-2 text-xs">
              <div>
                <label className="block font-bold text-[#334155] mb-1">TG_BOT_TOKEN</label>
                <input
                  type="password"
                  value={settings.tg_bot_token}
                  onChange={(e) => setSettings({ ...settings, tg_bot_token: e.target.value })}
                  placeholder="123456:ABC-DEF..."
                  className="w-full h-9 px-3 rounded-xl bg-[#F4F7FB] border border-[#E2E8F0] font-mono text-[11.5px] focus:outline-none focus:border-[#0098EA]"
                />
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block font-bold text-[#334155] mb-1">TG_ADMIN_CHAT_ID</label>
                  <input
                    type="text"
                    value={settings.tg_admin_chat_id}
                    onChange={(e) =>
                      setSettings({ ...settings, tg_admin_chat_id: e.target.value })
                    }
                    placeholder="Ваш Telegram ID"
                    className="w-full h-9 px-3 rounded-xl bg-[#F4F7FB] border border-[#E2E8F0] font-mono text-[11.5px] focus:outline-none focus:border-[#0098EA]"
                  />
                </div>
                <div>
                  <label className="block font-bold text-[#334155] mb-1">WEBAPP_URL</label>
                  <input
                    type="text"
                    value={settings.webapp_url}
                    onChange={(e) => setSettings({ ...settings, webapp_url: e.target.value })}
                    placeholder="https://..."
                    className="w-full h-9 px-3 rounded-xl bg-[#F4F7FB] border border-[#E2E8F0] text-[11.5px] focus:outline-none focus:border-[#0098EA]"
                  />
                </div>
              </div>

              <button
                type="button"
                disabled={testingTg}
                onClick={handleTestTelegram}
                className="w-full h-9 rounded-xl bg-[#E8F5FE] hover:bg-[#D4ECFD] border border-[#BAE3FC] text-[#0077C8] font-extrabold inline-flex items-center justify-center gap-1.5 transition-colors cursor-pointer disabled:opacity-60"
              >
                <Send className="w-3.5 h-3.5" />
                <span>{testingTg ? 'Перевіряємо...' : 'Перевірити зв’язок з ТГ'}</span>
              </button>
            </div>
          </section>

          {/* Risk Management */}
          <section className="ton-card rounded-2xl p-4 space-y-3">
            <h2 className="font-display text-[14px] font-extrabold text-[#0B1120] flex items-center gap-1.5">
              {settings.dry_run ? (
                <ShieldCheck className="w-4 h-4 text-[#0098EA]" />
              ) : (
                <ShieldAlert className="w-4 h-4 text-[#0077C8]" />
              )}
              Ризик-менеджмент
            </h2>

            {/* Prominent DRY RUN Toggle */}
            <div
              className={`p-3 rounded-2xl border flex items-center justify-between gap-3 ${
                settings.dry_run
                  ? 'bg-[#E8F5FE] border-[#BAE3FC]'
                  : 'bg-[#F8FAFC] border-[#CBD5E1]'
              }`}
            >
              <div>
                <p className="text-xs font-extrabold text-[#0B1120]">
                  DRY RUN (Безпечний режим)
                </p>
                <p className="text-[10.5px] text-[#334155] mt-0.5">
                  {settings.dry_run
                    ? 'Усі покупки та авто-андеркати симулюються без витрат TON'
                    : 'УВАГА: Реальні угоди будуть виконуватися автоматично!'}
                </p>
              </div>
              <button
                type="button"
                onClick={() => {
                  haptic('medium');
                  setSettings((prev) => ({ ...prev, dry_run: !prev.dry_run }));
                }}
                className={`w-12 h-6.5 rounded-full p-0.5 transition-colors cursor-pointer shrink-0 ${
                  settings.dry_run ? 'bg-[#0098EA]' : 'bg-[#64748B]'
                }`}
              >
                <span
                  className={`block w-5.5 h-5.5 rounded-full bg-white shadow-sm transition-transform ${
                    settings.dry_run ? 'translate-x-5.5' : 'translate-x-0'
                  }`}
                />
              </button>
            </div>

            {/* Numeric Guardrails */}
            <div className="grid grid-cols-3 gap-2 text-xs">
              <div>
                <label className="block text-[10.5px] font-bold text-[#334155] mb-1">
                  Денний ліміт (TON)
                </label>
                <input
                  type="number"
                  value={settings.daily_limit_ton}
                  onChange={(e) =>
                    setSettings({ ...settings, daily_limit_ton: Number(e.target.value) })
                  }
                  className="w-full h-9 px-2.5 rounded-xl bg-[#F4F7FB] border border-[#E2E8F0] font-extrabold tabular-nums focus:outline-none focus:border-[#0098EA]"
                />
              </div>
              <div>
                <label className="block text-[10.5px] font-bold text-[#334155] mb-1">
                  Макс. 1 покупка
                </label>
                <input
                  type="number"
                  value={settings.max_single_buy_ton}
                  onChange={(e) =>
                    setSettings({ ...settings, max_single_buy_ton: Number(e.target.value) })
                  }
                  className="w-full h-9 px-2.5 rounded-xl bg-[#F4F7FB] border border-[#E2E8F0] font-extrabold tabular-nums focus:outline-none focus:border-[#0098EA]"
                />
              </div>
              <div>
                <label className="block text-[10.5px] font-bold text-[#334155] mb-1">
                  Стоп-лос (%)
                </label>
                <input
                  type="number"
                  value={settings.stop_loss_percent}
                  onChange={(e) =>
                    setSettings({ ...settings, stop_loss_percent: Number(e.target.value) })
                  }
                  className="w-full h-9 px-2.5 rounded-xl bg-[#F4F7FB] border border-[#E2E8F0] font-extrabold tabular-nums focus:outline-none focus:border-[#0098EA]"
                />
              </div>
            </div>

            <button
              type="button"
              disabled={saving}
              onClick={handleSave}
              className="w-full ton-btn-primary h-11 rounded-xl font-extrabold text-sm flex items-center justify-center gap-2 cursor-pointer disabled:opacity-60"
            >
              <Save className="w-4 h-4" />
              <span>{saving ? 'Збереження...' : 'Зберегти налаштування'}</span>
            </button>
          </section>
        </div>
      </div>
    </div>
  );
};
