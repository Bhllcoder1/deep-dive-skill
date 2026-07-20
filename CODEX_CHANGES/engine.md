# `core/engine.py` hardening

- Preserved the public `run(question, runtime=None, dashboard=None)` signature.
- Made configuration parsing resilient to malformed or non-positive `DR_*` values and kept the refutation threshold attainable.
- Added safe runtime-call, fetch, logging, and parallel-execution boundaries so malformed LLM JSON, network exceptions, and failed verifier batches degrade into partial results instead of crashing a run.
- Passed the existing structured-output schemas to every LLM call, validated each phase's JSON shape, and discarded malformed angles, search results, claims, verdicts, and synthesis fields.
- Fixed the extractor to receive the fetched source text (it previously received only URL/title metadata), required quoted claims with source provenance, and prevented untrusted source text from acting as instructions.
- Enforced the global fetch cap for every relevance level, normalized/deduplicated HTTP(S) URLs, and rejected direct local/private-IP fetch targets.
- Batched verifier calls at `MAX_WORKERS` even if a runtime ignores its worker limit; corrected vote logic so ties and incomplete support are unverified rather than confirmed.
- Sanitized synthesis output so it cannot replace engine-owned fields and every structured finding must cite a surviving source URL.

Validation: `python3 -m py_compile core/engine.py` and an in-memory pipeline smoke test covering malformed configuration/data, blocked URLs, timeout handling, fetch-cap enforcement, source-text extraction, bounded verifier batches, uncited findings, and tied votes.
