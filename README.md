# Jaime — Juju AI Medic Engine

Jaime is a headless Juju subordinate charm for local diagnostics and incident reporting on the same machine as a principal application charm.


The phase-1 MVP focuses on **Observe mode**:

- deploy Jaime alongside a principal machine charm, for example PostgreSQL or MySQL
- monitor the principal unit status from Juju context
- detect unhealthy states such as `error` or `blocked`
- wait for a configurable timeout before creating an incident report
- collect compact local context from Juju, systemd, journal, disk, memory, and network state
- write structured JSONL audit logs
- optionally call an AI provider such as Gemini to generate a Markdown report
- do **not** perform remediation in phase-1 unless explicitly implemented later

## Scope

The eventual goal is that Jaime attempts to fix infrastructure and environment issues, that are causing the principa charm to enter into an `error` state. Jaime shouldn't touch any of the principal charm's application code. Phase-1 is intentionally conservative. Jaime should first become a reliable observer and reporter before it becomes an automated remediation engine.

Phase 1:

- Juju machine subordinate charm
- `update-status` based monitoring
- Juju action based interaction
- local log and host diagnostics collection
- structured audit log
- Markdown incident report generation
- AI provider abstraction, initially Gemini

Out of scope for phase-1:

- automatic remediation
- Kubernetes sidecar mode
- Slack, Mattermost, GitHub, or ticketing integrations
- controller API integration
- broad arbitrary command execution
- OpenClaw integration

## First target behaviour

The initial target workflow is:

```text
Jaime deployed as subordinate
→ identifies related principal unit
→ checks principal status periodically
→ detects watched status: error/blocked
→ tracks how long the unit remains unhealthy
→ after timeout, collects diagnostics
→ writes JSONL incident events
→ writes Markdown report
→ exposes report path/result via Juju action output
```

## Example deployment

```bash
juju deploy postgresql --channel 14/stable
juju deploy ./jaime.charm
juju integrate postgresql Jaime
```

## Example actions

```bash
juju run jaime/0 diagnose
juju run jaime/0 collect-context
juju run jaime/0 generate-report
juju run jaime/0 list-reports
juju run jaime/0 get-report
```

A future phase may add:

```bash
juju run jaime/0 remediate dry-run=true
juju run jaime/0 remediate execute=true
```

## Suggested MVP config

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

## Design principle

Jaime should be boring, auditable, and safe.

It should collect facts first, produce reports second, and only attempt changes in later phases with strict allowlists, dry-run support, and explicit operator intent.
