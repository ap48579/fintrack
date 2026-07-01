"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api-client";
import type { TickerHolder } from "@/lib/types";

function formatUSD(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1e9) return `$${(value / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `$${(value / 1e6).toFixed(2)}M`;
  return `$${value.toFixed(0)}`;
}

export function WhaleHolders({ ticker }: { ticker: string }) {
  const [holders, setHolders] = useState<TickerHolder[] | null>(null);

  useEffect(() => {
    setHolders(null);
    api
      .getTickerHolders(ticker)
      .then(setHolders)
      .catch(() => setHolders([]));
  }, [ticker]);

  if (holders === null) return <p className="text-sm text-gray-500">Loading whale holders…</p>;
  if (holders.length === 0) {
    return <p className="text-sm text-gray-500">None of the tracked institutions currently hold this ticker.</p>;
  }

  return (
    <div className="flex flex-col gap-2">
      <h2 className="text-lg font-bold text-gray-900">Blue Whale Holders</h2>
      <p className="text-xs text-gray-500">13F filings have up to a 45-day reporting lag — this is not real-time.</p>
      <div className="flex flex-col divide-y divide-gray-200 rounded-lg border border-gray-200 bg-white">
        {holders.map((h) => (
          <div key={h.institution} className="flex items-center justify-between px-4 py-2">
            <div>
              <div className="font-medium text-gray-900">{h.institution}</div>
              <div className="text-xs text-gray-500">as of {h.period}</div>
            </div>
            <div className="text-right">
              <div className="font-medium text-gray-900">{formatUSD(h.market_value)}</div>
              <div className="text-xs text-gray-500">{h.shares.toLocaleString()} shares</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
