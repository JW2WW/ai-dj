"""Tests for RSS feed source mapping."""
from news_fetcher import DEFAULT_FEEDS, feeds_from_sources


def test_feeds_from_sources_none_uses_default():
    assert feeds_from_sources(None) == DEFAULT_FEEDS


def test_feeds_from_sources_maps_known_names():
    feeds = feeds_from_sources(["CNN", "BBC"])
    assert "CNN" in feeds
    assert "BBC" in feeds
    assert len(feeds) == 2


def test_feeds_from_sources_ignores_unknown():
    feeds = feeds_from_sources(["Not A Real Feed", "NPR"])
    assert feeds == {"NPR": DEFAULT_FEEDS["NPR"]}


def test_feeds_from_sources_empty_list_falls_back():
    assert feeds_from_sources([]) == DEFAULT_FEEDS
