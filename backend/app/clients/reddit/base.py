from abc import ABC, abstractmethod
from datetime import datetime

from pydantic import BaseModel


class RedditPost(BaseModel):
    id: str
    subreddit: str
    title: str
    selftext: str
    url: str
    score: int
    num_comments: int
    created_utc: datetime
    permalink: str  # full reddit.com URL


class RedditClient(ABC):
    @abstractmethod
    async def search(self, query: str, subreddits: list[str] | None = None, limit: int = 25) -> list[RedditPost]:
        """Search Reddit for posts matching query, optionally scoped to specific subreddits."""

    @abstractmethod
    async def get_subreddit_hot(self, subreddit: str, limit: int = 25) -> list[RedditPost]:
        """Hot posts from a specific subreddit — used for the lightweight passive-scan aggregation."""
