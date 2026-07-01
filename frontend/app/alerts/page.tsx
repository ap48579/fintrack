import { AlertsPanel } from "@/components/AlertsPanel";
import { BackNav } from "@/components/BackNav";

export default function AlertsPage() {
  return (
    <main className="mx-auto max-w-3xl p-8">
      <BackNav />
      <AlertsPanel />
    </main>
  );
}
