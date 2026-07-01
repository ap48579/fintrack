# Stock Research Platform

**MVP Specification & Build Plan**

- **Prepared for:** Akhilesh
- **Date:** June 2026
- **Scope:** Web application — delayed real-time prices, SEC fundamentals, institutional ("blue whale") holdings, news/social sentiment & theme research
- **Budget target:** $0/month MVP, all data sources free-tier

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [Pillar 1 — Price & Trends](#3-pillar-1--price--trends)
4. [Pillar 2 — SEC Fundamentals](#4-pillar-2--sec-fundamentals)
5. [Pillar 3 — Blue Whale Holdings](#5-pillar-3--blue-whale-holdings)
6. [Pillar 4 — Research (Sentiment & Themes, On-Demand)](#6-pillar-4--research-sentiment--themes-on-demand)
7. [Cross-Cutting — Alert Engine](#7-cross-cutting--alert-engine)
8. [Data Model (Core Tables)](#8-data-model-core-tables)
9. [Cost Summary — $0/month MVP Target](#9-cost-summary--0month-mvp-target)
10. [Build Order](#10-build-order)
11. [Explicitly Out of Scope for v1](#11-explicitly-out-of-scope-for-v1)

---

## 1. Overview

This is the build spec for a stock research web application with four core feature pillars, built entirely on free-tier data sources for the MVP. The app is web-first (not native mobile), built as a Progressive Web App so it can still deliver installable home-screen access and push notifications on phones without app store overhead.

### 1.1 The four pillars

| Pillar | What it shows | Primary data source |
|---|---|---|
| Price & trends | 15-min delayed quotes, charts, technical trend indicators | Yahoo Finance / Alpha Vantage (free tier) |
| SEC fundamentals | Revenue, debt, profit, margins, ratios, filing history | SEC EDGAR (free, official) |
| Blue whale holdings | Institutional 13F positions, quarter-over-quarter changes | SEC EDGAR 13F filings (free, official) |
| Sentiment & themes | On-demand deep research on a ticker or theme, plus a lightweight daily "worth a look" candidate flag | GDELT + Reddit API (free) + SEC EDGAR + web search, synthesized by an LLM research agent |

### 1.2 Design principle for v1

All four pillars are built in parallel rather than sequentially, per your preference. To keep this manageable, each pillar is intentionally scoped to its simplest useful version first — a "thin slice" across all four rather than full depth on one. Depth gets added in v2 once the thin slices are working end-to-end.

## 2. Architecture

### 2.1 System diagram (textual)

- Data Sources (EDGAR, Yahoo/Alpha Vantage, GDELT, Reddit) →
- Ingestion Layer (scheduled Python jobs, Celery + Redis) →
- Processing (fundamentals parsing, 13F diffing, lightweight spike detection for candidate flagging) →
- PostgreSQL (structured data) →
- FastAPI (REST API) →
- Next.js frontend (PWA) → Web Push notifications

**On-demand path:** Research trigger (ticker or theme) → Agentic LLM research loop (news/Reddit/EDGAR/web search + reasoning) → Persisted research report → PostgreSQL → FastAPI → Frontend

### 2.2 Stack summary

| Layer | Choice | Why |
|---|---|---|
| Frontend | Next.js (React) + PWA plugin | Installable, push-capable, no app store |
| Backend API | FastAPI (Python) | Fast to build, strong data/ML ecosystem |
| Database | PostgreSQL (Supabase or Neon) | Free tier, relational fits filings/holdings data well |
| Background jobs | Celery + Redis (Upstash) | Scheduled scraping, alert evaluation |
| Auth | Clerk or Supabase Auth | Free up to 10k users, fast integration |
| Push notifications | Web Push API (VAPID) | Free, browser-native standard |
| Research agent | LLM with tool-calling (e.g. Claude with web/news search) | Powers on-demand deep research; replaces self-hosted NLP pipeline, usage-based cost only |
| Hosting (frontend) | Vercel | Free tier sufficient for MVP traffic |
| Hosting (backend) | Render or Railway | Free tier; ~$10-20/mo once always-on needed |

## 3. Pillar 1 — Price & Trends

### 3.1 Data source

- **Primary:** Yahoo Finance (via `yfinance` Python library) — free, 15-min delayed, no key required
- **Backup/structured:** Alpha Vantage free tier — 25 requests/day, use for data Yahoo lacks
- **Note:** true real-time data requires paid licensing — explicitly out of scope, delayed data is the industry standard for retail tools

### 3.2 MVP features

1. Ticker search and lookup
2. Current price (15-min delayed) + daily change %
3. Price chart: 1D / 1W / 1M / 1Y / 5Y views
4. Basic trend indicators: 50-day & 200-day moving averages, volume
5. Watchlist (add/remove tickers, persisted per user)

### 3.3 Data refresh cadence

Poll prices every 15 minutes during market hours (9:30am–4pm ET) via scheduled Celery task. Store as time-series rows in Postgres (or TimescaleDB extension if available on chosen host) for charting.

### 3.4 API endpoints

| Endpoint | Returns |
|---|---|
| `GET /stock/{ticker}/quote` | Current price, change %, volume, last updated timestamp |
| `GET /stock/{ticker}/history?range=1M` | OHLCV time series for charting |
| `GET /watchlist` | User's saved tickers with live quotes |
| `POST /watchlist/{ticker}` | Add ticker to watchlist |

## 4. Pillar 2 — SEC Fundamentals

### 4.1 Data source

- SEC EDGAR — fully free, official, no API key, rate-limited to ~10 req/sec (more than sufficient)
- Use EDGAR's XBRL "company facts" API for structured financial data (avoids manual filing parsing for MVP)

### 4.2 MVP features

1. Company financial summary: revenue, net income, total debt, total assets (latest + historical quarters)
2. Derived ratios: debt-to-equity, revenue growth % (YoY/QoQ), net margin
3. Filing history list with links to original 10-K/10-Q on EDGAR
4. Simple trend charts for revenue/profit/debt over last 8 quarters

### 4.3 Data refresh cadence

Fundamentals change quarterly (per filing), not daily. Run a daily check job per tracked ticker against EDGAR's submissions feed; only re-parse when a new filing is detected. This keeps load minimal.

### 4.4 API endpoints

| Endpoint | Returns |
|---|---|
| `GET /stock/{ticker}/fundamentals` | Latest revenue, debt, profit, margins, ratios |
| `GET /stock/{ticker}/fundamentals/history` | Last 8 quarters, for trend charts |
| `GET /stock/{ticker}/filings` | List of recent 10-K/10-Q with EDGAR links |

## 5. Pillar 3 — Blue Whale Holdings

### 5.1 Data source

- SEC EDGAR Form 13F filings — free, official, quarterly institutional holdings disclosure
- **Important caveat to surface in the UI:** 13F data has up to a 45-day filing lag — never present it as real-time

### 5.2 MVP features

1. Curated tracked-institution list to start (e.g. Berkshire Hathaway, Bridgewater, Renaissance Technologies — expandable later)
2. Per-ticker view: which tracked institutions hold it, position size
3. Quarter-over-quarter diff: new positions opened, positions exited, size increased/decreased
4. "Whale activity" feed: chronological list of recent notable moves across tracked institutions

### 5.3 Data refresh cadence

13F filings are quarterly (filed within 45 days of quarter end). Run a scheduled check weekly against EDGAR's full-text search for new 13F filings from tracked institutions; parse and diff against the prior quarter on detection.

### 5.4 API endpoints

| Endpoint | Returns |
|---|---|
| `GET /whales/{ticker}` | Tracked institutions holding this ticker + position sizes |
| `GET /whales/{institution}/holdings` | Full current portfolio for one tracked institution |
| `GET /whales/activity` | Recent feed of position changes across all tracked institutions |

## 6. Pillar 4 — Research (Sentiment & Themes, On-Demand)

### 6.1 Data sources

- **GDELT DOC 2.0 API** — free, global news with pre-tagged themes and tone scores; used for both the passive candidate scan and as a search source during deep research
- **Reddit API** — free, rate-limited; pulled on-demand during deep research, and aggregated lightly for the passive scan
- **SEC EDGAR** — reuses Pillar 2/3 ingestion; the research agent can pull filings directly when researching a company
- **General web search** (via the LLM agent's search tool) — fills in context GDELT/Reddit don't cover
- **X/FinTwit** — explicitly out of scope for MVP (official API has no free tier as of 2026; revisit as a paid v2 add-on, ~$49/mo via a flat-rate third-party provider)

### 6.2 Two research modes

*(per your direction — manual trigger over continuous pipeline)*

**A. Passive candidate scan** (cheap, automatic, daily)

- A lightweight daily job checks GDELT tone/volume for unusual spikes on watchlisted tickers and broad financial news — no clustering, no LLM calls, just a heuristic "this moved more than usual today" flag
- Surfaced as a simple candidate list: ticker or rough topic + why it was flagged — a prompt to go research it, not a finished answer

**B. On-demand deep research** (user-triggered, agentic)

- User points the agent at a ticker or a free-text theme (typed query, or one click from the candidate list / a watchlisted ticker)
- The agent runs a multi-step research loop: search news + Reddit + EDGAR filings + general web → read/reason over results → synthesize
- Output: a structured report — summary, sentiment direction, cited sources, and (for a theme) which tickers are exposed and how, or (for a company) which themes are affecting it
- Each report is persisted so it can be revisited later and compared against future research on the same subject

### 6.3 MVP features

1. Daily passive candidate list — tickers/topics flagged for unusual news/sentiment activity, no LLM cost
2. "Research" action — trigger a deep-research run on any ticker or theme, from a typed query, the candidate list, or a watchlisted ticker
3. Research report view — persisted report: synthesis, sentiment direction, cited sources, related tickers/themes, timestamp
4. Research history — past reports per ticker/theme, so you can see how the picture changed over time
5. Watchlist integration — "Research" button available directly from any watchlisted ticker's page

### 6.4 Data refresh cadence

- **Passive candidate scan:** daily batch job, GDELT polling only — no LLM cost
- **Deep research:** fully on-demand, no schedule — runs only when triggered, taking the place of the previous always-on FinBERT + BERTopic + daily LLM-labeling pipeline

### 6.5 API endpoints

| Endpoint | Returns |
|---|---|
| `GET /research/candidates` | Today's passive-scan candidates (ticker/theme + reason flagged) |
| `POST /research` | Trigger a new deep-research run (body: ticker or free-text theme query) |
| `GET /research/{report_id}` | A persisted research report |
| `GET /research/history?subject={ticker_or_query}` | Past reports for a given ticker or theme |
| `GET /stock/{ticker}/research` | Most recent report(s) for a ticker, shown on the stock detail page |

## 7. Cross-Cutting — Alert Engine

Alerts are what turn raw data into a reason to open the app. The rule engine runs after each data refresh and evaluates user-defined conditions across all four pillars.

### 7.1 MVP alert types

| Alert type | Example trigger | Pillar |
|---|---|---|
| Fundamental threshold | Debt-to-equity crosses a set value | Fundamentals |
| Whale movement | Tracked institution opens/exits a position | Blue whale |
| Price move | Ticker moves more than X% in a day | Price |
| Candidate flagged | Passive scan flags unusual news/sentiment activity on a tracked ticker | Research |
| Watchlist candidate match | A flagged candidate touches a watchlisted ticker — prompts you to trigger research | Cross-pillar |

### 7.2 Delivery

- Web Push notification (works on Android/desktop natively; iOS Safari supports web push when the PWA is added to home screen)
- In-app alert feed as a fallback/history view regardless of push support

## 8. Data Model (Core Tables)

### 8.1 Reference & price data

- `tickers` — id, symbol, name, sector, exchange
- `price_history` — ticker_id, timestamp, open, high, low, close, volume

### 8.2 Fundamentals

- `fundamentals_quarterly` — ticker_id, period, revenue, net_income, total_debt, total_assets
- `filings` — ticker_id, filing_type, filed_date, edgar_url

### 8.3 Whale holdings

- `institutions` — id, name, cik
- `holdings_quarterly` — institution_id, ticker_id, period, shares, market_value
- `holdings_changes` — institution_id, ticker_id, period, change_type (new/exit/increase/decrease), magnitude

### 8.4 Research

- `research_candidates` — id, subject_type (ticker/theme), subject, date, reason, score
- `research_reports` — id, subject_type, subject, query, created_at, summary, sentiment_direction, full_report
- `research_sources` — report_id, source_type (news/reddit/edgar/web), url, title, published_at, excerpt
- `research_ticker_links` — report_id, ticker_id, exposure_type (positive/negative/neutral), confidence

### 8.5 User data

- `users` — id, email, created_at
- `watchlists` — user_id, ticker_id
- `alert_rules` — user_id, rule_type, ticker_id (nullable), theme_id (nullable), condition, threshold
- `alert_log` — alert_rule_id, triggered_at, message, delivered

## 9. Cost Summary — $0/month MVP Target

| Component | Service | Cost at MVP scale |
|---|---|---|
| Price data | Yahoo Finance / Alpha Vantage | Free |
| Fundamentals + 13F | SEC EDGAR | Free |
| News + candidate scan | GDELT | Free |
| Social sentiment (research) | Reddit API | Free (rate-limited) |
| Agentic deep research | LLM API w/ tool-calling (news/Reddit/EDGAR/web search) | Usage-based — cents per research run; near-$0 at personal-use volume, scales with how often you trigger it |
| Database | Supabase / Neon free tier | Free |
| Frontend hosting | Vercel | Free |
| Backend hosting | Render / Railway free tier | Free → ~$10-20/mo once always-on needed |
| Auth | Clerk / Supabase Auth | Free up to 10k users |
| Push notifications | Web Push API (VAPID) | Free |

**Realistic floor** once the app needs to run reliably (alerts checked on schedule, not sleeping): roughly $10–20/month for an always-on backend worker. Everything else stays free at MVP scale.

## 10. Build Order

All four pillars in parallel per your direction. Suggested internal sequencing within that parallel build:

1. **Project scaffold** — Next.js frontend + FastAPI backend + Postgres schema + auth wired up
2. **Pillar 1 (Price)** — fastest to a visible result, validates the data pipeline pattern end-to-end
3. **Pillar 2 (Fundamentals)** — EDGAR integration, reuses ingestion pattern from Pillar 1
4. **Pillar 3 (Whales)** — EDGAR 13F parsing, the most fiddly parsing logic, budget extra time here
5. **Pillar 4 (Research)** — passive candidate scan (GDELT spike detection) first, reuses Pillar 1's ingestion pattern; agentic deep-research loop (tool-calling LLM agent across news/Reddit/EDGAR/web) second — the most novel and highest-effort piece of the build
6. **Alert engine** — once at least 2 pillars have live data to evaluate rules against
7. **PWA setup + Web Push** — wraps the finished app for installability and notifications

## 11. Explicitly Out of Scope for v1

- True real-time pricing (licensing cost — 15-min delay is the v1 standard)
- X/Twitter sentiment (no free API tier in 2026 — paid v2 add-on)
- Continuous/automatic theme detection across all tickers (v1 only researches what you explicitly point it at, plus a lightweight daily candidate flag — full passive theme discovery is a v2 upgrade)
- Self-hosted NLP models (FinBERT, BERTopic) — superseded by the LLM research agent, no longer needed
- Buy/sell signals or personalized investment advice (regulatory gray zone — add disclaimers throughout instead, mirroring how Seeking Alpha frames its AI-generated content as informational, not advice)
- Native mobile app (PWA covers installability and push without app store overhead)
- Broad institution coverage for whale tracking (start with a small curated list, expand later)
