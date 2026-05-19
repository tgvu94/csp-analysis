import math
import re
from datetime import date, timedelta

import requests
import yfinance as yf
from bs4 import BeautifulSoup
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("csp-data")

# ---------------------------------------------------------------------------
# Data sources
# ---------------------------------------------------------------------------

# Barchart: IV data and fundamentals (scraped via HTTP)
BARCHART_HOST          = "https://www.barchart.com"
BARCHART_OVERVIEW_PATH = "/stocks/quotes/{ticker}/overview"

# Yahoo Finance: technicals and options chain (via yfinance library)
# To swap providers, replace yf.Ticker() calls in get_technicals / get_options_chain
YFINANCE_SOURCE = "Yahoo Finance (yfinance)"

# ---------------------------------------------------------------------------

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

IV_FIELDS = [
    "Implied Volatility",
    "Historical Volatility",
    "IV Percentile",
    "IV Rank",
    "IV High",
    "IV Low",
    "Expected Move (DTE 2)",
]

FUNDAMENTAL_FIELDS = [
    "Price/Earnings ttm",
    "Earnings Per Share ttm",
    "Annual Dividend & Yield (Fwd)",
    "Most Recent Dividend",
    "Most Recent Earnings",
    "Next Earnings Date",
    "60-Month Beta",
    "Market Capitalization, $K",
    "Annual Sales, $",
    "Annual Income, $",
    "Price/Sales",
    "Expected Range",
]


def format_ticker(ticker: str) -> str:
    return ticker.upper()


def _barchart_url(ticker: str, path: str = BARCHART_OVERVIEW_PATH) -> str:
    return f"{BARCHART_HOST}{path.format(ticker=ticker)}"


def _scrape_li_fields(soup: BeautifulSoup, fields: list[str]) -> dict:
    data = {}
    for li in soup.find_all("li"):
        left = li.find("span", class_="left")
        right = li.find("span", class_="right")
        if left and right:
            key = left.get_text(strip=True)
            if key in fields:
                data[key] = right.get_text(strip=True)
    return data


def _next_friday() -> str:
    today = date.today()
    days_ahead = (4 - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")


def _norm_cdf(x: float) -> float:
    return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0


def _put_delta(S: float, K: float, T: float, sigma: float, r: float = 0.045) -> float | None:
    """Black-Scholes put delta. Returns None if inputs are invalid."""
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return None
    try:
        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        return _norm_cdf(d1) - 1.0  # put delta is negative
    except (ValueError, ZeroDivisionError):
        return None


@mcp.tool()
def get_iv_data(ticker: str) -> str:
    """
    Fetch implied volatility data for a stock from Barchart.
    Returns IV, HV, IV Percentile, IV Rank, IV High, IV Low.
    Supports US tickers (F, RIVN) and Canadian TSX tickers (AQN.TO).
    """
    url_ticker = format_ticker(ticker)
    url = _barchart_url(url_ticker)

    resp = requests.get(url, headers=HEADERS, timeout=15)
    if resp.status_code != 200:
        return f"Failed to fetch {ticker}: HTTP {resp.status_code}"

    soup = BeautifulSoup(resp.text, "html.parser")
    data = _scrape_li_fields(soup, IV_FIELDS)

    if not data:
        return (
            f"No IV data found for {ticker}. "
            "Ticker may be wrong or Barchart page structure changed."
        )

    lines = [f"IV Data for {ticker} — {url}"]
    for field in IV_FIELDS:
        if field in data:
            lines.append(f"  {field}: {data[field]}")

    return "\n".join(lines)


@mcp.tool()
def get_price_and_fundamentals(ticker: str) -> str:
    """
    Fetch current price and fundamental data for a stock from Barchart.
    Returns price, 52-week high/low, P/E ratio, dividend yield, next earnings date, sector.
    Supports US tickers (F, RIVN) and Canadian TSX tickers (AQN.TO).
    """
    url_ticker = format_ticker(ticker)
    url = _barchart_url(url_ticker)

    resp = requests.get(url, headers=HEADERS, timeout=15)
    if resp.status_code != 200:
        return f"Failed to fetch {ticker}: HTTP {resp.status_code}"

    soup = BeautifulSoup(resp.text, "html.parser")
    data = _scrape_li_fields(soup, FUNDAMENTAL_FIELDS)

    # Price and 52w high/low from yfinance — Barchart's static HTML doesn't carry the live price
    # (div.price matches the 52w-range widget, not the current quote) and FastInfo.keys() uses
    # camelCase while attribute access uses snake_case, so guard with getattr instead of `in`.
    price = week52_high = week52_low = None
    try:
        fi = yf.Ticker(format_ticker(ticker)).fast_info
        lp = getattr(fi, "last_price", None)
        yh = getattr(fi, "year_high", None)
        yl = getattr(fi, "year_low", None)
        if lp:
            price = f"{lp:.2f}"
        if yh:
            week52_high = f"${yh:.2f}"
        if yl:
            week52_low  = f"${yl:.2f}"
    except Exception:
        pass

    # Human-readable label remapping
    label_map = {
        "Price/Earnings ttm":           "P/E Ratio (TTM)",
        "Earnings Per Share ttm":        "EPS (TTM)",
        "Annual Dividend & Yield (Fwd)": "Dividend & Yield",
        "Most Recent Dividend":          "Last Dividend",
        "Most Recent Earnings":          "Last Earnings",
        "Next Earnings Date":            "Next Earnings",
        "60-Month Beta":                 "Beta (5yr)",
        "Market Capitalization, $K":     "Market Cap ($K)",
        "Annual Sales, $":               "Annual Revenue",
        "Annual Income, $":              "Annual Income",
        "Price/Sales":                   "Price/Sales",
        "Expected Range":                "Expected Range (week)",
    }

    lines = [f"Fundamentals for {ticker} — {url}"]
    if price:
        lines.append(f"  Current Price:   ${price}")
    if week52_high:
        lines.append(f"  52-Week High:    {week52_high}")
    if week52_low:
        lines.append(f"  52-Week Low:     {week52_low}")
    for field in FUNDAMENTAL_FIELDS:
        if field in data:
            lines.append(f"  {label_map.get(field, field)}: {data[field]}")

    if len(lines) == 1:
        return f"No fundamental data found for {ticker}. Barchart page structure may have changed."

    return "\n".join(lines)


def _ema(values: list[float], period: int) -> list[float]:
    k = 2 / (period + 1)
    emas = [values[0]]
    for v in values[1:]:
        emas.append(v * k + emas[-1] * (1 - k))
    return emas


def _calc_rsi(closes: list[float], period: int = 14) -> float:
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, 0) for d in deltas[-period:]]
    losses = [abs(min(d, 0)) for d in deltas[-period:]]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _calc_macd(closes: list[float]) -> tuple[float, float, float]:
    """Returns (macd_line, signal_line, histogram)."""
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    macd_line = [ema12[i] - ema26[i] for i in range(len(closes))]
    signal = _ema(macd_line, 9)
    histogram = macd_line[-1] - signal[-1]
    return macd_line[-1], signal[-1], histogram


@mcp.tool()
def get_technicals(ticker: str) -> str:
    """
    Calculate technical indicators for a stock using price history from Yahoo Finance.
    Returns 50/200-day SMA, RSI(14), MACD, trend signals for CSP evaluation.
    Supports US tickers (F, RIVN) and Canadian TSX tickers (AQN.TO).
    """
    t = yf.Ticker(format_ticker(ticker))

    hist = t.history(period="1y")
    if hist.empty:
        return f"No price history available for {ticker}."

    closes = hist["Close"].tolist()
    price = closes[-1]

    if len(closes) < 26:
        return f"Not enough price history for {ticker} (need at least 26 days)."

    sma50  = sum(closes[-50:])  / min(50,  len(closes))
    sma200 = sum(closes[-200:]) / min(200, len(closes))
    rsi    = _calc_rsi(closes)
    macd_line, signal_line, histogram = _calc_macd(closes)

    above_50  = price > sma50
    above_200 = price > sma200

    # Trend assessment
    if above_200 and above_50:
        trend = "Uptrend ✅ (above both 50d & 200d SMA)"
    elif above_200 and not above_50:
        trend = "Pullback ⚠️ (above 200d but below 50d SMA)"
    elif not above_200 and above_50:
        trend = "Mixed ⚠️ (below 200d but above 50d SMA)"
    else:
        trend = "Downtrend ❌ (below both 50d & 200d SMA)"

    # RSI signal
    if rsi < 30:
        rsi_signal = "Oversold ⚠️ (potential bounce but watch 200d SMA)"
    elif rsi < 45:
        rsi_signal = "Weak ⚠️"
    elif rsi <= 65:
        rsi_signal = "Healthy ✅"
    else:
        rsi_signal = "Overbought ⚠️ (avoid selling puts near top)"

    # MACD signal
    macd_signal = "Bullish ✅" if histogram > 0 else "Bearish ❌"

    lines = [
        f"Technicals for {ticker}  |  Price: ${price:.2f}",
        f"",
        f"  Trend:        {trend}",
        f"  50-Day SMA:   ${sma50:.2f}  ({'above' if above_50 else 'BELOW'} ↑)" ,
        f"  200-Day SMA:  ${sma200:.2f}  ({'above' if above_200 else 'BELOW'} ↑)",
        f"",
        f"  RSI (14):     {rsi:.1f}  — {rsi_signal}",
        f"  MACD:         {macd_line:.3f}  Signal: {signal_line:.3f}  Hist: {histogram:.3f}  — {macd_signal}",
    ]

    return "\n".join(lines)


@mcp.tool()
def get_options_chain(ticker: str, expiry_date: str = "") -> str:
    """
    Fetch the weekly put options chain for a stock via Yahoo Finance.
    Returns strike, bid, ask, mid, delta (calculated), OI, net% after $1 commission.
    expiry_date: YYYY-MM-DD (defaults to next Friday weekly expiry).
    Supports US tickers (F, RIVN) and Canadian TSX tickers (AQN.TO).
    """
    yf_ticker = format_ticker(ticker)

    t = yf.Ticker(yf_ticker)

    available = t.options
    if not available:
        return f"No options data available for {ticker} on Yahoo Finance."

    if not expiry_date:
        target = _next_friday()
        expiry_date = target if target in available else available[0]

    if expiry_date not in available:
        return (
            f"Expiry {expiry_date} not available for {ticker}. "
            f"Available: {', '.join(available[:6])}"
        )

    chain = t.option_chain(expiry_date)
    puts = chain.puts

    if puts.empty:
        return f"No put options found for {ticker} expiring {expiry_date}."

    # Current price for delta calculation and net% display
    price = t.fast_info.get("last_price") or t.fast_info.get("lastPrice") or 0.0

    # Days to expiry → annualised T
    expiry_dt = date.fromisoformat(expiry_date)
    T = max((expiry_dt - date.today()).days, 1) / 365.0

    lines = [
        f"Put Options for {ticker} — Expiry: {expiry_date}  |  Stock: ${price:.2f}",
        f"  {'Strike':>7}  {'Bid':>5}  {'Ask':>5}  {'Mid':>5}  {'Delta':>6}  {'Net%':>5}  {'OI':>6}  {'Vol':>6}",
        "  " + "─" * 60,
    ]

    for _, row in puts.iterrows():
        strike = row["strike"]
        bid    = row["bid"] if not math.isnan(row["bid"]) else 0.0
        ask    = row["ask"] if not math.isnan(row["ask"]) else 0.0
        oi     = int(row["openInterest"]) if not math.isnan(row["openInterest"]) else 0
        vol    = int(row["volume"]) if not math.isnan(row["volume"]) else 0
        iv     = row["impliedVolatility"] if not math.isnan(row["impliedVolatility"]) else 0.0

        mid = (bid + ask) / 2
        delta = _put_delta(price, strike, T, iv)
        delta_str = f"{delta:.2f}" if delta is not None else "  —"

        # Net % after $1 commission on 1 contract (100 shares)
        net_pct = ((mid * 100) - 1.0) / (strike * 100) * 100 if strike > 0 and mid > 0 else 0.0
        net_str = f"{net_pct:.2f}%" if net_pct > 0 else "  —"

        lines.append(
            f"  {strike:>7.2f}  {bid:>5.2f}  {ask:>5.2f}  {mid:>5.2f}  {delta_str:>6}  {net_str:>5}  {oi:>6}  {vol:>6}"
        )

    lines.append("")
    lines.append(f"  Target mid for 1% net/week: ${(price * 0.01) + 0.01:.2f}/share  |  Cash needed per contract: ~${price * 100:,.0f}")
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
