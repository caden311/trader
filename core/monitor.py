from __future__ import annotations

import hashlib
import time
from datetime import datetime
from xml.etree import ElementTree

import requests
import structlog

from config.settings import settings
from models.post import Post
from store.database import Database

logger = structlog.get_logger()

TRUMP_TRUTH_RSS = "https://www.trumpstruth.org/feed"


class TruthSocialMonitor:
    def __init__(self, db: Database):
        self.db = db

    def fetch_new_posts(self, max_retries: int = 3) -> list[Post]:
        """Poll the Trump Truth RSS feed for new posts. Returns only unseen posts."""
        for attempt in range(max_retries):
            try:
                return self._fetch_rss(attempt)
            except Exception:
                wait = 2 ** (attempt + 1)
                logger.warning(
                    "rss_fetch_failed",
                    attempt=attempt + 1,
                    max_retries=max_retries,
                    retry_in=wait,
                )
                if attempt < max_retries - 1:
                    time.sleep(wait)
        logger.error("rss_all_retries_exhausted")
        return []

    def _fetch_rss(self, attempt: int) -> list[Post]:
        logger.info("polling_rss", url=TRUMP_TRUTH_RSS, attempt=attempt + 1)

        resp = requests.get(TRUMP_TRUTH_RSS, timeout=15)
        resp.raise_for_status()

        root = ElementTree.fromstring(resp.content)
        channel = root.find("channel")
        if channel is None:
            logger.warning("rss_no_channel_element")
            return []

        items = channel.findall("item")
        new_posts = []

        for item in items:
            title = (item.findtext("title") or "").strip()
            description = (item.findtext("description") or "").strip()
            link = item.findtext("link") or ""
            pub_date = item.findtext("pubDate") or ""
            guid = item.findtext("guid") or ""

            # Use guid as post ID, fall back to hashing the content
            post_id = guid or hashlib.sha256(
                (title + description + pub_date).encode()
            ).hexdigest()[:16]

            # Prefer description (full text), fall back to title
            text = description or title
            if not text:
                continue

            if self.db.has_seen_post(post_id):
                continue

            # Parse pub date (RSS format: "Thu, 03 Apr 2026 08:30:00 +0000")
            created_at = self._parse_rss_date(pub_date)

            post = Post(
                id=post_id,
                text=text,
                created_at=created_at,
                url=link or None,
                has_media=False,
            )

            self.db.save_post(post)
            new_posts.append(post)

        logger.info(
            "rss_poll_complete",
            total_items=len(items),
            new_posts=len(new_posts),
        )
        return new_posts

    @staticmethod
    def _parse_rss_date(date_str: str) -> datetime:
        """Parse RSS pubDate format into datetime."""
        formats = [
            "%a, %d %b %Y %H:%M:%S %z",
            "%a, %d %b %Y %H:%M:%S %Z",
            "%Y-%m-%dT%H:%M:%S%z",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except ValueError:
                continue
        logger.warning("unparseable_date", date_str=date_str)
        return datetime.now()
