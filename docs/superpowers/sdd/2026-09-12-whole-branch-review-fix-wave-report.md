# Whole-Branch Review Fix Wave

## Changes

- Normal orchestrator worker dispatches now send the exact worker JSON body through the authenticated campaign-service capture seam before calling a copy, image, video, or ads worker.
- Capture persistence failures return a non-success response, so the orchestrator does not silently dispatch an uncaptured normal LLM request.
- The GCP deployment writes `/opt/ai-marketing-factory/.env.context-viewer` from the existing Cloud SQL private IP and generated secrets. PostgreSQL remains unpublished; the viewer connects over the existing VM-to-Cloud-SQL path.
- Viewer redaction now handles secret-bearing string values, bearer tokens, URL query credentials, and URL userinfo while preserving ordinary business text.
- Deployment output no longer prints a viewer password.

## Verification

- `python -m pytest services/orchestrator -q`: 26 passed, 2 framework deprecation warnings.
- `python -m pytest services/campaign_service/test_llm_context_capture.py -q`: 6 passed, 1 integration test skipped because `CAMPAIGN_TEST_DATABASE_URL` is unset, 2 framework deprecation warnings.
- `python -m pytest services/campaign_service -q`: 150 passed, 2 skipped, 3 failures.
- Isolated permission/validation failures: 2 passed. They are full-suite fixture/global-state ordering failures.
- Isolated regeneration failure: reproduces independently because its persistence double does not provide the existing generated-asset cache contract; it is unrelated to this fix wave.
- `npm test` in `context-viewer`: 8 passed.
- `npm run build` in `context-viewer`: passed. Next.js reported only the existing multiple-lockfile workspace-root warning.
- `python -m compileall -q services/orchestrator/app services/campaign_service/app`: passed.
- `git diff --check`: passed.
- `docker compose -f deploy/docker-compose.gcp.yml config --quiet`: not runnable locally because the GCP-only `/opt/ai-marketing-factory/.env.video.local` file is absent. The file is present on the target VM deployment topology.

## Concerns

- The live authenticated Cloud SQL query could not be executed from this workstation without the target VM credentials and network. The deployment script now supplies the configured Cloud SQL host, and viewer authentication/query route tests plus the production build pass.
- The existing campaign-service full-suite fixture failures remain documented above and should be handled in their owning tests separately.
