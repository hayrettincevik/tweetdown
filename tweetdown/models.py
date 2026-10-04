from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class AuthBundle:
    auth_token: str
    ct0: str
    user_id: str
    source: str = "manual"


@dataclass(slots=True)
class TweetRecord:
    tweet_id: str
    url: str
    text: str
    created_at: str | None
    author_id: str | None
    author_username: str | None
    author_name: str | None
    author_avatar_url: str | None
    media_urls: list[str] = field(default_factory=list)
    expanded_urls: list[str] = field(default_factory=list)
    reply_count: int | None = None
    retweet_count: int | None = None
    favorite_count: int | None = None
    quote_count: int | None = None
    raw_json: dict[str, Any] | None = None

    def to_json(self, *, include_raw: bool) -> dict[str, Any]:
        payload = {
            "tweet_id": self.tweet_id,
            "url": self.url,
            "text": self.text,
            "created_at": self.created_at,
            "author": {
                "id": self.author_id,
                "username": self.author_username,
                "name": self.author_name,
                "avatar_url": self.author_avatar_url,
            },
            "media_urls": self.media_urls,
            "expanded_urls": self.expanded_urls,
            "counts": {
                "replies": self.reply_count,
                "retweets": self.retweet_count,
                "likes": self.favorite_count,
                "quotes": self.quote_count,
            },
        }
        if include_raw:
            payload["raw_json"] = self.raw_json
        return payload
