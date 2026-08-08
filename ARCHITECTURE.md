# Jaime Architecture

## Overview

Jaime is a Juju machine subordinate charm that runs on the same machine as one or more application charms. Its job is to observe all co-located units (principal and subordinate), detect sustained unhealthy states, collect compact diagnostics, and generate structured incident reports.

Phase-1 is observe-only. Remediation is a future feature.

## High-level architecture

```text
Juju model
└── machine
    ├── principal charm unit A
    │   ├── application workload (daemon or systemd service)
    │   └── subordinate charm unit B
    ├── principal charm unit C (unrelated, ignored by jaime)
    └── jaime subordinate unit
        ├── charm event handlers
        ├── co-located unit monitor (all units on machine except jaime)
        ├── context collector
        ├── incident tracker (per-unit)
        ├── JSONL audit logger
        ├── report generator (per-incident)
        └── AI provider adapter, optional
```

## Technology Choices

### Juju Charm Framework

Jaime is implemented as a Juju machine subordinate charm using the Ops Framework.

The Ops Framework is responsible for:

- charm lifecycle events
- relation handling
- action handling
- configuration management
- secret integration
- status updates

Business logic should remain outside the charm event handlers where possible to keep functionality testable without a running Juju model.

## Core loop

Jaime uses Juju charm events, especially `update-status`, to periodically inspect all co-located units on the same machine.
Jaimie should not talk directly to the Juju controller API in phase-1.
On `update-status`, Jaimie should identify all co-located units (excluding itself) using goal-state.
Each unit's status should be read from the local Juju execution context where possible, not by authenticating to the controller as an external client.

The diagnostics plan is generated once per related principal app and applies to all co-located units sharing that machine.

Algorithm per co-located unit:

```text
on update-status:
  discover all co-located units via goal-state
  for each unit (excluding jaime itself):

    read unit status

    if unit status is healthy:
      if there is an active incident for this unit:
        write incident-recovered event
        close incident
      continue

    if unit status is in watch-statuses:
      if there is no active incident for this unit:
        create incident
        store first_seen timestamp
        write incident-start event

      if unhealthy duration is below failure-timeout-minutes:
        write still-unhealthy event
        continue

      if report already generated for this incident:
        respect cooldown and continue

      load diagnostics plan
      if plan is available and has items in a section:
        collect per-plan context (tail log files, pgrep processes, systemctl is-active, ss port check, os.environ.get)
      else for each empty or missing section:
        collect broad fallback (ps aux for processes, systemctl --failed for systemd, ss -tlnp for ports)
      collect background context (Juju unit logs, disk usage, memory summary)
      write raw context bundle

      if mode is suggest or act and AI provider is configured:
        generate AI-assisted Markdown report with AI suggestions
      else:
        generate non-AI Markdown report

      write report-generated event
```

## Modes

### observe

Default mode.

Jaime may:

- read Juju/local state
- collect logs per diagnostics plan
- write JSONL audit logs
- write Markdown reports
- call AI provider for diagnosis/reporting

Jaime must not:

- restart services
- modify files outside its own state/report directories
- change charm or system configuration
- run AI-generated remediation commands

### suggest

Same as observe, but after generating the base report, Jaime calls the AI provider
and appends an "AI Diagnosis & Suggestions" section. No commands are executed.
AI output is purely advisory.

### act

**Not part of the first MVP.** Code exists but is gated behind `mode: act`.

Capabilities:

Not part of the first MVP implementation.

When implemented, act mode must use:

- explicit operator intent
- dry-run action parameter
- strict command allowlists
- structured audit trail
- rollback metadata where possible

## Unit discovery and status source

Jaime discovers co-located units by reading goal-state on every `update-status` tick.
Units are identified by filtering goal-state to those running on the same machine as jaime itself.
The `principal` relation is used only for co-location (placing jaime on the correct machine) and for
diagnostics plan generation, not for unit discovery.

Primary source:

- Juju charm context and hook tools
- goal-state for co-located unit discovery and status
- relation context for diagnostics plan generation

Secondary source:

- systemd state
- journal logs
- application logs
- host health checks

Logs are used to explain failures, not as the primary source of truth for Juju unit status.

## AI usage

AI is optional in phase-1.

AI is used for:

- summarizing compact context
- identifying likely root cause
- producing Markdown reports
- suggesting safe next manual checks

AI is not used for:

- deciding whether a unit is unhealthy
- executing commands automatically
- receiving unlimited raw logs
- receiving secrets

## Data flow

```text
Diagnostics plan (generated on relation-joined)
        ↓
Juju status / local checks
        ↓
Principal monitor (StatusTracker)
        ↓
Incident tracker
        ↓
Context collector
  ├── plan-driven (log files, processes, systemd units, network, env vars)
  └── background (Juju logs, disk, memory)
        ↓
Sanitizer / compactor
        ↓
Report generator
        ↓
JSONL audit log + Markdown report
```

Optional:

```text
Sanitized context
        ↓
AI provider adapter
        ↓
AI-assisted diagnosis
        ↓
Markdown report
```

## Filesystem layout

Suggested runtime paths:

```text
/var/lib/jaime/
  incidents/
    <incident-id>.json
    <incident-id>-context.json

/var/log/jaime/
  events.jsonl
  reports/
    <incident-id>.md
```

## Initial config

```yaml
mode: observe
provider: gemini
model: gemini-1.5-flash
watch-statuses: error,blocked
failure-timeout-minutes: 5
cooldown-minutes: 30
log-window-minutes: 30
max-context-lines: 500
```

## Juju actions

Phase-1 actions:

```text
diagnose
collect-context
generate-report
show-status
reset
```

Future actions:

```text
remediate
list-incidents
show-incident
clear-incident
```

## MVP acceptance test

1. Deploy a principal machine charm.
2. Deploy Jaime as a subordinate.
3. Integrate Jaime with the principal.
4. Simulate or detect an unhealthy principal state.
5. Confirm Jaime records the incident start.
6. Wait for `failure-timeout-minutes`.
7. Confirm Jaime writes a bounded context bundle.
8. Confirm Jaime writes a Markdown report.
9. Confirm Jaime performs no remediation in observe mode.

# Jaimie Roadmap

## Phase 1 – Observe

Deploy Jaimie as a machine subordinate charm. Detect unhealthy principal units, collect diagnostics, and generate structured incident reports without modifying the environment.

## Phase 2 – Assisted Remediation

Integrate AI providers to analyze incidents, suggest remediation actions, and optionally execute approved fixes while maintaining a complete audit trail.

## Phase 3 – Environment Hygiene

Detect and safely clean residual resources left behind by charms, applications, or machines, with a focus on reclaiming failed or unprovisioned infrastructure.

## Phase 4 – Knowledge and Support

Generate issue reports, identify known failure patterns, and assist operators with troubleshooting and bug filing.

## Phase 5 – Local Knowledge Engine

Learn from previously observed incidents, reports, and remediation outcomes to provide local recommendations without requiring external AI providers.

## Phase 6 – Fleet Management

Introduce centralized visibility, controller integration, fleet-wide incident analysis, and optional user interfaces for managing multiple Jaimie deployments.
