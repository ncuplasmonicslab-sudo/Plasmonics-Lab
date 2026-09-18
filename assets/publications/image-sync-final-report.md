# Publication image sync report

- Executed (UTC): 2026-09-17 11:54:33Z
- Scope: current publications.json only (37 records)
- Cache parsing and retry-after decisions: Python discovery tool only

## Preflight
```text
preflight: 37 publications; JSON valid
```

## Discovery
```text
{"verified": 0, "needs_review": 1, "deferred": 0, "no_candidate": 36}
```
Exit code: 0

## Import
```text
No enabled sources. Nothing to import.
```
Exit code: 0

## Validation
```json
{"json_valid": true, "publication_cards": 37, "image_sources": {"local": 0, "https": 4, "default": 33}, "empty_src": 0, "missing_local_assets": [], "candidate_summary": {"verified": 0, "needs_review": 1, "deferred": 0, "no_candidate": 36}, "manual_review_entries": 37, "deferred_sources": {}}
```
Exit code: 0
