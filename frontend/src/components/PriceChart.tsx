import React, { useEffect, useRef, useState } from 'react';
import {
  ColorType,
  CrosshairMode,
  createChart,
  type IChartApi,
  type Time,
} from 'lightweight-charts';
import type { ChartPoint } from '../types/api';
import { formatTon } from '../utils/format';

interface PriceChartProps {
  points: ChartPoint[];
  height?: number;
}

export const PriceChart: React.FC<PriceChartProps> = ({ points, height = 220 }) => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const [hoverPoint, setHoverPoint] = useState<ChartPoint | null>(null);

  const latestPoint = points.length > 0 ? points[points.length - 1] : null;
  const activePoint = hoverPoint ?? latestPoint;

  useEffect(() => {
    const el = containerRef.current;
    if (!el || points.length === 0) return;

    const sorted = [...points]
      .sort((a, b) => a.time - b.time)
      .filter((p, idx, arr) => idx === 0 || p.time > arr[idx - 1].time);

    if (sorted.length === 0) return;

    const pointByTime = new Map<number, ChartPoint>();
    sorted.forEach((p) => pointByTime.set(p.time, p));

    const chart = createChart(el, {
      width: el.clientWidth,
      height,
      layout: {
        background: { type: ColorType.Solid, color: '#FFFFFF' },
        textColor: '#0B1120',
        fontFamily: 'Inter, -apple-system, sans-serif',
        fontSize: 11,
      },
      grid: {
        vertLines: { color: '#F1F5F9' },
        horzLines: { color: '#EDF2F9' },
      },
      rightPriceScale: {
        borderColor: '#E2E8F0',
        scaleMargins: { top: 0.14, bottom: 0.28 },
      },
      timeScale: {
        borderColor: '#E2E8F0',
        timeVisible: true,
        secondsVisible: false,
      },
      crosshair: {
        mode: CrosshairMode.Magnet,
        vertLine: {
          color: '#7DD3FC',
          width: 1,
          style: 2,
          labelBackgroundColor: '#0B1120',
        },
        horzLine: {
          color: '#7DD3FC',
          width: 1,
          style: 2,
          labelBackgroundColor: '#0B1120',
        },
      },
      handleScroll: { vertTouchDrag: false },
    });

    chartRef.current = chart;

    const areaSeries = chart.addAreaSeries({
      lineColor: '#0098EA',
      lineWidth: 2,
      topColor: 'rgba(0, 152, 234, 0.24)',
      bottomColor: 'rgba(0, 152, 234, 0.01)',
      crosshairMarkerRadius: 4,
      crosshairMarkerBorderColor: '#FFFFFF',
      crosshairMarkerBackgroundColor: '#0098EA',
      priceFormat: {
        type: 'price',
        precision: 2,
        minMove: 0.01,
      },
    });

    const avgLineSeries = chart.addLineSeries({
      color: '#0B1120',
      lineWidth: 1,
      lineStyle: 2,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    });

    const volumeSeries = chart.addHistogramSeries({
      color: 'rgba(0, 152, 234, 0.22)',
      priceFormat: { type: 'volume' },
      priceScaleId: '',
    });

    volumeSeries.priceScale().applyOptions({
      scaleMargins: {
        top: 0.78,
        bottom: 0,
      },
    });

    areaSeries.setData(
      sorted.map((p) => ({
        time: p.time as Time,
        value: Number(p.floor),
      })),
    );

    avgLineSeries.setData(
      sorted.map((p) => ({
        time: p.time as Time,
        value: Number(p.avg_sale),
      })),
    );

    volumeSeries.setData(
      sorted.map((p, idx) => {
        const prev = idx > 0 ? sorted[idx - 1].floor : p.floor;
        const up = p.floor >= prev;
        return {
          time: p.time as Time,
          value: Number(p.volume),
          color: up ? 'rgba(26, 107, 255, 0.25)' : 'rgba(148, 163, 184, 0.28)',
        };
      }),
    );

    chart.timeScale().fitContent();

    chart.subscribeCrosshairMove((param) => {
      if (!param.time || typeof param.time !== 'number') {
        setHoverPoint(null);
        return;
      }
      const match = pointByTime.get(param.time);
      setHoverPoint(match ?? null);
    });

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const width = Math.floor(entry.contentRect.width);
        if (width > 0) {
          chart.applyOptions({ width });
        }
      }
    });
    observer.observe(el);

    return () => {
      observer.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, [points, height]);

  return (
    <div className="w-full">
      {/* Live Crosshair Readout */}
      {activePoint && (
        <div className="flex flex-wrap items-center justify-between gap-2 mb-2 px-1 text-[11px]">
          <div className="flex items-center gap-3 tabular-nums">
            <span className="inline-flex items-center gap-1.5 font-bold text-[#0F172A]">
              <span className="w-2 h-2 rounded-full bg-[#1A6BFF]" />
              Флор: {formatTon(activePoint.floor)} TON
            </span>
            <span className="inline-flex items-center gap-1.5 font-semibold text-[#475569]">
              <span className="w-2 h-0.5 bg-[#0088CC]" />
              Сер.: {formatTon(activePoint.avg_sale)} TON
            </span>
          </div>
          <span className="text-[#64748B] font-semibold tabular-nums">
            Об&apos;єм: {formatTon(activePoint.volume, 1)} TON
          </span>
        </div>
      )}

      <div
        ref={containerRef}
        className="w-full rounded-xl overflow-hidden border border-[#EDF2FA] bg-white"
        style={{ height }}
      />
    </div>
  );
};
