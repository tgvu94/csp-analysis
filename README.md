# csp-analysis

An MCP server that fetches stock data to support weekly cash-secured put (CSP) analysis using the wheel strategy.

> **Disclaimer:** This tool is for informational and educational purposes only. Output is purely technical analysis based on publicly available market data and does not constitute financial advice. Do not make investment decisions based solely on this output. Always do your own research and consult a qualified financial advisor before trading options.

## Tools

| Tool | Description |
|------|-------------|
| `get_iv_data` | IV, HV, IV Percentile, IV Rank (scraped from Barchart) |
| `get_price_and_fundamentals` | Price, 52w high/low, P/E, dividend, earnings date |
| `get_technicals` | 50/200d SMA, RSI, MACD, trend signal |
| `get_options_chain` | Weekly put chain with delta and net% after commission |

Supports US tickers (e.g. `T`, `F`) and Canadian TSX tickers (e.g. `AQN.TO`).

## Setup

```bash
uv pip install -r requirements.txt
```

## Usage

Designed to be used with the `/csp-analysis` Claude Code skill, which runs a full scorecard — IV environment, trend, assignment risk, and strike selection — for any ticker.

## Sample Output

```
=== CSP Analysis: T — 2026-05-19 ===

PREMIUM QUALITY
  IV Percentile: 51%         [✅ > 40%]
  IV Rank: 38.0%             [⚠️  just below 40% threshold]
  IV vs HV: 24.23% vs 26.39% [⚠️  IV < HV — stock moving more than priced]
  Best strike spread ($24.50): $0.08–$0.11 (30% of mid) [❌ > 20%]
  Best strike delta ($24.50): -0.21                      [✅ in range]
  Best strike OI ($24.50): 5,845                         [✅ > 100]

ASSIGNMENT RISK
  Trend: Downtrend                                [❌ below both SMAs]
  Price vs 200d SMA: $24.98 vs $26.10            [❌ below]
  Price vs 50d SMA:  $24.98 vs $26.59            [❌ below]
  RSI (14): 40.7                                 [⚠️  below 45, weak]
  MACD: -0.564 / Signal: -0.518 — Bearish        [❌]
  Next Earnings: 2026-07-22                      [✅ safe, 9+ weeks away]

IF ASSIGNED
  Price vs 52w high: $24.98 vs $29.79 (16.1% below high) [✅ not chasing top]
  P/E: 11.07                                             [✅ well below 30]
  Dividend: $1.11/yr (4.62% yield)                       [✅ solid cushion]

CANDIDATE STRIKES (expiry 2026-05-22)
  ┌─────────────────────────────────────────────────────────────────────┐
  │ $24.50 | Bid $0.08 / Ask $0.11 | Mid $0.10 | Δ -0.21 | OI 5,845  │
  │  Net%: 0.35%  ❌ — delta in range but only 35% of 1% target        │
  ├─────────────────────────────────────────────────────────────────────┤
  │ $25.00 | Bid $0.24 / Ask $0.48 | Mid $0.36 | Δ -0.50 | OI 3,934  │
  │  Net%: 1.40% ✅ — meets 1% but delta too high, spread 67% ❌       │
  └─────────────────────────────────────────────────────────────────────┘
  Target mid needed: $0.26/share | Cash needed: ~$2,498/contract
  ⚠️   No single strike satisfies delta (–0.20 to –0.35) AND 1% net target

VERDICT: ❌ SKIP

Reason: T is in a confirmed downtrend — price sits ~$1.12 below its 200d SMA
and ~$1.61 below its 50d SMA, with bearish MACD and RSI in weak territory (40.7).
The options market can't bridge the gap: the only in-range delta strike ($24.50)
delivers just 0.35% net, and the first strike that clears 1% ($25.00) carries a
–0.50 delta with a 67% bid-ask spread — both disqualifying. The fundamentals (low
P/E, strong dividend) make T acceptable to own long-term, but wait for a technical
recovery above the 200d SMA before selling CSPs.
```
