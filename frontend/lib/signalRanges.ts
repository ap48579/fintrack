export type SignalRangeKey = "3M" | "6M" | "1Y" | "All";

export const SIGNAL_RANGES: { key: SignalRangeKey; days: number | null }[] = [
  { key: "3M", days: 90 },
  { key: "6M", days: 180 },
  { key: "1Y", days: 365 },
  { key: "All", days: null },
];
