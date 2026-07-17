"""Thin, quota-conscious wrapper over the YouTube Data API v3.

Quota notes (free tier = 10,000 units/day):
  - search.list        = 100 units per call
  - channels.list      =   1 unit  per call (up to 50 ids)
  - playlistItems.list =   1 unit  per call
  - videos.list        =   1 unit  per call (up to 50 ids)

A single niche run costs roughly:
  search (a few calls) + channels + ~2 * top_n_creators list calls
which stays well within the daily free quota.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from googleapiclient.discovery import build

_DURATION_RE = re.compile(
    r"P(?:(?P<days>\d+)D)?T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?"
)


def parse_iso8601_duration(value: str) -> int:
    """Convert an ISO-8601 duration like 'PT1M35S' to total seconds."""
    if not value:
        return 0
    m = _DURATION_RE.fullmatch(value)
    if not m:
        return 0
    parts = {k: int(v) if v else 0 for k, v in m.groupdict().items()}
    return (
        parts["days"] * 86400
        + parts["hours"] * 3600
        + parts["minutes"] * 60
        + parts["seconds"]
    )


@dataclass
class Video:
    video_id: str
    title: str
    description: str
    published_at: str
    duration_seconds: int
    views: int
    likes: int
    comments: int
    tags: list[str] = field(default_factory=list)

    @property
    def is_short(self) -> bool:
        # Overridden by caller using the configured threshold; default 60s.
        return self.duration_seconds <= 60

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"

    @property
    def engagement_rate(self) -> float:
        """(likes + comments) / views, as a fraction. 0 if no views."""
        if self.views <= 0:
            return 0.0
        return (self.likes + self.comments) / self.views


@dataclass
class Channel:
    channel_id: str
    title: str
    subscribers: int
    total_views: int
    video_count: int
    uploads_playlist: str
    videos: list[Video] = field(default_factory=list)

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/channel/{self.channel_id}"


def _to_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


class YouTubeClient:
    def __init__(self, api_key: str):
        self._yt = build("youtube", "v3", developerKey=api_key, cache_discovery=False)

    def find_channels_for_niche(
        self,
        niche: str,
        region_code: str = "IN",
        relevance_language: str = "hi",
        pool_size: int = 60,
    ) -> list[str]:
        """Search videos in a niche and collect the channels behind them.

        Searching videos (rather than channels) surfaces creators who are
        *currently* active and relevant to the niche, which is a better proxy
        for 'top creators' than YouTube's channel search.
        """
        channel_ids: list[str] = []
        seen: set[str] = set()
        page_token = None
        while len(channel_ids) < pool_size:
            resp = (
                self._yt.search()
                .list(
                    q=niche,
                    part="snippet",
                    type="video",
                    regionCode=region_code,
                    relevanceLanguage=relevance_language,
                    order="viewCount",
                    maxResults=50,
                    pageToken=page_token,
                )
                .execute()
            )
            for item in resp.get("items", []):
                cid = item.get("snippet", {}).get("channelId")
                if cid and cid not in seen:
                    seen.add(cid)
                    channel_ids.append(cid)
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        return channel_ids

    def get_channels(self, channel_ids: list[str]) -> list[Channel]:
        """Fetch channel stats. Handles >50 ids by batching."""
        channels: list[Channel] = []
        for i in range(0, len(channel_ids), 50):
            batch = channel_ids[i : i + 50]
            resp = (
                self._yt.channels()
                .list(part="snippet,statistics,contentDetails", id=",".join(batch))
                .execute()
            )
            for item in resp.get("items", []):
                stats = item.get("statistics", {})
                uploads = (
                    item.get("contentDetails", {})
                    .get("relatedPlaylists", {})
                    .get("uploads", "")
                )
                channels.append(
                    Channel(
                        channel_id=item["id"],
                        title=item.get("snippet", {}).get("title", ""),
                        subscribers=_to_int(stats.get("subscriberCount")),
                        total_views=_to_int(stats.get("viewCount")),
                        video_count=_to_int(stats.get("videoCount")),
                        uploads_playlist=uploads,
                    )
                )
        return channels

    def get_recent_video_ids(self, uploads_playlist: str, limit: int) -> list[str]:
        video_ids: list[str] = []
        page_token = None
        while len(video_ids) < limit and uploads_playlist:
            resp = (
                self._yt.playlistItems()
                .list(
                    part="contentDetails",
                    playlistId=uploads_playlist,
                    maxResults=min(50, limit - len(video_ids)),
                    pageToken=page_token,
                )
                .execute()
            )
            for item in resp.get("items", []):
                vid = item.get("contentDetails", {}).get("videoId")
                if vid:
                    video_ids.append(vid)
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        return video_ids[:limit]

    def get_videos(self, video_ids: list[str]) -> list[Video]:
        videos: list[Video] = []
        for i in range(0, len(video_ids), 50):
            batch = video_ids[i : i + 50]
            resp = (
                self._yt.videos()
                .list(part="snippet,statistics,contentDetails", id=",".join(batch))
                .execute()
            )
            for item in resp.get("items", []):
                snip = item.get("snippet", {})
                stats = item.get("statistics", {})
                details = item.get("contentDetails", {})
                videos.append(
                    Video(
                        video_id=item["id"],
                        title=snip.get("title", ""),
                        description=snip.get("description", ""),
                        published_at=snip.get("publishedAt", ""),
                        duration_seconds=parse_iso8601_duration(
                            details.get("duration", "")
                        ),
                        views=_to_int(stats.get("viewCount")),
                        likes=_to_int(stats.get("likeCount")),
                        comments=_to_int(stats.get("commentCount")),
                        tags=snip.get("tags", []) or [],
                    )
                )
        return videos
