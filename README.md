# Jaime - Juju AI Medic Engine

Jaime is a Juju diagnostic and incident reporting engine, available in two variants:
- **machine subordinate** (`charms/machine/`) — co-located with a principal machine charm
- **Kubernetes standalone** (`charms/k8s/`) — runs as its own pod and monitors other applications in the same Juju model

The phase-1 MVP focuses on **Observe and Suggest modes**:

- deploy Jaime alongside a principal machine charm, for example PostgreSQL or MySQL, or in a k8s model
- monitor the unit status from Juju context via `update-status`
- detect unhealthy states such as `error` or `blocked`
- wait for a configurable timeout before creating an incident report
- collect diagnostics by iterating the monitoring plan, or fall back to broad commands (`ps aux`, `ss -tlnp`, etc.)
- write structured JSONL audit logs
- optionally call an AI provider (Gemini or OpenRouter) for diagnosis suggestions

## Incident flow

```text
Jaime
→ identifies principal unit to monitor
→ checks unit status on every update-status
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

## Quickstart (machine charm)

```bash
# Deploy Jaime from CharmHub
juju deploy jaime

# Deploy a principal charm (e.g. postgresql)
juju deploy postgresql --channel 16/stable

juju relate postgresql jaime

# Monitor
juju status
juju run jaime/0 show-status
```

To update an existing deployment:

```bash
juju refresh jaime
```

To enable AI-assisted reports (optional):

```bash
juju config jaime mode=suggest

# Store the token as a Juju secret (token is never stored in plain config)
SECRET_URI=$(juju add-secret jaime-token token=<your-api-token>)
juju grant-secret jaime-token jaime

# Configure provider and point api-token at the secret URI
juju config jaime provider=gemini
juju config jaime api-token="${SECRET_URI}"

# Or for OpenRouter
juju config jaime provider=openrouter
juju config jaime api-token="${SECRET_URI}"
```

For development only, a plain token string is also accepted:

```bash
juju config jaime api-token="<your-token>"
```

## Actions

```bash
juju run jaime/0 diagnose              # Basic principal info
juju run jaime/0 collect-context       # Collect and return context bundle
juju run jaime/0 generate-report       # Generate report for current open incident
juju run jaime/0 get-suggestion        # Get AI suggestion for current incident
juju run jaime/0 show-status           # Show monitoring state for all units
juju run jaime/0 reset                 # Clear all incidents and start fresh
juju run jaime/0 show-usage            # Show LLM API usage (tokens, cost...) per model
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
| `log-window-minutes` | `30` | How far back to collect logs |
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

Run the tests for each charm from its own directory:

```bash
cd charms/machine && python3 -m pytest tests/
cd charms/k8s     && python3 -m pytest tests/
```

## Kubernetes charm (jaime-k8s)

The k8s variant runs as a standalone pod and monitors other applications in
the same Juju model. Workload statuses come from the **Juju controller API**;
pod logs/events/metrics come from the **Kubernetes API** via the pod's
in-cluster service account (no `kubectl` binary).

The machine charm discovers its principal through a relation; the k8s charm
has no relation, so it needs read access to the model's controller API.

### Deploy

```bash
juju deploy jaime-k8s
```

### Grant read access to the Kubernetes API

All applications in a Juju model share one namespace, so the charm can reach
other pods there. Its default service account can only list pods; grant pod
log/event/metrics access once per model:

```bash
kubectl apply -f charms/k8s/jaime-k8s-rbac.yaml -n <model-name>
```

### Grant read access to the Juju controller API

Create a dedicated read-only user (a unit's own agent identity does not have
the `ModelRead` permission required by `Client.FullStatus`):

```bash
MODEL_NAME=<your-model>

# Create a new juju user with read access on the model
juju add-user jaime-observer
juju grant jaime-observer read ${MODEL_NAME}

# Set a password non-interactively
NEW_PASS=<your-password>
echo "$NEW_PASS" | juju change-user-password jaime-observer --no-prompt

# Pass the username and password (as a juju secret) to jaime-k8s
SECRET_URI=$(juju add-secret jaime-juju-api password="$NEW_PASS")
juju grant-secret jaime-juju-api ${MODEL_NAME}
juju config jaime-k8s juju-api-user=jaime-observer juju-api-password="${SECRET_URI}"
```

### Choose which applications to monitor

Monitoring is **opt-in**: an empty `watch-applications` list monitors nothing.

```bash
juju config jaime-k8s watch-applications=postgresql-k8s,mysql-k8s
```

### Actions

```bash
juju run jaime-k8s/0 show-status          # monitoring state
juju run jaime-k8s/0 generate-report      # report for the open incident
juju run jaime-k8s/0 get-suggestion       # AI diagnosis for the open incident
juju run jaime-k8s/0 show-usage           # Show LLM API usage (tokens, cost...) per model
juju run jaime-k8s/0 reset                # clear all incidents
```

### k8s-specific configuration

| Key | Default | Description |
|---|---|---|
| `watch-applications` | `""` | Comma-separated apps to monitor (empty = none) |
| `juju-api-user` | `""` | Juju user with read access on the model |
| `juju-api-password` | `""` | Password or Juju secret URI for `juju-api-user` |

The AI provider options (`mode`, `provider`, `model`, `api-token`) work the
same as the machine charm, as do `watch-statuses`, `failure-timeout-minutes`,
`cooldown-minutes`, `log-window-minutes`, `max-context-lines`,
`report-dir`, and `audit-log-path`.

## Design principle

Jaime should be boring, auditable, and safe.

It collects facts first, produces reports second, and only attempts changes in later phases with strict allowlists, dry-run support, and explicit operator intent.
