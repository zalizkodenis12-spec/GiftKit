import React, { useState } from 'react';
import { Sparkles } from 'lucide-react';

interface NftImageProps {
  src?: string;
  alt: string;
  className?: string;
  fallbackText?: string;
}

const GRADIENTS = [
  'from-[#EBF4FF] via-[#DCEBFF] to-[#C2DCFF]',
  'from-[#E6F4FE] via-[#D0EBFF] to-[#B6DFFF]',
  'from-[#EEF2FF] via-[#E0E7FF] to-[#C7D2FE]',
  'from-[#ECFEFF] via-[#CFFAFE] to-[#BAE6FD]',
];

function getInitials(name: string): string {
  // Strip emojis and non-alphanumeric chars safely across Unicode code points
  const cleaned = name.replace(/[^\p{L}\p{N}\s]/gu, ' ').trim();
  const parts = cleaned.split(/\s+/).filter(Boolean);
  if (parts.length === 0) return 'TG';
  if (parts.length === 1) return Array.from(parts[0]).slice(0, 2).join('').toUpperCase();
  return (Array.from(parts[0])[0] + Array.from(parts[1])[0]).toUpperCase();
}

function hashIndex(str: string): number {
  let hash = 0;
  for (let i = 0; i < str.length; i += 1) {
    hash = (hash * 31 + str.charCodeAt(i)) >>> 0;
  }
  return hash % GRADIENTS.length;
}

export const NftImage: React.FC<NftImageProps> = ({
  src,
  alt,
  className = 'w-full h-full object-cover',
  fallbackText,
}) => {
  const [failed, setFailed] = useState(false);

  if (!src || failed) {
    const label = fallbackText || alt;
    const grad = GRADIENTS[hashIndex(label)];
    return (
      <div
        className={`flex flex-col items-center justify-center bg-gradient-to-br ${grad} text-[#0077CC] select-none ${className}`}
      >
        <div className="flex items-center justify-center w-9 h-9 rounded-2xl bg-white/80 shadow-sm border border-white/90 mb-1">
          <Sparkles className="w-4 h-4 text-[#1A6BFF]" />
        </div>
        <span className="text-xs font-extrabold tracking-wide text-[#0F4C81]">
          {getInitials(label)}
        </span>
      </div>
    );
  }

  return (
    <img
      src={src}
      alt={alt}
      loading="lazy"
      onError={() => setFailed(true)}
      className={className}
    />
  );
};
