import React, { useEffect, useMemo, useState } from 'react';

interface NftImageProps {
  src?: string;
  alt: string;
  className?: string;
  fallbackText?: string;
  collectionName?: string;
  shortName?: string;
  modelName?: string;
  backdropName?: string;
  symbolName?: string;
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
  malachite: ['#58A97C', '#246B45'],
  'camo green': ['#7A8F6B', '#46573A'],
  'electric cyan': ['#5ED4E8', '#238CA3'],
  indigo: ['#6872C9', '#343D8A'],
  magenta: ['#D962A8', '#8F2968'],
  maroon: ['#9C4858', '#571E2A'],
  olive: ['#99A162', '#5F6632'],
  peach: ['#F0A884', '#B86A48'],
  pink: ['#EB8DB6', '#A84874'],
  red: ['#DB5E5E', '#8F2929'],
  teal: ['#4BA3A3', '#1F6363'],
  violet: ['#9E72D9', '#5A358F'],
  yellow: ['#E6C455', '#A6821E'],
};

// Official Telegram Gift background pattern orbital positions (matches Portals/Fragment/Tonnel cards)
const PATTERN_SPOTS: Array<{ top: string; left: string; size: string; opacity: number; rot: number }> = [
  { top: '8%', left: '16%', size: '12%', opacity: 0.24, rot: -12 },
  { top: '6%', left: '46%', size: '11%', opacity: 0.2, rot: 8 },
  { top: '10%', left: '76%', size: '12%', opacity: 0.24, rot: 14 },
  { top: '34%', left: '7%', size: '13%', opacity: 0.22, rot: -8 },
  { top: '34%', left: '82%', size: '13%', opacity: 0.22, rot: 10 },
  { top: '62%', left: '9%', size: '12%', opacity: 0.22, rot: 12 },
  { top: '62%', left: '80%', size: '12%', opacity: 0.22, rot: -10 },
  { top: '83%', left: '20%', size: '11%', opacity: 0.2, rot: -6 },
  { top: '85%', left: '50%', size: '11%', opacity: 0.18, rot: 5 },
  { top: '82%', left: '75%', size: '11%', opacity: 0.2, rot: 14 },
];

function resolveBackdropGradient(backdropName?: string, seed?: string): string {
  const key = (backdropName || '').trim().toLowerCase();
  const exact = BACKDROP_GRADIENTS[key];
  if (exact) {
    return `radial-gradient(circle at 50% 44%, ${exact[0]} 0%, ${exact[1]} 100%)`;
  }
  if (key) {
    const partial = Object.entries(BACKDROP_GRADIENTS).find(
      ([k]) => key.includes(k) || k.includes(key),
    );
    if (partial) {
      return `radial-gradient(circle at 50% 44%, ${partial[1][0]} 0%, ${partial[1][1]} 100%)`;
    }
  }
  const s = (seed || 'gift').length % 3;
  if (s === 0) return 'radial-gradient(circle at 50% 44%, #6D9EEB 0%, #3B69B5 100%)';
  if (s === 1) return 'radial-gradient(circle at 50% 44%, #76B89A 0%, #3E785E 100%)';
  return 'radial-gradient(circle at 50% 44%, #9582D6 0%, #554296 100%)';
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

  // 1. Always try the real original marketplace card first (Portals / Fragment / Getgems / on-chain Tonnel & MRKT)
  if (params.src) {
    const isCdnModel =
      params.src.includes('cdn.changes.tg/gifts/models/') ||
      params.src.includes('/models/png/');
    add(params.src, isCdnModel);

    // If Fragment .large.jpg fails transiently or isn't generated, try .webp too
    if (params.src.includes('nft.fragment.com/gift/') && params.src.endsWith('.large.jpg')) {
      add(params.src.replace(/\.large\.jpg$/, '.webp'), false);
    }
  }

  const col = (params.collectionName || '').trim();
  const cleanShort = (params.shortName || col).toLowerCase().replace(/[^a-z0-9]/g, '');
  const model = (params.modelName || '').trim();
  const cleanModel = model.toLowerCase().replace(/[^a-z0-9]/g, '');

  // 2. Exact model PNG on official Changes.tg CDN (200 OK for 100% of models — rendered over real backdrop + symbol pattern!)
  if (col && model) {
    add(
      `https://cdn.changes.tg/gifts/models/${encodeURIComponent(col)}/png/${encodeURIComponent(model)}.png`,
      true,
    );
  }

  // 3. Exact model PNG on Portals CDN
  if (cleanShort && cleanModel) {
    add(
      `https://storage.portal-market.com/portals-market/gifts/${cleanShort}/models/png/${cleanModel}.png`,
      true,
    );
  }

  // 4. Collection Original PNG on Changes.tg CDN (guaranteed 200 OK!)
  if (col) {
    add(
      `https://cdn.changes.tg/gifts/models/${encodeURIComponent(col)}/png/Original.png`,
      true,
    );
  }

  // 5. Collection Original PNG on Portals CDN
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
  symbolName,
}) => {
  const resolvedCol = useMemo(
    () => inferCollectionName(collectionName, fallbackText, alt),
    [collectionName, fallbackText, alt],
  );

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

  const patternUrl = useMemo(() => {
    if (!resolvedCol || !symbolName) return '';
    return `https://cdn.changes.tg/gifts/patterns/${encodeURIComponent(resolvedCol)}/png/${encodeURIComponent(symbolName.trim())}.png`;
  }, [resolvedCol, symbolName]);

  const [attemptIdx, setAttemptIdx] = useState(0);
  const [retryCount, setRetryCount] = useState(0);

  useEffect(() => {
    setAttemptIdx(0);
    setRetryCount(0);
  }, [src, resolvedCol, modelName, shortName, symbolName]);

  // If a transient burst-load hiccup exhausts all candidates in the feed, retry once automatically
  useEffect(() => {
    if (attemptIdx < candidates.length || candidates.length === 0 || retryCount >= 1) return;
    const timer = window.setTimeout(() => {
      const firstCdnIdx = candidates.findIndex((c) => c.isTransparentModel);
      setRetryCount((r) => r + 1);
      setAttemptIdx(firstCdnIdx >= 0 ? firstCdnIdx : 0);
    }, 900);
    return () => window.clearTimeout(timer);
  }, [attemptIdx, candidates, retryCount]);

  const current = candidates[attemptIdx];
  const backdropBg = useMemo(
    () => resolveBackdropGradient(backdropName, resolvedCol),
    [backdropName, resolvedCol],
  );

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

  const handleImageError = () => {
    setAttemptIdx((idx) => (idx < candidates.length ? idx + 1 : idx));
  };

  // Authentic 3-layer Telegram Gift card composite for off-chain gifts (Backdrop + Official Symbol Pattern + Model PNG)
  if (current.isTransparentModel) {
    return (
      <div
        className="relative w-full h-full flex items-center justify-center overflow-hidden"
        style={{ background: backdropBg }}
      >
        {/* Official Telegram background symbol pattern layer — single cached CSS mask, zero extra <img> stalls */}
        {patternUrl && (
          <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
            {PATTERN_SPOTS.map((spot, idx) => (
              <span
                key={idx}
                className="absolute block select-none"
                style={{
                  top: spot.top,
                  left: spot.left,
                  width: spot.size,
                  height: spot.size,
                  opacity: spot.opacity,
                  transform: `rotate(${spot.rot}deg)`,
                  backgroundColor: 'rgba(11, 17, 32, 0.72)',
                  WebkitMaskImage: `url("${patternUrl}")`,
                  maskImage: `url("${patternUrl}")`,
                  WebkitMaskSize: 'contain',
                  maskSize: 'contain',
                  WebkitMaskRepeat: 'no-repeat',
                  maskRepeat: 'no-repeat',
                  WebkitMaskPosition: 'center',
                  maskPosition: 'center',
                }}
              />
            ))}
          </div>
        )}

        {/* Centered crisp model PNG — keyed by URL and eager on fallback so WebKit never stalls */}
        <img
          key={`${attemptIdx}-${retryCount}-${current.url}`}
          src={current.url}
          alt={alt}
          loading="eager"
          decoding="async"
          onError={handleImageError}
          className="relative z-10 w-[72%] h-[72%] object-contain drop-shadow-[0_6px_14px_rgba(0,0,0,0.24)] transition-transform duration-300 group-hover:scale-[1.04]"
        />
      </div>
    );
  }

  // Real original full marketplace card (Portals / Fragment / Getgems / on-chain Tonnel & MRKT)
  return (
    <img
      key={`${attemptIdx}-${retryCount}-${current.url}`}
      src={current.url}
      alt={alt}
      loading={attemptIdx > 0 ? 'eager' : 'lazy'}
      decoding="async"
      onError={handleImageError}
      className={className}
    />
  );
};
