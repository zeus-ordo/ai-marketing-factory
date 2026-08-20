# Tri-language UAT Checklist

## Scope

- Locales: `en`, `zh-Hant`, `ja`
- Pages: `dashboard`, `campaigns`, `workflow`, `content-studio`, `system`, `assets`, `performance`, `review`

## Test Matrix

For each locale, verify:

1. TopNav language switch updates all visible copy immediately.
2. Sidebar navigation labels are fully translated.
3. Dashboard KPI labels and throughput chart labels are translated.
4. Campaign table headers / action buttons / status labels are translated.
5. Workflow title, log panel title, and node labels are translated.
6. Content Studio summary cards and pass/fail badges are translated.
7. System page controls (operator, filters, buttons, confirms) are translated.
8. System operation/result display avoids raw token leakage where mapped.
9. Placeholder pages (`assets`, `performance`, `review`) are translated.

## Formatting Checks

1. Campaign budget uses locale-aware currency display.
2. Campaign/System timestamps use locale-aware datetime display.

## Negative Scenarios

1. Force API fallback and confirm fallback banners/messages are translated.
2. Trigger operation cooldown and confirm warning copy is translated.
3. Trigger operation failure and confirm error copy + tone are correct.

## Sign-off Criteria

- No hardcoded end-user text found by `npm run check:i18n`.
- `npm run lint` and `npm run build` pass.
- Manual page pass for all matrix items across 3 locales.
