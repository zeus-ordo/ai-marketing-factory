# Campaign Edit Reference Layout

## Goal

Make the campaign edit dialog unambiguous: users should see only the references saved for the campaign being edited, without the background page's reference list leaking around the modal.

## Design

- Keep the campaign-specific saved Reference panel on the right.
- When the edit dialog is open, render an opaque full-screen backdrop above the campaign page so the underlying reference-management list is not visible or interactive.
- Keep the reference panel above the edit dialog content and show filename, MIME type, folder, and reference ID.
- Rename the central generated-output table heading back to `Assets`; it must not be labeled `Reference 檔案`.
- Do not change reference persistence, campaign APIs, or asset data flow.

## Acceptance Criteria

1. Opening Edit Campaign hides the left/background reference list entirely.
2. The right panel remains visible and contains only references returned for `editTarget.campaign_id`.
3. Generated assets remain in a separate `Assets` section with their existing preview/download actions.
4. Closing the dialog restores the normal campaign page.
5. Frontend build and a focused edit-reference contract check pass.
