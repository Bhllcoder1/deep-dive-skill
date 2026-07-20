# `harness.py` reliability changes

- Validated Python API inputs: questions must be non-empty strings; runtime names, tiers, numeric limits, unknown overrides, worker caps, and the votes/refutations relationship now fail as structured error results instead of producing obscure runtime failures or silently doing nothing.
- Isolated each `deep_research()` call's `DR_*` configuration with a process lock, temporary environment overlay, and engine reload before/after the run. This fixes import-time configuration being ignored and prevents one call's overrides from leaking into later calls.
- Fixed the bundled dashboard integration from the entrypoint: it now adapts the actual `Dashboard` API, runs only on a TTY, and is stopped/joined deterministically so dashboard failures or render-thread races cannot break the pipeline.
- Contained unexpected pipeline/network/timeout failures in structured reports, and made report rendering tolerate partial or malformed result data.
- Made `--format json` emit only valid JSON on stdout, wrote output files as UTF-8 with save-error handling, and fixed CLI handling for zero/negative limits, closed stdin, empty filenames, and output failures.
