"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { api } from "@/lib/api-client";
import { SENTIMENT_COLOR } from "@/lib/sentiment";
import type { ResearchReportDetail } from "@/lib/types";

export function ResearchReportView({ reportId }: { reportId: string }) {
  const [report, setReport] = useState<ResearchReportDetail | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    api
      .getReport(reportId)
      .then(setReport)
      .catch(() => setError(true));
  }, [reportId]);

  if (error) return <p className="text-loss">Report not found.</p>;
  if (!report) return <p className="text-sm text-gray-500">Loading report…</p>;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <div className="text-xs uppercase text-gray-400">{report.subject_type}</div>
        <h1 className="text-2xl font-extrabold text-gray-900">{report.subject}</h1>
        <p className="mt-1 text-sm text-gray-500">
          &quot;{report.query}&quot; · {new Date(report.created_at).toLocaleString()}
        </p>
        <span className={`mt-2 inline-block text-sm font-medium uppercase ${SENTIMENT_COLOR[report.sentiment_direction]}`}>
          {report.sentiment_direction}
        </span>
      </div>

      <p className="text-gray-700">{report.summary}</p>

      {report.ticker_links.length > 0 && (
        <div>
          <h2 className="mb-2 text-sm font-semibold text-gray-700">Ticker Exposure</h2>
          <div className="flex flex-wrap gap-2">
            {report.ticker_links.map((t) => (
              <Link
                key={t.ticker}
                href={`/stock/${t.ticker}`}
                className={`rounded-full border px-3 py-1 text-sm ${SENTIMENT_COLOR[t.exposure_type === "positive" ? "bullish" : t.exposure_type === "negative" ? "bearish" : "neutral"]} border-current`}
              >
                {t.ticker} · {t.exposure_type} ({(t.confidence * 100).toFixed(0)}%)
              </Link>
            ))}
          </div>
        </div>
      )}

      <div className="whitespace-pre-wrap rounded-lg border border-gray-200 bg-white p-4 text-sm leading-relaxed text-gray-700">
        {report.full_report}
      </div>

      <div>
        <h2 className="mb-2 text-sm font-semibold text-gray-700">Sources</h2>
        <ul className="flex flex-col gap-1">
          {report.sources.map((s, i) => (
            <li key={i} className="text-sm">
              <span className="mr-2 text-xs uppercase text-gray-400">{s.source_type}</span>
              <a href={s.url} target="_blank" rel="noopener noreferrer" className="text-brand hover:underline">
                {s.title}
              </a>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
