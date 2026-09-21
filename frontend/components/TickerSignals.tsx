"use client";

import { useEffect, useState } from "react";

import { Pagination } from "@/components/Pagination";
import { SignalRow } from "@/components/SignalRow";
import { api } from "@/lib/api-client";
import { SIGNAL_RANGES, type SignalRangeKey } from "@/lib/signalRanges";
import type { SignalItem } from "@/lib/types";

const PAGE_SIZE = 25;

export function TickerSignals({ ticker }: { ticker: string }) {
  const [signals, setSignals] = useState<SignalItem[] | null>(null);
  const [total, setTotal] = useState(0);
  const [range, setRange] = useState<SignalRangeKey>("3M");
  const [page, setPage] = useState(1);

  useEffect(() => setPage(1), [ticker, range]);

  useEffect(() => {
    const days = SIGNAL_RANGES.find((r) => r.key === range)!.days;
    setSignals(null);
    api
      .getSignalsForTicker(ticker, PAGE_SIZE, (page - 1) * PAGE_SIZE, days)
      .then((res) => {
        setSignals(res.items);
        setTotal(res.total);
      })
      .catch(() => {
        setSignals([]);
        setTotal(0);
      });
  }, [ticker, range, page]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold text-gray-900">Disclosed Buys & Sells</h2>
        <div className="flex gap-1">
          {SIGNAL_RANGES.map((r) => (
            <button
              key={r.key}
              onClick={() => setRange(r.key)}
              className={`rounded-md px-2 py-0.5 text-xs font-semibold ${
                range === r.key ? "bg-gray-800 text-white" : "bg-gray-100 text-gray-500 hover:bg-gray-200"
              }`}
            >
              {r.key}
            </button>
          ))}
        </div>
      </div>
      <p className="text-xs text-gray-500">
        Congressional trades (House PTR) and corporate insider trades (SEC Form 4) disclosed for this ticker.
      </p>

      {signals === null && <p className="text-sm text-gray-500">Loading…</p>}
      {signals?.length === 0 && (
        <p className="text-sm text-gray-500">No disclosed insider or congressional trades in this window — try a wider range.</p>
      )}

      {signals && signals.length > 0 && (
        <div className="flex flex-col divide-y divide-gray-200 rounded-lg border border-gray-200 bg-white">
          {signals.map((s, i) => (
            <SignalRow key={`${s.source}-${s.actor}-${s.date}-${i}`} signal={s} showTicker={false} />
          ))}
        </div>
      )}

      <Pagination page={page} totalPages={totalPages} onChange={setPage} />
    </div>
  );
}
