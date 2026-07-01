"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { api, streamResearch } from "@/lib/api-client";
import { SENTIMENT_COLOR } from "@/lib/sentiment";
import type { CandidateItem, ResearchReportSummary } from "@/lib/types";

export function ResearchHub() {
  const router = useRouter();
  const [candidates, setCandidates] = useState<CandidateItem[] | null>(null);
  const [recent, setRecent] = useState<ResearchReportSummary[] | null>(null);
  const [subjectType, setSubjectType] = useState<"ticker" | "theme">("ticker");
  const [subject, setSubject] = useState("");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [steps, setSteps] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  function refreshRecent() {
    api.getRecentResearch().then(setRecent).catch(() => setRecent([]));
  }

  useEffect(() => {
    api.getCandidates().then(setCandidates).catch(() => setCandidates([]));
    refreshRecent();
  }, []);

  async function runResearch(targetSubjectType: "ticker" | "theme", targetSubject: string, targetQuery?: string) {
    setLoading(true);
    setError(null);
    setSteps([]);
    try {
      const report = await streamResearch(targetSubjectType, targetSubject, targetQuery, (step) =>
        setSteps((prev) => [...prev, step])
      );
      router.push(`/research/${report.id}`);
    } catch {
      setError("Research failed — try again.");
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-2xl font-extrabold text-gray-900">Research</h1>
        <p className="mt-1 text-sm text-gray-500">
          Trigger a deep-dive on any ticker or theme — synthesized from news, Reddit, filings, price/volume,
          capex trends, and blue whale activity.
        </p>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (subject.trim()) runResearch(subjectType, subject.trim(), query.trim());
        }}
        className="flex flex-col gap-3 rounded-lg border border-gray-200 bg-white p-4"
      >
        <div className="flex gap-2">
          <select
            value={subjectType}
            onChange={(e) => setSubjectType(e.target.value as "ticker" | "theme")}
            disabled={loading}
            className="rounded-md border border-gray-300 bg-white px-2 py-2 text-sm outline-none focus:border-brand"
          >
            <option value="ticker">Ticker</option>
            <option value="theme">Theme</option>
          </select>
          <input
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            disabled={loading}
            placeholder={subjectType === "ticker" ? "e.g. NVDA" : "e.g. AI chip export controls"}
            className="flex-1 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm outline-none focus:border-brand"
          />
        </div>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          disabled={loading}
          placeholder="Optional: a specific question to focus the research on"
          className="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm outline-none focus:border-brand"
        />
        <button
          type="submit"
          disabled={loading || !subject.trim()}
          className="self-start rounded-full bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-dark disabled:opacity-50"
        >
          {loading ? "Researching…" : "Run Deep Research"}
        </button>
        {error && <p className="text-sm text-loss">{error}</p>}

        {loading && steps.length > 0 && (
          <div className="flex flex-col gap-1 rounded-md bg-gray-50 p-3 text-sm">
            {steps.map((step, i) => (
              <div key={i} className="flex items-center gap-2 text-gray-500">
                {i === steps.length - 1 ? (
                  <span className="h-2 w-2 animate-pulse rounded-full bg-brand" />
                ) : (
                  <span className="text-gain">✓</span>
                )}
                <span className={i === steps.length - 1 ? "text-gray-900" : ""}>{step}</span>
              </div>
            ))}
          </div>
        )}
      </form>

      <div>
        <h2 className="mb-2 text-lg font-bold text-gray-900">Today&apos;s Candidates</h2>
        <p className="mb-2 text-xs text-gray-500">Flagged by the passive daily scan — click to research further.</p>
        {candidates === null && <p className="text-sm text-gray-500">Loading…</p>}
        {candidates?.length === 0 && <p className="text-sm text-gray-500">No candidates flagged today.</p>}
        <div className="flex flex-col divide-y divide-gray-200 rounded-lg border border-gray-200 bg-white">
          {candidates?.map((c) => (
            <button
              key={`${c.subject_type}-${c.subject}`}
              onClick={() => runResearch(c.subject_type, c.subject)}
              disabled={loading}
              className="flex items-center justify-between px-4 py-3 text-left hover:bg-gray-50 disabled:opacity-50"
            >
              <div>
                <span className="font-medium text-gray-900">{c.subject}</span>
                <span className="ml-2 text-xs uppercase text-gray-400">{c.subject_type}</span>
                <div className="text-sm text-gray-500">{c.reason}</div>
              </div>
              <span className="text-sm text-gray-400">score {c.score.toFixed(2)}</span>
            </button>
          ))}
        </div>
      </div>

      <div>
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-lg font-bold text-gray-900">Recent Research</h2>
          <button onClick={refreshRecent} className="text-sm font-semibold text-brand hover:underline">
            Refresh
          </button>
        </div>
        {recent === null && <p className="text-sm text-gray-500">Loading…</p>}
        {recent?.length === 0 && <p className="text-sm text-gray-500">No research run yet — try one above.</p>}
        <div className="flex flex-col divide-y divide-gray-200 rounded-lg border border-gray-200 bg-white">
          {recent?.map((r) => (
            <Link key={r.id} href={`/research/${r.id}`} className="flex items-center justify-between gap-3 px-4 py-3 hover:bg-gray-50">
              <div className="min-w-0">
                <span className="font-medium text-gray-900">{r.subject}</span>
                <span className="ml-2 text-xs uppercase text-gray-400">{r.subject_type}</span>
                <div className="truncate text-sm text-gray-500">{r.summary}</div>
              </div>
              <span className={`shrink-0 text-xs font-medium uppercase ${SENTIMENT_COLOR[r.sentiment_direction]}`}>
                {r.sentiment_direction}
              </span>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
