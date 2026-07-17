"""Turn raw channel/video data into insights.

Two layers:
  1. Heuristic analysis (always on, free): engagement math, hook-pattern
     detection in titles, topic keywords, shorts-vs-long comparison.
  2. Optional LLM layer: if ANTHROPIC_API_KEY is set, Claude summarizes
     *why* the top videos likely work (qualitative hooks/topics).
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from .youtube_client import Channel, Video

# Words too common to be useful as "topics".
_STOPWORDS = set(
    """a an the and or but if then this that these those to of in on for with at by from
    is are was were be been being do does did how what why when where who which you your my
    our we they it its as so not no yes new best top vs video shorts short full official
    ka ki ke ko me mein hai ho na se par or aur ye yeh wo woh kya kaise
    """.split()
)

_NUMBER_RE = re.compile(r"\b\d+\b")
_HOOK_PATTERNS = {
    "number/listicle": re.compile(r"\b\d+\b"),
    "question": re.compile(r"\?|^(how|why|what|which|kya|kaise|kyun)\b", re.I),
    "curiosity/reveal": re.compile(
        r"\b(secret|truth|revealed|exposed|nobody|shocking|you won'?t believe|"
        r"finally|mystery|hidden|sach|raaz)\b",
        re.I,
    ),
    "superlative": re.compile(
        r"\b(best|worst|biggest|first|last|only|ever|most|ultimate|insane|crazy|"
        r"cheapest|fastest)\b",
        re.I,
    ),
    "urgency/news": re.compile(
        r"\b(now|today|breaking|new|just|update|2024|2025|2026|before)\b", re.I
    ),
    "personal/story": re.compile(
        r"\b(i|my|we|our|meri|mera|hum|main)\b", re.I
    ),
    "emotional": re.compile(
        r"\b(amazing|shocking|emotional|heartbreaking|hilarious|love|hate|"
        r"regret|mistake|warning)\b",
        re.I,
    ),
    "how-to/tutorial": re.compile(
        r"\b(how to|tutorial|guide|step by step|tips|tricks|explained|seekho)\b", re.I
    ),
}


@dataclass
class NicheInsights:
    niche: str
    channels: list[Channel]
    total_creators: int
    # aggregate stats
    shorts_avg_views: float = 0.0
    long_avg_views: float = 0.0
    shorts_avg_engagement: float = 0.0
    long_avg_engagement: float = 0.0
    top_videos: list[Video] = field(default_factory=list)
    top_shorts: list[Video] = field(default_factory=list)
    top_long: list[Video] = field(default_factory=list)
    hook_frequency: list[tuple[str, int]] = field(default_factory=list)
    topic_keywords: list[tuple[str, int]] = field(default_factory=list)
    llm_summary: str = ""
    notes: list[str] = field(default_factory=list)


def detect_hooks(title: str) -> list[str]:
    return [name for name, rx in _HOOK_PATTERNS.items() if rx.search(title)]


def _keywords(text: str) -> list[str]:
    words = re.findall(r"[a-zA-Zऀ-ॿ]+", text.lower())
    return [w for w in words if len(w) > 2 and w not in _STOPWORDS]


def _avg(nums: list[float]) -> float:
    return sum(nums) / len(nums) if nums else 0.0


def analyze_niche(
    niche: str,
    channels: list[Channel],
    short_max_seconds: int,
) -> NicheInsights:
    all_videos: list[Video] = []
    shorts: list[Video] = []
    long: list[Video] = []

    for ch in channels:
        for v in ch.videos:
            all_videos.append(v)
            if v.duration_seconds <= short_max_seconds and v.duration_seconds > 0:
                shorts.append(v)
            else:
                long.append(v)

    insights = NicheInsights(
        niche=niche,
        channels=channels,
        total_creators=len(channels),
    )

    if not all_videos:
        insights.notes.append("No videos found for analysis.")
        return insights

    insights.shorts_avg_views = _avg([v.views for v in shorts])
    insights.long_avg_views = _avg([v.views for v in long])
    insights.shorts_avg_engagement = _avg([v.engagement_rate for v in shorts])
    insights.long_avg_engagement = _avg([v.engagement_rate for v in long])

    insights.top_videos = sorted(all_videos, key=lambda v: v.views, reverse=True)[:15]
    insights.top_shorts = sorted(shorts, key=lambda v: v.views, reverse=True)[:10]
    insights.top_long = sorted(long, key=lambda v: v.views, reverse=True)[:10]

    # Hook patterns weighted by the views of the videos using them:
    # a pattern that appears on high-view videos matters more.
    hook_counter: Counter[str] = Counter()
    for v in insights.top_videos + insights.top_shorts + insights.top_long:
        for hook in detect_hooks(v.title):
            hook_counter[hook] += 1
    insights.hook_frequency = hook_counter.most_common()

    # Topic keywords from the titles of the best-performing videos.
    topic_counter: Counter[str] = Counter()
    for v in insights.top_videos + insights.top_shorts:
        topic_counter.update(_keywords(v.title))
    insights.topic_keywords = topic_counter.most_common(20)

    if shorts and long:
        if insights.shorts_avg_views > insights.long_avg_views:
            insights.notes.append(
                "Shorts pull higher average views than long-form in this niche — "
                "creators use Shorts for reach/discovery."
            )
        else:
            insights.notes.append(
                "Long-form pulls higher average views than Shorts here — "
                "depth/watch-time is rewarded in this niche."
            )
        if insights.shorts_avg_engagement > insights.long_avg_engagement:
            insights.notes.append(
                "Shorts have a higher engagement rate (likes+comments per view)."
            )

    return insights


def add_llm_summary(insights: NicheInsights, api_key: str) -> None:
    """Best-effort qualitative summary via Claude. Silently degrades on error."""
    try:
        import anthropic
    except ImportError:
        insights.notes.append(
            "anthropic package not installed; skipping LLM summary."
        )
        return

    top_titles = "\n".join(
        f"- [{v.views:,} views] {v.title}" for v in insights.top_videos[:15]
    )
    prompt = (
        f"You are analyzing the '{insights.niche}' niche on Indian YouTube.\n"
        f"Here are the current top-performing video titles by views:\n\n{top_titles}\n\n"
        "In 4-6 tight bullet points, explain WHY these are getting views: "
        "the hooks, topic angles, and audience psychology at play. "
        "Then give 2 concrete, specific content ideas a new creator in this niche "
        "could try. Be specific to these titles, not generic."
    )
    try:
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=700,
            messages=[{"role": "user", "content": prompt}],
        )
        insights.llm_summary = "".join(
            block.text for block in msg.content if getattr(block, "type", "") == "text"
        ).strip()
    except Exception as exc:  # noqa: BLE001 - degrade gracefully in a cron job
        insights.notes.append(f"LLM summary unavailable: {exc}")
