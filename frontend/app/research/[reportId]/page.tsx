import { BackNav } from "@/components/BackNav";
import { ResearchReportView } from "@/components/ResearchReportView";

export default async function ResearchReportPage({ params }: { params: Promise<{ reportId: string }> }) {
  const { reportId } = await params;
  return (
    <main className="mx-auto max-w-3xl p-8">
      <BackNav href="/research" label="Research" />
      <ResearchReportView reportId={reportId} />
    </main>
  );
}
