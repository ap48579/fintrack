"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api-client";
import type { HypothesisItem } from "@/lib/types";

const HORIZON_ORDER = ["7d", "30d", "60d"];

function excessColor(value: number | undefined): string {
  if (value === undefined) return "text-gray-400";
  return value >= 0 ? "text-gain" : "text-loss";
}

export function HypothesisResults() {
  const [hypotheses, setHypotheses] = useState<HypothesisItem[] | null>(null);

  useEffect(() => {
    api
      .getHypotheses()
      .then(setHypotheses)
      .catch(() => setHypotheses([]));
  }, []);

  if (hypotheses !== null && hypotheses.length === 0) return null;

  return (
    <div className="flex w-full flex-col gap-3">
      <div>
        <h2 className="text-lg font-bold text-gray-900">Hypothesis Backtests</h2>
        <p className="text-xs text-gray-500">
          Does a disclosed-buying signal actually correlate with forward returns? Excess return vs. SPY over the
          same window, re-run periodically as more data lands — treat a single run as directional, not proof.
        </p>
      </div>

      {hypotheses === null && <p className="text-sm text-gray-500">Loading…</p>}

      <div className="flex flex-col gap-2">
        {hypotheses?.map((h) => (
          <div key={h.name} className="rounded-lg border border-gray-200 bg-white p-3">
            <div className="flex items-baseline justify-between gap-2">
              <h3 className="text-sm font-semibold text-gray-900">{h.name}</h3>
              {h.latest_run && (
                <span className="shrink-0 text-xs text-gray-400">
                  n={h.latest_run.sample_size} · {h.latest_run.data_window_start} to {h.latest_run.data_window_end}
                </span>
              )}
            </div>
            <p className="mt-0.5 text-xs text-gray-500">{h.description}</p>

            {!h.latest_run && <p className="mt-2 text-xs text-gray-400">Not run yet.</p>}

            {h.latest_run && (
              <div className="mt-2 flex flex-wrap gap-3">
                {HORIZON_ORDER.filter((horizon) => horizon in h.latest_run!.results).map((horizon) => {
                  const stats = h.latest_run!.results[horizon]!;
                  if (stats.note) {
                    return (
                      <div key={horizon} className="text-xs text-gray-400">
                        {horizon}: {stats.note} (n={stats.n})
                      </div>
                    );
                  }
                  return (
                    <div key={horizon} className="rounded-md bg-gray-50 px-2 py-1 text-xs">
                      <span className="font-semibold text-gray-700">{horizon}</span>{" "}
                      <span className={excessColor(stats.mean_excess)}>
                        {stats.mean_excess !== undefined && stats.mean_excess >= 0 ? "+" : ""}
                        {stats.mean_excess}% mean
                      </span>{" "}
                      <span className="text-gray-400">
                        · {stats.win_rate}% win · n={stats.n}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
