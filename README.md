# Cassie AEO News — Daily Brief

A self-hosted web app that scans SEO / AEO / GEO / AI Search signals every day and delivers a team-ready TL;DR, powered by Claude.

## What it does

| Source | What's pulled |
|---|---|
| **Industry RSS feeds** | Search Engine Journal, Search Engine Land, Moz, SEMrush, Verge AI, TechCrunch AI, and more |
| **Google Trends** | Rising/falling interest scores for tracked keywords (AI search, AEO, GEO, SGE, etc.) |
| **LinkedIn via Google News** | Publicly indexed LinkedIn articles and posts about these topics |

Claude processes all of that and returns:
- **TL;DR** — 2–4 sentence executive summary
- **Highlights** — up to 8 bullet points by category
- **Watch list** — keywords/topics to monitor tomorrow
- **Sentiment** — Bullish / Cautious / Neutral with one-line rationale

Briefs are stored locally (up to 60 days) and served in a clean, dark-mode web UI.

---

## Quick start

### 1. Clone & install
```bash
git clone <repo-url>
cd Cassie_AEO_News
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure
```bash
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
```

### 3. Run
```bash
python app.py
```
Open **http://localhost:5000** in your browser, then click **"Generate Today's Brief"**.

---

## Daily automation

The built-in scheduler fires automatically at `BRIEF_HOUR:BRIEF_MINUTE` (default 07:00 UTC) when `RUN_SCHEDULER=true` in your `.env`.

You can also run the scheduler as a standalone process (useful for Docker multi-container setups):
```bash
python scheduler.py
```

---

## API

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Web UI |
| `GET` | `/api/summaries` | All stored briefs (lightweight, no source lists) |
| `GET` | `/api/summaries/latest` | Most recent brief (full detail) |
| `GET` | `/api/summaries/2026-04-05` | Brief for a specific date |
| `POST` | `/api/refresh` | Trigger generation immediately |
| `GET` | `/api/status` | Health / scheduler info |

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | **Required.** Your Anthropic API key |
| `RUN_SCHEDULER` | `false` | Auto-schedule daily brief in `app.py` |
| `BRIEF_HOUR` | `7` | Hour (24h) for daily run |
| `BRIEF_MINUTE` | `0` | Minute for daily run |
| `BRIEF_TIMEZONE` | `UTC` | Any IANA timezone string |
| `PORT` | `5000` | HTTP port |

---

## LinkedIn note

LinkedIn does not provide a public RSS feed or unauthenticated API. This app surfaces **publicly indexed LinkedIn articles** via Google News RSS searches. For deeper LinkedIn integration (profile posts, engagement metrics) you would need the [LinkedIn Marketing Developer Platform](https://developer.linkedin.com/) and OAuth approval.
