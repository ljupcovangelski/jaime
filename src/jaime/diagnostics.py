"""Diagnostics plan generation, validation, and persistence.

File format (version 2 — multi-app):

.. code-block:: json

    {
      "generated_at": "2026-07-15T...",
      "plans": {
        "postgresql": { "log_files": [...], "processes": [...], ... },
        "logrotated":  { "log_files": [...], ... }
      }
    }

The old single-app format (version 1) is automatically migrated on read.
"""

import json
import logging
import os
import datetime

logger = logging.getLogger(__name__)

MONITORING_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "log_files": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "priority": {"type": "string", "enum": ["high", "medium", "low"]},
                    "description": {"type": "string"},
                },
                "required": ["path", "priority", "description"],
            },
        },
        "processes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "expected_min_count": {"type": "integer"},
                    "expected_max_count": {"type": "integer"},
                    "parent": {"type": "string"},
                },
                "required": ["name"],
            },
        },
        "env_variables": {
            "type": "array",
            "items": {"type": "string"},
        },
        "network": {
            "type": "object",
            "properties": {
                "ports": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "port": {"type": "integer"},
                            "protocol": {"type": "string", "enum": ["tcp", "udp"]},
                        },
                        "required": ["port", "protocol"],
                    },
                },
            },
        },
        "systemd_units": {
            "type": "array",
            "items": {"type": "string"},
        },
        "health_commands": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "timeout_seconds": {"type": "integer"},
                },
                "required": ["command", "timeout_seconds"],
            },
        },
    },
    "required": ["log_files", "processes", "env_variables", "network"],
}


def validate_monitoring_plan(mp: dict) -> list[str]:
    """Validate a monitoring plan dict against the schema.

    Returns a list of error strings. An empty list means valid.
    """
    errors = []

    if not isinstance(mp, dict):
        return ["monitoring plan must be a JSON object"]

    if "log_files" in mp:
        if not isinstance(mp["log_files"], list):
            errors.append("'log_files' must be a list")
        else:
            for i, lf in enumerate(mp["log_files"]):
                if not isinstance(lf, dict):
                    errors.append(f"log_files[{i}] must be an object")
                    continue
                for f in ("path", "priority", "description"):
                    if f not in lf:
                        errors.append(f"log_files[{i}] missing '{f}'")
                if lf.get("priority") not in (None, "high", "medium", "low"):
                    errors.append(f"log_files[{i}] 'priority' must be 'high', 'medium', or 'low'")

    if "processes" in mp:
        if not isinstance(mp["processes"], list):
            errors.append("'processes' must be a list")
        else:
            for i, proc in enumerate(mp["processes"]):
                if not isinstance(proc, dict):
                    errors.append(f"processes[{i}] must be an object")
                    continue
                if "name" not in proc:
                    errors.append(f"processes[{i}] missing 'name'")

    if "env_variables" in mp:
        if not isinstance(mp["env_variables"], list):
            errors.append("'env_variables' must be a list")
        else:
            for i, ev in enumerate(mp["env_variables"]):
                if not isinstance(ev, str):
                    errors.append(f"env_variables[{i}] must be a string")

    if "network" in mp:
        net = mp["network"]
        if not isinstance(net, dict):
            errors.append("'network' must be an object")
        elif "ports" in net:
            if not isinstance(net["ports"], list):
                errors.append("'network.ports' must be a list")
            else:
                for i, p in enumerate(net["ports"]):
                    if not isinstance(p, dict):
                        errors.append(f"network.ports[{i}] must be an object")
                        continue
                    for f in ("port", "protocol"):
                        if f not in p:
                            errors.append(f"network.ports[{i}] missing '{f}'")

    if "systemd_units" in mp:
        if not isinstance(mp["systemd_units"], list):
            errors.append("'systemd_units' must be a list")
        else:
            for i, u in enumerate(mp["systemd_units"]):
                if not isinstance(u, str):
                    errors.append(f"systemd_units[{i}] must be a string")

    if "health_commands" in mp:
        if not isinstance(mp["health_commands"], list):
            errors.append("'health_commands' must be a list")
        else:
            for i, cmd in enumerate(mp["health_commands"]):
                if not isinstance(cmd, dict):
                    errors.append(f"health_commands[{i}] must be an object")
                    continue
                if "command" not in cmd:
                    errors.append(f"health_commands[{i}] missing 'command'")

    return errors


def build_prompt(app_name: str) -> str:
    """Build the prompt sent to the AI provider."""
    schema_json = json.dumps(MONITORING_PLAN_SCHEMA, indent=2)

    prompt = (
        "You are a diagnostic planning assistant for Juju charms running on Ubuntu 24.04.\n"
        f"\n"
        f"The charm name is: {app_name}\n"
        f"\n"
        f"Generate a monitoring plan for this charm's workload following this JSON schema:\n"
        f"\n"
        f"{schema_json}\n"
        f"\n"
        "Include:\n"
        "- Log files the charm or its workload typically writes (up to 5 items)\n"
        "- Systemd units the workload depends on\n"
        "- Processes the workload runs (include expected count ranges where known)\n"
        "- Environment variables the workload uses for configuration\n"
        "- Network ports the workload listens on\n"
        "- Health commands that can safely check the workload status\n"
        "\n"
        "Use the actual current UTC date and time for the 'generated_at' field.\n"
        "\n"
        "Respond with ONLY valid JSON matching the schema. "
        "Do not include markdown fences, explanations, or extra text. "
        "The response must be parseable as raw JSON."
    )
    return prompt


def make_empty_plan() -> dict:
    """Create a minimal empty monitoring plan dict."""
    return {
        "log_files": [],
        "processes": [],
        "env_variables": [],
        "network": {"ports": []},
        "systemd_units": [],
        "health_commands": [],
    }


# ---------------------------------------------------------------------------
# File persistence — version 2 (multi-app) format
# ---------------------------------------------------------------------------


def _migrate_v1_to_v2(data: dict) -> dict:
    """Convert a version-1 (single-app) file to version 2."""
    principal_name = data.get("principal_name", "unknown")
    monitoring_plan = data.get("monitoring_plan", make_empty_plan())
    return {
        "generated_at": data.get("generated_at", datetime.datetime.now(datetime.timezone.utc).isoformat()),
        "plans": {principal_name: monitoring_plan},
    }


def read_diagnostics_file(path: str) -> dict | None:
    """Read the diagnostics file. Returns None if missing.

    Automatically migrates version-1 (single-app) format to version 2
    (multi-app) on read.
    """
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    # Version 1 → version 2 migration
    if "principal_name" in data and "monitoring_plan" in data and "plans" not in data:
        data = _migrate_v1_to_v2(data)
        write_diagnostics_file(data, path)

    return data


def write_diagnostics_file(data: dict, path: str) -> str:
    """Persist diagnostics data to a JSON file.

    Accepts version-2 (multi-app) or version-1 (single-app) dicts.
    Version-1 dicts are migrated to version 2 before writing.
    Returns the file path written.
    """
    # Migrate v1 on write too, in case caller passes old format
    if "principal_name" in data and "monitoring_plan" in data and "plans" not in data:
        data = _migrate_v1_to_v2(data)

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    return path


def read_plan_for_app(app_name: str, path: str) -> dict:
    """Read the monitoring plan for a specific app.

    Returns a dict with a ``monitoring_plan`` key, compatible with
    ``collect_context()``.  Falls back to an empty plan if the app
    has no plan yet or the file is missing.
    """
    data = read_diagnostics_file(path)
    if data is None:
        return {"monitoring_plan": make_empty_plan()}

    plans = data.get("plans", {})
    mp = plans.get(app_name)
    if mp is None:
        return {"monitoring_plan": make_empty_plan()}

    return {"monitoring_plan": mp}


def ensure_plan_for_app(
    app_name: str,
    path: str,
    provider: object | None = None,
) -> dict:
    """Ensure a monitoring plan exists for *app_name*.

    If the plan already exists in the file it is returned immediately.
    Otherwise the AI *provider* (if available) is called to generate one.
    On failure or when no provider is configured an empty plan is stored.

    Returns the plan dict (suitable for passing to ``collect_context()``).
    """
    data = read_diagnostics_file(path)
    if data is None:
        data = {
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "plans": {},
        }

    plans = data.get("plans", {})
    if app_name in plans:
        return {"monitoring_plan": plans[app_name]}

    mp = _generate_plan_for_app(app_name, provider)
    plans[app_name] = mp
    data["plans"] = plans
    data["generated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    write_diagnostics_file(data, path)

    return {"monitoring_plan": mp}


def _generate_plan_for_app(app_name: str, provider: object | None) -> dict:
    """Call the AI provider to generate a monitoring plan for *app_name*.

    Returns a monitoring plan dict. Falls back to empty plan when the
    provider is None, the API call fails, or validation fails.
    """
    if provider is None:
        logger.info("no AI provider configured — empty plan for '%s'", app_name)
        return make_empty_plan()

    logger.info("generating monitoring plan for '%s' via %s", app_name, provider.__class__.__name__)
    try:
        prompt = build_prompt(app_name)
        response = provider.generate(prompt)
        logger.info("Monitoring plan generated successfully for '%s'", app_name)
        logger.debug("Monitoring plan AI response for %s:\n%s", app_name, response)

        stripped = response.strip()
        if stripped.startswith("```"):
            lines = stripped.splitlines()
            inner = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
            stripped = inner.strip()

        if not stripped:
            raise ValueError("AI provider returned an empty response")

        mp = json.loads(stripped)
    except Exception as e:
        logger.error("Monitoring plan generation for '%s' failed: %s — falling back to empty plan",
                     app_name, e)
        return make_empty_plan()

    errors = validate_monitoring_plan(mp)
    if errors:
        logger.error("AI generated invalid monitoring plan for '%s': %s — falling back to empty plan",
                     app_name, errors)
        return make_empty_plan()

    return mp
