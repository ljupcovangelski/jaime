# AGENTS.md

This repository contains **Jaime — Juju AI Medic Engine**, a Juju machine subordinate charm for observing unhealthy principal charms, collecting diagnostics, and generating structured incident reports.

All agents must optimize for correctness, safety, and Juju charm conventions over speed.

## Product intent

Jaime is not a general chatbot. It is a local Juju-aware diagnostic and incident reporting charm.

Phase-1 MVP:

- machine subordinate charm
- observe-only by default
- monitor related principal unit status
- detect statuses such as `error` and `blocked`
- wait for `failure-timeout-minutes`
- collect compact logs and host diagnostics
- write structured JSONL audit logs
- optionally call Gemini or another provider to write a Markdown report
- no automatic remediation in the first implementation

## Global Engineering Principles

### How We Work

#### Task Ownership

All implementation tasks must be assigned to a single owner agent.

Agent responsibilities are defined in this file.

Examples:

```text
Owner: charm
Owner: python
Owner: test
Owner: docs
```

The owner is responsible for implementing the task and updating any related files such as `CHANGELOG.md`.

Other agents may review the work, but ownership should remain clear.

#### Commit Types

The following commit types are used throughout the project:

* `feature` — new functionality
* `bug` — defect fix
* `change` — refactoring, architecture changes, configuration changes, non-functional improvements
* `docs` — documentation-only changes

#### Commit Message Format

Commit messages should follow:

```text
[agent] type: description
```

Examples:

```text
[charm] feature: Add subordinate charm skeleton
[charm] change: Add principal status monitoring
[python] feature: Add JSONL audit logger
[python] bug: Fix cooldown logic
[test] feature: Add incident timeout tests
[docs] docs: Add configuration reference
```

Descriptions should be short, factual, and written in the imperative style.

#### Source of Truth

`ARCHITECTURE.md` defines the product roadmap and long-term direction.

`TASKS.md` contains the currently active implementation plan.

When a conflict exists, `ARCHITECTURE.md` takes precedence.

#### Other considerations

Assume that other agents and humans may edit the repository.
### Think Before Coding

Before implementing:

* State assumptions explicitly.
* If multiple interpretations exist, present them.
* If a simpler approach exists, explain it.
* If requirements are unclear, ask clarifying questions before implementing.

When unsure, ask.

A clarifying question is preferred over an incorrect implementation.

### Simplicity First

Implement the minimum solution that satisfies the requirement.

Avoid:

* speculative features
* premature abstractions
* extensibility that is not yet needed
* configuration that is not yet required

Prefer:

* working implementation first
* extraction and abstraction later

Ask:

"Would a senior engineer consider this overengineered?"

If yes, simplify.

### Surgical Changes

When modifying existing code:

* change only what is required
* avoid unrelated refactoring
* avoid formatting-only changes
* preserve existing style unless instructed otherwise

Remove only code made obsolete by your own changes.

### Goal-Driven Execution

Convert tasks into verifiable goals.

For multi-step work:

1. Define a small implementation plan.
2. Define how success will be verified.
3. Implement.
4. Verify.

Every task should end with a clear verification step.

### Edge Case Policy

Do not attempt to handle every possible environment or charm failure.

Handle the expected MVP cases:

- principal unit is healthy
- principal unit is `error` or `blocked`
- timeout has not elapsed
- timeout has elapsed
- AI provider is not configured
- log collection partially fails

For everything else:

- fail safely
- write a structured JSONL error event
- return a clear action/status message
- do not add complex recovery logic unless requested

## Safety rules

Agents must follow these rules:

1. Do not implement automatic remediation unless explicitly requested in a task.
2. Do not add arbitrary shell command execution.
3. Do not log AI provider tokens or Juju secrets.
4. Do not send full unlimited logs to an AI provider.
5. Always bound collected logs by time, lines, or bytes.
6. Prefer observe/report behaviour over mutate/fix behaviour.
7. All decisions and generated outputs must be auditable.
8. Every incident event should be written in structured JSONL.
9. The charm must work without an AI provider configured by producing a non-AI report.
10. Keep phase-1 focused on machine charms, not Kubernetes sidecars.

## Preferred repository structure

```text
.
├── README.md
├── AGENTS.md
├── architecture.md
├── tasks.md
├── charmcraft.yaml
├── metadata.yaml
├── config.yaml
├── actions.yaml
├── src/
│   ├── charm.py
│   └── jaime/
│       ├── collector.py
│       ├── incident.py
│       ├── logging.py
│       ├── principal.py
│       ├── report.py
│       ├── providers/
│       │   ├── base.py
│       │   └── gemini.py
│       └── utils.py
├── tests/
│   ├── unit/
│   └── integration/
└── docs/
```

## Agents

### plan

Use this agent for product decomposition, task ordering, scope control, and design review.

Responsibilities:

- keep the MVP small
- prevent premature remediation features
- maintain `tasks.md`
- update what is changed in `CHANGELOG.md`
- clarify acceptance criteria
- split work into small implementation steps

The planner should not write most implementation code.

### charm

Use this agent for Juju-specific implementation.

Responsibilities:

- `charmcraft.yaml`
- `metadata.yaml`
- `config.yaml`
- `actions.yaml`
- `src/charm.py`
- subordinate charm relation design
- Juju event handling
- Juju actions
- `update-status` monitoring logic
- unit status handling
- charm config and secrets integration

Rules:

- Jaime is a machine subordinate charm for phase-1.
- Do not design Kubernetes sidecar support yet.
- Do not talk directly to the Juju controller API unless explicitly required.
- Prefer Juju hook tools and local charm context.
- Keep observe mode as the default.
- Implement functionality through charm events and actions first.
- Avoid introducing background daemons, services, snaps, or plugin frameworks unless explicitly requested.
- Prefer:
  `action -> collector -> report` over
  `action -> framework -> plugin system -> collector -> report`
- Extract reusable modules only after the behaviour works end-to-end.

### python

Use this agent for reusable Python modules that are not Juju-specific.

Responsibilities:

- diagnostic collectors
  - Juju logs
  - journal logs
  - disk
  - memory
  - network
  - systemd

- incident lifecycle model
  - incident creation
  - incident state tracking
  - incident recovery

- report generation
  - JSONL audit logs
  - Markdown reports

- AI provider framework
  - provider abstraction
  - prompt construction
  - response parsing

- context processing
  - compaction
  - redaction
  - sanitization

- reusable utility modules

Rules:

- keep modules testable without Juju
- avoid hard-coding PostgreSQL-specific assumptions in generic code
- never leak secrets into logs, reports, prompts, or test fixtures
- Every AI interaction must be reproducible and auditable.
- Persist collected context before sending it to an AI provider.
- Reports should reference the stored incident context used to generate them.
- AI output must never be the only source of truth; raw collected evidence must always be retained.

### test

Use this agent for tests and acceptance scenarios.

Responsibilities:

- unit tests
- scenario tests where appropriate
- fake provider tests
- fake collector tests
- action behaviour tests
- integration test plan using Juju

The tester should verify:

- unhealthy status creates an incident
- timeout logic works
- duplicate reports are not generated repeatedly
- recovery closes the incident
- missing AI token still produces a useful non-AI report
- log limits are enforced

### security

Use this agent for reviewing risk.

Responsibilities:

- check secret handling
- check shell command usage
- check AI prompt contents for secret leakage
- check filesystem permissions
- check audit log safety
- check future remediation boundaries

For phase-1, the security reviewer should reject:

- arbitrary AI-generated commands
- automatic remediation
- unlimited log upload
- token logging
- broad sudo/root command helpers without allowlists

### docs

Use this agent for user-facing documentation.

Responsibilities:

- README updates
- architecture diagrams in text form
- Juju deployment instructions
- action examples
- troubleshooting notes
- acceptance test docs
