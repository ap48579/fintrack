"use client";

import { useEffect, useState } from "react";

import { Pagination } from "@/components/Pagination";
import { SignalRow } from "@/components/SignalRow";
import { api } from "@/lib/api-client";
import { SIGNAL_RANGES, type SignalRangeKey } from "@/lib/signalRanges";
import type { SignalItem } from "@/lib/types";

type SourceFilter = "all" | SignalItem["source"];

const FILTERS: { value: SourceFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "insider", label: "Insiders" },
  { value: "congress", label: "Congress" },
  { value: "whale", label: "13F Whales" },
];

const PAGE_SIZE = 10;

export function SignalsFeed() {
  const [signals, setSignals] = useState<SignalItem[] | null>(null);
  const [total, setTotal] = useState(0);
  const [filter, setFilter] = useState<SourceFilter>("all");
  const [range, setRange] = useState<SignalRangeKey>("3M");
  const [page, setPage] = useState(1);

  // Changing the range or source tab invalidates the current page — jump back to page 1 rather
  // than risk landing past the end of a now-smaller result set.
  useEffect(() => setPage(1), [range, filter]);

  useEffect(() => {
    const days = SIGNAL_RANGES.find((r) => r.key === range)!.days;
    setSignals(null);
    api
      .getRecentSignals(PAGE_SIZE, (page - 1) * PAGE_SIZE, days, filter === "all" ? undefined : filter)
      .then((res) => {
        setSignals(res.items);
        setTotal(res.total);
      })
      .catch(() => {
        setSignals([]);
        setTotal(0);
      });
  }, [range, filter, page]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="flex w-full flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold text-gray-900">Recent Disclosures</h2>
        <div className="flex gap-1">
          {FILTERS.map((f) => (
            <button
              key={f.value}
              onClick={() => setFilter(f.value)}
              className={`rounded-full px-3 py-1 text-xs font-semibold ${
                filter === f.value ? "bg-brand text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex items-center justify-between">
        <p className="text-xs text-gray-400">
          {total > 0 ? `${total.toLocaleString()} disclosures in the selected window, newest first.` : "Showing disclosures filed in the selected window, newest first."}
        </p>
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

      {signals === null && <p className="text-sm text-gray-500">Loading…</p>}
      {signals?.length === 0 && (
        <p className="text-sm text-gray-500">No disclosures found in this window — try a wider range, or run the Phase 1 batch job to ingest more.</p>
      )}

      <div className="flex flex-col divide-y divide-gray-200 rounded-lg border border-gray-200 bg-white">
        {signals?.map((s, i) => (
          <SignalRow key={`${s.source}-${s.ticker}-${s.actor}-${s.date}-${i}`} signal={s} />
        ))}
      </div>

      <Pagination page={page} totalPages={totalPages} onChange={setPage} />
    </div>
  );
}
