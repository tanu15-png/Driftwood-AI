from supabase import AsyncClient, create_async_client

from app.config import settings


async def create_admin_client() -> AsyncClient:
    return await create_async_client(
        settings.supabase_url,
        settings.supabase_service_role_key,
    )


async def create_user_client(access_token: str) -> AsyncClient:
    client = await create_async_client(
        settings.supabase_url,
        settings.supabase_anon_key,
    )
    # create_async_client authorizes as the anon key. Reset PostgREST so the
    # next query uses the caller's JWT and RLS policies.
    client.options.headers["Authorization"] = f"Bearer {access_token}"
    client._postgrest = None
    return client
