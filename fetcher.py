"""
fetcher.py — Pulls data from three source categories:
  1. Industry news & research via RSS feeds
  2. Google Trends for tracked keywords
  3. Influencer & LinkedIn/social content via Google News RSS search
"""

import feedparser
import requests
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# RSS — Industry publications
# ---------------------------------------------------------------------------

NEWS_FEEDS = [
    # Core SEO publications
    {"name": "Search Engine Journal",      "url": "https://www.searchenginejournal.com/feed/"},
    {"name": "Search Engine Land",         "url": "https://searchengineland.com/feed"},
    {"name": "Search Engine Roundtable",   "url": "https://www.seroundtable.com/feed"},
    {"name": "Search Engine Watch",        "url": "https://www.searchenginewatch.com/feed/"},

    # Tool companies — blogs & research
    {"name": "Ahrefs Blog",               "url": "https://ahrefs.com/blog/feed/"},
    {"name": "Semrush Blog",              "url": "https://www.semrush.com/blog/feed/"},
    {"name": "Moz Blog",                  "url": "https://moz.com/blog/feed"},
    {"name": "SparkToro Blog",            "url": "https://sparktoro.com/blog/feed/"},
    {"name": "BrightEdge Blog",           "url": "https://www.brightedge.com/blog/rss"},
    {"name": "Conductor Blog",            "url": "https://www.conductor.com/blog/feed/"},
    {"name": "Botify Blog",               "url": "https://www.botify.com/blog/rss.xml"},

    # Platform / AI company blogs
    {"name": "Google Search Central",     "url": "https://developers.google.com/search/blog/rss.xml"},
    {"name": "Google Blog (AI & Search)", "url": "https://blog.google/rss/"},
    {"name": "OpenAI Blog",               "url": "https://openai.com/news/rss.xml"},
    {"name": "Anthropic Blog",            "url": "https://www.anthropic.com/rss.xml"},
    {"name": "Microsoft Bing Blogs",      "url": "https://blogs.microsoft.com/feed/"},

    # Marketing / broader digital
    {"name": "The Verge AI",              "url": "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml"},
    {"name": "TechCrunch AI",             "url": "https://techcrunch.com/tag/artificial-intelligence/feed/"},
    {"name": "Marketing Land / Martech",  "url": "https://martech.org/feed/"},
    {"name": "Wired AI",                  "url": "https://www.wired.com/feed/tag/artificial-intelligence/rss"},

    # Independent expert blogs
    {"name": "iPullRank (Mike King)",     "url": "https://ipullrank.com/feed/"},
    {"name": "Kevin Indig",               "url": "https://www.kevin-indig.com/feed/"},
    {"name": "Marie Haynes Consulting",   "url": "https://www.mariehaynes.com/feed/"},
    {"name": "Cyrus Shepard / Zyppy",     "url": "https://zyppy.com/feed/"},
    {"name": "Siege Media (Ross Hudgens)","url": "https://www.siegemedia.com/feed"},
    {"name": "Eli Schwartz Blog",         "url": "https://elischwartz.co/feed/"},
]

# ---------------------------------------------------------------------------
# Google News RSS — Influencer & platform tracking
# ---------------------------------------------------------------------------

# Influencers tracked by name via Google News
INFLUENCERS = [
    ("Lily Ray",     "SEO AEO AI search"),
    ("Mike King",    "iPullRank SEO"),
    ("Chris Long",   "SEO search"),
    ("Barry Schwartz","Google SEO"),
    ("Glenn Gabe",   "Google SEO algorithm"),
    ("Wil Reynolds", "SEO search"),
    ("Kevin Indig",  "SEO AI search"),
    ("Rand Fishkin", "search SEO"),
    ("Marie Haynes", "Google SEO"),
    ("Cyrus Shepard","SEO"),
    ("Ross Hudgens", "SEO content"),
]

# Platforms tracked directly via Google News (for blogs/announcements not in RSS)
PLATFORM_NEWS_QUERIES = [
    "Perplexity AI search update",
    "site:perplexity.ai blog OR announcement",
    "Profound AI search research study",
    "Google AI Overviews update announcement",
    "OpenAI SearchGPT update",
    "Anthropic Claude search update",
    "Bing AI search update",
]

# LinkedIn-specific searches
LINKEDIN_QUERIES = [
    "SEO AEO answer engine optimization site:linkedin.com",
    "GEO generative engine optimization site:linkedin.com",
    "AI search SEO strategy site:linkedin.com",
    "Google AI Overviews impact site:linkedin.com",
]


def _google_news_rss_url(query: str) -> str:
    q = query.replace(" ", "+")
    return f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


INFLUENCER_FEEDS = [
    {
        "name": f"{name} (via Google News)",
        "url": _google_news_rss_url(f'"{name}" {context}'),
    }
    for name, context in INFLUENCERS
]

PLATFORM_FEEDS = [
    {"name": "Platform News (Google News)", "url": _google_news_rss_url(q)}
    for q in PLATFORM_NEWS_QUERIES
]

LINKEDIN_FEEDS = [
    {"name": "LinkedIn (via Google News)", "url": _google_news_rss_url(q)}
    for q in LINKEDIN_QUERIES
]

# ---------------------------------------------------------------------------
# Relevance filtering
# ---------------------------------------------------------------------------

RELEVANCE_KEYWORDS = [
    "seo", "aeo", "geo", "ai search", "generative search", "answer engine",
    "ai overviews", "sge", "search generative experience", "zero-click",
    "chatgpt search", "perplexity", "llm seo", "search engine", "organic search",
    "featured snippet", "knowledge graph", "structured data", "schema markup",
    "voice search", "semantic search", "entity seo", "topical authority",
    "google search", "bing ai", "ai mode", "search ranking", "algorithm update",
    "core update", "helpful content", "e-e-a-t", "eeat", "search visibility",
    "rank", "serp", "indexing", "crawling", "openai", "anthropic", "gemini",
    "claude", "gpt", "llm", "large language model", "retrieval", "citation",
    "profound", "brightedge", "botify", "ahrefs", "semrush", "moz",
    "generative engine", "answer box", "ai citation", "search experience",
    "search traffic", "click-through", "search intent", "search behavior",
]


def _is_recent(entry, hours: int = 48) -> bool:
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            pub = datetime(*t[:6], tzinfo=timezone.utc)
            return pub >= datetime.now(timezone.utc) - timedelta(hours=hours)
    return True  # no date → include by default


def _is_relevant(entry, loose: bool = False) -> bool:
    """
    loose=True skips keyword filtering (for influencer/platform feeds where
    the query already ensures relevance).
    """
    if loose:
        return True
    text = " ".join([
        getattr(entry, "title", ""),
        getattr(entry, "summary", ""),
    ]).lower()
    return any(kw in text for kw in RELEVANCE_KEYWORDS)


def _parse_feed(url: str, source_name: str, hours: int = 48, loose: bool = False) -> list[dict]:
    articles = []
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries:
            if not _is_recent(entry, hours):
                continue
            if not _is_relevant(entry, loose=loose):
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


def _dedup(items: list[dict]) -> list[dict]:
    seen, unique = set(), []
    for item in items:
        if item["url"] not in seen:
            seen.add(item["url"])
            unique.append(item)
    return unique


# ---------------------------------------------------------------------------
# Public fetch functions
# ---------------------------------------------------------------------------

def fetch_news_articles(hours: int = 48) -> list[dict]:
    """Fetch from all industry RSS feeds and return deduplicated relevant articles."""
    articles = []
    for feed_info in NEWS_FEEDS:
        batch = _parse_feed(feed_info["url"], feed_info["name"], hours)
        articles.extend(batch)
        if batch:
            logger.info("  %s → %d articles", feed_info["name"], len(batch))
    unique = _dedup(articles)
    logger.info("News total: %d unique articles from %d feeds", len(unique), len(NEWS_FEEDS))
    return unique


def fetch_influencer_posts(hours: int = 72) -> list[dict]:
    """
    Fetch recent content by tracked industry influencers via Google News.
    Uses a slightly wider 72h window since influencer posts index more slowly.
    """
    posts = []
    for feed_info in INFLUENCER_FEEDS:
        # loose=True — query already targets the person + topic
        batch = _parse_feed(feed_info["url"], feed_info["name"], hours, loose=True)
        posts.extend(batch)
    unique = _dedup(posts)
    logger.info("Influencer signals: %d results", len(unique))
    return unique


def fetch_platform_news(hours: int = 48) -> list[dict]:
    """
    Fetch announcements / blog posts from AI & search platforms
    (Perplexity, Profound, Google AI, OpenAI, Bing) via Google News.
    """
    posts = []
    for feed_info in PLATFORM_FEEDS:
        batch = _parse_feed(feed_info["url"], feed_info["name"], hours, loose=True)
        posts.extend(batch)
    unique = _dedup(posts)
    logger.info("Platform news: %d results", len(unique))
    return unique


def fetch_linkedin_posts(hours: int = 48) -> list[dict]:
    """
    LinkedIn-adjacent content via Google News RSS searches.
    Note: LinkedIn's own API requires OAuth + Marketing Developer Platform approval.
    This surfaces publicly indexed LinkedIn articles and posts.
    """
    posts = []
    for feed_info in LINKEDIN_FEEDS:
        batch = _parse_feed(feed_info["url"], feed_info["name"], hours, loose=True)
        posts.extend(batch)
    unique = _dedup(posts)
    logger.info("LinkedIn/social: %d results", len(unique))
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
            "Perplexity AI",
            "zero click search",
            "LLM SEO",
        ]

        pytrends = TrendReq(hl="en-US", tz=0, timeout=(10, 25))
        results = []

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
