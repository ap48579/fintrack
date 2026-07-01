import { BackNav } from "@/components/BackNav";
import { StockDetail } from "@/components/StockDetail";

export default async function StockPage({ params }: { params: Promise<{ ticker: string }> }) {
  const { ticker } = await params;
  return (
    <main className="mx-auto max-w-4xl p-8">
      <BackNav />
      <StockDetail ticker={ticker} />
    </main>
  );
}
