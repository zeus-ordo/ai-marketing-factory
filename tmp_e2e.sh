#!/bin/bash
set -e

WORKER_COPY="http://localhost:8091"
CAMPAIGN="http://localhost:8080"
KEY="change_me_internal_key"
COMPANY_ID="00000000-0000-0000-0000-000000000001"

echo "=== Step 1: Call copy worker ==="
curl -s -X POST "$WORKER_COPY/internal/workers/copy/run" \
  -H "X-Internal-Api-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "test-e2e-001",
    "campaign_id": "test-campaign-001",
    "company_id": "'"$COMPANY_ID"'",
    "prompt": "Write a short ad for Nike shoes.",
    "brand_context": {},
    "variants": 1
  }' | python3 -c "import sys,json; d=json.load(sys.stdin); print('Status:', 'OK' if 'variants' in d else 'ERROR'); print('Response:', d)"

echo ""
echo "=== Step 2: Wait 2 seconds for async processing ==="
sleep 2

echo "=== Step 3: Check Redis buffer ==="
docker exec deploy-redis-1 redis-cli LLEN llm_usage_buffer

echo ""
echo "=== Step 4: Check Redis buffer contents ==="
docker exec deploy-redis-1 redis-cli LRANGE llm_usage_buffer 0 -1

echo ""
echo "=== Step 5: Check llm_usage table ==="
docker exec deploy-postgres-1 psql -U app -d marketing_ai -c "SELECT * FROM llm_usage LIMIT 5;"

echo ""
echo "=== Step 6: Check llm_model_pricing ==="
docker exec deploy-postgres-1 psql -U app -d marketing_ai -c "SELECT * FROM llm_model_pricing;"

echo ""
echo "=== E2E Test Complete ==="
