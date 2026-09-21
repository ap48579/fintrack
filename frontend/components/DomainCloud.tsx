"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { VerdictPanel } from "@/components/VerdictPanel";
import { api } from "@/lib/api-client";
import type { DomainGroup, DomainTickerItem } from "@/lib/types";

const SOURCE_DOT: Record<DomainTickerItem["sources"][number], string> = {
  insider: "bg-blue-500",
  congress: "bg-brand",
  whale: "bg-amber-500",
};

const TOP_N_FOR_VERDICT = 3;

function fontSizeFor(weight: number, minWeight: number, maxWeight: number): string {
  if (maxWeight === minWeight) return "1rem";
  const t = (weight - minWeight) / (maxWeight - minWeight);
  return `${(0.8 + t * 0.9).toFixed(2)}rem`;
}

export function DomainCloud() {
  const [domains, setDomains] = useState<DomainGroup[] | null>(null);
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);

  useEffect(() => {
    api
      .getDomainBuySignals(180, 2)
      .then(setDomains)
      .catch(() => setDomains([]));
  }, []);

  if (domains !== null && domains.length === 0) return null;

  const allWeights = domains?.flatMap((d) => d.tickers.map((t) => t.weight)) ?? [];
  const minWeight = allWeights.length ? Math.min(...allWeights) : 0;
  const maxWeight = allWeights.length ? Math.max(...allWeights) : 1;

  return (
    <div className="flex w-full flex-col gap-3">
      <div>
        <h2 className="text-lg font-bold text-gray-900">What's Being Bought, By Domain</h2>
        <p className="text-xs text-gray-500">
          Tickers sized by how many distinct insiders, legislators, and institutions bought in the last 6 months.
          Not a recommendation — just where the disclosed buying is concentrated. The top 3 per sector (✨) have
          an AI bull/bear verdict available.
        </p>
      </div>

      {domains === null && <p className="text-sm text-gray-500">Loading…</p>}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {domains?.slice(0, 15).map((domain) => (
          <div key={domain.sector} className="rounded-lg border border-gray-200 bg-white p-3">
            <h3 className="mb-2 text-xs font-bold uppercase tracking-wide text-gray-400">{domain.sector}</h3>
            <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
              {domain.tickers.map((t, i) => (
                <span key={t.ticker} className="inline-flex items-center gap-0.5">
                  <Link
                    href={`/stock/${t.ticker}`}
                    title={`${t.name} — bought by ${t.weight} distinct ${t.weight === 1 ? "buyer" : "buyers"} (${t.sources.join(", ")})`}
                    className="inline-flex items-center gap-1 font-semibold text-gray-700 hover:text-brand"
                    style={{ fontSize: fontSizeFor(t.weight, minWeight, maxWeight) }}
                  >
                    {t.sources.map((s) => (
                      <span key={s} className={`inline-block h-1.5 w-1.5 rounded-full ${SOURCE_DOT[s]}`} />
                    ))}
                    {t.ticker}
                  </Link>
                  {i < TOP_N_FOR_VERDICT && (
                    <button
                      onClick={() => setSelectedTicker(t.ticker)}
                      title={`AI bull/bear verdict for ${t.ticker}`}
                      className="text-sm leading-none hover:opacity-70"
                    >
                      ✨
                    </button>
                  )}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>

      {selectedTicker && <VerdictPanel ticker={selectedTicker} onClose={() => setSelectedTicker(null)} />}
    </div>
  );
}
