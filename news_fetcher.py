"""Fetch news headlines from RSS feeds and condense via LLM."""
import feedparser

from llm_client import get_llm_client

# Free, no-auth RSS feeds. These change occasionally as sites update feeds.
# Feeds update multiple times per day. Keys are the user-facing source names.
# Sourced from Feedspot's major US/world news outlet listings and verified to
# return headlines.
NEWS_FEEDS = {
    "NPR": "https://feeds.npr.org/1001/rss.xml",
    "NPR World": "https://feeds.npr.org/1004/rss.xml",
    "BBC": "https://feeds.bbc.co.uk/news/rss.xml",
    "CNN": "http://rss.cnn.com/rss/cnn_topstories.rss",
    "Fox News": "https://moxie.foxnews.com/google-publisher/latest.xml",
    "ABC News": "https://abcnews.go.com/abcnews/topstories",
    "NBC News": "https://feeds.nbcnews.com/nbcnews/public/news",
    "New York Times": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    "LA Times": "https://www.latimes.com/world-nation/rss2.0.xml",
    "CNBC": "https://www.cnbc.com/id/100727362/device/rss/rss.html",
    "Washington Times": "https://www.washingtontimes.com/rss/headlines/news/world/",
    "The Guardian": "https://www.theguardian.com/world/rss",
    "Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    "Hacker News": "https://news.ycombinator.com/rss",
}

# List of source names for UI dropdowns.
AVAILABLE_SOURCES = list(NEWS_FEEDS.keys())

# Default: NPR + Hacker News (reliably structured RSS)
DEFAULT_FEEDS = {
    "NPR": NEWS_FEEDS["NPR"],
    "Hacker News": NEWS_FEEDS["Hacker News"],
}


def feeds_from_sources(sources: list[str] | None) -> dict:
    """Map a list of source names (e.g. ['CNN', 'BBC']) to a feeds dict.

    Unknown names are ignored. Falls back to DEFAULT_FEEDS if nothing valid.
    """
    if not sources:
        return DEFAULT_FEEDS
    feeds = {name: NEWS_FEEDS[name] for name in sources if name in NEWS_FEEDS}
    return feeds or DEFAULT_FEEDS


def fetch_headlines(num_headlines: int = 5, feeds: dict | None = None) -> list[dict]:
    """Fetch top N headlines from multiple RSS feeds.

    Returns a list of dicts: {"title": ..., "url": ..., "source": ...}
    """
    if feeds is None:
        feeds = DEFAULT_FEEDS

    headlines = []
    # Some outlets (e.g. BBC) reject the default feedparser user-agent.
    agent = "AI-DJ/1.0 (+https://github.com/JW2WW/Radio-DJ-for-MP3s)"
    for source_name, feed_url in feeds.items():
        try:
            feed = feedparser.parse(feed_url, agent=agent)
            for entry in feed.entries[:num_headlines // len(feeds) + 1]:
                headlines.append({
                    "title": entry.get("title", ""),
                    "url": entry.get("link", ""),
                    "source": source_name,
                })
        except Exception:
            pass  # silently skip feed on error

    return headlines[:num_headlines]


def condense_news(headlines: list[dict], llm=None, target_seconds: int = 15) -> str:
    """Turn a list of headlines into a short spoken news summary."""
    if not headlines:
        return ""

    llm = llm or get_llm_client()
    headlines_text = "\n".join(
        f"- {h['title']} (from {h['source']})" for h in headlines
    )
    word_budget = int(target_seconds * 2.3)  # ~2.3 words/sec spoken pace
    prompt = (
        f"You are a radio news anchor. Using ONLY the headlines below, write a "
        f"single spoken news brief of about {word_budget} words. Deliver it as "
        f"if you're reading news on air. Pick the most interesting 2-3 stories, "
        f"paraphrase them naturally, and avoid the word 'according' or 'reports'. "
        f"Sound authoritative but warm. No stage directions, no quotation marks.\n\n"
        f"HEADLINES:\n{headlines_text}"
    )
    max_tokens = max(100, int(word_budget * 2.2))
    return llm.generate(prompt, max_tokens=max_tokens).strip().strip('"')


if __name__ == "__main__":
    headlines = fetch_headlines(num_headlines=5)
    print("Fetched headlines:")
    for h in headlines:
        print(f"  [{h['source']}] {h['title']}")
    print()
    summary = condense_news(headlines, target_seconds=15)
    print(f"News brief ({len(summary.split())} words):")
    print(summary)
