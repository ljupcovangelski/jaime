# Jaime Architecture

## Overview

Jaime is a Juju machine subordinate charm that runs on the same machine as a principal application charm. Its job is to observe the principal unit, detect sustained unhealthy states, collect compact diagnostics, and generate structured incident reports.

Phase-1 is observe-only. Remediation is a future feature.

## High-level architecture

```text
Juju model
└── machine
    ├── principal charm unit
    │   └── application workload (daemon or systemd service)
    └── jaime subordinate unit
        ├── charm event handlers
        ├── principal status monitor
        ├── context collector
        ├── incident tracker
        ├── JSONL audit logger
        ├── report generator
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

Jaime uses Juju charm events, especially `update-status`, to periodically inspect the related principal unit.
Jaimie should not talk directly to the Juju controller API in phase-1.
On `update-status`, Jaimie should identify the related principal unit using local charm context, subordinate relation data, Juju hook tools, and/or `goal-state`.
The principal status should be read from the local Juju execution context where possible, not by authenticating to the controller as an external client.

Algorithm:

```text
on update-status:
  identify related principal unit
  read principal status

  if principal status is healthy:
    if there is an active incident:
      write incident-recovered event
      close incident
    exit

  if principal status is in watch-statuses:
    if there is no active incident:
      create incident
      store first_seen timestamp
      write incident-start event

    if unhealthy duration is below failure-timeout-minutes:
      write still-unhealthy event
      exit

    if report already generated for this incident:
      respect cooldown and exit

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

## Principal status source

Primary source:

- Juju charm context and hook tools
- relation context
- goal-state/status-related information where available

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
ai-report-enabled: true
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
