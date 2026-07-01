"use client";

import { useEffect, useState } from "react";

import { PushNotificationToggle } from "@/components/PushNotificationToggle";
import { api } from "@/lib/api-client";
import type { AlertLogItem, AlertRuleResponse, AlertRuleType } from "@/lib/types";

const RULE_LABELS: Record<AlertRuleType, string> = {
  price_move: "Price move",
  fundamental_threshold: "Fundamental threshold",
  whale_movement: "Whale movement",
  candidate_flagged: "Candidate flagged",
  watchlist_candidate_match: "Watchlist candidate match",
};

const NEEDS_TICKER: AlertRuleType[] = ["price_move", "fundamental_threshold", "whale_movement", "candidate_flagged"];
const NEEDS_THRESHOLD: AlertRuleType[] = ["price_move", "fundamental_threshold"];

export function AlertsPanel() {
  const [rules, setRules] = useState<AlertRuleResponse[] | null>(null);
  const [log, setLog] = useState<AlertLogItem[] | null>(null);
  const [ruleType, setRuleType] = useState<AlertRuleType>("price_move");
  const [ticker, setTicker] = useState("");
  const [condition, setCondition] = useState<"gt" | "lt">("gt");
  const [threshold, setThreshold] = useState("");
  const [error, setError] = useState<string | null>(null);

  function refresh() {
    api.getAlertRules().then(setRules).catch(() => setRules([]));
    api.getAlertLog().then(setLog).catch(() => setLog([]));
  }

  useEffect(refresh, []);

  async function createRule(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api.createAlertRule({
        rule_type: ruleType,
        ticker: NEEDS_TICKER.includes(ruleType) && ticker ? ticker : undefined,
        condition: NEEDS_THRESHOLD.includes(ruleType) ? condition : undefined,
        threshold: NEEDS_THRESHOLD.includes(ruleType) && threshold ? Number(threshold) : undefined,
      });
      setTicker("");
      setThreshold("");
      refresh();
    } catch {
      setError("Could not create rule — check the required fields for this alert type.");
    }
  }

  async function removeRule(ruleId: string) {
    await api.deleteAlertRule(ruleId);
    refresh();
  }

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-2xl font-extrabold text-gray-900">Alerts</h1>
        <p className="mt-1 text-sm text-gray-500">Rules are evaluated automatically after each pillar&apos;s data refresh.</p>
      </div>

      <PushNotificationToggle />

      <form onSubmit={createRule} className="flex flex-col gap-3 rounded-lg border border-gray-200 bg-white p-4">
        <select
          value={ruleType}
          onChange={(e) => setRuleType(e.target.value as AlertRuleType)}
          className="rounded-md border border-gray-300 bg-white px-2 py-2 text-sm outline-none focus:border-brand"
        >
          {Object.entries(RULE_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>

        {NEEDS_TICKER.includes(ruleType) && (
          <input
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            placeholder="Ticker, e.g. AAPL"
            className="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm outline-none focus:border-brand"
          />
        )}

        {NEEDS_THRESHOLD.includes(ruleType) && (
          <div className="flex gap-2">
            <select
              value={condition}
              onChange={(e) => setCondition(e.target.value as "gt" | "lt")}
              className="rounded-md border border-gray-300 bg-white px-2 py-2 text-sm outline-none focus:border-brand"
            >
              <option value="gt">greater than</option>
              <option value="lt">less than</option>
            </select>
            <input
              value={threshold}
              onChange={(e) => setThreshold(e.target.value)}
              type="number"
              step="any"
              placeholder={ruleType === "price_move" ? "% move, e.g. 5" : "e.g. 1.5"}
              className="flex-1 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm outline-none focus:border-brand"
            />
          </div>
        )}

        <button type="submit" className="self-start rounded-full bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-dark">
          Create Rule
        </button>
        {error && <p className="text-sm text-loss">{error}</p>}
      </form>

      <div>
        <h2 className="mb-2 text-lg font-bold text-gray-900">Active Rules</h2>
        {rules?.length === 0 && <p className="text-sm text-gray-500">No alert rules yet.</p>}
        <div className="flex flex-col divide-y divide-gray-200 rounded-lg border border-gray-200 bg-white">
          {rules?.map((r) => (
            <div key={r.id} className="flex items-center justify-between px-4 py-3">
              <div className="text-sm">
                <span className="font-medium text-gray-900">{RULE_LABELS[r.rule_type]}</span>
                {r.ticker && <span className="ml-2 text-gray-500">{r.ticker}</span>}
                {r.threshold !== null && (
                  <span className="ml-2 text-gray-500">
                    {r.condition ?? "gt"} {r.threshold}
                  </span>
                )}
              </div>
              <button onClick={() => removeRule(r.id)} className="text-sm font-medium text-loss hover:underline">
                Remove
              </button>
            </div>
          ))}
        </div>
      </div>

      <div>
        <h2 className="mb-2 text-lg font-bold text-gray-900">Alert Feed</h2>
        {log?.length === 0 && <p className="text-sm text-gray-500">No alerts triggered yet.</p>}
        <div className="flex flex-col divide-y divide-gray-200 rounded-lg border border-gray-200 bg-white">
          {log?.map((item) => (
            <div key={item.id} className="px-4 py-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium uppercase text-gray-400">{RULE_LABELS[item.rule_type]}</span>
                <span className="text-xs text-gray-400">{new Date(item.triggered_at).toLocaleString()}</span>
              </div>
              <p className="text-sm text-gray-700">{item.message}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
