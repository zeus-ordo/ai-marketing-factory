# Membership Route Sync Database Fix

## Root Cause

`get_connection()` is a synchronous context manager backed by psycopg's synchronous `ConnectionPool`. The affected async routes used `async with` and asyncpg methods (`await conn.execute`, `fetch`, and `fetchrow`), causing request-time `TypeError`/attribute failures and 500 responses.

## TDD Evidence

Red command:

```text
python -m pytest test_route_sync_database.py -q
```

Exact result before production changes: `3 failed, 2 passed in 0.49s`. The failures were the expected sync-context-manager errors in platform company creation, platform company member listing, and company member listing.

Green command:

```text
python -m pytest test_route_sync_database.py -q
```

Exact result after production changes: `5 passed in 0.49s`.

Additional verification:

```text
python -m pytest -q
```

Exact result: `23 passed in 0.63s`.

```text
python -m compileall -q app
```

Exact result: completed successfully with no output.

The route audit found no remaining `async with get_connection`, awaited sync DB calls, or PostgreSQL `$n` placeholders in the route files.

## Changed Files

- `services/membership_service/app/routes/company.py`: converted member role lookup, member listing, and member removal to psycopg sync cursors.
- `services/membership_service/app/routes/platform.py`: converted audit writes, admin verification, member listings, and audit-log queries to psycopg sync cursors.
- `services/membership_service/app/routes/invitation.py`: narrowly converted invitation acceptance email verification to a psycopg sync cursor.
- `services/membership_service/test_route_sync_database.py`: added focused fake-backed tests for platform key validation, company creation audit, platform/company member listings, and role updates.

## Concerns

- Async route handlers now perform the existing synchronous DB operations directly, matching the requested existing DB API but potentially blocking the event loop during database I/O.
- Pytest emits the repository's existing `pytest-asyncio` deprecation warning about an unset fixture loop scope.
