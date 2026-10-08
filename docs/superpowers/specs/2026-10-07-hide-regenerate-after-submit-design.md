# Hide Regenerate After Submit Design

## Goal

Prevent duplicate regeneration work orders from the Campaign edit screen after
the user has successfully submitted a regeneration request for an Asset.

## Behavior

- Track successfully submitted Asset IDs in the current edit-screen session.
- Hide the `重新生成` action for a tracked Asset immediately after the API
  request succeeds.
- Keep the action available when the API request fails so the user can retry.
- Keep the existing modal, validation, API payload, loading state, and new-asset
  review flow unchanged.
- Do not change backend behavior or data contracts.

## Verification

- Add a focused UI contract proving the action is present before submission and
  absent after a successful submission.
- Verify failed submission does not mark the Asset as submitted.
- Run TypeScript, frontend build, focused contract, and diff checks.
