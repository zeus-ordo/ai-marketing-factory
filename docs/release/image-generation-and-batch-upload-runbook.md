# Image Generation and Batch Upload Runbook

## Offline Gate

Run from the approved branch worktree:

```bash
python -m pytest tests_e2e/test_image_generation_and_batch_upload.py -q
python -m pytest services/worker_image -q
python -m pytest services/campaign_service -q
npm run lint
npm run build
git diff --check
```

The deterministic E2E suite must use mocked provider responses and local test
files only. Required scenarios are empty real image failure, valid image asset
persistence, partial batch failure blocking campaign start, retrying only the
failed file, and persistence/file readability after a service-object restart.

## Backup And Deployment

Do not make production persistence/schema changes until a backup is created and
verified. Use the current approved commit and the existing Compose workflow:

```bash
COMMIT="$(git rev-parse HEAD)"
gcloud sql backups create --project=market-factory --instance=ai-marketing-postgres --description="image-batch-pre-deploy-${COMMIT}"
gcloud sql backups list --project=market-factory --instance=ai-marketing-postgres --filter="description=image-batch-pre-deploy-${COMMIT}" --format="table(id,status,description)"
docker compose -f deploy/docker-compose.gcp.yml ps
curl -fsS http://127.0.0.1/
```

Never print environment values, credentials, JWTs, provider bodies, or secret
prompts. Keep the local reference/generated stores until backend persistence and
restart checks pass.

## Controlled Validation

- Run one neutral image request and record only provider, HTTP status, attempts, and asset count.
- Run 1-, 2-, and 10-file uploads with one intentional failure.
- Verify campaign start remains blocked while any selected file is failed or uploading.
- Retry only the failed file and verify all-success state permits start.
- Compare database metadata with stored file names/sizes and bytes.
- Recreate the relevant service/persistence object and verify metadata/files remain readable.
- Record backup ID/status, deployed commit, Compose status, health/smoke results, test counts, and limitations in the task report.
