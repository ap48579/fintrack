"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { api } from "@/lib/api-client";
import type { TickerSearchResult, WatchlistItem } from "@/lib/types";

function groupBySector(items: WatchlistItem[]): [string, WatchlistItem[]][] {
  const groups = new Map<string, WatchlistItem[]>();
  for (const item of items) {
    const key = item.sector ?? "Other";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(item);
  }
  return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));
}

export function WatchlistPanel() {
  const [items, setItems] = useState<WatchlistItem[] | null>(null);
  const [adding, setAdding] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<TickerSearchResult[]>([]);
  const [highlighted, setHighlighted] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  function refresh() {
    api
      .getWatchlist()
      .then(setItems)
      .catch(() => setItems([]));
  }

  useEffect(refresh, []);

  useEffect(() => {
    const q = query.trim();
    if (!q) {
      setResults([]);
      return;
    }
    const timer = setTimeout(() => {
      api
        .searchTickers(q)
        .then((r) => {
          setResults(r);
          setHighlighted(0);
        })
        .catch(() => setResults([]));
    }, 150);
    return () => clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) setResults([]);
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  async function addSymbol(symbol: string) {
    setError(null);
    try {
      await api.addToWatchlist(symbol);
      setQuery("");
      setResults([]);
      setAdding(false);
      refresh();
    } catch {
      setError(`Couldn't add "${symbol}".`);
    }
  }

  async function removeSymbol(symbol: string) {
    await api.removeFromWatchlist(symbol);
    refresh();
  }

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (results.length > 0) addSymbol(results[highlighted]!.symbol);
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (results.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlighted((h) => Math.min(h + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlighted((h) => Math.max(h - 1, 0));
    }
  }

  return (
    <div className="flex w-full max-w-md flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-700">Watchlist</h2>
        <button
          onClick={() => {
            setAdding((a) => !a);
            setQuery("");
            setResults([]);
            setError(null);
          }}
          className="rounded-full bg-brand px-3 py-1 text-xs font-semibold text-white hover:bg-brand-dark"
        >
          {adding ? "Cancel" : "+ Add Stock"}
        </button>
      </div>

      {adding && (
        <div ref={containerRef} className="relative">
          <form onSubmit={onSubmit} className="flex gap-2">
            <input
              autoFocus
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder="Search company or ticker, e.g. Bloom Energy"
              autoComplete="off"
              className="flex-1 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm outline-none focus:border-brand"
            />
          </form>
          {results.length > 0 && (
            <div className="absolute z-10 mt-1 w-full overflow-hidden rounded-md border border-gray-200 bg-white shadow-lg">
              {results.map((r, i) => (
                <button
                  key={r.symbol}
                  type="button"
                  onMouseDown={() => addSymbol(r.symbol)}
                  onMouseEnter={() => setHighlighted(i)}
                  className={`flex w-full items-center justify-between px-3 py-2 text-left text-sm ${
                    i === highlighted ? "bg-brand-light" : "hover:bg-gray-50"
                  }`}
                >
                  <span className="text-gray-700">{r.name}</span>
                  <span className="ml-3 shrink-0 font-mono text-xs font-semibold text-gray-500">{r.symbol}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
      {error && <p className="text-sm text-loss">{error}</p>}

      {items === null && <p className="text-sm text-gray-500">Loading watchlist…</p>}
      {items?.length === 0 && <p className="text-sm text-gray-500">Your watchlist is empty — add a stock above.</p>}

      {items && items.length > 0 && (
        <div className="flex flex-col gap-4">
          {groupBySector(items).map(([sector, group]) => (
            <div key={sector}>
              <div className="mb-1 text-xs font-medium uppercase tracking-wide text-gray-400">{sector}</div>
              <div className="flex flex-col divide-y divide-gray-200 rounded-lg border border-gray-200 bg-white">
                {group.map((item) => (
                  <div key={item.ticker_id} className="group flex items-center justify-between px-4 py-3 hover:bg-gray-50">
                    <Link href={`/stock/${item.symbol}`} className="min-w-0 flex-1">
                      <div className="font-medium text-gray-900">{item.symbol}</div>
                      <div className="truncate text-xs text-gray-500">{item.name}</div>
                    </Link>
                    <div className="flex items-center gap-3">
                      {item.quote && (
                        <div className="text-right">
                          <div className="font-medium text-gray-900">${item.quote.price.toFixed(2)}</div>
                          <div className={item.quote.change_percent >= 0 ? "text-sm text-gain" : "text-sm text-loss"}>
                            {item.quote.change_percent >= 0 ? "+" : ""}
                            {item.quote.change_percent.toFixed(2)}%
                          </div>
                        </div>
                      )}
                      <button
                        onClick={() => removeSymbol(item.symbol)}
                        title={`Remove ${item.symbol} from watchlist`}
                        className="text-gray-300 opacity-0 hover:text-loss group-hover:opacity-100"
                      >
                        ✕
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
