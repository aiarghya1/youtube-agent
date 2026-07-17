# YouTube Niche Agent

Finds the **top 20 Indian YouTubers** in a niche, analyzes their Shorts and
long-form videos (topics, hooks, engagement), works out **why** the top videos
are performing, and **emails you a report** — daily, automatically.

## What it analyzes

| Signal | Source | Notes |
|---|---|---|
| Views, likes, comments | YouTube Data API v3 | Public, reliable |
| Engagement rate | computed | `(likes + comments) / views` |
| Shorts vs long-form | video duration | Short = ≤ 60s (configurable) |
| Hook patterns in titles | heuristic | listicle, question, curiosity, superlative, urgency, story, emotional, how-to |
| Recurring topic keywords | heuristic | from top-performing titles |
| "Why it works" write-up | Claude (optional) | only if `ANTHROPIC_API_KEY` set |

> **Shares & saves are NOT provided by the YouTube API** (they aren't public data).
> The report is honest about this and uses likes + comments as the engagement proxy.
> The only reliable ways to get shares/saves are YouTube Studio Analytics for
> channels *you own*, or paid third-party tools (e.g. Social Blade, VidIQ) — not
> available through the public API for arbitrary creators.

---

## 1. Install

```bash
cd "youtube agent"
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
```

## 2. Configure

```bash
cp .env.example .env
```

Then edit `.env` and fill in `YOUTUBE_API_KEY` and `GMAIL_APP_PASSWORD` (below).

### Getting a YouTube Data API key (free)

1. Go to <https://console.cloud.google.com/> and sign in.
2. Create a project (top bar → project dropdown → **New Project**).
3. In the search bar, find **"YouTube Data API v3"** → open it → **Enable**.
4. Left menu → **APIs & Services → Credentials → Create Credentials → API key**.
5. Copy the key into `.env` as `YOUTUBE_API_KEY=...`.
6. (Recommended) Click the key → **Restrict key** → restrict to *YouTube Data API v3*.

Free quota is 10,000 units/day. One niche run costs a few hundred units, so you
can run several niches daily comfortably.

### Getting a Gmail app password

An app password is a 16-character password just for this script (not your real one).

1. Turn on **2-Step Verification** for your Google account (required):
   <https://myaccount.google.com/signinoptions/two-step-verification>
2. Go to <https://myaccount.google.com/apppasswords>.
3. Name it e.g. "YouTube Agent" → **Create** → copy the 16-char code.
4. Put it in `.env` as `GMAIL_APP_PASSWORD=...` (spaces don't matter).

## 3. Run it

```bash
# Analyze a niche and email the report:
./.venv/bin/python run.py "tech reviews"

# Several niches in one email:
./.venv/bin/python run.py "tech reviews" "personal finance"

# Preview without sending, and save an HTML copy:
./.venv/bin/python run.py "tech reviews" --no-email --save

# No niche given → uses default_niches from config.yaml (what the daily job runs)
./.venv/bin/python run.py
```

## 4. Schedule it daily (macOS launchd)

The daily job runs `run.py` with no arguments, so set your niche(s) in
`config.yaml` under `default_niches`.

1. Edit `com.youtubeagent.daily.plist` if you want a different time
   (default: **8:00 AM**).
2. Install it:

   ```bash
   cp com.youtubeagent.daily.plist ~/Library/LaunchAgents/
   launchctl load ~/Library/LaunchAgents/com.youtubeagent.daily.plist
   ```

3. Test it fires immediately:

   ```bash
   launchctl start com.youtubeagent.daily
   ```

4. Logs are written to `agent.log` in this folder.

To stop the daily job:

```bash
launchctl unload ~/Library/LaunchAgents/com.youtubeagent.daily.plist
```

> Note: launchd only runs while your Mac is on (and awake). If it's asleep at
> 8 AM, the job runs when the Mac next wakes. For always-on delivery you'd need
> a cloud/server host instead.

## Configuration (`config.yaml`)

| Key | Meaning |
|---|---|
| `default_niches` | niche(s) the daily job analyzes |
| `region_code` | `IN` for India |
| `relevance_language` | biases results (`hi` = Hindi/India) |
| `top_n_creators` | how many creators to rank & analyze (default 20) |
| `videos_per_creator` | recent videos pulled per creator (default 25) |
| `short_max_seconds` | duration cutoff for "Short" (default 60) |
| `rank_by` | `subscribers` or `views` |

## Optional: richer AI analysis

Set `ANTHROPIC_API_KEY` in `.env` to add a Claude-written "why these work"
section per niche. Without it, the report still includes full heuristic analysis.

## Project layout

```
run.py                     # entry point
config.yaml                # niches & tuning
.env                       # secrets (gitignored)
youtube_agent/
  config.py                # settings loader
  youtube_client.py        # YouTube Data API wrapper
  analyzer.py              # engagement + hook/topic analysis
  report.py                # HTML/text report builder
  emailer.py               # Gmail SMTP sender
  cli.py                   # orchestration
com.youtubeagent.daily.plist  # macOS daily schedule
```
