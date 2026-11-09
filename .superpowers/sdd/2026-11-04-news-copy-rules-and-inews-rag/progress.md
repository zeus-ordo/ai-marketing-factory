# SDD ledger — plan: docs/superpowers/plans/2026-11-04-news-copy-rules-and-inews-rag.md

Baseline: 751d4f0

Pre-flight:
- Focused tests pass when campaign-service and worker-copy tests run separately.
- Combined collection has an existing `app` module-path collision: worker-copy imports campaign-service `app.schemas`; no source changes made for this baseline issue.

Task 1: complete (commits d5e58dd..5df81d9, review clean)
Task 2: complete (external RTF corrected, review clean)
Task 3: complete (commits b3116fb..d10b8b5, review clean; DOCX converted in-memory to TXT per human decision)
Task 4: complete (dry-run review clean; production blocked by missing authorized API URL/admin credential)
Text embedding pipeline: complete through `bd66a28` (final branch review approved; production not called)
Task 5: complete (fresh focused verification passed; production import remains blocked by missing authorized URL/key)

Review correction for text embedding response regression:
- Updated `test_reference_pack_text.py` to use the nested `text_embedding` shape returned by `PostgresPersistence.list_reference_pack_items()`.
- The API serialization test now covers `ready`, `pending`, and `failed` embedding states while asserting private paths remain absent.
- Verification: `python -m pytest -q test_reference_pack_text.py test_reference_packs.py test_text_embedding_contract.py` — 50 passed, 2 existing deprecation warnings.
