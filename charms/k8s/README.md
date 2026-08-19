Jaime k8s is a Juju **Kubernetes standalone** charm that runs as its own pod
and monitors other applications in the same Juju model. It detects unhealthy
workload statuses, collects bounded diagnostic context from the pod, and
writes structured incident reports. Optionally, it calls an AI provider
(Gemini or OpenRouter) to produce a diagnosis suggestion.

Workload statuses come from the **Juju controller API**; pod logs/events/metrics come from the **Kubernetes API** via the pod's in-cluster service account

## Quickstart

```bash
juju deploy jaime-k8s
```

### Grant read access to the Kubernetes API

All applications in a Juju model share one namespace, so the charm can reach
other pods there. Its default service account can only list pods; grant pod
log/event/metrics access once per model:

```bash
kubectl apply -f charm-jaime-k8s-<revision>/jaime-k8s-rbac.yaml -n <model-name>
```

### Grant read access to the Juju controller API

A unit's own agent identity does not have the `ModelRead` permission required
by `Client.FullStatus`, so create a dedicated read-only user:

```bash
MODEL_NAME=<your-model>

juju add-user jaime-observer
juju grant jaime-observer read ${MODEL_NAME}

# Set a password
NEW_PASS=<your-password>
echo "$NEW_PASS" | juju change-user-password jaime-observer --no-prompt

# Pass the username and password (as a Juju secret) to jaime-k8s
SECRET_URI=$(juju add-secret jaime-juju-api password="$NEW_PASS")
juju grant-secret jaime-juju-api ${MODEL_NAME}
juju config jaime-k8s juju-api-user=jaime-observer juju-api-password="${SECRET_URI}"
```

### Choose which applications to monitor

Monitoring is opt-in: an empty `watch-applications` list monitors nothing.

```bash
juju config jaime-k8s watch-applications=postgresql-k8s,mysql-k8s
```

## Actions

```bash
juju run jaime-k8s/0 show-status          # monitoring state
juju run jaime-k8s/0 generate-report      # report for the open incident
juju run jaime-k8s/0 get-suggestion       # AI diagnosis for the open incident
juju run jaime-k8s/0 show-usage           # LLM API usage (tokens, cost) per model
juju run jaime-k8s/0 reset                # clear all incidents
```

## Configuration

| Key | Default | Description |
|---|---|---|
| `watch-applications` | `""` | Comma-separated apps to monitor (empty = none) |
| `juju-api-user` | `""` | Juju user with read access on the model |
| `juju-api-password` | `""` | Password or Juju secret URI for `juju-api-user` |
| `mode` | `observe` | `observe`, `suggest`, or `act` |
| `provider` | `none` | AI provider (`none`, `gemini`, or `openrouter`) |
| `api-token` | `""` | Juju secret reference for the AI token |

The usual options also apply (`watch-statuses`, `failure-timeout-minutes`,
`cooldown-minutes`, `log-window-minutes`, `max-context-lines`,
`report-dir`, `audit-log-path`).

## Design principle

Jaime should be boring, auditable, and safe: it collects facts first, produces
reports second, and only attempts changes with explicit operator intent.
