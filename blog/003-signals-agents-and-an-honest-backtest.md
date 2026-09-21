# Disclosure Signals, a Local AI Agent, and an Honest Backtest

**FinTrack — Article 003 · September 21, 2026**

---

The last article ended with a research agent that could answer *"what's driving sentiment around X"* from pre-fetched context. Since then the project has grown a second, arguably more important leg: a pipeline that ingests every disclosed insider trade, congressional trade, and institutional 13F filing it can get its hands on, and a set of agents built on top of that data to help decide what's actually worth looking at.

This article covers the disclosure pipeline, the local multi-agent layer built on top of it, and — the part I think matters most — the backtest that tells you whether any of it is real.

---

## The Data: Three Disclosure Sources, One Feed

FinTrack now ingests three independent disclosure streams:

- **SEC Form 4** — corporate insider buys and sells, filed within days of the transaction
- **House Clerk PTRs** — congressional trading disclosures, filed within 30–45 days
- **13F-HR** — quarterly institutional holdings, tracked across 12 funds (Berkshire, Bridgewater, Renaissance, Citadel, Point72, Soros, Pershing Square, and others)

Each source has its own shape, its own filing cadence, and its own quirks — PTR PDFs wrap the Asset and Amount columns across lines in a way that breaks naive text extraction, Form 4 filings get attributed to multiple CIKs, 13F CUSIPs need resolving to tickers via OpenFIGI. All three get normalized into one common "signal" shape — source, ticker, direction, actor, amount, disclosure lag — so the frontend renders one feed instead of three.

A full year of backfill across all three sources now sits in the database: roughly 10,000 insider trades, 10,000+ congressional trades, and 4,000+ institutional holdings changes.

### The merge bug worth mentioning

The first version of the combined feed pulled the top N most-recent rows from each source, merged them, and sorted by date. It looked reasonable and was wrong: Form 4 filing volume is so much higher than congressional or 13F volume that a same-size date cut filled entirely with insider rows and never reached a congressional or whale signal at all — even with hundreds of qualifying rows sitting in the database. The fix was a floor-then-fill merge that guarantees each source a fair minimum share of the page before the rest fills in by date, plus real pagination so a specific source's full history is reachable, not just its top slice.

---

## What's Being Bought, By Domain

On top of the raw feed sits a sector-grouped view — insider, congressional, and institutional buys grouped by sector, sized by how many *distinct* buyers hit the same ticker rather than raw event count (so one person filing five small buys doesn't outweigh five different people each buying once). It renders as a word-cloud-style grid: bigger ticker, more independent buyers.

This is explicitly framed as "where disclosed buying is concentrated," not a recommendation — a distinction that turned out to matter a lot once the backtest results came in (more on that below).

---

## A Local Multi-Agent Research Layer

Everything here runs on Ollama, on-device — no API key, no per-call cost, and (deliberately) no live internet access for the model. Three agent surfaces sit on top of the disclosure data:

**Per-ticker research chat.** Ask anything about a specific ticker and get an answer grounded in that ticker's actual disclosed trades, news, and filings — with the model's reasoning trace streamed live and collapsed once the answer starts, the way a hosted reasoning-model chat does it.

**Bull/bear/judge verdicts.** Modeled loosely on the TradingAgents multi-agent pattern: one pass builds the strongest case *for* buying a ticker from the real data, a second pass builds the strongest case *against* using the same data, and a third pass — seeing only the two arguments, not the raw data — weighs them into a verdict with a confidence score. Three sequential passes instead of one, because a single pass tends to just agree with whatever framing it started with. It surfaces on the top three tickers per sector in the domain cloud.

**A global assistant.** A persistent chat panel, available from anywhere in the app, that answers questions using the aggregate picture — domain concentration, hypothesis backtest results, data coverage — rather than one ticker's context.

### Where a 7B model actually breaks

Worth being specific about failure modes rather than glossing over them, because they were instructive:

- Asked "is Bloom Energy good to buy?", the first version of the assistant invented a wrong ticker (BLS instead of BE) and a wrong sector, because the aggregate context simply had no data on that specific company and the model filled the gap from its own pretrained guesses instead of saying so. Fixed by detecting when a question names a specific company and injecting that company's *actual* disclosed data into context — with an explicit instruction that a missing "specific data" section means the tool has nothing, full stop.
- Even with correct, clearly labeled data, the model would sometimes attribute a 13F institution's trade to "congressional activity" while summarizing three adjacent lists — a genuine attention limitation, not a data problem. The fix that actually worked wasn't a stronger prompt (tried that first, didn't help) — it was computing the net buy/sell direction per category in Python and handing the model the already-correct headline, so a mid-summary mix-up could blur supporting detail but couldn't flip the conclusion.

The general lesson: a small local model is good at synthesizing and writing, and not reliably good at multi-list attribution under its own steam. Do the parts that need to be exactly right in code, and let the model do the parts that benefit from language.

---

## The Backtest: Does Any of This Predict Anything?

This is the part I think is more important than any of the UI above it. It's easy to build a tool that tracks insider and congressional trades and implies — through framing, through a polished dashboard — that the tracking itself is valuable. Whether it actually is turned out to be a real, testable, and only partially answered question.

The engine: a parameterized backtest that pulls disclosed buy or sell events, fetches forward price data, and computes excess return against SPY over the same window — logged as a named, reproducible `Hypothesis` with every run's results persisted, specifically so a hypothesis gets re-tested as more data lands instead of trusted from one lucky run.

A few honest results, from a full year of data:

| Hypothesis | 7-day excess | 60-day excess |
|---|---|---|
| 3+ distinct buyers on one ticker | +2.74% mean, 56% win rate | −3.36% mean, 39% win rate |
| Insider officers only (CEO/CFO-level) | +7.89% mean, 67% win rate | −10.38% mean, 38% win rate |
| All sell signals (robustness check) | −0.71% mean | +1.56% mean |

The pattern that jumps out: every short-term positive signal *reverses* by 60 days. That's either a real drift-then-reversion effect, or a methodological artifact — only the older signals in the window have a complete 60-day forward return yet, so the 7-day and 60-day columns aren't quite sampling the same period. I don't know which it is yet, and I'd rather say that plainly than round it off into a clean story.

The sell-signal robustness check is doing real work here too: if sell signals showed the same predictive pattern as buy signals, that would suggest the whole effect is market-regime noise rather than real information content in the disclosures. It doesn't, cleanly, but it's close enough that I'm treating the buy-side result as directional at best.

None of this is dressed up as a trading signal in the product. The domain cloud says "where buying is concentrated." The backtest results say "here's what we actually checked, and here's what came back." Keeping those separated is deliberate.

---

## What's Next

- **Wider historical backfill** — a year gives one market regime; multiple years would let the same hypotheses be tested walk-forward across different conditions instead of one continuous stretch
- **An LLM-as-hypothesis-generator pass** — have the agent read the qualitative context and *propose* new testable hypotheses (a sector-specific pattern, a lag-based filter) rather than asking it to judge them; the backtest engine stays the arbiter of whether a proposal holds up
- **A strategy simulator** on top of the same backtest engine — actual position sizing and entry/exit rules, so multiple strategy variants can be compared on portfolio-level metrics (Sharpe, drawdown) instead of raw per-event excess return

The throughline hasn't changed since article 001: build the thing that's actually useful, and don't let a convincing-looking dashboard substitute for asking whether it's true.
