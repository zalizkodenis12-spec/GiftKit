import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { api, useLiveSocket } from './api/client';
import type {
  AnalyzedListing,
  CollectionSummary,
  LiveSocketEvent,
  OverviewResponse,
  PortfolioResponse,
  SaleRecord,
  TabKey,
  ToastItem,
  XRayResponse,
} from './types/api';
import { TopHeader } from './components/TopHeader';
import { BottomNav } from './components/BottomNav';
import { ToastAlerts } from './components/ToastAlerts';
import { NftDetailDrawer } from './components/NftDetailDrawer';
import { ScannerPage } from './pages/ScannerPage';
import { AnalyticsPage } from './pages/AnalyticsPage';
import { SniperPage } from './pages/SniperPage';
import { PortfolioPage } from './pages/PortfolioPage';
import { MarketsPage } from './pages/MarketsPage';

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabKey>('scanner');
  const [overview, setOverview] = useState<OverviewResponse | null>(null);
  const [collections, setCollections] = useState<CollectionSummary[]>([]);
  const [portfolio, setPortfolio] = useState<PortfolioResponse | null>(null);
  const [portfolioLoading, setPortfolioLoading] = useState(true);

  const [refreshTick, setRefreshTick] = useState(0);
  const [focusXRayTrigger, setFocusXRayTrigger] = useState(0);

  // Selected listing drawer state
  const [drawerItem, setDrawerItem] = useState<AnalyzedListing | null>(null);
  const [drawerRec, setDrawerRec] = useState<string | undefined>(undefined);
  const [drawerSales, setDrawerSales] = useState<SaleRecord[] | undefined>(undefined);

  // Toasts
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const notify = useCallback(
    (
      title: string,
      message?: string,
      variant: 'info' | 'success' | 'warning' | 'error' = 'info',
    ) => {
      const id = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
      setToasts((prev) => [{ id, title, message, variant }, ...prev].slice(0, 2));
      window.setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
      }, 3600);
    },
    [],
  );

  // Reset scroll to top on tab switch
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'auto' });
  }, [activeTab]);

  // Initialize Telegram Mini App WebApp SDK
  useEffect(() => {
    try {
      const wa = window.Telegram?.WebApp;
      if (wa) {
        wa.ready();
        wa.expand();
        wa.setHeaderColor?.('#FFFFFF');
        wa.setBackgroundColor?.('#F4F7FB');
      }
    } catch {
      // safe fallback outside Telegram
    }
  }, []);

  const loadOverview = useCallback(async () => {
    try {
      const data = await api.getOverview();
      setOverview(data);
    } catch {
      // silent during initial boot
    }
  }, []);

  const loadCollections = useCallback(async () => {
    try {
      const data = await api.getCollections({ sort: 'volume_desc', limit: 250 });
      setCollections(data.collections || []);
    } catch {
      // silent
    }
  }, []);

  const loadPortfolio = useCallback(async () => {
    setPortfolioLoading(true);
    try {
      const data = await api.getPortfolio();
      setPortfolio(data);
    } catch {
      // silent
    } finally {
      setPortfolioLoading(false);
    }
  }, []);

  useEffect(() => {
    loadOverview();
    loadCollections();
    loadPortfolio();
  }, [loadOverview, loadCollections, loadPortfolio]);

  // Live WebSocket subscription
  const handleWsEvent = useCallback(
    (ev: LiveSocketEvent) => {
      if (!ev || ev.type === 'ping' || ev.type === 'pong' || ev.type === 'heartbeat') {
        return;
      }

      if (ev.title || ev.message) {
        notify(
          ev.title || 'Живе оновлення',
          ev.message,
          ev.severity || (ev.type.includes('undercut') ? 'warning' : 'info'),
        );
      }

      if (
        ev.type.includes('portfolio') ||
        ev.type.includes('undercut') ||
        ev.type.includes('trade')
      ) {
        loadPortfolio();
        loadOverview();
      } else if (ev.type.includes('alert') || ev.type.includes('sniper') || ev.type.includes('listing')) {
        setRefreshTick((t) => t + 1);
        loadOverview();
      }
    },
    [notify, loadPortfolio, loadOverview],
  );

  const { connected: wsConnected } = useLiveSocket(handleWsEvent);

  // Serverless auto-refresh fallback (e.g. Vercel where WebSockets aren't persistent)
  useEffect(() => {
    if (wsConnected) return;
    const timer = window.setInterval(() => {
      loadOverview();
      loadCollections();
    }, 45000);
    return () => window.clearInterval(timer);
  }, [wsConnected, loadOverview, loadCollections]);

  const undercutCount = useMemo(
    () => (portfolio?.items || []).filter((i) => i.is_undercut_by_competitor).length,
    [portfolio],
  );

  const openListingDrawer = useCallback((item: AnalyzedListing) => {
    setDrawerItem(item);
    setDrawerRec(undefined);
    setDrawerSales(undefined);
  }, []);

  const handleXRayResult = useCallback((res: XRayResponse) => {
    setDrawerItem(res.item);
    setDrawerRec(res.recommendation);
    setDrawerSales(res.comparable_sales);
  }, []);

  const closeDrawer = useCallback(() => {
    setDrawerItem(null);
    setDrawerRec(undefined);
    setDrawerSales(undefined);
  }, []);

  const handleUpdateDrawerItem = useCallback((updated: AnalyzedListing) => {
    setDrawerItem(updated);
  }, []);

  // Drawer Actions
  const handleBuyListing = async (item: AnalyzedListing) => {
    try {
      const res = await api.executeTrade({
        listing_id: item.id,
        tg_id: item.tg_id,
        collection_name: item.collection_name,
        short_name: item.short_name,
        number: item.number,
        price: item.price,
        market: item.market,
        photo_url: item.photo_url,
        fair_value: item.fair_value,
        collection_floor: item.collection_floor,
      });
      await Promise.all([loadPortfolio(), loadOverview()]);
      notify(
        res.dry_run ? 'DRY-RUN покупка успішна!' : 'NFT успішно куплено!',
        res.message || `${item.collection_name} #${item.number} додано в портфель`,
        'success',
      );
      closeDrawer();
    } catch (err) {
      notify(
        'Помилка покупки',
        err instanceof Error ? err.message : 'Перевірте ліміти ризику',
        'error',
      );
    }
  };

  const handleMakeOffer = async (item: AnalyzedListing) => {
    const bid = Number(Math.max(0.5, item.price * 0.88).toFixed(2));
    const maxBid = Number(Math.max(bid + 0.5, item.price * 0.95).toFixed(2));
    try {
      await api.createOffer({
        collection_short_name: item.short_name,
        collection_name: item.collection_name,
        market: item.market,
        bid_price: bid,
        max_bid: maxBid,
        auto_outbid: true,
      });
      setRefreshTick((t) => t + 1);
      notify(
        'Офер виставлено!',
        `${item.collection_name} · ставка ${bid} TON (авто-перебиття увімк.)`,
        'success',
      );
    } catch (err) {
      notify(
        'Помилка офера',
        err instanceof Error ? err.message : 'Спробуйте ще раз',
        'error',
      );
    }
  };

  const handleAddToPortfolio = async (item: AnalyzedListing) => {
    try {
      await api.addPortfolioItem({
        tg_id: item.tg_id,
        collection_name: item.collection_name,
        short_name: item.short_name,
        number: item.number,
        photo_url: item.photo_url,
        buy_price: item.price,
        listed_price: Number((item.fair_value * 0.98).toFixed(2)),
        market: item.market,
        auto_undercut_enabled: true,
        undercut_mode: 'notify',
        min_price_guard: Number((item.price * 1.05).toFixed(2)),
        undercut_step: 0.05,
        status: 'listed',
      });
      await Promise.all([loadPortfolio(), loadOverview()]);
      notify(
        'Додано в портфель',
        `${item.collection_name} #${item.number} з Auto-Undercut`,
        'success',
      );
      closeDrawer();
    } catch (err) {
      notify(
        'Помилка додавання',
        err instanceof Error ? err.message : 'Спробуйте ще раз',
        'error',
      );
    }
  };

  const tonUsd = overview?.ton_usd ?? 1.03;
  const dryRun = overview?.dry_run ?? true;

  return (
    <div className="min-h-screen w-full bg-[#F4F7FB] flex flex-col overflow-x-clip relative">
      <ToastAlerts toasts={toasts} onDismiss={dismissToast} />

      <TopHeader
        overview={overview}
        wsConnected={wsConnected}
        activeTab={activeTab}
        undercutCount={undercutCount}
        onChangeTab={setActiveTab}
        onOpenXRay={() => {
          setActiveTab('analytics');
          setFocusXRayTrigger((n) => n + 1);
        }}
        onOpenMarkets={() => setActiveTab('markets')}
        onNotify={notify}
      />

      <main className="flex-1 w-full max-w-[1440px] mx-auto px-3 sm:px-5 lg:px-6 pt-3.5 pb-6 lg:pb-10">
        {activeTab === 'scanner' && (
          <ScannerPage
            collections={collections}
            tonUsd={tonUsd}
            refreshTick={refreshTick}
            onSelectListing={openListingDrawer}
            onNotify={notify}
          />
        )}

        {activeTab === 'analytics' && (
          <AnalyticsPage
            collections={collections}
            tonUsd={tonUsd}
            focusXRayTrigger={focusXRayTrigger}
            onXRayResult={handleXRayResult}
            onSelectListing={openListingDrawer}
            onNotify={notify}
          />
        )}

        {activeTab === 'sniper' && (
          <SniperPage
            collections={collections}
            refreshTick={refreshTick}
            onSelectListing={openListingDrawer}
            onNotify={notify}
          />
        )}

        {activeTab === 'portfolio' && (
          <PortfolioPage
            portfolio={portfolio}
            collections={collections}
            tonUsd={tonUsd}
            loading={portfolioLoading}
            onReload={async () => {
              await Promise.all([loadPortfolio(), loadOverview()]);
            }}
            onNotify={notify}
          />
        )}

        {activeTab === 'markets' && (
          <MarketsPage
            overview={overview}
            onSettingsSaved={loadOverview}
            onNotify={notify}
          />
        )}
      </main>

      <BottomNav
        activeTab={activeTab}
        onChange={setActiveTab}
        undercutCount={undercutCount}
      />

      <NftDetailDrawer
        item={drawerItem}
        recommendation={drawerRec}
        comparableSales={drawerSales}
        tonUsd={tonUsd}
        dryRun={dryRun}
        onClose={closeDrawer}
        onUpdateItem={handleUpdateDrawerItem}
        onBuy={handleBuyListing}
        onMakeOffer={handleMakeOffer}
        onAddPortfolio={handleAddToPortfolio}
        onNotify={notify}
      />
    </div>
  );
};

export default App;
