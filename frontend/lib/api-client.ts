import type {
  ActivityItem,
  AlertLogItem,
  AlertRuleResponse,
  AlertRuleType,
  CandidateItem,
  ChatMessageItem,
  ChatThreadResponse,
  DomainGroup,
  HypothesisItem,
  FilingItem,
  FundamentalsQuarter,
  FundamentalsSummary,
  HistoryResponse,
  InstitutionOverview,
  InstitutionSummary,
  PortfolioPosition,
  PriceRange,
  Quote,
  ResearchReportDetail,
  ResearchReportSummary,
  ResearchSourceItem,
  SignalItem,
  SignalPage,
  TickerHolder,
  TickerSearchResult,
  VerdictItem,
  WatchlistItem,
} from "@/lib/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    throw new ApiError(res.status, `${init?.method ?? "GET"} ${path} failed: ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

/** Consumes the SSE reasoning-trace stream from POST /research/stream, calling `onStep` for
 * each progress line as it arrives, and resolving with the final persisted report. */
export async function streamResearch(
  subjectType: "ticker" | "theme",
  subject: string,
  query: string | undefined,
  onStep: (step: string) => void
): Promise<ResearchReportDetail> {
  const res = await fetch(`${API_URL}/research/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ subject_type: subjectType, subject, query }),
  });
  if (!res.ok || !res.body) {
    throw new ApiError(res.status, "Research stream request failed");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let report: ResearchReportDetail | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() ?? "";
    for (const chunk of chunks) {
      if (!chunk.startsWith("data: ")) continue;
      const payload = JSON.parse(chunk.slice(6));
      if (payload.done) {
        report = payload.report as ResearchReportDetail;
      } else if (payload.step) {
        onStep(payload.step);
      }
    }
  }

  if (!report) throw new Error("Research stream ended without a report");
  return report;
}

/** Consumes the SSE stream from POST /research/chat/{ticker}/stream: thinking/content deltas as
 * the model reasons and writes, then a final done event with sources. */
export async function streamChatMessage(
  ticker: string,
  message: string | null,
  onThinking: (delta: string) => void,
  onContent: (delta: string) => void
): Promise<{ sources: ResearchSourceItem[] }> {
  const res = await fetch(`${API_URL}/research/chat/${ticker}/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  if (!res.ok || !res.body) {
    throw new ApiError(res.status, "Chat stream request failed");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let sources: ResearchSourceItem[] = [];

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() ?? "";
    for (const chunk of chunks) {
      if (!chunk.startsWith("data: ")) continue;
      const payload = JSON.parse(chunk.slice(6));
      if (payload.error) throw new Error(payload.error);
      if (payload.thinking) onThinking(payload.thinking);
      if (payload.content) onContent(payload.content);
      if (payload.done) sources = payload.sources ?? [];
    }
  }

  return { sources };
}

/** Consumes the SSE stream from POST /verdicts/{ticker}/stream: bull/bear phase text as each
 * completes, then the final structured verdict. */
export async function streamVerdictGeneration(
  ticker: string,
  onPhase: (phase: "bull" | "bear", text: string) => void
): Promise<VerdictItem> {
  const res = await fetch(`${API_URL}/verdicts/${ticker}/stream`, { method: "POST" });
  if (!res.ok || !res.body) {
    throw new ApiError(res.status, "Verdict stream request failed");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let verdict: VerdictItem | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() ?? "";
    for (const chunk of chunks) {
      if (!chunk.startsWith("data: ")) continue;
      const payload = JSON.parse(chunk.slice(6));
      if (payload.error) throw new Error(payload.error);
      if (payload.phase === "bull" || payload.phase === "bear") onPhase(payload.phase, payload.text);
      if (payload.phase === "judge") verdict = payload.verdict;
    }
  }

  if (!verdict) throw new Error("Verdict stream ended without a result");
  return verdict;
}

/** Consumes the SSE stream from POST /assistant/chat/stream: thinking/content deltas, then done. */
export async function streamAssistantChat(
  message: string,
  onThinking: (delta: string) => void,
  onContent: (delta: string) => void
): Promise<void> {
  const res = await fetch(`${API_URL}/assistant/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  if (!res.ok || !res.body) {
    throw new ApiError(res.status, "Assistant stream request failed");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() ?? "";
    for (const chunk of chunks) {
      if (!chunk.startsWith("data: ")) continue;
      const payload = JSON.parse(chunk.slice(6));
      if (payload.error) throw new Error(payload.error);
      if (payload.thinking) onThinking(payload.thinking);
      if (payload.content) onContent(payload.content);
    }
  }
}

export const api = {
  searchTickers: (q: string, limit = 8) =>
    apiFetch<TickerSearchResult[]>(`/stock/search?q=${encodeURIComponent(q)}&limit=${limit}`),
  getQuote: (ticker: string) => apiFetch<Quote>(`/stock/${ticker}/quote`),
  getHistory: (ticker: string, range: PriceRange) =>
    apiFetch<HistoryResponse>(`/stock/${ticker}/history?range=${range}`),
  getWatchlist: () => apiFetch<WatchlistItem[]>("/watchlist"),
  addToWatchlist: (ticker: string) => apiFetch<WatchlistItem>(`/watchlist/${ticker}`, { method: "POST" }),
  removeFromWatchlist: (ticker: string) => apiFetch<void>(`/watchlist/${ticker}`, { method: "DELETE" }),
  getFundamentals: (ticker: string) => apiFetch<FundamentalsSummary>(`/stock/${ticker}/fundamentals`),
  getFundamentalsHistory: (ticker: string) =>
    apiFetch<FundamentalsQuarter[]>(`/stock/${ticker}/fundamentals/history`),
  getFilings: (ticker: string) => apiFetch<FilingItem[]>(`/stock/${ticker}/filings`),
  getInstitutions: () => apiFetch<InstitutionSummary[]>("/whales/institutions"),
  getInstitutionsOverview: () => apiFetch<InstitutionOverview[]>("/whales/overview"),
  searchInstitutions: (name: string) =>
    apiFetch<InstitutionSummary[]>(`/whales/search-institutions?name=${encodeURIComponent(name)}`),
  addInstitution: (name: string, cik: string) =>
    apiFetch<InstitutionSummary>("/whales/institutions", { method: "POST", body: JSON.stringify({ name, cik }) }),
  getWhaleActivity: () => apiFetch<ActivityItem[]>("/whales/activity"),
  getInstitutionHoldings: (institution: string) =>
    apiFetch<PortfolioPosition[]>(`/whales/${encodeURIComponent(institution)}/holdings`),
  getTickerHolders: (ticker: string) => apiFetch<TickerHolder[]>(`/whales/${ticker}`),
  getHypotheses: () => apiFetch<HypothesisItem[]>("/hypotheses"),
  getDomainBuySignals: (days = 180, minWeight = 1) =>
    apiFetch<DomainGroup[]>(`/signals/domains?days=${days}&min_weight=${minWeight}`),
  getRecentSignals: (limit = 50, offset = 0, days: number | null = 90, source?: SignalItem["source"]) =>
    apiFetch<SignalPage>(
      `/signals/recent?limit=${limit}&offset=${offset}&days=${days ?? 0}${source ? `&source=${source}` : ""}`
    ),
  getSignalsForTicker: (
    ticker: string,
    limit = 50,
    offset = 0,
    days: number | null = 90,
    source?: SignalItem["source"]
  ) =>
    apiFetch<SignalPage>(
      `/signals/ticker/${ticker}?limit=${limit}&offset=${offset}&days=${days ?? 0}${source ? `&source=${source}` : ""}`
    ),
  getCandidates: () => apiFetch<CandidateItem[]>("/research/candidates"),
  triggerResearch: (subjectType: "ticker" | "theme", subject: string, query?: string) =>
    apiFetch<ResearchReportDetail>("/research", {
      method: "POST",
      body: JSON.stringify({ subject_type: subjectType, subject, query }),
    }),
  getReport: (reportId: string) => apiFetch<ResearchReportDetail>(`/research/${reportId}`),
  getResearchHistory: (subjectType: "ticker" | "theme", subject: string) =>
    apiFetch<ResearchReportSummary[]>(
      `/research/history?subject_type=${subjectType}&subject=${encodeURIComponent(subject)}`
    ),
  getTickerResearch: (ticker: string) => apiFetch<ResearchReportSummary[]>(`/stock/${ticker}/research`),
  getRecentResearch: (limit = 20) => apiFetch<ResearchReportSummary[]>(`/research/recent?limit=${limit}`),
  getVerdict: (ticker: string) => apiFetch<VerdictItem | null>(`/verdicts/${ticker}`),
  getAssistantThread: () => apiFetch<ChatMessageItem[]>("/assistant/chat"),
  resetAssistantThread: () => apiFetch<void>("/assistant/chat", { method: "DELETE" }),
  getChatThread: (ticker: string) => apiFetch<ChatThreadResponse>(`/research/chat/${ticker}`),
  resetChatThread: (ticker: string) => apiFetch<void>(`/research/chat/${ticker}`, { method: "DELETE" }),
  getAlertRules: () => apiFetch<AlertRuleResponse[]>("/alerts/rules"),
  createAlertRule: (rule: {
    rule_type: AlertRuleType;
    ticker?: string;
    subject?: string;
    condition?: "gt" | "lt";
    threshold?: number;
  }) => apiFetch<AlertRuleResponse>("/alerts/rules", { method: "POST", body: JSON.stringify(rule) }),
  deleteAlertRule: (ruleId: string) => apiFetch<void>(`/alerts/rules/${ruleId}`, { method: "DELETE" }),
  getAlertLog: () => apiFetch<AlertLogItem[]>("/alerts/log"),
  getVapidPublicKey: () => apiFetch<{ public_key: string }>("/push/vapid-public-key"),
  subscribePush: (subscription: PushSubscriptionJSON) =>
    apiFetch<{ status: string }>("/push/subscribe", { method: "POST", body: JSON.stringify(subscription) }),
  unsubscribePush: (endpoint: string) =>
    apiFetch<void>("/push/unsubscribe", { method: "POST", body: JSON.stringify({ endpoint }) }),
};
