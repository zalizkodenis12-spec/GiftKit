import React from 'react';
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from 'lucide-react';
import type { ToastItem } from '../types/api';

interface ToastAlertsProps {
  toasts: ToastItem[];
  onDismiss: (id: string) => void;
}

export const ToastAlerts: React.FC<ToastAlertsProps> = ({ toasts, onDismiss }) => {
  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-[76px] left-1/2 -translate-x-1/2 lg:bottom-6 lg:right-6 lg:left-auto lg:translate-x-0 z-50 w-[calc(100%-24px)] max-w-[420px] flex flex-col gap-2 pointer-events-none">
      {toasts.slice(0, 2).map((toast) => {
        const styleMap = {
          success: {
            wrap: 'bg-white border-[#A7F3D0] border-l-4 border-l-[#059669] shadow-[0_10px_28px_rgba(15,23,42,0.14)]',
            icon: <CheckCircle2 className="w-4.5 h-4.5 text-[#059669] shrink-0" />,
            title: 'text-[#065F46]',
          },
          warning: {
            wrap: 'bg-white border-[#BAE3FC] border-l-4 border-l-[#0098EA] shadow-[0_10px_28px_rgba(15,23,42,0.14)]',
            icon: <AlertTriangle className="w-4.5 h-4.5 text-[#0098EA] shrink-0" />,
            title: 'text-[#0B1120]',
          },
          error: {
            wrap: 'bg-white border-[#FECACA] border-l-4 border-l-[#DC2626] shadow-[0_10px_28px_rgba(15,23,42,0.14)]',
            icon: <XCircle className="w-4.5 h-4.5 text-[#DC2626] shrink-0" />,
            title: 'text-[#991B1B]',
          },
          info: {
            wrap: 'bg-white border-[#BAE3FC] border-l-4 border-l-[#0098EA] shadow-[0_10px_28px_rgba(15,23,42,0.14)]',
            icon: <Info className="w-4.5 h-4.5 text-[#0098EA] shrink-0" />,
            title: 'text-[#0B1120]',
          },
        }[toast.variant];

        return (
          <div
            key={toast.id}
            className={`animate-toast pointer-events-auto flex items-start gap-2.5 p-3 rounded-2xl border ${styleMap.wrap}`}
          >
            <div className="mt-0.5">{styleMap.icon}</div>
            <div className="flex-1 min-w-0">
              <p className={`text-xs font-bold leading-snug ${styleMap.title}`}>
                {toast.title}
              </p>
              {toast.message && (
                <p className="text-[11px] text-[#475569] mt-0.5 leading-snug break-words">
                  {toast.message}
                </p>
              )}
            </div>
            <button
              type="button"
              onClick={() => onDismiss(toast.id)}
              className="text-[#94A3B8] hover:text-[#475569] p-0.5 cursor-pointer"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        );
      })}
    </div>
  );
};
