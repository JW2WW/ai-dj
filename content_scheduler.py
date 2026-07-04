"""Schedule news/market content to be injected into playback on a cadence."""
import threading
from queue import Queue

from apscheduler.schedulers.background import BackgroundScheduler

from news_fetcher import fetch_headlines, condense_news
from market_fetcher import fetch_market_data, condense_market


class ContentScheduler:
    """Runs scheduled jobs (news, market) in the background and queues them
    for injection into the main playback loop via a thread-safe Queue."""

    def __init__(self, news_interval_minutes: int | None = 30,
                 market_time: str | None = "16:00",
                 news_target_seconds: int = 15,
                 market_target_seconds: int = 12,
                 news_feeds: dict | None = None):
        self.scheduler = BackgroundScheduler(daemon=True)
        self.pending = Queue()  # thread-safe queue of (content_type, text) tuples
        self.news_target_seconds = news_target_seconds
        self.market_target_seconds = market_target_seconds
        self.news_feeds = news_feeds  # None -> fetcher's DEFAULT_FEEDS

        # Schedule news to fetch every N minutes (if enabled)
        if news_interval_minutes:
            self.scheduler.add_job(
                self._fetch_and_queue_news,
                "interval",
                minutes=news_interval_minutes,
                id="news_job",
            )

        # Schedule market wrap at a specific time (once per day, if enabled)
        if market_time:
            self.scheduler.add_job(
                self._fetch_and_queue_market,
                "cron",
                hour=market_time.split(":")[0],
                minute=market_time.split(":")[1],
                id="market_job",
            )

    def _fetch_and_queue_news(self) -> None:
        try:
            headlines = fetch_headlines(num_headlines=5, feeds=self.news_feeds)
            if headlines:
                summary = condense_news(headlines, target_seconds=self.news_target_seconds)
                if summary:
                    self.pending.put(("news", summary))
        except Exception:
            pass

    def fetch_news_now(self) -> None:
        """Force an immediate news fetch and queue (used for 'after every song')."""
        self._fetch_and_queue_news()

    def _fetch_and_queue_market(self) -> None:
        try:
            data = fetch_market_data()
            if data:
                wrap = condense_market(data, target_seconds=self.market_target_seconds)
                if wrap:
                    self.pending.put(("market", wrap))
        except Exception:
            pass

    def start(self) -> None:
        """Start the background scheduler."""
        if not self.scheduler.running:
            self.scheduler.start()

    def stop(self) -> None:
        """Stop the background scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=True)

    def has_pending(self) -> bool:
        """Check if there's queued content ready to play."""
        return not self.pending.empty()

    def get_pending(self) -> tuple[str, str] | None:
        """Get the next pending content (content_type, text), or None."""
        try:
            return self.pending.get_nowait()
        except:
            return None
