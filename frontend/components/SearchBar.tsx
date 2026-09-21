"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { api } from "@/lib/api-client";
import type { TickerSearchResult } from "@/lib/types";

export function SearchBar() {
  const [value, setValue] = useState("");
  const [results, setResults] = useState<TickerSearchResult[]>([]);
  const [open, setOpen] = useState(false);
  const [highlighted, setHighlighted] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const router = useRouter();

  useEffect(() => {
    const query = value.trim();
    if (!query) {
      setResults([]);
      return;
    }
    const timer = setTimeout(() => {
      api
        .searchTickers(query)
        .then((r) => {
          setResults(r);
          setHighlighted(0);
        })
        .catch(() => setResults([]));
    }, 150);
    return () => clearTimeout(timer);
  }, [value]);

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  function goToSymbol(symbol: string) {
    setOpen(false);
    setValue("");
    setResults([]);
    router.push(`/stock/${symbol.toUpperCase()}`);
  }

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (open && results.length > 0) {
      goToSymbol(results[highlighted]!.symbol);
    } else if (value.trim()) {
      goToSymbol(value.trim());
    }
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (!open || results.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlighted((h) => Math.min(h + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlighted((h) => Math.max(h - 1, 0));
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  return (
    <div ref={containerRef} className="relative w-full max-w-sm">
      <form onSubmit={onSubmit} className="flex w-full gap-2">
        <input
          value={value}
          onChange={(e) => {
            setValue(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKeyDown}
          placeholder="Search company or ticker (e.g. Apple, AAPL)"
          className="flex-1 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm outline-none focus:border-brand"
          autoComplete="off"
        />
        <button type="submit" className="rounded-md bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-dark">
          Go
        </button>
      </form>

      {open && results.length > 0 && (
        <div className="absolute z-10 mt-1 w-full overflow-hidden rounded-md border border-gray-200 bg-white shadow-lg">
          {results.map((r, i) => (
            <button
              key={r.symbol}
              type="button"
              onMouseDown={() => goToSymbol(r.symbol)}
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
  );
}
