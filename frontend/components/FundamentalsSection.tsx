"use client";

import { useEffect, useState } from "react";

import { FundamentalsTrendChart } from "@/components/charts/FundamentalsTrendChart";
import { api } from "@/lib/api-client";
import type { FilingItem, FundamentalsQuarter, FundamentalsSummary } from "@/lib/types";

function formatUSD(value: number | null): string {
  if (value === null) return "—";
  const abs = Math.abs(value);
  if (abs >= 1e9) return `$${(value / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `$${(value / 1e6).toFixed(2)}M`;
  return `$${value.toFixed(0)}`;
}

function formatPercent(value: number | null): string {
  if (value === null) return "—";
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
}

export function FundamentalsSection({ ticker }: { ticker: string }) {
  const [summary, setSummary] = useState<FundamentalsSummary | null>(null);
  const [history, setHistory] = useState<FundamentalsQuarter[] | null>(null);
  const [filings, setFilings] = useState<FilingItem[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    setError(false);
    setSummary(null);
    setHistory(null);
    setFilings(null);
    Promise.all([api.getFundamentals(ticker), api.getFundamentalsHistory(ticker), api.getFilings(ticker)])
      .then(([s, h, f]) => {
        setSummary(s);
        setHistory(h);
        setFilings(f);
      })
      .catch(() => setError(true));
  }, [ticker]);

  if (error) return null; // not every searched symbol is an SEC filer (e.g. some ETFs) — fail quietly
  if (!summary || !history || !filings) {
    return <p className="text-sm text-gray-500">Loading fundamentals…</p>;
  }

  const stats: { label: string; value: string }[] = [
    { label: "Revenue (qtr)", value: formatUSD(summary.revenue) },
    { label: "Net Income (qtr)", value: formatUSD(summary.net_income) },
    { label: "Total Debt", value: formatUSD(summary.total_debt) },
    { label: "Total Assets", value: formatUSD(summary.total_assets) },
    { label: "Debt/Equity", value: summary.debt_to_equity?.toFixed(2) ?? "—" },
    { label: "Net Margin", value: summary.net_margin !== null ? `${(summary.net_margin * 100).toFixed(1)}%` : "—" },
    { label: "Revenue QoQ", value: formatPercent(summary.revenue_growth_qoq) },
    { label: "Revenue YoY", value: formatPercent(summary.revenue_growth_yoy) },
  ];

  return (
    <div className="flex flex-col gap-4">
      <h2 className="text-lg font-bold text-gray-900">Fundamentals</h2>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {stats.map((s) => (
          <div key={s.label} className="rounded-lg border border-gray-200 p-3">
            <div className="text-xs text-gray-500">{s.label}</div>
            <div className="text-base font-semibold text-gray-900">{s.value}</div>
          </div>
        ))}
      </div>

      <FundamentalsTrendChart quarters={history} />

      <div>
        <h3 className="mb-2 text-sm font-semibold text-gray-700">Recent Filings</h3>
        <ul className="flex flex-col gap-1">
          {filings.map((f) => (
            <li key={f.edgar_url} className="text-sm">
              <a href={f.edgar_url} target="_blank" rel="noopener noreferrer" className="font-medium text-brand hover:underline">
                {f.filing_type}
              </a>
              <span className="ml-2 text-gray-500">{f.filed_date}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
