"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { api, streamVerdictGeneration } from "@/lib/api-client";
import type { VerdictItem } from "@/lib/types";

const VERDICT_STYLE: Record<VerdictItem["verdict"], string> = {
  bullish: "bg-green-50 text-gain",
  bearish: "bg-red-50 text-loss",
  neutral: "bg-gray-100 text-gray-600",
};

export function VerdictPanel({ ticker, onClose }: { ticker: string; onClose: () => void }) {
  const [verdict, setVerdict] = useState<VerdictItem | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [phaseText, setPhaseText] = useState<{ bull?: string; bear?: string }>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoaded(false);
    setVerdict(null);
    setPhaseText({});
    setError(null);
    api
      .getVerdict(ticker)
      .then((v) => {
        setVerdict(v);
        setLoaded(true);
      })
      .catch(() => setLoaded(true));
  }, [ticker]);

  async function onGenerate() {
    setGenerating(true);
    setError(null);
    setPhaseText({});
    try {
      const result = await streamVerdictGeneration(ticker, (phase, text) =>
        setPhaseText((prev) => ({ ...prev, [phase]: text }))
      );
      setVerdict(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong generating this verdict.");
    } finally {
      setGenerating(false);
    }
  }

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Link href={`/stock/${ticker}`} className="text-lg font-bold text-gray-900 hover:text-brand">
            {ticker}
          </Link>
          {verdict && (
            <span className={`rounded px-2 py-0.5 text-xs font-bold uppercase ${VERDICT_STYLE[verdict.verdict]}`}>
              {verdict.verdict} · {(verdict.confidence * 100).toFixed(0)}% confidence
            </span>
          )}
        </div>
        <button onClick={onClose} className="text-sm text-gray-400 hover:text-gray-700">
          ✕
        </button>
      </div>

      {!loaded && <p className="mt-2 text-sm text-gray-500">Loading…</p>}

      {loaded && !verdict && !generating && (
        <div className="mt-3 flex flex-col items-start gap-2">
          <p className="text-sm text-gray-500">
            No AI verdict yet for {ticker}. This runs a bull case, a bear case, and a judge pass that weighs
            both — takes a minute or two on local hardware.
          </p>
          <button
            onClick={onGenerate}
            className="rounded-full bg-brand px-3 py-1.5 text-sm font-semibold text-white hover:bg-brand-dark"
          >
            Generate AI verdict
          </button>
        </div>
      )}

      {error && <p className="mt-2 text-sm text-loss">{error}</p>}

      {generating && (
        <div className="mt-3 flex flex-col gap-3">
          <PhaseBlock label="Bull case" text={phaseText.bull} pending={!phaseText.bull} />
          <PhaseBlock label="Bear case" text={phaseText.bear} pending={!!phaseText.bull && !phaseText.bear} />
          {phaseText.bear && (
            <div className="flex items-center gap-2 text-sm text-gray-400">
              <span className="h-2 w-2 animate-pulse rounded-full bg-brand" /> Judge weighing both cases…
            </div>
          )}
        </div>
      )}

      {verdict && !generating && (
        <div className="mt-3 flex flex-col gap-3">
          <PhaseBlock label="Bull case" text={verdict.bull_case} />
          <PhaseBlock label="Bear case" text={verdict.bear_case} />
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <h4 className="text-xs font-semibold uppercase text-gray-400">Key risks</h4>
              <p className="text-sm text-gray-700">{verdict.key_risks}</p>
            </div>
            <div>
              <h4 className="text-xs font-semibold uppercase text-gray-400">Key catalysts</h4>
              <p className="text-sm text-gray-700">{verdict.key_catalysts}</p>
            </div>
          </div>
          <div className="flex items-center justify-between text-xs text-gray-400">
            <span>Generated {new Date(verdict.generated_at).toLocaleString()}</span>
            <button onClick={onGenerate} className="font-semibold text-gray-400 hover:text-brand">
              Regenerate
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function PhaseBlock({ label, text, pending }: { label: string; text?: string; pending?: boolean }) {
  if (pending) {
    return (
      <div className="flex items-center gap-2 text-sm text-gray-400">
        <span className="h-2 w-2 animate-pulse rounded-full bg-brand" /> Building {label.toLowerCase()}…
      </div>
    );
  }
  if (!text) return null;
  return (
    <div>
      <h4 className="mb-1 text-xs font-semibold uppercase text-gray-400">{label}</h4>
      <p className="whitespace-pre-wrap text-sm text-gray-700">{text}</p>
    </div>
  );
}
