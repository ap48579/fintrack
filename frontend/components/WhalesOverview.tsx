"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { api } from "@/lib/api-client";
import type { ActivityItem, InstitutionOverview, InstitutionSummary } from "@/lib/types";

const CHANGE_LABEL: Record<ActivityItem["change_type"], string> = {
  new: "Opened new position",
  exit: "Exited position",
  increase: "Increased position",
  decrease: "Decreased position",
};

const CHANGE_COLOR: Record<ActivityItem["change_type"], string> = {
  new: "text-gain",
  exit: "text-loss",
  increase: "text-gain",
  decrease: "text-loss",
};

function formatUSD(value: number | null): string {
  if (value === null) return "—";
  const abs = Math.abs(value);
  if (abs >= 1e9) return `$${(value / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `$${(value / 1e6).toFixed(2)}M`;
  return `$${value.toFixed(0)}`;
}

export function WhalesOverview() {
  const [institutions, setInstitutions] = useState<InstitutionOverview[] | null>(null);
  const [activity, setActivity] = useState<ActivityItem[] | null>(null);
  const [searchName, setSearchName] = useState("");
  const [searchResults, setSearchResults] = useState<InstitutionSummary[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [adding, setAdding] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function refreshInstitutions() {
    api.getInstitutionsOverview().then(setInstitutions).catch(() => setInstitutions([]));
  }

  useEffect(() => {
    refreshInstitutions();
    api.getWhaleActivity().then(setActivity).catch(() => setActivity([]));
  }, []);

  async function runSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!searchName.trim()) return;
    setSearching(true);
    setError(null);
    try {
      setSearchResults(await api.searchInstitutions(searchName.trim()));
    } catch {
      setError("Search failed — try again.");
    } finally {
      setSearching(false);
    }
  }

  async function addInstitution(name: string, cik: string) {
    setAdding(cik);
    setError(null);
    try {
      await api.addInstitution(name, cik);
      setSearchResults(null);
      setSearchName("");
      refreshInstitutions();
    } catch {
      setError(`Couldn't add ${name} — its CIK may not have any 13F-HR filings on record.`);
    } finally {
      setAdding(null);
    }
  }

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-2xl font-extrabold text-gray-900">Blue Whale Holdings</h1>
        <p className="mt-1 text-sm text-gray-500">
          Tracked institutional 13F filings — up to a 45-day reporting lag, never real-time.
        </p>
      </div>

      <form onSubmit={runSearch} className="flex flex-col gap-2 rounded-lg border border-gray-200 bg-white p-4">
        <label className="text-sm font-semibold text-gray-700">Track a new institution</label>
        <div className="flex gap-2">
          <input
            value={searchName}
            onChange={(e) => setSearchName(e.target.value)}
            placeholder="Institution name, e.g. Citadel Advisors"
            className="flex-1 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm outline-none focus:border-brand"
          />
          <button
            type="submit"
            disabled={searching}
            className="rounded-md bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-dark disabled:opacity-50"
          >
            {searching ? "Searching…" : "Search"}
          </button>
        </div>
        {error && <p className="text-sm text-loss">{error}</p>}
        {searchResults && (
          <div className="flex flex-col divide-y divide-gray-200 rounded-md border border-gray-200">
            {searchResults.length === 0 && <p className="px-3 py-2 text-sm text-gray-500">No 13F filers found by that name.</p>}
            {searchResults.map((r) => (
              <div key={r.cik} className="flex items-center justify-between px-3 py-2">
                <div>
                  <span className="text-sm font-medium text-gray-900">{r.name}</span>
                  <span className="ml-2 text-xs text-gray-400">CIK {r.cik}</span>
                </div>
                <button
                  onClick={() => addInstitution(r.name, r.cik)}
                  disabled={adding !== null}
                  className="rounded-full bg-brand px-3 py-1 text-xs font-semibold text-white hover:bg-brand-dark disabled:opacity-50"
                >
                  {adding === r.cik ? "Pulling 13F data…" : "Add & Pull Data"}
                </button>
              </div>
            ))}
          </div>
        )}
      </form>

      <div>
        <h2 className="mb-2 text-lg font-bold text-gray-900">Tracked Institutions</h2>
        {institutions === null && <p className="text-sm text-gray-500">Loading…</p>}
        <div className="flex flex-col gap-2">
          {institutions?.map((inst) => (
            <Link
              key={inst.cik}
              href={`/whales/${inst.cik}`}
              className="flex items-center justify-between rounded-lg border border-gray-200 bg-white px-4 py-3 hover:border-brand hover:shadow-sm"
            >
              <div>
                <span className="font-medium text-gray-900">{inst.name}</span>
                <div className="text-xs text-gray-500">
                  {inst.position_count} positions {inst.period && `· as of ${inst.period}`}
                </div>
              </div>
              <div className="text-right">
                <div className="font-semibold text-gray-900">{formatUSD(inst.total_market_value)}</div>
                <div className="flex gap-2 text-xs">
                  {inst.value_change_pct !== null && (
                    <span className={inst.value_change_pct >= 0 ? "text-gain" : "text-loss"}>
                      {inst.value_change_pct >= 0 ? "+" : ""}
                      {inst.value_change_pct.toFixed(1)}%
                    </span>
                  )}
                  <span className="text-gray-400">
                    {inst.new_positions} new / {inst.exited_positions} exited
                  </span>
                </div>
              </div>
            </Link>
          ))}
        </div>
      </div>

      <div>
        <h2 className="mb-2 text-lg font-bold text-gray-900">Recent Whale Activity</h2>
        {activity === null && <p className="text-sm text-gray-500">Loading…</p>}
        {activity?.length === 0 && <p className="text-sm text-gray-500">No activity recorded yet.</p>}
        <div className="flex flex-col divide-y divide-gray-200 rounded-lg border border-gray-200 bg-white">
          {activity?.map((item, i) => (
            <div key={i} className="flex items-center justify-between px-4 py-3">
              <div>
                <span className="font-medium text-gray-900">{item.institution}</span>
                <span className={`ml-2 ${CHANGE_COLOR[item.change_type]}`}>{CHANGE_LABEL[item.change_type]}</span>
                <div className="text-sm text-gray-500">
                  <Link href={`/stock/${item.symbol}`} className="text-brand hover:underline">
                    {item.symbol}
                  </Link>{" "}
                  — {item.name}
                </div>
              </div>
              <div className="text-right">
                <div className="font-medium text-gray-900">{Math.round(item.magnitude).toLocaleString()} sh</div>
                <div className="text-xs text-gray-500">{item.period}</div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
