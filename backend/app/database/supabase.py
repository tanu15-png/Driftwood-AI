from supabase import AsyncClient, AsyncClientOptions, create_async_client

from app.config import settings


async def create_admin_client() -> AsyncClient:
    """Bypasses RLS — trusted server-side operations only."""
    # Explicit Authorization header skips the client's anon-key session
    # lookup; refresh/persist are off because the service role key is not a
    # user session.
    options = AsyncClientOptions(
        headers={"Authorization": f"Bearer {settings.supabase_service_role_key}"},
        auto_refresh_token=False,
        persist_session=False,
    )
    return await create_async_client(
        settings.supabase_url,
        settings.supabase_service_role_key,
        options,
    )


async def create_user_client(access_token: str) -> AsyncClient:
    """Queries run as the caller — PostgREST enforces the user's RLS policies."""
    # Passing the JWT via options (instead of patching headers after
    # creation) means the lazily-built PostgREST client carries it and no
    # anon-key session lookup runs.
    options = AsyncClientOptions(
        headers={"Authorization": f"Bearer {access_token}"},
        auto_refresh_token=False,
        persist_session=False,
    )
    return await create_async_client(
        settings.supabase_url,
        settings.supabase_anon_key,
        options,
    )
