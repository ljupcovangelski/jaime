"""Context collection for Jaime incidents.

Collects bounded diagnostics from the local machine without modifying
any state. All collection is read-only and bounded by time and line count.
"""

import datetime
import logging
import os
import re
import subprocess

logger = logging.getLogger(__name__)

_DEFAULT_LOG_WINDOW_MINUTES = 30
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


def _tail_lines(text: str, max_lines: int) -> list[str]:
    lines = text.splitlines()
    return lines[-max_lines:] if len(lines) > max_lines else lines


def collect_unit_logs(
    unit_name: str,
    log_window_minutes: int = _DEFAULT_LOG_WINDOW_MINUTES,
    max_lines: int = _DEFAULT_MAX_LINES,
) -> list[str]:
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

    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        minutes=log_window_minutes
    )

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

    return _tail_lines("\n".join(recent), max_lines)


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


# ---------------------------------------------------------------------------
# Main collection entry point
# ---------------------------------------------------------------------------


def collect_context(
    unit_name: str,
    log_window_minutes: int = _DEFAULT_LOG_WINDOW_MINUTES,
    max_lines: int = _DEFAULT_MAX_LINES,
    diagnostics_plan: dict | None = None,
) -> dict:
    """Collect all context for an incident.

    If ``diagnostics_plan`` is provided with non-empty sections, collection is
    driven by the plan (only what the plan specifies).  If a section is empty
    or ``diagnostics_plan`` is None, a broad fallback is used for that section
    (e.g. ``ps aux`` for processes, ``ss -tlnp`` for ports).

    Background context (unit logs, disk usage, memory) is always collected.
    """
    context = {
        "unit_logs": collect_unit_logs(unit_name, log_window_minutes, max_lines),
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
