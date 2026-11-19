import React from 'react';
import {
  BarChart3,
  Briefcase,
  Crosshair,
  Flame,
  SlidersHorizontal,
} from 'lucide-react';
import type { TabKey } from '../types/api';
import { haptic } from '../utils/format';

interface BottomNavProps {
  activeTab: TabKey;
  onChange: (tab: TabKey) => void;
  undercutCount: number;
}

const TABS: {
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

export const BottomNav: React.FC<BottomNavProps> = ({
  activeTab,
  onChange,
  undercutCount,
}) => {
  return (
    <nav className="lg:hidden sticky bottom-0 z-30 w-full backdrop-blur-lg bg-white/94 border-t border-[#E2E8F0] px-2 pt-1.5 pb-[max(0.5rem,env(safe-area-inset-bottom))]">
      <div className="max-w-[640px] mx-auto grid grid-cols-5 gap-1">
        {TABS.map(({ key, label, icon: Icon }) => {
          const isActive = activeTab === key;
          return (
            <button
              key={key}
              type="button"
              onClick={() => {
                haptic('light');
                onChange(key);
              }}
              className={`relative flex flex-col items-center justify-center py-1.5 rounded-2xl transition-all cursor-pointer ${
                isActive
                  ? 'bg-[#E8F5FE] text-[#0098EA]'
                  : 'text-[#64748B] hover:text-[#0B1120] hover:bg-[#F8FAFC]'
              }`}
            >
              <div className="relative">
                <Icon
                  className={`w-[20px] h-[20px] transition-transform ${
                    isActive ? 'scale-105 stroke-[2.3]' : 'stroke-[1.9]'
                  }`}
                />
                {key === 'portfolio' && undercutCount > 0 && (
                  <span className="absolute -top-1.5 -right-2.5 min-w-[16px] h-[16px] px-1 flex items-center justify-center rounded-full bg-[#0098EA] text-white text-[10px] font-extrabold tabular-nums shadow-sm ring-2 ring-white">
                    {undercutCount}
                  </span>
                )}
              </div>
              <span
                className={`text-[10px] mt-1 leading-none tracking-tight ${
                  isActive ? 'font-extrabold text-[#0098EA]' : 'font-semibold'
                }`}
              >
                {label}
              </span>
            </button>
          );
        })}
      </div>
    </nav>
  );
};
