# Campaign Edit Reference Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Hide the background campaign reference list while editing and keep a clear campaign-specific Reference panel separate from Assets.

**Architecture:** Keep the existing `listCampaignReferences(campaignId)` data flow and `editReferences` state. Change only the edit modal layering and presentation: use an opaque backdrop, keep the saved Reference panel inside the modal, and label the generated output table as Assets.

**Tech Stack:** Next.js 16, React 19, TypeScript, existing contract scripts, Docker Compose GCP deployment.

## Global Constraints

- Keep the campaign-specific saved Reference panel on the right.
- The edit dialog must hide the background reference-management list entirely.
- Show filename, MIME type, folder, and reference ID for saved references.
- Generated outputs remain in a separate `Assets` section.
- Do not change reference persistence, campaign APIs, or asset data flow.

---

### Task 1: Add focused layout contract

**Files:**
- Modify: `scripts/check-edit-reference-contract.mjs`
- Test: `scripts/check-edit-reference-contract.mjs`

- [ ] **Step 1: Assert modal layering and Assets label requirements**

Add checks that `app/campaigns/page.tsx` contains an opaque edit backdrop, a `Saved References`/campaign-specific reference panel, and an `Assets` heading.

- [ ] **Step 2: Run the contract before implementation**

Run:

```powershell
node scripts/check-edit-reference-contract.mjs
```

Expected: FAIL because the current implementation exposes the background and labels the asset table as Reference.

### Task 2: Correct the edit modal presentation

**Files:**
- Modify: `app/campaigns/page.tsx:2004-2128`

**Interfaces:**
- Consumes: `editReferences`, `editReferencesLoading`, and `loadEditReferences(campaignId)`.
- Produces: an opaque modal backdrop, an in-modal saved Reference panel, and a separately labeled Assets table.

- [ ] **Step 1: Replace the translucent edit backdrop**

Change the edit modal backdrop from `bg-black/40` to an opaque overlay such as `bg-slate-950/80`, keeping the modal above it with `z-50`.

- [ ] **Step 2: Move saved Reference content into the modal layout**

Render the saved Reference panel inside the edit dialog scroll area. For each `editReferences` row show:

```tsx
reference.file_name
reference.file_type
reference.folder || reference.folder_id || "未分類"
reference.reference_id
```

Do not use the page-level `references` state for this panel.

- [ ] **Step 3: Restore the generated output heading**

Rename the table section heading to `Assets`; keep existing asset preview, download, status, and regenerate actions unchanged.

- [ ] **Step 4: Remove any duplicate floating Reference panel**

Keep one in-modal Reference panel only; remove the temporary fixed-position Reference panels outside the modal.

- [ ] **Step 5: Run focused contract and build**

Run:

```powershell
node scripts/check-edit-reference-contract.mjs
npm run build
```

Expected: both pass.

### Task 3: Deploy and verify

**Files:**
- Deploy: `app/campaigns/page.tsx`

- [ ] **Step 1: Copy the frontend page to the GCP VM**

Use `gcloud compute scp` to copy the file to `/opt/ai-marketing-factory/app/campaigns/page.tsx` without printing environment values.

- [ ] **Step 2: Rebuild and restart only frontend**

Run on the VM:

```bash
cd /opt/ai-marketing-factory
docker compose -f deploy/docker-compose.gcp.yml build frontend
docker compose -f deploy/docker-compose.gcp.yml up -d frontend
```

- [ ] **Step 3: Verify online route**

Run:

```powershell
curl.exe -sS -o NUL -w "campaigns HTTP:%{http_code}\n" http://35.221.249.149/campaigns
```

Expected: HTTP `200`.
