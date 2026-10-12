# Human-Readable LLM Activity Design

## Goal

Make the independent Context Viewer understandable to customers by clearly separating what was sent to the LLM from what the LLM returned, while preserving the raw technical record for administrators.

## Product Decisions

- Use a deterministic presentation layer in Context Viewer; do not call another LLM and do not change persisted logs.
- Preserve the original language of prompts, references, and model responses.
- Show complete readable content, not only keywords or a generated summary.
- Keep technical fields available in a collapsed technical-details section.
- Never infer missing historical prompt content; show an explicit unavailable message.

## Customer View

### What was sent to the LLM

Show the complete readable prompt and a structured list of supplied context:

- Reference filename
- Folder
- Source type
- External search query/results when present
- User instructions and task requirements already present in the captured prompt

Do not show JSON wrappers, database IDs, token counts, task IDs, or provider internals in this section.

### What the LLM returned

Show persisted outputs in readable form:

- Copy text
- Image/video asset name and result link or preview
- Ads strategy content
- Review status and failure reason when applicable

### Technical details

Keep a collapsed administrator section containing the raw payload, context JSON, generation context ID, run ID, token counts/ratios, provider, model, and task ID.

## Historical Data Handling

When a record predates exact prompt capture, display: `This historical activity does not contain the complete LLM prompt.` Do not reconstruct or invent missing content.

## Acceptance Criteria

1. A selected activity clearly presents two primary sections: what was sent and what was returned.
2. Reference names and folders are readable without exposing implementation IDs in the primary view.
3. Raw technical data remains available through an explicit collapsed section.
4. Existing prompt/output copy and download actions continue to work.
5. Historical records without captured prompts show an explicit limitation message.
6. Existing viewer authentication, filtering, and redaction behavior remain unchanged.
