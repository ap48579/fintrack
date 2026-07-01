"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { api } from "@/lib/api-client";
import type { WatchlistItem } from "@/lib/types";

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
  const [newTicker, setNewTicker] = useState("");
  const [error, setError] = useState<string | null>(null);

  function refresh() {
    api
      .getWatchlist()
      .then(setItems)
      .catch(() => setItems([]));
  }

  useEffect(refresh, []);

  async function addTicker(e: React.FormEvent) {
    e.preventDefault();
    if (!newTicker.trim()) return;
    setError(null);
    try {
      await api.addToWatchlist(newTicker.trim().toUpperCase());
      setNewTicker("");
      setAdding(false);
      refresh();
    } catch {
      setError(`Couldn't find ticker "${newTicker.toUpperCase()}".`);
    }
  }

  return (
    <div className="flex w-full max-w-md flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-700">Watchlist</h2>
        <button onClick={() => setAdding((a) => !a)} className="rounded-full bg-brand px-3 py-1 text-xs font-semibold text-white hover:bg-brand-dark">
          {adding ? "Cancel" : "+ Add Stock"}
        </button>
      </div>

      {adding && (
        <form onSubmit={addTicker} className="flex gap-2">
          <input
            autoFocus
            value={newTicker}
            onChange={(e) => setNewTicker(e.target.value)}
            placeholder="Ticker, e.g. NVDA"
            className="flex-1 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm outline-none focus:border-brand"
          />
          <button type="submit" className="rounded-md bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-dark">
            Add
          </button>
        </form>
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
                  <Link
                    key={item.ticker_id}
                    href={`/stock/${item.symbol}`}
                    className="flex items-center justify-between px-4 py-3 hover:bg-gray-50"
                  >
                    <div>
                      <div className="font-medium text-gray-900">{item.symbol}</div>
                      <div className="text-xs text-gray-500">{item.name}</div>
                    </div>
                    {item.quote && (
                      <div className="text-right">
                        <div className="font-medium text-gray-900">${item.quote.price.toFixed(2)}</div>
                        <div className={item.quote.change_percent >= 0 ? "text-sm text-gain" : "text-sm text-loss"}>
                          {item.quote.change_percent >= 0 ? "+" : ""}
                          {item.quote.change_percent.toFixed(2)}%
                        </div>
                      </div>
                    )}
                  </Link>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
