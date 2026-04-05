"""
scheduler.py — Standalone scheduler entrypoint.

Run this process alongside (or instead of) the Flask app when you want
the daily brief to be generated automatically without the web process
handling it.

Usage:
  python scheduler.py

The scheduler reads from .env for configuration.
"""

import logging
import os
import sys
import time

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def run_daily_job():
    """Import and execute the pipeline from app.py."""
    logger.info("Daily brief job triggered.")
    try:
        # Import here so the scheduler can run independently of Flask
        from fetcher import fetch_google_trends, fetch_linkedin_posts, fetch_news_articles
        from summarizer import generate_daily_brief
        from app import add_summary

        articles       = fetch_news_articles()
        trends         = fetch_google_trends()
        linkedin_posts = fetch_linkedin_posts()
        brief          = generate_daily_brief(articles, trends, linkedin_posts)
        add_summary(brief)
        logger.info("Brief generated and saved for %s.", brief["date"])
    except Exception:
        logger.exception("Daily brief job failed.")


def main():
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger

    hour   = int(os.environ.get("BRIEF_HOUR", "7"))
    minute = int(os.environ.get("BRIEF_MINUTE", "0"))
    tz     = os.environ.get("BRIEF_TIMEZONE", "UTC")

    scheduler = BlockingScheduler(timezone=tz)
    scheduler.add_job(
        run_daily_job,
        CronTrigger(hour=hour, minute=minute),
        id="daily_brief",
        replace_existing=True,
    )

    logger.info("Standalone scheduler started — brief runs daily at %02d:%02d %s", hour, minute, tz)
    logger.info("Press Ctrl+C to stop.")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")


if __name__ == "__main__":
    main()
