import Link from "next/link";

import type { SignalItem } from "@/lib/types";

const SOURCE_LABEL: Record<SignalItem["source"], string> = {
  insider: "Insider",
  congress: "Congress",
  whale: "13F Whale",
};

const SOURCE_COLOR: Record<SignalItem["source"], string> = {
  insider: "bg-blue-50 text-blue-700",
  congress: "bg-purple-50 text-brand",
  whale: "bg-amber-50 text-amber-700",
};

const DIRECTION_UP = new Set(["buy", "increase", "new"]);

// A handful of "ticker" rows aren't real symbols (an unresolved CUSIP, a bond descriptor with
// spaces, a literal "[NONE]"/"N/A" placeholder from a PTR row that had no ticker) — one of those
// literally crashed the page, since Next.js reads square brackets in a <Link href> as dynamic
// route syntax. Render those as plain text instead of a link rather than filtering the row out
// entirely, since the underlying disclosure is still real data worth showing.
const SAFE_SYMBOL_RE = /^[A-Z0-9.\-/]{1,10}$/;
const JUNK_SYMBOLS = new Set(["NONE", "N/A", "NULL"]);
function isSafeTickerSymbol(symbol: string): boolean {
  return SAFE_SYMBOL_RE.test(symbol) && !JUNK_SYMBOLS.has(symbol.toUpperCase());
}

function directionLabel(direction: string): string {
  if (direction === "new") return "NEW";
  return direction.toUpperCase();
}

function relativeDate(isoDate: string): string {
  const days = Math.round((Date.now() - new Date(isoDate).getTime()) / 86_400_000);
  if (days <= 0) return "today";
  if (days === 1) return "1 day ago";
  if (days < 30) return `${days} days ago`;
  if (days < 60) return "1 month ago";
  if (days < 365) return `${Math.round(days / 30)} months ago`;
  return `${(days / 365).toFixed(1)} years ago`;
}

function lagBadge(lagDays: number | null) {
  if (lagDays === null) return null;
  let color = "bg-gray-100 text-gray-600";
  if (lagDays <= 3) color = "bg-green-50 text-gain";
  else if (lagDays <= 15) color = "bg-gray-100 text-gray-600";
  else if (lagDays <= 45) color = "bg-amber-50 text-amber-700";
  else color = "bg-red-50 text-loss";

  return (
    <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${color}`} title="Days between trade and disclosure">
      {lagDays}d lag
    </span>
  );
}

export function SignalRow({ signal, showTicker = true }: { signal: SignalItem; showTicker?: boolean }) {
  const isUp = DIRECTION_UP.has(signal.direction);

  return (
    <div className="flex items-start justify-between gap-3 px-4 py-3">
      <div className="flex min-w-0 flex-col gap-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${SOURCE_COLOR[signal.source]}`}>
            {SOURCE_LABEL[signal.source]}
          </span>
          <span
            className={`rounded px-1.5 py-0.5 text-xs font-bold ${isUp ? "bg-green-50 text-gain" : "bg-red-50 text-loss"}`}
          >
            {directionLabel(signal.direction)}
          </span>
          {showTicker &&
            (signal.ticker && isSafeTickerSymbol(signal.ticker) ? (
              <Link href={`/stock/${signal.ticker}`} className="text-sm font-bold text-gray-900 hover:text-brand">
                {signal.ticker}
              </Link>
            ) : (
              <span className="text-sm font-medium text-gray-400">{signal.ticker || "non-equity"}</span>
            ))}
          {lagBadge(signal.lag_days)}
        </div>
        <div className="truncate text-sm text-gray-700">
          {signal.actor}
          {signal.actor_detail && <span className="text-gray-400"> · {signal.actor_detail}</span>}
        </div>
        {signal.detail && <div className="truncate text-xs text-gray-400">{signal.detail}</div>}
      </div>
      <div className="shrink-0 text-right">
        <div className="text-sm font-semibold text-gray-900">{signal.amount_label}</div>
        <div className="text-xs text-gray-400" title={`filed ${signal.date}`}>
          filed {relativeDate(signal.date)}
        </div>
      </div>
    </div>
  );
}
