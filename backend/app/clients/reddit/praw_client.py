"""Real Reddit client — built alongside the mock so swapping REDDIT_CLIENT_IMPL=praw is a
config change, not a redesign. Unused until REDDIT_CLIENT_ID/SECRET are configured."""

from datetime import UTC, datetime

import asyncpraw

from app.clients.reddit.base import RedditClient, RedditPost
from app.config import settings


class PrawRedditClient(RedditClient):
    def _make_reddit(self) -> asyncpraw.Reddit:
        return asyncpraw.Reddit(
            client_id=settings.reddit_client_id,
            client_secret=settings.reddit_client_secret,
            user_agent=settings.reddit_user_agent,
        )

    def _to_post(self, submission) -> RedditPost:
        return RedditPost(
            id=submission.id,
            subreddit=str(submission.subreddit.display_name),
            title=submission.title,
            selftext=submission.selftext or "",
            url=submission.url,
            score=submission.score,
            num_comments=submission.num_comments,
            created_utc=datetime.fromtimestamp(submission.created_utc, tz=UTC),
            permalink=f"https://reddit.com{submission.permalink}",
        )

    async def search(self, query: str, subreddits: list[str] | None = None, limit: int = 25) -> list[RedditPost]:
        async with self._make_reddit() as reddit:
            target = "+".join(subreddits) if subreddits else "all"
            subreddit = await reddit.subreddit(target)
            return [self._to_post(s) async for s in subreddit.search(query, limit=limit)]

    async def get_subreddit_hot(self, subreddit: str, limit: int = 25) -> list[RedditPost]:
        async with self._make_reddit() as reddit:
            sub = await reddit.subreddit(subreddit)
            return [self._to_post(s) async for s in sub.hot(limit=limit)]
