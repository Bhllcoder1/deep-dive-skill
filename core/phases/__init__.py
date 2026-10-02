"""Pipeline phases. Each module exposes ``NAME`` and ``run(ctx, state)``.

A phase reads/writes ``RunState`` and may set ``state.result`` to end the run. To add or
replace a phase, write a module with that interface and edit ``PHASES`` in core/engine.py.
"""
