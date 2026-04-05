"""
app.py — Flask backend for the Cassie AEO News daily briefing app.

Endpoints:
  GET  /                       → serve the main webpage
  GET  /api/summaries          → all stored daily summaries (newest first)
  GET  /api/summaries/latest   → most recent summary
  POST /api/refresh            → manually trigger a new brief generation
  GET  /api/status             → scheduler and app health info
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

DATA_FILE = Path(__file__).parent / "data" / "summaries.json"
DATA_FILE.parent.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def load_summaries() -> list[dict]:
    if not DATA_FILE.exists():
        return []
    try:
        return json.loads(DATA_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return []


def save_summaries(summaries: list[dict]) -> None:
    DATA_FILE.write_text(json.dumps(summaries, indent=2))


def add_summary(brief: dict) -> None:
    summaries = load_summaries()
    # Replace today's entry if it already exists
    today = brief["date"]
    summaries = [s for s in summaries if s.get("date") != today]
    summaries.insert(0, brief)
    # Keep only the last 60 days
    summaries = summaries[:60]
    save_summaries(summaries)


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------

_is_generating = False


def run_pipeline() -> dict:
    """Fetch data → summarise with Claude → persist → return brief."""
    global _is_generating
    if _is_generating:
        raise RuntimeError("A generation is already in progress.")
    _is_generating = True
    try:
        from fetcher import fetch_google_trends, fetch_linkedin_posts, fetch_news_articles
        from summarizer import generate_daily_brief

        logger.info("Pipeline: fetching news articles…")
        articles = fetch_news_articles()

        logger.info("Pipeline: fetching Google Trends…")
        trends = fetch_google_trends()

        logger.info("Pipeline: fetching LinkedIn / social…")
        linkedin_posts = fetch_linkedin_posts()

        logger.info(
            "Pipeline: generating brief (articles=%d trends=%d social=%d)…",
            len(articles), len(trends), len(linkedin_posts),
        )
        brief = generate_daily_brief(articles, trends, linkedin_posts)
        add_summary(brief)
        logger.info("Pipeline: done. Brief for %s saved.", brief["date"])
        return brief
    finally:
        _is_generating = False


# ---------------------------------------------------------------------------
# Scheduler (optional — starts if RUN_SCHEDULER=true in env)
# ---------------------------------------------------------------------------

_scheduler = None


def start_scheduler():
    global _scheduler
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger

        hour   = int(os.environ.get("BRIEF_HOUR", "7"))
        minute = int(os.environ.get("BRIEF_MINUTE", "0"))
        tz     = os.environ.get("BRIEF_TIMEZONE", "UTC")

        _scheduler = BackgroundScheduler(timezone=tz)
        _scheduler.add_job(
            run_pipeline,
            CronTrigger(hour=hour, minute=minute),
            id="daily_brief",
            replace_existing=True,
        )
        _scheduler.start()
        logger.info("Scheduler started — daily brief at %02d:%02d %s", hour, minute, tz)
    except Exception as exc:
        logger.warning("Scheduler could not start: %s", exc)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/summaries")
def get_summaries():
    summaries = load_summaries()
    # Strip heavy article/post lists from the list view to keep payload small
    slim = []
    for s in summaries:
        entry = {k: v for k, v in s.items() if k not in ("articles", "linkedin_posts", "trends")}
        slim.append(entry)
    return jsonify(slim)


@app.route("/api/summaries/latest")
def get_latest():
    summaries = load_summaries()
    if not summaries:
        return jsonify({"error": "No summaries yet. Hit POST /api/refresh to generate the first one."}), 404
    return jsonify(summaries[0])


@app.route("/api/summaries/<date>")
def get_by_date(date: str):
    summaries = load_summaries()
    for s in summaries:
        if s.get("date") == date:
            return jsonify(s)
    return jsonify({"error": f"No summary found for {date}"}), 404


@app.route("/api/refresh", methods=["POST"])
def refresh():
    if _is_generating:
        return jsonify({"error": "Generation already in progress."}), 409
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return jsonify({"error": "ANTHROPIC_API_KEY is not configured on the server."}), 500
    try:
        brief = run_pipeline()
        return jsonify({
            "message": "Brief generated successfully.",
            "date":    brief["date"],
            "timestamp": brief["timestamp"],
        })
    except Exception as exc:
        logger.exception("Pipeline error")
        return jsonify({"error": str(exc)}), 500


@app.route("/api/status")
def status():
    summaries = load_summaries()
    latest_date = summaries[0]["date"] if summaries else None
    scheduler_running = _scheduler is not None and _scheduler.running if _scheduler else False
    return jsonify({
        "status":            "ok",
        "summaries_stored":  len(summaries),
        "latest_date":       latest_date,
        "generating":        _is_generating,
        "scheduler_running": scheduler_running,
        "api_key_set":       bool(os.environ.get("ANTHROPIC_API_KEY")),
        "server_time_utc":   datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if os.environ.get("RUN_SCHEDULER", "false").lower() == "true":
        start_scheduler()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
