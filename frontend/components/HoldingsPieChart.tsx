"use client";

const COLORS = [
  "#410093",
  "#0c8a44",
  "#d92424",
  "#9b59d0",
  "#0e9594",
  "#d97706",
  "#c2185b",
  "#6a8caf",
  "#7cb342",
  "#8e6c8a",
  "#94a3b8",
];

export function HoldingsPieChart({ slices }: { slices: { label: string; value: number }[] }) {
  const total = slices.reduce((sum, s) => sum + s.value, 0);
  if (total <= 0) return null;

  let cumulative = 0;
  const stops = slices.map((s, i) => {
    const start = (cumulative / total) * 360;
    cumulative += s.value;
    const end = (cumulative / total) * 360;
    return `${COLORS[i % COLORS.length]} ${start}deg ${end}deg`;
  });

  return (
    <div className="flex flex-wrap items-center gap-6">
      <div
        className="h-40 w-40 shrink-0 rounded-full"
        style={{ background: `conic-gradient(${stops.join(", ")})` }}
      />
      <div className="flex flex-col gap-1.5 text-sm">
        {slices.map((s, i) => (
          <div key={s.label} className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: COLORS[i % COLORS.length] }} />
            <span className="font-medium text-gray-900">{s.label}</span>
            <span className="text-gray-500">{((s.value / total) * 100).toFixed(1)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}
