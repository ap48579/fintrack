"use client";

import { createChart, IChartApi, LineSeries } from "lightweight-charts";
import { useEffect, useRef } from "react";

import type { FundamentalsQuarter } from "@/lib/types";

interface FundamentalsTrendChartProps {
  quarters: FundamentalsQuarter[];
}

const SERIES: { key: keyof FundamentalsQuarter; label: string; color: string }[] = [
  { key: "revenue", label: "Revenue", color: "#410093" },
  { key: "net_income", label: "Net Income", color: "#0c8a44" },
  { key: "total_debt", label: "Total Debt", color: "#d92424" },
];

export function FundamentalsTrendChart({ quarters }: FundamentalsTrendChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      height: 280,
      layout: { background: { color: "transparent" }, textColor: "#6b7280" },
      grid: { vertLines: { color: "#e5e7eb" }, horzLines: { color: "#e5e7eb" } },
      localization: { priceFormatter: (p: number) => `$${p.toFixed(1)}B` },
    });
    chartRef.current = chart;

    // Ascending order, oldest first — lightweight-charts requires data sorted by time.
    const ascending = [...quarters].reverse();

    for (const { key, label, color } of SERIES) {
      const points = ascending
        .filter((q) => q[key] !== null)
        .map((q) => ({ time: q.period, value: Number(q[key]) / 1e9 })); // raw USD -> billions, matches priceFormatter
      if (points.length === 0) continue;
      const series = chart.addSeries(LineSeries, { color, lineWidth: 2, title: label });
      series.setData(points);
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
  }, [quarters]);

  return <div ref={containerRef} className="w-full" />;
}
