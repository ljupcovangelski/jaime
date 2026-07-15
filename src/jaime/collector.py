"""Context collection for Jaime incidents.

Collects bounded diagnostics from the local machine without modifying
any state. All collection is read-only and bounded by time and line count.
"""

import datetime
import json
import logging
import os
import re
import sqlite3
import subprocess

logger = logging.getLogger(__name__)

_DEFAULT_LOG_WINDOW_MINUTES = 120
_DEFAULT_MAX_LINES = 500
_JUJU_LOG_DIR = "/var/log/juju"


def _run(cmd: list[str], timeout: int = 10) -> str:
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
        )
        return result.stdout
    except Exception as e:
        logger.debug("collection command %s failed: %s", cmd, e)
        return ""


def collect_tracing_events(
    unit_name: str,
    from_time: datetime.datetime | None = None,
    max_events: int = 50,
    buffer_minutes: int = 5,
) -> list[dict]:
    """Read recent Ops framework events from the principal unit's tracing DB.

    The tracing DB (``.tracing-data.db``) is written by the Ops framework's
    built-in OpenTelemetry tracing layer. It only exists for charms that use
    the Ops framework with tracing enabled. Returns an empty list if the file
    is absent, unreadable, or not an Ops tracing DB.

    Each returned dict has:
      - ``timestamp``: ISO 8601 UTC
      - ``event``: Ops event name (e.g. ``UpdateStatusEvent``)
      - ``kind``: hook kind (e.g. ``update_status``)
      - ``exception_type``: exception class name if the hook failed, else ``""``
      - ``exception_message``: first line of exception message, else ``""``
    """
    tag = "unit-" + unit_name.replace("/", "-")
    db_path = f"/var/lib/juju/agents/{tag}/charm/.tracing-data.db"

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2)
    except Exception as e:
        logger.debug("tracing DB not accessible for %s: %s", unit_name, e)
        return []

    if from_time is not None:
        from_time = from_time - datetime.timedelta(minutes=buffer_minutes)

    events = []
    try:
        rows = conn.execute(
            "SELECT data FROM tracing ORDER BY id DESC LIMIT 500"
        ).fetchall()

        for (data,) in rows:
            try:
                payload = json.loads(data)
            except Exception:
                continue

            for rs in payload.get("resourceSpans", []):
                for ss in rs.get("scopeSpans", []):
                    for span in ss.get("spans", []):
                        if span.get("name") != "ops.main":
                            continue

                        ts_ns = int(span.get("startTimeUnixNano", 0))
                        ts = datetime.datetime.fromtimestamp(
                            ts_ns / 1e9, tz=datetime.timezone.utc
                        )

                        if from_time and ts < from_time:
                            continue

                        for evt in span.get("events", []):
                            evt_name = evt.get("name", "")
                            if evt_name in (
                                "PreCommitEvent", "CommitEvent",
                                "CollectAppStatusEvent", "CollectUnitStatusEvent",
                                "UpdateStatusEvent",
                            ):
                                continue

                            attrs = {
                                a["key"]: list(a["value"].values())[0]
                                for a in evt.get("attributes", [])
                            }

                            if evt_name == "exception":
                                # Attach exception to the previous event if any
                                if events:
                                    events[-1]["exception_type"] = attrs.get(
                                        "exception.type", ""
                                    )
                                    msg = attrs.get("exception.message", "")
                                    events[-1]["exception_message"] = msg.splitlines()[0] if msg else ""
                                continue

                            events.append({
                                "timestamp": ts.isoformat(),
                                "event": evt_name,
                                "kind": attrs.get("kind", ""),
                                "exception_type": "",
                                "exception_message": "",
                            })

        conn.close()
    except Exception as e:
        logger.debug("could not read tracing DB for %s: %s", unit_name, e)
        return []

    # Sort ascending by timestamp, return most recent max_events
    events.sort(key=lambda e: e["timestamp"])
    return events[-max_events:]

def _tail_lines(text: str, max_lines: int) -> list[str]:
    lines = text.splitlines()
    return lines[-max_lines:] if len(lines) > max_lines else lines


def collect_unit_logs(
    unit_name: str,
    log_window_minutes: int = _DEFAULT_LOG_WINDOW_MINUTES,
    max_lines: int = _DEFAULT_MAX_LINES,
    from_time: datetime.datetime | None = None,
    buffer_minutes: int = 5,
    context_window: int = 10,
) -> list[str]:
    """Read recent lines from the principal unit's Juju log file.

    The log window is anchored to ``from_time`` when provided (typically the
    incident's ``first_seen`` timestamp).  Lines before
    ``from_time - buffer_minutes`` are excluded.  ``log_window_minutes`` still
    acts as a hard cap so very old incidents don't pull unbounded history.

    When ``from_time`` is None the window falls back to
    ``now - log_window_minutes`` (the original behaviour).

    Lines are filtered to include only those matching ``(error|warning)``
    (case-insensitive).  All matching lines are included, plus a context
    window of ``context_window`` lines before and after the **last**
    chronological match.  If no matches are found, all time-bounded lines
    are returned as a fallback.
    """
    tag = "unit-" + unit_name.replace("/", "-")
    log_path = os.path.join(_JUJU_LOG_DIR, f"{tag}.log")

    try:
        with open(log_path) as f:
            raw_lines = f.readlines()
    except FileNotFoundError:
        logger.debug("log file not found: %s", log_path)
        return []
    except Exception as e:
        logger.debug("could not read %s: %s", log_path, e)
        return []

    now = datetime.datetime.now(datetime.timezone.utc)
    earliest_allowed = now - datetime.timedelta(minutes=log_window_minutes)

    if from_time is not None:
        cutoff = from_time - datetime.timedelta(minutes=buffer_minutes)
    else:
        cutoff = earliest_allowed

    recent = []
    for line in raw_lines:
        try:
            ts_str = line[:19]
            ts = datetime.datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=datetime.timezone.utc
            )
            if ts >= cutoff:
                recent.append(line.rstrip())
        except ValueError:
            if recent:
                recent.append(line.rstrip())

    # Find indices of lines where the log level is ERROR or WARNING
    matched_indices = [
        i for i, line in enumerate(recent)
        if re.search(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} (ERROR|WARNING)\s", line)
    ]

    if not matched_indices:
        return _tail_lines("\n".join(recent), max_lines)

    # Build set of indices to include: all matched lines + context around last
    include_indices = set(matched_indices)
    last_idx = matched_indices[-1]
    window_start = max(0, last_idx - context_window)
    window_end = min(len(recent) - 1, last_idx + context_window)
    for j in range(window_start, window_end + 1):
        include_indices.add(j)

    result = [recent[i] for i in sorted(include_indices)]
    return result[-max_lines:] if len(result) > max_lines else result


def collect_systemd_failed() -> list[str]:
    output = _run(["systemctl", "--failed", "--no-legend", "--plain"])
    lines = [l.strip() for l in output.splitlines() if l.strip()]
    return lines


def collect_disk_usage() -> list[str]:
    output = _run(["df", "-h", "--output=source,size,used,avail,pcent,target"])
    return [l.rstrip() for l in output.splitlines() if l.strip()]


def collect_memory_summary() -> list[str]:
    output = _run(["free", "-h"])
    return [l.rstrip() for l in output.splitlines() if l.strip()]


# ---------------------------------------------------------------------------
# Plan-driven collection helpers
# ---------------------------------------------------------------------------


def _collect_log_files(plan_log_files: list[dict], max_lines: int) -> list[dict]:
    results = []
    for lf in plan_log_files:
        path = lf.get("path", "")
        priority = lf.get("priority", "medium")
        description = lf.get("description", "")
        try:
            with open(path) as f:
                lines = _tail_lines(f.read(), max_lines)
            results.append({
                "path": path,
                "priority": priority,
                "description": description,
                "status": "available",
                "lines": lines,
            })
        except FileNotFoundError:
            results.append({
                "path": path,
                "priority": priority,
                "description": description,
                "status": "not_found",
                "lines": [],
            })
        except Exception as e:
            logger.debug("could not read log file %s: %s", path, e)
            results.append({
                "path": path,
                "priority": priority,
                "description": description,
                "status": "error",
                "lines": [],
            })
    return results


def _collect_processes(plan_processes: list[dict]) -> list[dict]:
    results = []
    for proc in plan_processes:
        name = proc.get("name", "")
        output = _run(["pgrep", "-f", name])
        count = len([l for l in output.splitlines() if l.strip()]) if output else 0
        expected_min = proc.get("expected_min_count", 1)
        expected_max = proc.get("expected_max_count", 1)
        if count < expected_min:
            status = "too_few"
        elif count > expected_max:
            status = "too_many"
        else:
            status = "ok"
        results.append({
            "name": name,
            "expected_min_count": expected_min,
            "expected_max_count": expected_max,
            "running_count": count,
            "status": status,
        })
    return results


def _collect_systemd_units(plan_units: list[str]) -> list[dict]:
    results = []
    for unit in plan_units:
        output = _run(["systemctl", "is-active", unit])
        state = output.strip()
        results.append({
            "unit": unit,
            "status": state if state else "unknown",
        })
    return results


def _collect_network_ports(plan_ports: list[dict]) -> list[dict]:
    output = _run(["ss", "-tlnp"])
    results = []
    for port_def in plan_ports:
        port = port_def.get("port")
        protocol = port_def.get("protocol", "tcp")
        listening = str(port) in output
        results.append({
            "port": port,
            "protocol": protocol,
            "status": "listening" if listening else "not_listening",
        })
    return results


def _collect_env_variables(plan_vars: list[str]) -> list[dict]:
    results = []
    for var in plan_vars:
        value = os.environ.get(var)
        results.append({
            "name": var,
            "value": value if value is not None else "",
            "status": "set" if value is not None else "unset",
        })
    return results


# ---------------------------------------------------------------------------
# Broad fallback collection helpers (used when no plan or empty plan)
# ---------------------------------------------------------------------------


def _collect_broad_processes(max_lines: int = 100) -> list[str]:
    output = _run(["ps", "aux"])
    return _tail_lines(output, max_lines)


def _collect_broad_ports() -> list[str]:
    output = _run(["ss", "-tlnp"])
    return [l.rstrip() for l in output.splitlines() if l.strip()]





def collect_charm_config(unit_name: str) -> dict:
    """Read the principal charm's config.yaml and actions.yaml.

    Returns a dict with keys ``config_yaml`` and ``actions_yaml`` containing
    the raw file content, or ``""`` if the file is missing/unreadable.
    """
    tag = "unit-" + unit_name.replace("/", "-")
    charm_dir = f"/var/lib/juju/agents/{tag}/charm"
    result = {}
    for name in ("config.yaml", "actions.yaml"):
        path = os.path.join(charm_dir, name)
        try:
            with open(path) as f:
                result[name.replace(".yaml", "_yaml")] = f.read()
        except Exception as e:
            logger.debug("could not read %s for %s: %s", path, unit_name, e)
            result[name.replace(".yaml", "_yaml")] = ""
    return result


# ---------------------------------------------------------------------------
# Main collection entry point
# ---------------------------------------------------------------------------


def collect_context(
    unit_name: str,
    log_window_minutes: int = _DEFAULT_LOG_WINDOW_MINUTES,
    max_lines: int = _DEFAULT_MAX_LINES,
    diagnostics_plan: dict | None = None,
    from_time: datetime.datetime | None = None,
    buffer_minutes: int = 5,
) -> dict:
    """Collect all context for an incident.

    ``from_time`` should be set to the incident's ``first_seen`` datetime so
    that unit logs are anchored to the start of the incident rather than the
    current time, avoiding noise from unrelated prior events.

    If ``diagnostics_plan`` is provided with non-empty sections, collection is
    driven by the plan (only what the plan specifies).  If a section is empty
    or ``diagnostics_plan`` is None, a broad fallback is used for that section.

    Background context (unit logs, disk usage, memory) is always collected.

    Background context (unit logs, disk usage, memory) is always collected.
    """
    context = {
        "unit_logs": collect_unit_logs(
            unit_name, log_window_minutes, max_lines,
            from_time=from_time, buffer_minutes=buffer_minutes,
        ),
        "tracing_events": collect_tracing_events(
            unit_name, from_time=from_time, buffer_minutes=buffer_minutes,
        ),
        "charm_config": collect_charm_config(unit_name),
        "disk_usage": collect_disk_usage(),
        "memory_summary": collect_memory_summary(),
        "collected_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }

    plan_results = {}

    if diagnostics_plan is None:
        plan_results["processes"] = {
            "type": "broad",
            "lines": _collect_broad_processes(max_lines),
        }
        plan_results["network_ports"] = {
            "type": "broad",
            "lines": _collect_broad_ports(),
        }
        context["systemd_failed"] = collect_systemd_failed()
    else:
        mp = diagnostics_plan.get("monitoring_plan", {})

        log_files = mp.get("log_files", [])
        if log_files:
            plan_results["log_files"] = {
                "type": "plan",
                "items": _collect_log_files(log_files, max_lines),
            }

        processes = mp.get("processes", [])
        if processes:
            plan_results["processes"] = {
                "type": "plan",
                "items": _collect_processes(processes),
            }
        else:
            plan_results["processes"] = {
                "type": "broad",
                "lines": _collect_broad_processes(max_lines),
            }

        systemd_units = mp.get("systemd_units", [])
        if systemd_units:
            plan_results["systemd_units"] = {
                "type": "plan",
                "items": _collect_systemd_units(systemd_units),
            }
        else:
            plan_results["systemd_units"] = {
                "type": "broad",
                "lines": collect_systemd_failed(),
            }

        network = mp.get("network", {})
        ports = network.get("ports", []) if isinstance(network, dict) else []
        if ports:
            plan_results["network_ports"] = {
                "type": "plan",
                "items": _collect_network_ports(ports),
            }
        else:
            plan_results["network_ports"] = {
                "type": "broad",
                "lines": _collect_broad_ports(),
            }

        env_variables = mp.get("env_variables", [])
        if env_variables:
            plan_results["env_variables"] = {
                "type": "plan",
                "items": _collect_env_variables(env_variables),
            }

    context["plan_results"] = plan_results
    return context
