# Jaime Tasks

## 0. Phase 0 — Repository bootstrap

- [x] Create charm repository structure
- [x] Add README.md
- [x] Add AGENTS.md
- [x] Add architecture.md
- [x] Add tasks.md
- [x] Add .gitignore
- [x] Add initial license decision

## 1. Phase 1 — Observe-only MVP

Deploy Jaimie as a machine subordinate charm. Detect unhealthy principal units, collect diagnostics, and generate structured incident reports without modifying the environment.
Only logic for `observe` mode is added at this phase.

### 1.1. Charm skeleton

- [x] [charm] Add `charmcraft.yaml`
- ~~[ ] [charm] Add `metadata.yaml` for machine subordinate charm~~
- [x] [charm] Add `config.yaml`
- [x] [charm] Add `actions.yaml`
- [x] [charm] Add `src/charm.py`
- [x] [charm] Add basic charm unit status handling
- [x] [charm] Add relation handling for principal/subordinate relation

### 1.2. Config

- [x] [charm] Add `mode`, default `observe`
- [x] [charm] Add `watch-statuses`, default `error,blocked`
- [x] [charm] Add `failure-timeout-minutes`, default `5`
- [x] [charm] Add `cooldown-minutes`, default `30`
- [x] [charm] Add `log-window-minutes`, default `30`
- [x] [charm] Add `max-context-lines`, default `500`
- [x] [charm] Add `provider`, default `none` or `gemini`
- [x] [charm] Add `model`
- [x] [charm] Add `ai-report-enabled`, default `false` initially
- [x] [charm] Add token/secret config only after non-AI observe path works

### 1.3. Diagnostics plan generation

- [x] [charm] Add `diagnostics` config variable to `config.yaml`
- [x] [python] Define diagnostics JSON schema (`src/jaime/diagnostics.py`)
- [x] [python] Add diagnostics validation against schema
- [x] [python] Add AI prompt builder for diagnostics generation
- [x] [python] Add diagnostics file persistence/reading (`/var/lib/jaime/diagnostics.json`)
- [x] [python] Add Gemini provider using REST API (`src/jaime/providers/gemini.py`)
- [x] [charm] On `principal-relation-joined`: if `diagnostics` config empty, generate via AI and write to file
- [x] [charm] On `principal-relation-joined`: if `diagnostics` config non-empty, validate and write to file
- [x] [charm] Create `src/jaime/` and `src/jaime/providers/` package structure

### 1.4. Principal status monitoring

- [x] [charm] Implement principal unit discovery via goal-state
- [x] [python] Implement `StatusTracker` for per-unit state persistence
- [x] [python] Implement real status reader using Juju goal-state hook tool
- [x] [charm] Detect watched statuses from config
- [x] [python] Detect recovery (status leaving watch list)
- [x] [python] Avoid duplicate incident creation via incident ID tracking

### 1.5. Incident tracking

- [x] [python] Define `Incident` dataclass with open/close lifecycle
- [x] [python] Use UUID4 for incident IDs
- [x] [python] Store active incident state in `StatusTracker` under `/var/lib/jaime/status-state.json`
- [x] [python] Record `first_seen` timestamp per unit
- [x] [python] Record current status per unit
- [x] [python] Record report generation state as `last_reported` timestamp
- [x] [python] Close incident on recovery detection
- [x] [python] Add cooldown logic to prevent repeated report generation

### 1.6. Context collection

- [x] [charm] Collect Juju goal-state/status context via hook tool
- [x] [python] Collect recent Juju unit logs bounded by `log-window-minutes` and `max-context-lines`
- [x] [python] Collect systemd failed units via `systemctl --failed`
- [x] [python] Collect disk usage via `df -h`
- [x] [python] Collect memory summary via `free -h`
- [x] [python] Enforce `max-context-lines` on all log/collect output
- [ ] [python] Collect journal snippets bounded by time/lines
- [ ] [python] Redact obvious secrets/tokens/passwords

### 1.6a. Plan-driven context collection

- [x] [python] Load diagnostics plan in collector and iterate sections
- [x] [python] Collect per-plan log files (`tail -n max_lines` each path)
- [x] [python] Collect per-plan processes (`pgrep -f` and compare count)
- [x] [python] Collect per-plan systemd units (`systemctl is-active`)
- [x] [python] Collect per-plan network ports (`ss -tlnp` filtering)
- [x] [python] Collect per-plan environment variables (`os.environ.get`)
- [x] [python] Return plan_results alongside background context
- [x] [python] Handle empty plan gracefully (broad fallback)
- [x] [python] Broad fallback for missing plan (`ps aux`, `ss -tlnp`, `systemctl --failed`)

### 1.7. Structured logging

- [x] [python] Create append-only JSONL audit logger (`logging.py`)
- [x] [python] Write `incident-start` event on incident open
- [x] [python] Write `context-collected` event with log line count
- [x] [python] Write `report-generated` event with path and mode
- [ ] [python] Write `still-unhealthy` event during timeout wait
- [ ] [python] Write `incident-recovered` event on recovery
- [x] [python] Include timestamp, incident ID, principal unit, status in all events

### 1.8. Reports

- [x] [python] Generate non-AI Markdown report from collected context
- [x] [python] Include timeline (incident ID, first seen, generated at)
- [x] [python] Include observed workload status
- [x] [python] Include bounded Juju unit log excerpts
- [x] [python] Include host checks (disk, memory, systemd)
- [x] [python] Include plan-driven sections (log files, processes, systemd units, network ports, env vars)
- [ ] [python] Include suggested manual next steps
- [x] [python] Store reports under `/var/log/jaime/reports/`

### 1.9. Actions

- [x] [charm] `diagnose`: return current principal context and mode
- [x] [charm] `collect-context`: collect and return context
- [x] [charm] `generate-report`: collect context, generate report, return path and content
- [x] [charm] `show-status`: return current monitoring state for all units
- [x] [charm] `reset`: close open incidents and clear status state
- [x] [charm] Ensure all actions are read-only in observe mode

### 1.10. Tests

- [x] [test] Set up pytest with test infrastructure (`pyproject.toml`, venv, tests/ structure)
- [x] [test] Unit test `diagnostics.py` — `validate_diagnostics` (valid/invalid plans, schema edge cases)
- [x] [test] Unit test `diagnostics.py` — `build_prompt`, `make_empty_plan`
- [x] [test] Unit test `diagnostics.py` — `write_diagnostics_file`, `read_diagnostics_file` (round-trip, missing file, invalid JSON, directory creation)
- [x] [test] Unit test `diagnostics.py` — `DIAGNOSTICS_SCHEMA` structure
- [x] [test] Unit test `providers/base.py` — abstract class contract
- [x] [test] Unit test `providers/gemini.py` — init, successful generation, error handling, empty responses
- [x] [test] Unit test `Incident` model — create, close, is_open, to/from dict
- [x] [test] Unit test `StatusTracker` — observe, episode detection, open/close incident
- [x] [test] Unit test cooldown behaviour (in `test_charm_status.py`)
- [x] [test] Unit test log line bounding (`_tail_lines`)
- [x] [test] Unit test plan-driven collection — log files, processes, systemd units, network ports, env vars
- [x] [test] Unit test plan-driven collection — empty plan, missing sections
- [x] [test] Unit test report generation — background sections
- [x] [test] Unit test report generation — plan-driven sections
- [x] [test] Unit test `write_event` audit logging
- [ ] [test] Add fake provider for AI tests

## 2. Phase 2 — Assisted Remediation

Integrate AI providers to analyze incidents, suggest remediation actions, and optionally execute approved fixes while maintaining a complete audit trail.

- [ ] Add provider interface
- [ ] Add Gemini provider
- [ ] Add provider config validation
- [ ] Add Juju secret/token handling
- [ ] Add prompt builder
- [ ] Add context sanitizer before AI call
- [ ] Add AI response parser
- [ ] Add AI-assisted Markdown report
- [ ] Ensure provider failures fall back to non-AI report
- [ ] Add tests with fake provider

## 3. Phase 3 – Environment Hygiene

Detect and safely clean residual resources left behind by charms, applications, or machines, with a focus on reclaiming failed or unprovisioned infrastructure.

## 4. Phase 4 – Knowledge and Support

Generate issue reports, identify known failure patterns, and assist operators with troubleshooting and bug filing.

## 5. Phase 5 – Local Knowledge Engine

Learn from previously observed incidents, reports, and remediation outcomes to provide local recommendations without requiring external AI providers.

## 6. Phase 6 – Fleet Management

Introduce centralized visibility, controller integration, fleet-wide incident analysis, and optional user interfaces for managing multiple Jaimie deployments.
