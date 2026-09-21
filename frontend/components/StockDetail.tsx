"use client";

import { useEffect, useState } from "react";

import { PriceChart } from "@/components/charts/PriceChart";
import { FundamentalsSection } from "@/components/FundamentalsSection";
import { TickerResearchChat } from "@/components/TickerResearchChat";
import { TickerSignals } from "@/components/TickerSignals";
import { WhaleHolders } from "@/components/WhaleHolders";
import { api } from "@/lib/api-client";
import type { HistoryResponse, PriceRange, Quote } from "@/lib/types";

const RANGES: PriceRange[] = ["1D", "1W", "1M", "1Y", "5Y"];
const RANGE_LABEL: Record<PriceRange, string> = {
  "1D": "today",
  "1W": "past week",
  "1M": "past month",
  "1Y": "past year",
  "5Y": "past 5 years",
};

export function StockDetail({ ticker }: { ticker: string }) {
  const [quote, setQuote] = useState<Quote | null>(null);
  const [history, setHistory] = useState<HistoryResponse | null>(null);
  const [range, setRange] = useState<PriceRange>("1M");
  const [onWatchlist, setOnWatchlist] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([api.getQuote(ticker), api.getHistory(ticker, range)])
      .then(([q, h]) => {
        if (cancelled) return;
        setQuote(q);
        setHistory(h);
      })
      .catch(() => !cancelled && setError(`No data found for ${ticker}`))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [ticker, range]);

  useEffect(() => {
    api
      .getWatchlist()
      .then((items) => setOnWatchlist(items.some((i) => i.symbol === ticker.toUpperCase())))
      .catch(() => {});
  }, [ticker]);

  async function toggleWatchlist() {
    if (onWatchlist) {
      await api.removeFromWatchlist(ticker);
      setOnWatchlist(false);
    } else {
      await api.addToWatchlist(ticker);
      setOnWatchlist(true);
    }
  }

  if (error) {
    return <p className="text-loss">{error}</p>;
  }

  // The quote endpoint only ever returns today's change vs. the prior close, so the badge used
  // to show the same "today" number no matter which range tab was selected. Deriving it from the
  // selected range's own candles instead makes it actually track the range: change from that
  // period's opening price to its latest close.
  const rangeChange =
    history && history.candles.length > 0
      ? (() => {
          const first = history.candles[0]!;
          const last = history.candles[history.candles.length - 1]!;
          const amount = last.close - first.open;
          return { amount, percent: first.open !== 0 ? (amount / first.open) * 100 : 0 };
        })()
      : null;
  const isUp = (rangeChange?.percent ?? quote?.change_percent ?? 0) >= 0;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-extrabold text-gray-900">{ticker.toUpperCase()}</h1>
          {quote && (
            <div className="mt-1 flex items-baseline gap-3">
              <span className="text-2xl font-bold text-gray-900">${quote.price.toFixed(2)}</span>
              {rangeChange && (
                <span
                  className={`rounded px-2 py-0.5 text-sm font-semibold ${
                    isUp ? "bg-green-50 text-gain" : "bg-red-50 text-loss"
                  }`}
                  title={`Change over the selected range (${RANGE_LABEL[range]})`}
                >
                  {isUp ? "▲" : "▼"} {isUp ? "+" : ""}
                  {rangeChange.amount.toFixed(2)} ({isUp ? "+" : ""}
                  {rangeChange.percent.toFixed(2)}%) {RANGE_LABEL[range]}
                </span>
              )}
              <span className="text-sm text-gray-500">Vol {quote.volume.toLocaleString()}</span>
            </div>
          )}
        </div>
        <button
          onClick={toggleWatchlist}
          className={`rounded-full px-4 py-2 text-sm font-semibold ${
            onWatchlist ? "bg-brand-light text-brand" : "bg-brand text-white hover:bg-brand-dark"
          }`}
        >
          {onWatchlist ? "On Watchlist ✓" : "Add to Watchlist"}
        </button>
      </div>

      <div className="flex gap-2">
        {RANGES.map((r) => (
          <button
            key={r}
            onClick={() => setRange(r)}
            className={`rounded-md px-3 py-1 text-sm font-semibold ${
              r === range ? "bg-brand text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"
            }`}
          >
            {r}
          </button>
        ))}
      </div>

      {loading && <p className="text-sm text-gray-500">Loading…</p>}
      {history && !loading && (
        <PriceChart candles={history.candles} ma50={history.ma50} ma200={history.ma200} />
      )}

      <hr className="border-gray-200" />
      <FundamentalsSection ticker={ticker} />

      <hr className="border-gray-200" />
      <TickerSignals ticker={ticker} />

      <hr className="border-gray-200" />
      <WhaleHolders ticker={ticker} />

      <hr className="border-gray-200" />
      <TickerResearchChat ticker={ticker} />
    </div>
  );
}
