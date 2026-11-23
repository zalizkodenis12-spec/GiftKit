import React, { useEffect, useMemo, useRef, useState } from 'react';
import lottie, { type AnimationItem } from 'lottie-web';

interface NftImageProps {
  src?: string;
  alt: string;
  className?: string;
  fallbackText?: string;
  collectionName?: string;
  shortName?: string;
  modelName?: string;
  backdropName?: string;
  animate?: boolean;
}

// Official Telegram Gifts radial backdrop gradients [center, edge]
const BACKDROP_GRADIENTS: Record<string, [string, string]> = {
  black: ['#363738', '#0E0F0F'],
  'onyx black': ['#4D5254', '#1E2124'],
  obsidian: ['#3B3E45', '#15171A'],
  'midnight blue': ['#5C6E99', '#2E3A59'],
  'navy blue': ['#6C8EBF', '#3A537B'],
  'cobalt blue': ['#6088CF', '#2E4C8A'],
  sapphire: ['#5C8AE6', '#2B4FA3'],
  'sky blue': ['#6CC2FF', '#3A8FD9'],
  'neon blue': ['#7596F9', '#3857C4'],
  'electric indigo': ['#9D7AF7', '#5E3AB8'],
  'electric purple': ['#C56DF0', '#7B34B5'],
  lavender: ['#B794F6', '#7B5BC9'],
  grape: ['#9D74C1', '#5D3C82'],
  fandango: ['#D66B9C', '#8F3161'],
  raspberry: ['#E06B88', '#99324F'],
  crimson: ['#DC5C68', '#8F2936'],
  burgundy: ['#A34E5D', '#5E222E'],
  rosewood: ['#B76B6B', '#6E3535'],
  'coral red': ['#EC8073', '#B0463C'],
  strawberry: ['#E3717B', '#A33944'],
  'cherry red': ['#D95966', '#8C2733'],
  tangerine: ['#F2A463', '#BA682B'],
  amber: ['#DAB345', '#9E7317'],
  'satin gold': ['#D4B974', '#8F7334'],
  'old gold': ['#B5A462', '#73652E'],
  'desert sand': ['#D4B98C', '#8E734B'],
  emerald: ['#68B884', '#2F7A4D'],
  'shamrock green': ['#6CC47E', '#338044'],
  'mint green': ['#7ED1A6', '#3F8E67'],
  pistachio: ['#97AE7C', '#5C7544'],
  'hunter green': ['#78997B', '#405E45'],
  'pine green': ['#669984', '#31614E'],
  aquamarine: ['#66C9C1', '#2E8780'],
  turquoise: ['#5CC2D6', '#297E94'],
  'pacific cyan': ['#5AA7C2', '#2B6D85'],
  'steel grey': ['#97A2AC', '#5E6873'],
  'silver blue': ['#8EA5BD', '#546B82'],
  'roman silver': ['#A3A7B0', '#696D75'],
  platinum: ['#B2B0A8', '#75736B'],
  'ivory white': ['#E3DDD1', '#ABA496'],
  'pure gold': ['#E5C25C', '#A68020'],
  cyberpunk: ['#966BE8', '#4F2B9E'],
  'deep cyan': ['#4E9AA8', '#225F6E'],
  'burnt sienna': ['#C97A5C', '#85432B'],
  'celtic blue': ['#5485C9', '#285291'],
  chestnut: ['#B07260', '#6E3E30'],
  chocolate: ['#946854', '#573628'],
  copper: ['#C48466', '#804A32'],
  'french blue': ['#598DC2', '#2B5B8C'],
  'french violet': ['#A36FD1', '#61388C'],
  'indigo dye': ['#537991', '#2B4B61'],
  'jade green': ['#58A883', '#276E4E'],
  'khaki green': ['#A3A675', '#676B3E'],
  'marine blue': ['#4E688A', '#263B57'],
  'mech purple': ['#9D7CE0', '#5B3E9E'],
  'mystic pearl': ['#C78DA3', '#824E63'],
  orange: ['#ED995A', '#B56026'],
  'persian green': ['#4BA89B', '#226B61'],
  plum: ['#9E628E', '#5E3052'],
  purple: ['#A575D4', '#633B8F'],
  'ranger green': ['#758F78', '#415944'],
  'seafoam green': ['#7EC4A8', '#42856A'],
  sky: ['#66B8F0', '#317DB8'],
  vermilion: ['#E06F5B', '#9E3928'],
  caramel: ['#D19462', '#8F582C'],
  'malachite': ['#58A97C', '#246B45'],
  'camo green': ['#7A8F6B', '#46573A'],
  'electric cyan': ['#5ED4E8', '#238CA3'],
  'indigo': ['#6872C9', '#343D8A'],
  'magenta': ['#D962A8', '#8F2968'],
  'maroon': ['#9C4858', '#571E2A'],
  'olive': ['#99A162', '#5F6632'],
  'peach': ['#F0A884', '#B86A48'],
  'pink': ['#EB8DB6', '#A84874'],
  'red': ['#DB5E5E', '#8F2929'],
  'teal': ['#4BA3A3', '#1F6363'],
  'violet': ['#9E72D9', '#5A358F'],
  'yellow': ['#E6C455', '#A6821E'],
};

// In-memory LRU cache for Lottie animation JSONs (shared across all cards)
const lottieCache = new Map<string, Record<string, unknown> | null>();
const lottieInFlight = new Map<string, Promise<Record<string, unknown> | null>>();

async function fetchLottieJson(url: string): Promise<Record<string, unknown> | null> {
  if (lottieCache.has(url)) {
    return lottieCache.get(url) ?? null;
  }
  const existing = lottieInFlight.get(url);
  if (existing) return existing;

  const p = fetch(url, { mode: 'cors' })
    .then(async (res) => {
      if (!res.ok) return null;
      const data = (await res.json()) as Record<string, unknown>;
      if (data && typeof data === 'object' && ('layers' in data || 'v' in data)) {
        return data;
      }
      return null;
    })
    .catch(() => null)
    .then((data) => {
      if (lottieCache.size > 160) {
        const firstKey = lottieCache.keys().next().value;
        if (firstKey) lottieCache.delete(firstKey);
      }
      lottieCache.set(url, data);
      lottieInFlight.delete(url);
      return data;
    });

  lottieInFlight.set(url, p);
  return p;
}

function resolveBackdropGradient(backdropName?: string, seed?: string): string {
  const key = (backdropName || '').trim().toLowerCase();
  const exact = BACKDROP_GRADIENTS[key];
  if (exact) {
    return `radial-gradient(circle at 50% 42%, ${exact[0]} 0%, ${exact[1]} 100%)`;
  }
  if (key) {
    const partial = Object.entries(BACKDROP_GRADIENTS).find(
      ([k]) => key.includes(k) || k.includes(key),
    );
    if (partial) {
      return `radial-gradient(circle at 50% 42%, ${partial[1][0]} 0%, ${partial[1][1]} 100%)`;
    }
  }
  // Clean soft TON radial backdrop when backdrop name isn't known
  const s = (seed || 'gift').length % 3;
  if (s === 0) return 'radial-gradient(circle at 50% 42%, #EAF5FF 0%, #CEE7FD 100%)';
  if (s === 1) return 'radial-gradient(circle at 50% 42%, #EEF3FF 0%, #D4E0FA 100%)';
  return 'radial-gradient(circle at 50% 42%, #E8F7FD 0%, #C7E8F9 100%)';
}

function inferCollectionName(collectionName?: string, fallbackText?: string, alt?: string): string {
  const raw = (collectionName || fallbackText || alt || '').trim();
  if (!raw) return '';
  return raw.replace(/\s*#\d+.*$/, '').trim();
}

function buildImageCandidates(params: {
  src?: string;
  collectionName?: string;
  shortName?: string;
  modelName?: string;
}): Array<{ url: string; isTransparentModel: boolean }> {
  const list: Array<{ url: string; isTransparentModel: boolean }> = [];
  const seen = new Set<string>();
  const add = (url: string, isTransparentModel: boolean) => {
    const clean = (url || '').trim();
    if (!clean || seen.has(clean)) return;
    seen.add(clean);
    list.push({ url: clean, isTransparentModel });
  };

  const col = (params.collectionName || '').trim();
  const cleanShort = (params.shortName || col).toLowerCase().replace(/[^a-z0-9]/g, '');
  const model = (params.modelName || '').trim();
  const cleanModel = model.toLowerCase().replace(/[^a-z0-9]/g, '');

  // If primary src is already a reliable non-404 full card (Portals/Fragment/TonAPI), use it first;
  // for guaranteed exact model PNGs, put Changes.tg right behind it so 404 instantly recovers!
  if (params.src) {
    const isCdnModel =
      params.src.includes('cdn.changes.tg/gifts/models/') ||
      params.src.includes('/models/png/');
    add(params.src, isCdnModel);
  }

  // 1. Exact model PNG on official Changes.tg Telegram Gifts CDN (200 OK for 100% of models!)
  if (col && model) {
    add(
      `https://cdn.changes.tg/gifts/models/${encodeURIComponent(col)}/png/${encodeURIComponent(model)}.png`,
      true,
    );
  }

  // 2. Exact model PNG on Portals CDN
  if (cleanShort && cleanModel) {
    add(
      `https://storage.portal-market.com/portals-market/gifts/${cleanShort}/models/png/${cleanModel}.png`,
      true,
    );
  }

  // 3. Collection Original PNG on Changes.tg CDN (guaranteed 200 OK!)
  if (col) {
    add(
      `https://cdn.changes.tg/gifts/models/${encodeURIComponent(col)}/png/Original.png`,
      true,
    );
  }

  // 4. Collection Original PNG on Portals CDN
  if (cleanShort) {
    add(
      `https://storage.portal-market.com/portals-market/gifts/${cleanShort}/models/png/original.png`,
      true,
    );
  }

  return list;
}

export const NftImage: React.FC<NftImageProps> = ({
  src,
  alt,
  className = 'w-full h-full object-cover',
  fallbackText,
  collectionName,
  shortName,
  modelName,
  backdropName,
  animate = true,
}) => {
  const resolvedCol = useMemo(
    () => inferCollectionName(collectionName, fallbackText, alt),
    [collectionName, fallbackText, alt],
  );

  const lottieUrl = useMemo(() => {
    if (!animate || !resolvedCol || !modelName) return '';
    return `https://cdn.changes.tg/gifts/models/${encodeURIComponent(resolvedCol)}/lottie/${encodeURIComponent(modelName.trim())}.json`;
  }, [animate, resolvedCol, modelName]);

  const candidates = useMemo(
    () =>
      buildImageCandidates({
        src,
        collectionName: resolvedCol,
        shortName,
        modelName,
      }),
    [src, resolvedCol, shortName, modelName],
  );

  const [attemptIdx, setAttemptIdx] = useState(0);
  const [inView, setInView] = useState(false);
  const [lottieReady, setLottieReady] = useState(false);

  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const lottieHostRef = useRef<HTMLDivElement | null>(null);
  const animRef = useRef<AnimationItem | null>(null);

  useEffect(() => {
    setAttemptIdx(0);
    setLottieReady(false);
  }, [src, resolvedCol, modelName, shortName]);

  // Only animate cards currently visible in viewport (smooth 60fps on iPhone)
  useEffect(() => {
    const node = wrapperRef.current;
    if (!node || !lottieUrl) return;
    if (typeof IntersectionObserver === 'undefined') {
      setInView(true);
      return;
    }
    const obs = new IntersectionObserver(
      (entries) => {
        const visible = entries.some((e) => e.isIntersecting);
        setInView(visible);
        if (animRef.current) {
          if (visible) animRef.current.play();
          else animRef.current.pause();
        }
      },
      { rootMargin: '120px 0px', threshold: 0.01 },
    );
    obs.observe(node);
    return () => obs.disconnect();
  }, [lottieUrl]);

  // Load & mount real Telegram Gift Lottie animation when visible
  useEffect(() => {
    if (!lottieUrl || !inView) return;
    let cancelled = false;

    fetchLottieJson(lottieUrl).then((data) => {
      if (cancelled || !data || !lottieHostRef.current) return;
      if (animRef.current) {
        animRef.current.destroy();
        animRef.current = null;
      }
      try {
        // Clone data so lottie-web never mutates cached object across cards
        const cloned = JSON.parse(JSON.stringify(data));
        const anim = lottie.loadAnimation({
          container: lottieHostRef.current,
          renderer: 'svg',
          loop: true,
          autoplay: true,
          animationData: cloned,
          rendererSettings: {
            preserveAspectRatio: 'xMidYMid meet',
            progressiveLoad: true,
          },
        });
        animRef.current = anim;
        setLottieReady(true);
      } catch {
        setLottieReady(false);
      }
    });

    return () => {
      cancelled = true;
      if (animRef.current) {
        animRef.current.destroy();
        animRef.current = null;
      }
    };
  }, [lottieUrl, inView]);

  const current = candidates[attemptIdx];
  const backdropBg = useMemo(
    () => resolveBackdropGradient(backdropName, resolvedCol),
    [backdropName, resolvedCol],
  );

  // Full animated Telegram-profile style card (radial official backdrop + live 60fps Lottie!)
  if (lottieUrl) {
    return (
      <div
        ref={wrapperRef}
        className="relative w-full h-full flex items-center justify-center overflow-hidden"
        style={{ background: backdropBg }}
      >
        {/* Subtle radial highlight matching Telegram profile gift card */}
        <div
          className="pointer-events-none absolute inset-0 opacity-30"
          style={{
            background:
              'radial-gradient(circle at 50% 35%, rgba(255,255,255,0.45) 0%, rgba(255,255,255,0) 65%)',
          }}
        />

        {/* Instant PNG poster while Lottie JSON loads (zero flash, zero broken icon!) */}
        {!lottieReady && current && (
          <img
            src={current.url}
            alt={alt}
            loading="lazy"
            onError={() => setAttemptIdx((idx) => idx + 1)}
            className={
              current.isTransparentModel
                ? 'relative z-10 w-[82%] h-[82%] object-contain drop-shadow-[0_6px_12px_rgba(0,0,0,0.22)]'
                : `relative z-10 ${className}`
            }
          />
        )}

        {/* Live 60fps Telegram Gift Lottie Animation */}
        <div
          ref={lottieHostRef}
          className={`relative z-10 w-[84%] h-[84%] flex items-center justify-center drop-shadow-[0_6px_14px_rgba(0,0,0,0.22)] transition-opacity duration-200 ${
            lottieReady ? 'opacity-100' : 'opacity-0 absolute inset-0 m-auto pointer-events-none'
          }`}
        />
      </div>
    );
  }

  if (!current) {
    return (
      <div
        className={`flex items-center justify-center p-4 ${className}`}
        style={{ background: backdropBg }}
      >
        <img
          src="/giftkit-logo.png"
          alt={alt}
          className="w-14 h-14 rounded-2xl object-contain opacity-90 drop-shadow-sm"
        />
      </div>
    );
  }

  if (current.isTransparentModel) {
    return (
      <div
        className="w-full h-full flex items-center justify-center p-2.5 overflow-hidden"
        style={{ background: backdropBg }}
      >
        <img
          src={current.url}
          alt={alt}
          loading="lazy"
          onError={() => setAttemptIdx((idx) => idx + 1)}
          className="w-full h-full object-contain drop-shadow-[0_6px_12px_rgba(0,0,0,0.22)] transition-transform duration-300 group-hover:scale-[1.04]"
        />
      </div>
    );
  }

  return (
    <img
      src={current.url}
      alt={alt}
      loading="lazy"
      onError={() => setAttemptIdx((idx) => idx + 1)}
      className={className}
    />
  );
};
