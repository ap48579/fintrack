import Link from "next/link";

export function BackNav({ href = "/", label = "FinTrack" }: { href?: string; label?: string }) {
  return (
    <div className="-mx-8 mb-6 border-b border-gray-200 px-8 pb-3">
      <Link href={href} className="inline-flex items-center gap-1 text-sm font-semibold text-brand hover:text-brand-dark">
        ← {label}
      </Link>
    </div>
  );
}
