"""Fetch market data from yfinance and condense via LLM."""
from datetime import datetime

import yfinance as yf

from llm_client import LLMClient

# Major US indices + some popular tickers (customize as desired)
DEFAULT_TICKERS = ["^GSPC", "^IXIC", "^DJI", "GLD", "^VIX"]

TICKER_NAMES = {
    "^GSPC": "S&P 500",
    "^IXIC": "Nasdaq Composite",
    "^DJI": "Dow Jones",
    "GLD": "Gold ETF",
    "^VIX": "VIX (Volatility)",
}


def fetch_market_data(tickers: list[str] | None = None) -> str:
    """Fetch latest market prices for tickers and return formatted data string."""
    if tickers is None:
        tickers = DEFAULT_TICKERS

    lines = []
    for ticker in tickers:
        try:
            data = yf.Ticker(ticker)
            hist = data.history(period="1d")
            if not hist.empty:
                price = hist["Close"].iloc[-1]
                name = TICKER_NAMES.get(ticker, ticker)
                lines.append(f"{name}: ${price:.2f}")
        except Exception:
            pass

    return "\n".join(lines) if lines else ""


def condense_market(market_data: str, llm: LLMClient | None = None,
                    target_seconds: int = 12) -> str:
    """Turn market data into a short radio-style market wrap."""
    if not market_data:
        return ""

    llm = llm or LLMClient()
    word_budget = int(target_seconds * 2.3)
    prompt = (
        f"You are an upbeat financial news anchor on a radio station. "
        f"Using ONLY the market data below, write a single spoken market wrap "
        f"of about {word_budget} words. Keep it light and accessible — not "
        f"technical. Mention which way the indices are moving and pick one "
        f"interesting detail. Sound positive and confident. "
        f"No stage directions, no quotation marks.\n\n"
        f"MARKET DATA:\n{market_data}"
    )
    max_tokens = max(80, int(word_budget * 2.2))
    return llm.generate(prompt, max_tokens=max_tokens).strip().strip('"')


if __name__ == "__main__":
    data = fetch_market_data()
    print("Market data:")
    print(data)
    print()
    wrap = condense_market(data, target_seconds=12)
    print(f"Market wrap ({len(wrap.split())} words):")
    print(wrap)
