import { BackNav } from "@/components/BackNav";
import { WhalesOverview } from "@/components/WhalesOverview";

export default function WhalesPage() {
  return (
    <main className="mx-auto max-w-3xl p-8">
      <BackNav />
      <WhalesOverview />
    </main>
  );
}
