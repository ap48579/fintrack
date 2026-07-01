"""Returns plausible, keyword-flavored synthetic posts — no network call, no API key. Titles
reference the actual query so report content built from this reads as on-topic, not generic
placeholder text. Swap to PrawRedditClient once REDDIT_CLIENT_ID/SECRET are configured."""

import random
from datetime import UTC, datetime, timedelta

from app.clients.reddit.base import RedditClient, RedditPost

_SUBREDDITS = ["stocks", "investing", "wallstreetbets", "StockMarket"]

_TITLE_TEMPLATES = [
    "{query} just had a huge move, what's everyone's take?",
    "Why is {query} all over the news this week?",
    "DD: {query} — bull case after the latest headlines",
    "{query} bears vs bulls — where are you positioned?",
    "Is the {query} reaction overblown or justified?",
    "Anyone else loading up on {query} after this?",
    "{query} earnings/news reaction megathread",
]

_BODY_TEMPLATES = [
    "Saw the news on {query} this morning and it's been the top discussion here all day. "
    "Curious what people think the medium-term impact actually is.",
    "Been tracking {query} for a while — this latest development changes the setup quite a bit imo.",
    "Not financial advice but {query} looks like it's at a decision point here given everything going on.",
]


class MockRedditClient(RedditClient):
    async def search(self, query: str, subreddits: list[str] | None = None, limit: int = 25) -> list[RedditPost]:
        return self._generate(query, subreddits or _SUBREDDITS, count=min(limit, random.randint(3, 8)))

    async def get_subreddit_hot(self, subreddit: str, limit: int = 25) -> list[RedditPost]:
        return self._generate(subreddit, [subreddit], count=min(limit, random.randint(3, 8)))

    def _generate(self, query: str, subreddits: list[str], count: int) -> list[RedditPost]:
        now = datetime.now(UTC)
        posts = []
        for i in range(count):
            subreddit = random.choice(subreddits)
            title = random.choice(_TITLE_TEMPLATES).format(query=query)
            body = random.choice(_BODY_TEMPLATES).format(query=query)
            post_id = f"mock{abs(hash((query, subreddit, i))) % 10**8:08d}"
            posts.append(
                RedditPost(
                    id=post_id,
                    subreddit=subreddit,
                    title=title,
                    selftext=body,
                    url=f"https://reddit.com/r/{subreddit}/comments/{post_id}/",
                    score=random.randint(20, 4000),
                    num_comments=random.randint(5, 600),
                    created_utc=now - timedelta(hours=random.randint(1, 72)),
                    permalink=f"https://reddit.com/r/{subreddit}/comments/{post_id}/",
                )
            )
        return posts
