# Copy Length Contract Design

## Goal

Ensure campaign copy follows the selected copy type's body-length range, especially public-relations copy at 300–500 characters, across initial generation and regeneration.

## Root Cause

`campaign-service` currently writes the selected copy policy into the campaign prompt, but `worker_copy` appends a later hard-coded rule requiring `body` to be 80–200 characters. The later instruction can override the campaign prompt. The same hard-coded rule exists in both the normal and regeneration paths.

## Design

### Single structured length contract

`campaign-service` will derive one copy-type contract and include it in the worker request:

- 宣傳文宣: maximum 100 characters
- 社群文章: 100–200 characters
- 公關稿: 300–500 characters

The request will carry explicit `body_min_length` and `body_max_length` values rather than relying only on natural-language prompt ordering. The contract applies equally to normal generation and regeneration.

### Worker prompt construction

`worker_copy` will build the final field rules from the structured contract. The fixed `80–200` body rule will be removed. The prompt will state the selected range after all campaign context and will explicitly require the body to remain within that range.

Title and CTA limits remain unchanged. The worker must continue returning the existing JSON shape: `title`, `body`, and `cta`.

### Deterministic validation and repair

After parsing the model JSON, the worker will validate the body length using Python Unicode character count. If the body is outside the contract, it will make one bounded repair request containing the exact required range and the existing JSON contract. If the repaired result is still invalid, the worker returns a clear 502 error instead of silently persisting an invalid copy.

The same validation path will be used by initial generation and regeneration.

### Backward compatibility

Requests from older callers that do not provide a length contract will retain a safe default of 80–200 characters. New campaign-service requests always provide the selected range. Existing title, CTA, provider, model, and response schemas remain compatible.

## Testing

- Campaign-service tests assert each copy type maps to the intended min/max contract and that the worker payload carries it.
- Worker tests assert the final prompt does not contain the old fixed rule and includes the dynamic range.
- Worker tests cover valid public-relations copy, one repair for too-short/too-long output, and failure when repair remains invalid.
- Regeneration tests cover the same length validation path.
- Existing campaign-service and worker-copy suites must remain green.
