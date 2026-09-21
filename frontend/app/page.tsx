import { DomainCloud } from "@/components/DomainCloud";
import { HypothesisResults } from "@/components/HypothesisResults";
import { SearchBar } from "@/components/SearchBar";
import { SignalsFeed } from "@/components/SignalsFeed";
import { WatchlistPanel } from "@/components/WatchlistPanel";

export default function DashboardPage() {
  return (
    <main className="mx-auto flex min-h-screen w-full max-w-3xl flex-col gap-6 bg-gray-50 p-8">
      <h1 className="text-2xl font-extrabold text-brand">FinTrack</h1>

      <SearchBar />

      <hr className="border-gray-200" />
      <WatchlistPanel />

      <hr className="border-gray-200" />
      <DomainCloud />

      <hr className="border-gray-200" />
      <HypothesisResults />

      <hr className="border-gray-200" />
      <p className="-mt-3 text-sm text-gray-500">
        Congressional trades, corporate insider trades, and institutional 13F activity — any disclosed buy or sell,
        newest first. No scoring yet, just what was filed.
      </p>
      <SignalsFeed />
    </main>
  );
}
