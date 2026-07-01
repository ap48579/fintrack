from functools import lru_cache

from app.clients.reddit.base import RedditClient
from app.config import settings


@lru_cache
def get_reddit_client() -> RedditClient:
    if settings.reddit_client_impl == "praw":
        from app.clients.reddit.praw_client import PrawRedditClient

        return PrawRedditClient()
    from app.clients.reddit.mock import MockRedditClient

    return MockRedditClient()
