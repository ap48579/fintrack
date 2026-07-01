import { BackNav } from "@/components/BackNav";
import { InstitutionPortfolio } from "@/components/InstitutionPortfolio";

export default async function InstitutionPage({ params }: { params: Promise<{ institution: string }> }) {
  const { institution } = await params;
  return (
    <main className="mx-auto max-w-4xl p-8">
      <BackNav href="/whales" label="Blue Whale Holdings" />
      <InstitutionPortfolio institution={institution} />
    </main>
  );
}
