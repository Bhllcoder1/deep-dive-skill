# `core/monitor.py`

- Made phase/agent lifecycle mutations thread-safe with a re-entrant lock, an indexed agent registry, and atomic ID allocation. This prevents duplicate IDs and inconsistent state when `parallel.py` workers update the monitor concurrently.
- Enforced terminal transitions: duplicate or late completion/failure notifications no longer overwrite the first terminal result or double-count progress. Cancellation marks active phases/agents as cancelled and counts skipped/cancelled work as finished.
- Rejects invalid questions, names, IDs, token counts, timeouts, unknown phases, and unknown agents instead of silently discarding status updates. Starting work in a closed/cancelled phase now fails explicitly.
- Locked all monitor reports/statistics and use a single report-time snapshot, preventing concurrent iteration over mutable phase/agent data. Timing uses a monotonic clock to avoid wall-clock adjustments corrupting elapsed durations.
- Fixed cost accounting to retain the configured provider's per-agent rates at start time; previously all reports priced every agent as DeepSeek. Also fixed provider switching so a previous provider's API key is not retained accidentally.
- Added additive `PhaseStatus.CANCELLED`, `PhaseRecord.skipped_agents`, and `PhaseRecord.cancelled_agents` fields. No existing public method or constructor signature changed.
