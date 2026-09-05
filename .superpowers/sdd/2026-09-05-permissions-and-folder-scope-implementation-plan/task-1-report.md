# Task 1 Report

## Changed Files

- `services/membership_service/app/permissions.py`
- `services/membership_service/app/main.py`
- `services/membership_service/app/routes/company.py`
- `services/membership_service/app/routes/roles.py`
- `services/membership_service/test_permissions.py`
- `services/campaign_service/app/main.py`
- `services/campaign_service/test_review_permissions.py`
- `lib/auth/permissions.ts`
- `app/review/page.tsx`
- `components/layout/side-nav-bar.tsx`

## Implementation Summary

Added the shared canonical permission contract, wildcard/admin bypass handling, and shared role-permission validation. Membership company and role routes now use the shared checker. Startup seeding is additive and idempotently adds `review:manage` to existing Manager roles without adding `member:assign_role`. Review queue reads and actions now require `review:manage` or an accepted legacy granular review permission, while preserving internal and platform-admin bypasses and company scoping. Frontend Review page and navigation use one shared helper.

## Tests

- `python -m pytest services/membership_service/test_permissions.py services/campaign_service/test_review_permissions.py -q`: **14 passed**, 2 warnings.
- `python -m pytest services/membership_service -q`: **6 passed**.
- `python -m pytest services/campaign_service -q`: **88 passed, 1 failed**. The failure is `test_invalid_campaign_is_not_persisted`, which receives 401 instead of its expected 422 due to the existing combined `app` import/module state.
- `python -m pytest services/membership_service services/campaign_service -q`: **collection blocked, 5 errors**. Existing dual-service `app` package import collision and unavailable `psycopg_pool` cause collection errors.

## Lint/Build

- `npm run lint`: passed with **0 errors and 13 warnings**; warnings are existing unused-symbol and `<img>` warnings.
- `npm run build`: passed. Next.js emitted the existing multiple-lockfile workspace-root warning.

## Concerns

- The combined backend pytest command remains blocked by the repository's existing service-package import collision and missing local membership database dependency.
- The isolated campaign suite retains one pre-existing test failure involving internal-key detection during mixed test imports.
- Existing unrelated worktree modifications in `deploy/docker-compose.yml`, `services/campaign_service/test_industry_matching.py`, and `services/worker_copy/app/main.py` were preserved.
