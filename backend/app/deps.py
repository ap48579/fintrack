from uuid import UUID

from app.config import settings


async def get_current_user() -> UUID:
    """Stub auth: always returns the seeded dev user's id.

    Swap path: replace this body with real session/token verification (Clerk/Supabase).
    No router or service signature needs to change — they already depend on "give me a
    user_id", not on this being a constant.
    """
    return settings.dev_user_id
