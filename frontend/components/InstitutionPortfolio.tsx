"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { api } from "@/lib/api-client";
import { HoldingsPieChart } from "@/components/HoldingsPieChart";
import type { PortfolioPosition } from "@/lib/types";

const PIE_TOP_N = 9;

function buildPieSlices(positions: PortfolioPosition[]): { label: string; value: number }[] {
  const sorted = [...positions].sort((a, b) => b.market_value - a.market_value);
  const top = sorted.slice(0, PIE_TOP_N);
  const rest = sorted.slice(PIE_TOP_N);
  const slices = top.map((p) => ({ label: p.symbol, value: p.market_value }));
  const otherValue = rest.reduce((sum, p) => sum + p.market_value, 0);
  if (otherValue > 0) slices.push({ label: `Other (${rest.length})`, value: otherValue });
  return slices;
}

function formatUSD(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1e9) return `$${(value / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `$${(value / 1e6).toFixed(2)}M`;
  return `$${value.toFixed(0)}`;
}

export function InstitutionPortfolio({ institution }: { institution: string }) {
  const [positions, setPositions] = useState<PortfolioPosition[] | null>(null);
  const [name, setName] = useState(institution);
  const [error, setError] = useState(false);

  useEffect(() => {
    api
      .getInstitutionHoldings(institution)
      .then(setPositions)
      .catch(() => setError(true));
    api
      .getInstitutions()
      .then((insts) => {
        const match = insts.find((i) => i.cik === institution || i.name.toLowerCase() === institution.toLowerCase());
        if (match) setName(match.name);
      })
      .catch(() => {});
  }, [institution]);

  if (error) return <p className="text-loss">Unknown tracked institution.</p>;
  if (positions === null) return <p className="text-sm text-gray-500">Loading portfolio…</p>;

  const total = positions.reduce((sum, p) => sum + p.market_value, 0);

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-2xl font-extrabold text-gray-900">{name}</h1>
        <p className="mt-1 text-sm text-gray-500">
          {positions.length} positions · {formatUSD(total)} total · as of{" "}
          {positions[0]?.period ?? "—"} · 13F filings have up to a 45-day reporting lag
        </p>
      </div>

      {positions.length > 0 && (
        <div className="rounded-lg border border-gray-200 bg-white p-4">
          <h2 className="mb-3 text-sm font-semibold text-gray-700">Holdings Breakdown</h2>
          <HoldingsPieChart slices={buildPieSlices(positions)} />
        </div>
      )}

      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-200 text-left text-gray-500">
            <th className="py-2">Symbol</th>
            <th className="py-2">Name</th>
            <th className="py-2 text-right">Shares</th>
            <th className="py-2 text-right">Market Value</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((p) => (
            <tr key={p.symbol} className="border-b border-gray-100">
              <td className="py-2 font-medium">
                <Link href={`/stock/${p.symbol}`} className="text-brand hover:underline">
                  {p.symbol}
                </Link>
              </td>
              <td className="py-2 text-gray-600">{p.name}</td>
              <td className="py-2 text-right">{p.shares.toLocaleString()}</td>
              <td className="py-2 text-right">{formatUSD(p.market_value)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
