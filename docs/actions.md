# Actions

This document describes the Juju actions exposed by **Jaime — Juju AI Medic Engine**.

For phase-1, Jaime exposes only one action: `diagnose`.

The action should be safe, read-only, and suitable for early acceptance testing.

## `diagnose`

Collects and prints basic information about the related principal charm.

The initial MVP action should return JSON containing:

- principal application name
- principal unit name
- principal unit status
- principal charm version, if discoverable
- Jaime unit name
- timestamp

It should not:

- call an external AI provider
- remediate anything
- restart services
- modify files
- upload logs
- require provider credentials

## Example

```bash
juju run jaime/0 diagnose
```

Expected output shape:

```json
{
  "principal": {
    "application": "postgresql",
    "unit": "postgresql/0",
    "status": "active",
    "status_message": "",
    "charm_version": "14/stable or unknown"
  },
  "jaime": {
    "unit": "jaime/0",
    "mode": "observe"
  },
  "timestamp": "2026-06-21T15:30:00Z"
}
```

The exact `charm_version` value depends on what the charm can safely discover from local Juju context or hook tools. If it cannot be discovered reliably in phase-1, the action should return:

```json
"charm_version": "unknown"
```

## Behaviour

The action should:

1. Identify the related principal unit.
2. Read the principal unit state from local Juju context or hook tools where possible.
3. Attempt to determine the principal charm version.
4. Return a JSON object.
5. Write a structured JSONL audit event indicating that `diagnose` was run.

## Error handling

If the principal unit cannot be determined, the action should fail clearly.

Example output:

```json
{
  "error": "principal_unit_not_found",
  "message": "Jaime is not related to a principal unit or could not determine the principal from local context."
}
```

If the charm version cannot be determined, the action should not fail. It should return:

```json
"charm_version": "unknown"
```

## Acceptance criteria

The `diagnose` action is complete when:

- `juju run jaime/0 diagnose` returns valid JSON
- the JSON includes principal unit name and status
- the JSON includes principal charm version or `unknown`
- no host mutation occurs
- no AI provider is required
- one JSONL audit event is written for the action
