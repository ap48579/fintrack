"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { api, streamResearch } from "@/lib/api-client";
import { SENTIMENT_COLOR } from "@/lib/sentiment";
import type { ResearchReportSummary } from "@/lib/types";

export function TickerResearch({ ticker }: { ticker: string }) {
  const router = useRouter();
  const [reports, setReports] = useState<ResearchReportSummary[] | null>(null);
  const [triggering, setTriggering] = useState(false);
  const [currentStep, setCurrentStep] = useState<string | null>(null);

  useEffect(() => {
    api
      .getTickerResearch(ticker)
      .then(setReports)
      .catch(() => setReports([]));
  }, [ticker]);

  async function research() {
    setTriggering(true);
    setCurrentStep(null);
    try {
      const report = await streamResearch("ticker", ticker, undefined, setCurrentStep);
      router.push(`/research/${report.id}`);
    } catch {
      setTriggering(false);
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold text-gray-900">Research</h2>
        <button
          onClick={research}
          disabled={triggering}
          className="rounded-full bg-brand px-3 py-1.5 text-sm font-semibold text-white hover:bg-brand-dark disabled:opacity-50"
        >
          {triggering ? "Researching…" : "Research " + ticker.toUpperCase()}
        </button>
      </div>
      {triggering && currentStep && (
        <div className="flex items-center gap-2 text-sm text-gray-500">
          <span className="h-2 w-2 animate-pulse rounded-full bg-brand" />
          {currentStep}
        </div>
      )}

      {reports === null && <p className="text-sm text-gray-500">Loading…</p>}
      {reports?.length === 0 && <p className="text-sm text-gray-500">No research yet for this ticker.</p>}
      <div className="flex flex-col divide-y divide-gray-200 rounded-lg border border-gray-200 bg-white">
        {reports?.map((r) => (
          <Link key={r.id} href={`/research/${r.id}`} className="flex items-center justify-between px-4 py-2 hover:bg-gray-50">
            <div>
              {r.subject_type === "theme" && <span className="mr-2 text-xs uppercase text-gray-400">theme: {r.subject}</span>}
              <span className="text-sm text-gray-700">{r.summary}</span>
            </div>
            <span className={`ml-3 shrink-0 text-xs font-medium uppercase ${SENTIMENT_COLOR[r.sentiment_direction]}`}>
              {r.sentiment_direction}
            </span>
          </Link>
        ))}
      </div>
    </div>
  );
}
