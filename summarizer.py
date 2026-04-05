"""
summarizer.py — Uses the Claude API to generate a daily TL;DR brief
from aggregated news articles, Google Trends data, and LinkedIn posts.
"""

import os
import json
import logging
from datetime import datetime, timezone

import anthropic
from typing import Optional

logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-opus-4-6"


def _build_prompt(articles: list[dict], trends: list[dict], linkedin_posts: list[dict]) -> str:
    """Construct the prompt sent to Claude."""

    today = datetime.now(timezone.utc).strftime("%A, %B %d, %Y")

    sections = [
        f"Today is {today}. You are a senior SEO/AEO/AI Search analyst.",
        "Your job: write a crisp, executive-level daily brief for a team that needs to stay on top of",
        "SEO, Answer Engine Optimization (AEO), Generative Engine Optimization (GEO), and AI Search trends.",
        "",
        "Format your response as valid JSON with this exact structure:",
        '{"tldr": "<2-4 sentence executive summary of the most important developments today>",',
        ' "highlights": [',
        '   {"category": "<News|Trends|Social>", "point": "<one impactful insight, max 25 words>"},',
        '   ...up to 8 highlights...',
        ' ],',
        ' "watch_list": ["<keyword or topic to monitor>", ...up to 5 items...],',
        ' "sentiment": "<Bullish|Cautious|Neutral> — <one sentence on overall industry mood>"}',
        "",
        "Source material follows. Prioritize recency, authority of source, and relevance to the team's focus areas.",
        "",
    ]

    # --- News articles ---
    if articles:
        sections.append("=== INDUSTRY NEWS (last 48 hours) ===")
        for a in articles[:20]:  # cap to avoid token overload
            sections.append(f"[{a['source']}] {a['title']}")
            if a.get("excerpt"):
                sections.append(f"  → {a['excerpt'][:250]}")
        sections.append("")

    # --- Google Trends ---
    if trends:
        sections.append("=== GOOGLE TRENDS (last 7 days) ===")
        for t in trends:
            arrow = "↑" if t["trend"] == "rising" else ("↓" if t["trend"] == "falling" else "→")
            sections.append(f"  {arrow} {t['keyword']} (interest score: {t['interest']}/100, trend: {t['trend']})")
        sections.append("")

    # --- LinkedIn / Social ---
    if linkedin_posts:
        sections.append("=== LINKEDIN / SOCIAL SIGNALS ===")
        for p in linkedin_posts[:10]:
            sections.append(f"[{p['source']}] {p['title']}")
            if p.get("excerpt"):
                sections.append(f"  → {p['excerpt'][:200]}")
        sections.append("")

    if not articles and not trends and not linkedin_posts:
        sections.append("No new data was fetched. Write a brief note that the data pipeline returned no results today and suggest the team check source configurations.")

    return "\n".join(sections)


def generate_daily_brief(
    articles: list[dict],
    trends: list[dict],
    linkedin_posts: list[dict],
    api_key: Optional[str] = None,
) -> dict:
    """
    Call Claude to produce a structured daily brief.
    Returns a dict ready to be stored / served to the frontend.
    """
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is not set.")

    client = anthropic.Anthropic(api_key=api_key)
    prompt = _build_prompt(articles, trends, linkedin_posts)

    logger.info("Sending prompt to Claude (%s)…", CLAUDE_MODEL)
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()

    # Strip markdown code fences if Claude wrapped the JSON
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        brief = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Claude returned non-JSON; storing raw text as tldr.")
        brief = {"tldr": raw, "highlights": [], "watch_list": [], "sentiment": ""}

    now = datetime.now(timezone.utc)
    return {
        "date":           now.strftime("%Y-%m-%d"),
        "timestamp":      now.isoformat(),
        "tldr":           brief.get("tldr", ""),
        "highlights":     brief.get("highlights", []),
        "watch_list":     brief.get("watch_list", []),
        "sentiment":      brief.get("sentiment", ""),
        "article_count":  len(articles),
        "trend_count":    len(trends),
        "social_count":   len(linkedin_posts),
        "articles":       articles[:30],
        "trends":         trends,
        "linkedin_posts": linkedin_posts[:15],
    }


# Allow standalone testing: python summarizer.py
if __name__ == "__main__":
    import sys
    from fetcher import fetch_news_articles, fetch_google_trends, fetch_linkedin_posts

    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    print("Fetching data…")
    a = fetch_news_articles()
    t = fetch_google_trends()
    lp = fetch_linkedin_posts()
    print(f"Articles: {len(a)}, Trends: {len(t)}, LinkedIn: {len(lp)}")
    brief = generate_daily_brief(a, t, lp)
    print(json.dumps(brief, indent=2))
