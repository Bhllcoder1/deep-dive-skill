# `runtime/base.py` changes

- Made `RuntimeCapabilities` genuinely immutable: model-family and authentication
  collections are normalized to tuples, so its `frozen=True` guarantee cannot be
  bypassed by mutating an inner list.
- Added construction-time validation for capability names, enum values, feature
  flags, parallel/context/setup limits, and finite non-negative cost estimates.
  Invalid adapter declarations now fail where they are declared instead of
  producing misleading capability output later.
- Kept every `BaseRuntime` public method signature unchanged. Existing list
  inputs for model families and auth methods remain accepted and are normalized
  to immutable tuples.
