# Changelog

## [0.0.6] - 2026-07-15

### Changes

- Reduce charm config in report to only option name and default value (YAML parse + extract, drop full raw dump)
- Filter unit logs to error/warning lines with context window (±10 rows) around the last chronological match
- Remove crude `" INFO "/" DEBUG "` substring filter in favour of context-window approach

## [0.0.5] - 2026-07-15

### Features

- Add OpenRouter as a second AI provider with configurable model selection
- Add provider connectivity check (`check()`) for both Gemini and OpenRouter

### Changes

- Log AI provider call results: INFO-level success/failure per provider, DEBUG-level full response
- Improve error messages in diagnostics generation to include the provider name

## [0.0.4] - 2026-07-14

### Features

- Wire diagnostics plan into collector: iterate plan sections and collect per-item data
- Add broad fallback collection when plan is empty or missing (ps aux, ss -tlnp, etc.)
- Add plan-driven Markdown report sections (log files, processes, systemd units, network ports, env vars)
- Add unit tests for plan-driven collection and report sections (23 new tests, 171 total)

## [0.0.3] - 2026-07-14

### Features

- Implement principal status monitoring with goal-state via `StatusTracker`
- Add incident lifecycle model (`Incident` dataclass) with open/close/recovery
- Add bounded context collector (Juju logs, systemd, disk, memory)
- Add plan-driven context collection: iterate diagnostics plan and collect per-section data
- Add Markdown report generation from collected context
- Add structured JSONL audit logging
- Add `show-status` and `reset` actions
- Add suggest/act mode support (gated behind mode config)
- Add test infrastructure (pytest, pyproject.toml, tox.ini, test script)
- Add unit tests for `diagnostics.py`, `providers/`

## [0.0.2] - 2026-07-05

### Features

- Add `diagnostics` config variable for monitoring plan
- Add diagnostics JSON schema and validation
- Add AI-powered diagnostics plan generation on `principal-relation-joined`
- Add Gemini provider using REST API (stdlib only)
- Create `src/jaime/` and `src/jaime/providers/` package structure
- Fall back to empty diagnostics plan when no AI provider is configured

## [0.0.1] - 2026-06-21

### Features

- Initial machine subordinate charm skeleton
- Add `metadata.yaml` for machine subordinate charm
