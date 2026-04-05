"""
fetcher.py — Pulls data from three source categories:
  1. Industry news via RSS feeds (SEJ, Search Engine Land, etc.)
  2. Google Trends for tracked keywords
  3. LinkedIn-adjacent content via Google News RSS search
"""

import feedparser
import requests
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# RSS sources
# ---------------------------------------------------------------------------

NEWS_FEEDS = [
    {"name": "Search Engine Journal", "url": "https://www.searchenginejournal.com/feed/"},
    {"name": "Search Engine Land",    "url": "https://searchengineland.com/feed"},
    {"name": "Search Engine Roundtable", "url": "https://www.seroundtable.com/feed"},
    {"name": "Moz Blog",              "url": "https://moz.com/blog/feed"},
    {"name": "The Verge AI",          "url": "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml"},
    {"name": "TechCrunch AI",         "url": "https://techcrunch.com/tag/artificial-intelligence/feed/"},
    {"name": "Marketing Land",        "url": "https://martech.org/feed/"},
    {"name": "Semrush Blog",          "url": "https://www.semrush.com/blog/feed/"},
]

# Google News RSS — searches specifically for LinkedIn posts/articles
LINKEDIN_GOOGLE_NEWS_QUERIES = [
    "SEO AEO AI search site:linkedin.com",
    "answer engine optimization linkedin",
    "GEO generative engine optimization linkedin",
]

LINKEDIN_FEEDS = [
    f"https://news.google.com/rss/search?q={q.replace(' ', '+')}&hl=en-US&gl=US&ceid=US:en"
    for q in LINKEDIN_GOOGLE_NEWS_QUERIES
]

# Keywords that mark an article as relevant
RELEVANCE_KEYWORDS = [
    "seo", "aeo", "geo", "ai search", "generative search", "answer engine",
    "ai overviews", "sge", "search generative experience", "zero-click",
    "chatgpt search", "perplexity", "llm seo", "search engine", "organic search",
    "featured snippet", "knowledge graph", "structured data", "schema markup",
    "voice search", "semantic search", "entity seo", "topical authority",
    "google search", "bing ai", "ai mode", "search ranking",
]


def _is_recent(entry, hours: int = 48) -> bool:
    """Return True if the feed entry was published within the last `hours`."""
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            pub = datetime(*t[:6], tzinfo=timezone.utc)
            return pub >= datetime.now(timezone.utc) - timedelta(hours=hours)
    return True  # no date info → include by default


def _is_relevant(entry) -> bool:
    """Return True if the entry title/summary mentions any tracked keyword."""
    text = " ".join([
        getattr(entry, "title", ""),
        getattr(entry, "summary", ""),
    ]).lower()
    return any(kw in text for kw in RELEVANCE_KEYWORDS)


def _parse_feed(url: str, source_name: str, hours: int = 48) -> list[dict]:
    """Parse a single RSS feed and return a list of article dicts."""
    articles = []
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries:
            if not _is_recent(entry, hours):
                continue
            if not _is_relevant(entry):
                continue
            articles.append({
                "title":     getattr(entry, "title", "Untitled"),
                "url":       getattr(entry, "link", ""),
                "source":    source_name,
                "published": getattr(entry, "published", "Unknown date"),
                "excerpt":   getattr(entry, "summary", "")[:400].strip(),
            })
    except Exception as exc:
        logger.warning("Feed error (%s): %s", source_name, exc)
    return articles


# ---------------------------------------------------------------------------
# Public fetch functions
# ---------------------------------------------------------------------------

def fetch_news_articles(hours: int = 48) -> list[dict]:
    """Fetch and filter articles from all industry RSS feeds."""
    articles = []
    for feed_info in NEWS_FEEDS:
        batch = _parse_feed(feed_info["url"], feed_info["name"], hours)
        articles.extend(batch)
        logger.info("  %s → %d relevant articles", feed_info["name"], len(batch))
    # Deduplicate by URL
    seen = set()
    unique = []
    for a in articles:
        if a["url"] not in seen:
            seen.add(a["url"])
            unique.append(a)
    return unique


def fetch_linkedin_posts(hours: int = 48) -> list[dict]:
    """
    Fetch LinkedIn-adjacent content via Google News RSS searches.
    Note: LinkedIn's own feed requires their official API + OAuth.
    This approach surfaces publicly indexed LinkedIn articles/posts.
    """
    posts = []
    for url in LINKEDIN_FEEDS:
        batch = _parse_feed(url, "LinkedIn (via Google News)", hours)
        posts.extend(batch)
    seen = set()
    unique = []
    for p in posts:
        if p["url"] not in seen:
            seen.add(p["url"])
            unique.append(p)
    logger.info("LinkedIn/Google News → %d results", len(unique))
    return unique


def fetch_google_trends() -> list[dict]:
    """
    Fetch Google Trends interest data for tracked keywords.
    Falls back to an empty list if pytrends is unavailable or rate-limited.
    """
    try:
        from pytrends.request import TrendReq

        keywords = [
            "AI search",
            "answer engine optimization",
            "AI Overviews",
            "generative engine optimization",
            "ChatGPT search",
            "Perplexity AI search",
            "zero click search",
            "LLM SEO",
        ]

        pytrends = TrendReq(hl="en-US", tz=0, timeout=(10, 25))
        results = []

        # pytrends only supports 5 keywords per payload
        for i in range(0, len(keywords), 5):
            chunk = keywords[i : i + 5]
            try:
                pytrends.build_payload(chunk, timeframe="now 7-d")
                df = pytrends.interest_over_time()
                if df.empty:
                    continue
                for kw in chunk:
                    if kw not in df.columns:
                        continue
                    series = df[kw]
                    latest = int(series.iloc[-1]) if not series.empty else 0
                    prev   = int(series.iloc[-7]) if len(series) >= 7 else latest
                    trend  = "rising" if latest > prev else ("falling" if latest < prev else "stable")
                    results.append({"keyword": kw, "interest": latest, "trend": trend})
            except Exception as chunk_err:
                logger.warning("pytrends chunk error: %s", chunk_err)

        logger.info("Google Trends → %d keyword signals", len(results))
        return results

    except ImportError:
        logger.warning("pytrends not installed; skipping Google Trends")
        return []
    except Exception as exc:
        logger.warning("Google Trends fetch failed: %s", exc)
        return []
