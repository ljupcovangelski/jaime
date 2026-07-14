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

- [X] [charm] Implement principal unit discovery
- [X] [python] Implement placeholder status reader
- [X] [python] Implement real status reader using Juju context/hook tools where possible
- [X] [charm] Detect watched statuses
- [X] [python] Detect recovery
- [X] [python] Avoid duplicate incident creation

### 1.5. Incident tracking

- [ ] [python] Define incident model
- [ ] [python] Create incident ID format
- [X] [python] Store active incident state under `/var/lib/jaime/incidents/`
- [X] [python] Record `first_seen`
- [X] [python] Record current status and message (only status is readable from hooks)
- [ ] [python] Record report generation state
- [ ] [python] Close incident on recovery
- [X] [python] Add cooldown logic

### 1.6. Context collection

- [ ] [charm] Collect Juju goal-state/status context
- [ ] [python] Collect recent Juju unit logs
- [ ] [python] Collect recent principal charm logs if available
- [ ] [python] Collect systemd failed units
- [ ] [python] Collect journal snippets bounded by time/lines
- [ ] [python] Collect disk usage
- [ ] [python] Collect memory summary
- [ ] [python] Collect network summary
- [ ] [python] Enforce `max-context-lines`
- [ ] [python] Redact obvious secrets/tokens/passwords

### 1.7. Structured logging

- [ ] [python] Create `/var/log/jaime/events.jsonl`
- [ ] [python] Write `incident-start` event
- [ ] [python] Write `still-unhealthy` event
- [ ] [python] Write `context-collected` event
- [ ] [python] Write `report-generated` event
- [ ] [python] Write `incident-recovered` event
- [ ] [python] Include timestamp, incident ID, principal unit, status, reason, and paths

### 1.8. Reports

- [ ] [python] Generate non-AI Markdown report
- [ ] [python] Include timeline
- [ ] [python] Include observed status
- [ ] [python] Include bounded log excerpts
- [ ] [python] Include host checks
- [ ] [python] Include suggested manual next steps
- [ ] [python] Store reports under `/var/log/jaime/reports/`

### 1.9. Actions

- [ ] [charm] `diagnose`: collect current context and return short result
- [ ] [python] Add diagnose result builder
- [ ] [charm] `collect-context`: write context bundle and return path
- [ ] [charm] `generate-report`: generate report and return path
- [ ] [charm] Ensure actions work in observe mode
- [ ] [charm] Ensure actions do not mutate principal workload

### 1.10. Tests

- [x] [test] Set up pytest with test infrastructure (`pyproject.toml`, venv, tests/ structure)
- [x] [test] Unit test `diagnostics.py` — `validate_diagnostics` (valid/invalid plans, schema edge cases)
- [x] [test] Unit test `diagnostics.py` — `build_prompt`, `make_empty_plan`
- [x] [test] Unit test `diagnostics.py` — `write_diagnostics_file`, `read_diagnostics_file` (round-trip, missing file, invalid JSON, directory creation)
- [x] [test] Unit test `diagnostics.py` — `DIAGNOSTICS_SCHEMA` structure
- [x] [test] Unit test `providers/base.py` — abstract class contract
- [x] [test] Unit test `providers/gemini.py` — init, successful generation, error handling, empty responses
- [ ] [test] Unit test incident creation
- [ ] [test] Unit test timeout threshold
- [ ] [test] Unit test cooldown behaviour
- [ ] [test] Unit test recovery closes incident
- [ ] [test] Unit test log line bounding
- [ ] [test] Unit test secret redaction
- [ ] [test] Unit test non-AI report generation
- [ ] [test] Add fake provider for later AI tests

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
