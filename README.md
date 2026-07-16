# Jaime — Juju AI Medic Engine

Jaime is a headless Juju subordinate charm for local diagnostics and incident reporting on the same machine as a principal application charm.

The phase-1 MVP focuses on **Observe mode**:

- deploy Jaime alongside a principal machine charm, for example PostgreSQL or MySQL
- monitor the principal unit status from Juju context via `update-status`
- detect unhealthy states such as `error` or `blocked`
- wait for a configurable timeout before creating an incident report
- collect diagnostics by iterating the monitoring plan, or fall back to broad commands (`ps aux`, `ss -tlnp`, etc.)
- write structured JSONL audit logs
- optionally call an AI provider (Gemini or OpenRouter) for diagnosis suggestions
- do **not** perform remediation in phase-1 unless explicitly enabled

## Scope

Phase 1:

- Juju machine subordinate charm
- `update-status` based principal monitoring via goal-state
- diagnostics monitoring plan (AI-generated or manually configured)
- plan-driven context collection with broad fallback
- incident lifecycle (open, timeout, collect, report, cooldown, recover)
- Markdown incident report generation
- Juju actions for diagnostics and report retrieval
- structured JSONL audit logging
- AI provider abstraction (Gemini, OpenRouter) for suggest/act modes
- 197 unit tests

Out of scope for phase-1:

- automatic remediation (gated behind `mode: act`)
- Kubernetes sidecar mode
- Slack, Mattermost, GitHub, or ticketing integrations
- controller API integration
- OpenClaw integration

## Incident flow

```text
Jaime deployed as subordinate
→ identifies related principal unit via goal-state
→ checks principal status on every update-status
→ detects watched status: error/blocked
→ tracks how long the unit remains unhealthy
→ after failure-timeout, opens an incident
→ loads diagnostics plan (or uses broad fallback)
→ collects per-plan context (logs, processes, systemd, ports, env vars, health commands)
→ collects background context (juju logs, charm config, disk, memory)
→ writes Markdown report
→ writes JSONL audit events
→ respects cooldown before next report
→ closes incident on recovery
```

## Quickstart

```bash
# Setup
sudo snap install charmcraft --classic
sudo snap install lxd
sudo usermod -aG lxd $USER
newgrp lxd

# Deploy a principal charm (e.g. postgresql)
juju deploy postgresql --channel 16/stable --to 0

# Set AI provider config (optional — works without AI too)
export JAIME_PROVIDER=gemini
export JAIME_MODEL=gemini-2.5-flash
export JAIME_API_TOKEN="<your-token>"

# Pack and deploy Jaime
make deploy

# Monitor
juju status
juju run jaime/0 show-status
```

## Actions

```bash
juju run jaime/0 diagnose              # Basic principal info
juju run jaime/0 collect-context       # Collect and return context bundle
juju run jaime/0 generate-report       # Generate report for current open incident
juju run jaime/0 get-suggestion        # Get AI suggestion for current incident
juju run jaime/0 show-status           # Show monitoring state for all units
juju run jaime/0 reset                 # Clear all incidents and start fresh
```

## Configuration

| Key | Default | Description |
|---|---|---|
| `mode` | `observe` | `observe`, `suggest`, or `act` |
| `provider` | `none` | AI provider (`none`, `gemini`, or `openrouter`) |
| `api-token` | `""` | Juju secret reference for the AI token |
| `watch-statuses` | `error,blocked` | Statuses that trigger an incident |
| `failure-timeout-minutes` | `5` | How long a status must persist before reporting |
| `cooldown-minutes` | `30` | Min time between reports for the same incident |
| `log-window-minutes` | `120` | How far back to collect logs |
| `max-context-lines` | `500` | Max lines per collected file/section |
| `diagnostics` | `""` | JSON monitoring plan (empty = AI-generated on relation) |

See `config.yaml` for full reference.

## Diagnostics plan

The diagnostics plan drives what gets collected. It can be:

1. **AI-generated** — on `principal-relation-joined`, Jaime calls Gemini to build a plan for the workload
2. **Manually configured** — set `diagnostics` config to a JSON monitoring plan
3. **Empty** — Jaime falls back to broad commands (`ps aux`, `ss -tlnp`, `systemctl --failed`)

Each plan section (`log_files`, `processes`, `systemd_units`, `network.ports`, `env_variables`, `health_commands`) is iterated by the collector, and results appear in the report with status icons (✓/✗).

See `examples/diagnostics.json` for a sample plan and `examples/report.md` for the generated report output.

## Modes

### observe (default)

Collect context, generate reports, write audit logs. No AI interaction.

### suggest

Same as observe, but after generating the base report, calls the AI provider (Gemini or OpenRouter) and appends a diagnosis section. No commands are executed.

### act

Same as suggest, but executes commands returned by the AI. Gated behind explicit opt-in. All executions are audited to the JSONL log.

## Testing

```bash
# Run all tests
./scripts/test.sh

# Run with coverage
./scripts/test.sh --cov=src --cov-report=term

# Run specific test file
./scripts/test.sh tests/test_collector.py -v
```

Tests auto-create a virtual environment in `.venv` on first run.

## Development

```bash
make clean    # Remove build artifacts
make pack     # Pack the charm
make deploy   # Pack and deploy with AI provider config (requires env vars)
```

To update an existing deployment after re-packing:

```bash
juju refresh jaime --path=./jaime_ubuntu-24.04-amd64.charm --force-units
```

## Design principle

Jaime should be boring, auditable, and safe.

It collects facts first, produces reports second, and only attempts changes in later phases with strict allowlists, dry-run support, and explicit operator intent.
