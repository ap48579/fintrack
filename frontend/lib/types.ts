export interface Quote {
  symbol: string;
  price: number;
  change_percent: number;
  volume: number;
  last_updated: string;
}

export interface CandlePoint {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface LinePoint {
  time: number;
  value: number;
}

export type PriceRange = "1D" | "1W" | "1M" | "1Y" | "5Y";

export interface HistoryResponse {
  symbol: string;
  range: PriceRange;
  candles: CandlePoint[];
  ma50: LinePoint[];
  ma200: LinePoint[];
}

export interface WatchlistItem {
  ticker_id: string;
  symbol: string;
  name: string;
  sector: string | null;
  quote: Quote | null;
}

export interface FundamentalsSummary {
  period: string | null;
  revenue: number | null;
  net_income: number | null;
  total_debt: number | null;
  total_assets: number | null;
  debt_to_equity: number | null;
  net_margin: number | null;
  revenue_growth_qoq: number | null;
  revenue_growth_yoy: number | null;
}

export interface FundamentalsQuarter {
  period: string;
  revenue: number | null;
  net_income: number | null;
  total_debt: number | null;
  total_assets: number | null;
}

export interface FilingItem {
  filing_type: string;
  filed_date: string;
  edgar_url: string;
}

export interface InstitutionSummary {
  cik: string;
  name: string;
}

export interface InstitutionOverview {
  cik: string;
  name: string;
  period: string | null;
  total_market_value: number | null;
  position_count: number;
  value_change_pct: number | null;
  new_positions: number;
  exited_positions: number;
}

export interface TickerHolder {
  institution: string;
  period: string;
  shares: number;
  market_value: number;
}

export interface PortfolioPosition {
  symbol: string;
  name: string;
  period: string;
  shares: number;
  market_value: number;
}

export interface ActivityItem {
  institution: string;
  symbol: string;
  name: string;
  period: string;
  change_type: "new" | "exit" | "increase" | "decrease";
  magnitude: number;
}

export interface CandidateItem {
  subject_type: "ticker" | "theme";
  subject: string;
  date: string;
  reason: string;
  score: number;
}

export interface ResearchSourceItem {
  source_type: "news" | "reddit" | "edgar" | "web";
  url: string;
  title: string;
  published_at: string | null;
  excerpt: string;
}

export interface ResearchTickerLinkItem {
  exposure_type: "positive" | "negative" | "neutral";
  confidence: number;
  ticker: string;
}

export interface ResearchReportDetail {
  id: string;
  subject_type: "ticker" | "theme";
  subject: string;
  query: string;
  created_at: string;
  summary: string;
  sentiment_direction: "bullish" | "bearish" | "neutral" | "mixed";
  full_report: string;
  sources: ResearchSourceItem[];
  ticker_links: ResearchTickerLinkItem[];
}

export interface ResearchReportSummary {
  id: string;
  subject_type: "ticker" | "theme";
  subject: string;
  created_at: string;
  summary: string;
  sentiment_direction: "bullish" | "bearish" | "neutral" | "mixed";
}

export type AlertRuleType =
  | "fundamental_threshold"
  | "whale_movement"
  | "price_move"
  | "candidate_flagged"
  | "watchlist_candidate_match";

export interface AlertRuleResponse {
  id: string;
  rule_type: AlertRuleType;
  ticker: string | null;
  subject: string | null;
  condition: "gt" | "lt" | null;
  threshold: number | null;
  active: boolean;
  created_at: string;
}

export interface AlertLogItem {
  id: string;
  rule_type: AlertRuleType;
  ticker: string | null;
  subject: string | null;
  triggered_at: string;
  message: string;
  delivered: boolean;
}
