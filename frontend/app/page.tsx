import Link from "next/link";

import { SearchBar } from "@/components/SearchBar";
import { WatchlistPanel } from "@/components/WatchlistPanel";

export default function DashboardPage() {
  return (
    <main className="flex min-h-screen flex-col items-center gap-6 bg-gray-50 p-8">
      <div className="flex w-full max-w-md items-center justify-between">
        <h1 className="text-2xl font-extrabold text-brand">FinTrack</h1>
        <div className="flex gap-3">
          <Link href="/research" className="text-sm font-semibold text-brand hover:text-brand-dark">
            Research →
          </Link>
          <Link href="/whales" className="text-sm font-semibold text-brand hover:text-brand-dark">
            Blue Whale Holdings →
          </Link>
          <Link href="/alerts" className="text-sm font-semibold text-brand hover:text-brand-dark">
            Alerts →
          </Link>
        </div>
      </div>
      <SearchBar />
      <WatchlistPanel />
    </main>
  );
}
