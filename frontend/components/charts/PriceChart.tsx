"use client";

import { CandlestickSeries, createChart, IChartApi, LineSeries, UTCTimestamp } from "lightweight-charts";
import { useEffect, useRef } from "react";

export interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface LinePoint {
  time: number;
  value: number;
}

interface PriceChartProps {
  candles: Candle[];
  ma50?: LinePoint[];
  ma200?: LinePoint[];
}

export function PriceChart({ candles, ma50 = [], ma200 = [] }: PriceChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      height: 400,
      layout: { background: { color: "transparent" }, textColor: "#6b7280" },
      grid: { vertLines: { color: "#e5e7eb" }, horzLines: { color: "#e5e7eb" } },
      timeScale: { timeVisible: true },
    });
    chartRef.current = chart;

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#0c8a44",
      downColor: "#d92424",
      borderVisible: false,
      wickUpColor: "#0c8a44",
      wickDownColor: "#d92424",
    });
    candleSeries.setData(
      candles.map((c) => ({
        time: c.time as UTCTimestamp,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      }))
    );

    if (ma50.length > 0) {
      const ma50Series = chart.addSeries(LineSeries, { color: "#410093", lineWidth: 1, title: "MA50" });
      ma50Series.setData(ma50.map((p) => ({ time: p.time as UTCTimestamp, value: p.value })));
    }

    if (ma200.length > 0) {
      const ma200Series = chart.addSeries(LineSeries, { color: "#d97706", lineWidth: 1, title: "MA200" });
      ma200Series.setData(ma200.map((p) => ({ time: p.time as UTCTimestamp, value: p.value })));
    }

    chart.timeScale().fitContent();

    const handleResize = () => {
      if (containerRef.current) chart.applyOptions({ width: containerRef.current.clientWidth });
    };
    window.addEventListener("resize", handleResize);
    handleResize();

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
    };
  }, [candles, ma50, ma200]);

  return <div ref={containerRef} className="w-full" />;
}
