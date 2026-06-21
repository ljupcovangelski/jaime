# Configuration

This document describes the Juju charm configuration options for **Jaime — Juju AI Medic Engine**.

Jaime is currently designed as an **observe-first machine subordinate charm**. The phase-1 MVP should detect unhealthy principal charm states, collect local diagnostic context, and generate structured incident information. It should not remediate or mutate the host unless a future task explicitly adds that behaviour.

## Summary

| Config | Type | Default | Description |
|---|---:|---|---|
| `mode` | string | `observe` | Controls whether Jaime only observes or may later act. For phase-1, only `observe` is implemented. |
| `provider` | string | `none` | AI provider to use for optional report generation. For phase-1 this may be `none` or a stub. |
| `model` | string | empty | AI model name used by the selected provider. Not required for non-AI reports. |
| `api-token` | secret | empty | Juju secret containing the provider API token. Must never be logged. |
| `watch-statuses` | string | `error,blocked` | Comma-separated principal unit statuses that should open an incident. |
| `failure-timeout-minutes` | int | `5` | How long a watched status must persist before a report is generated. |
| `cooldown-minutes` | int | `30` | Minimum time before generating another report for the same unresolved incident. |
| `log-window-minutes` | int | `30` | How far back Jaime should collect recent logs. |
| `max-context-lines` | int | `500` | Maximum number of log/context lines to include in a report context bundle. |
| `report-dir` | string | `/var/log/jaime/reports` | Directory where Markdown or JSON report artifacts are written. |
| `audit-log-path` | string | `/var/log/jaime/events.jsonl` | Path to the structured JSONL audit log. |

## `mode`

Controls Jaime's operating mode.

Allowed values:

- `observe`
- `act` — reserved for a later phase

Default:

```yaml
mode: observe
```

Phase-1 behaviour:

- `observe` only
- no remediation
- no host mutation
- collect state
- write structured logs
- generate diagnostic output

`act` should be documented but not implemented until remediation has explicit safety rules, allowlists, tests, and acceptance criteria.

## `provider`

Selects the AI provider for optional report generation.

Suggested values:

- `none`
- `gemini`
- `openai`

Default:

```yaml
provider: none
```

Phase-1 should work without any AI provider configured. In that case Jaime should still produce a non-AI diagnostic report from local state and logs.

## `model`

The model name to use with the configured provider.

Example:

```yaml
model: gemini-2.5-flash
```

For phase-1 this may be unused if `provider=none`.

## `api-token`

A Juju secret reference containing the AI provider token.

The token must never be written to:

- Juju logs
- JSONL audit logs
- Markdown reports
- prompts saved for debugging
- unit test fixtures

Example intent:

```bash
juju add-secret jaime-ai-token token=<TOKEN>
juju grant-secret jaime-ai-token jaime
juju config jaime api-token=<SECRET-ID-OR-REFERENCE>
```

Exact secret wiring may change during implementation.

## `watch-statuses`

Comma-separated list of principal unit statuses that Jaime should monitor.

Default:

```yaml
watch-statuses: error,blocked
```

Recommended phase-1 values:

```yaml
watch-statuses: error,blocked
```

Later values may include:

```yaml
watch-statuses: error,blocked,waiting,maintenance,unknown
```

For phase-1, `waiting` and `maintenance` should usually be ignored because they can be normal during deployment, relation setup, upgrades, or restarts.

## `failure-timeout-minutes`

How long the principal unit must remain in a watched status before Jaime generates a report.

Default:

```yaml
failure-timeout-minutes: 5
```

Example behaviour:

1. Principal becomes `error`.
2. Jaime records an `incident_started` event.
3. If the principal recovers before the timeout, Jaime records `incident_recovered`.
4. If the principal is still unhealthy after the timeout, Jaime collects diagnostic context and generates a report.

## `cooldown-minutes`

Prevents duplicate reports for the same unresolved incident.

Default:

```yaml
cooldown-minutes: 30
```

Example:

If `update-status` runs every 5 minutes, Jaime should not call the AI provider or regenerate a full report every time while the same incident remains unresolved.

## `log-window-minutes`

How far back recent logs should be collected.

Default:

```yaml
log-window-minutes: 30
```

This should be used when collecting logs from sources such as:

- Juju unit logs
- systemd journal
- principal workload service logs
- local host diagnostics

## `max-context-lines`

Maximum number of lines to include in the compact context bundle.

Default:

```yaml
max-context-lines: 500
```

This protects against:

- excessive report size
- excessive AI provider cost
- context-window overflow
- leaking too much unrelated log data

## `report-dir`

Directory where report artifacts are written.

Default:

```yaml
report-dir: /var/log/jaime/reports
```

Reports should be written with predictable incident IDs, for example:

```text
/var/log/jaime/reports/incident-20260621-153000-postgresql-0.md
/var/log/jaime/reports/incident-20260621-153000-postgresql-0.context.json
```

## `audit-log-path`

Path to the structured JSONL audit log.

Default:

```yaml
audit-log-path: /var/log/jaime/events.jsonl
```

Each line should be one JSON object.

Example event:

```json
{"timestamp":"2026-06-21T15:30:00Z","event":"incident_started","principal_unit":"postgresql/0","status":"error","message":"principal unit entered watched status"}
```

## Phase-1 recommended config

```yaml
mode: observe
provider: none
watch-statuses: error,blocked
failure-timeout-minutes: 5
cooldown-minutes: 30
log-window-minutes: 30
max-context-lines: 500
report-dir: /var/log/jaime/reports
audit-log-path: /var/log/jaime/events.jsonl
```
