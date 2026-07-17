"""Command-line entry point for the YouTube niche agent.

Usage:
  python run.py                       # uses default_niches from config.yaml
  python run.py "tech reviews"        # analyze one niche
  python run.py "tech" "finance"      # analyze several
  python run.py "tech reviews" --no-email   # print report, don't send
  python run.py "tech reviews" --save       # also save HTML to reports/
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from . import analyzer, report
from .config import (
    ROOT,
    load_settings,
    validate_for_email,
    validate_for_run,
)
from .emailer import send_email
from .youtube_client import YouTubeClient


def _log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def analyze_one_niche(client: YouTubeClient, settings, niche: str):
    _log(f"Searching creators for niche: {niche!r}")
    pool_ids = client.find_channels_for_niche(
        niche,
        region_code=settings.region_code,
        relevance_language=settings.relevance_language,
        pool_size=max(settings.top_n_creators * 3, 40),
    )
    _log(f"  found {len(pool_ids)} candidate channels; fetching stats")
    channels = client.get_channels(pool_ids)

    key = (lambda c: c.subscribers) if settings.rank_by == "subscribers" else (
        lambda c: c.total_views
    )
    channels.sort(key=key, reverse=True)
    top = channels[: settings.top_n_creators]
    _log(f"  ranked; keeping top {len(top)} by {settings.rank_by}")

    for i, ch in enumerate(top, 1):
        vids = client.get_recent_video_ids(
            ch.uploads_playlist, settings.videos_per_creator
        )
        ch.videos = client.get_videos(vids)
        _log(f"  [{i}/{len(top)}] {ch.title}: {len(ch.videos)} videos")

    insights = analyzer.analyze_niche(niche, top, settings.short_max_seconds)
    if settings.use_llm:
        _log("  adding LLM qualitative summary")
        analyzer.add_llm_summary(insights, settings.anthropic_api_key)
    return insights


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="YouTube niche analysis agent")
    parser.add_argument("niches", nargs="*", help="Niche(s) to analyze")
    parser.add_argument(
        "--no-email", action="store_true", help="Print report instead of emailing"
    )
    parser.add_argument(
        "--save", action="store_true", help="Save HTML report to reports/"
    )
    args = parser.parse_args(argv)

    settings = load_settings()

    problems = validate_for_run(settings)
    if problems:
        for p in problems:
            print(f"ERROR: {p}", file=sys.stderr)
        return 1

    niches = args.niches or settings.default_niches
    if not niches:
        print("ERROR: no niche given and no default_niches in config.yaml", file=sys.stderr)
        return 1

    client = YouTubeClient(settings.youtube_api_key)
    results = []
    for niche in niches:
        try:
            results.append(analyze_one_niche(client, settings, niche))
        except Exception as exc:  # noqa: BLE001
            _log(f"  FAILED for {niche!r}: {exc}")

    if not results:
        print("ERROR: no niches could be analyzed.", file=sys.stderr)
        return 1

    html = report.build_html(results)
    text = report.build_text(results)
    subject = report.subject_line(results)

    if args.save:
        out_dir = ROOT / "reports"
        out_dir.mkdir(exist_ok=True)
        out_file = out_dir / f"report-{datetime.now():%Y%m%d-%H%M}.html"
        out_file.write_text(html, encoding="utf-8")
        _log(f"Saved report to {out_file}")

    if args.no_email:
        print("\n" + text)
        return 0

    email_problems = validate_for_email(settings)
    if email_problems:
        for p in email_problems:
            print(f"ERROR: {p}", file=sys.stderr)
        print("(Report generated but not sent. Use --no-email to view it.)", file=sys.stderr)
        return 1

    _log(f"Sending email to {settings.report_to}")
    send_email(
        from_addr=settings.gmail_address,
        app_password=settings.gmail_app_password,
        to_addr=settings.report_to,
        subject=subject,
        html_body=html,
        text_body=text,
    )
    _log("Done ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
