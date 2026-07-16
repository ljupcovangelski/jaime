"""Markdown report generation for Jaime incidents.

A report captures the machine context at the time of the incident:
logs, systemd state, disk, memory. It is the input provided to the LLM
in suggest/act mode. It does not contain LLM output.
"""

import datetime
import logging
import os
import yaml

logger = logging.getLogger(__name__)

_DEFAULT_REPORT_DIR = "/var/log/jaime/reports"


def _append(lines: list[str], *chunks: list[str]) -> None:
    for chunk in chunks:
        lines.extend(chunk)
        lines.append("")


def generate_report(
    incident_id: str,
    unit_name: str,
    workload: str,
    first_seen: str,
    context: dict,
    report_dir: str = "",
) -> str:
    """Generate a Markdown context report and write it to disk.

    Falls back to _DEFAULT_REPORT_DIR if report_dir is empty.
    Returns the path of the written report file.
    """
    report_dir = report_dir or _DEFAULT_REPORT_DIR
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    lines = []

    _append(lines, [
        "# Incident Report",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Incident ID | `{incident_id}` |",
        f"| Unit | `{unit_name}` |",
        f"| Workload status | `{workload}` |",
        f"| First seen | `{first_seen}` |",
        f"| Report generated | `{now}` |",
    ])

    plan_results = context.get("plan_results", {})

    _append_section_network(lines, plan_results)
    _append_section_ss_connections(lines, context)
    _append_section_firewall_rules(lines, context)
    _append_section_log_files(lines, plan_results)
    _append_section_processes(lines, plan_results)
    _append_section_systemd(lines, plan_results, context)
    _append_section_env(lines, plan_results)
    _append_section_health_commands(lines, plan_results)

    # Background sections
    _append_section_charm_config(lines, context)
    _append_section_disk(lines, context)
    _append_section_memory(lines, context)
    # _append_section_tracing(lines, context)
    _append_section_logs(lines, context)

    content = "\n".join(lines)

    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(report_dir, f"{incident_id}.md")
    with open(report_path, "w") as f:
        f.write(content)

    logger.debug("report written to %s", report_path)
    return report_path


# ---------------------------------------------------------------------------
# Per-section append helpers
# ---------------------------------------------------------------------------


def _append_section_log_files(lines: list[str], plan_results: dict) -> None:
    section = plan_results.get("log_files")
    if not section:
        return

    if section["type"] == "plan":
        _append(lines, ["## Log files"])
        for item in section.get("items", []):
            path = item.get("path", "")
            priority = item.get("priority", "")
            status = item.get("status", "")
            desc = item.get("description", "")
            tag = f" ({priority})" if priority else ""
            label = f"{path}{tag} — _{desc}_" if desc else f"{path}{tag}"
            if status == "available":
                _append(lines, [f"- {label} ✓"])
                item_lines = item.get("lines", [])
                if item_lines:
                    _append(lines, ["```", *item_lines, "```"])
            else:
                _append(lines, [f"- {label} ✗ ({status})"])


def _append_section_processes(lines: list[str], plan_results: dict) -> None:
    section = plan_results.get("processes")
    if not section:
        return

    if section["type"] == "plan":
        _append(lines, ["## Processes"])
        for item in section.get("items", []):
            name = item.get("name", "")
            count = item.get("running_count", 0)
            expected_min = item.get("expected_min_count", 1)
            expected_max = item.get("expected_max_count", 1)
            status = item.get("status", "")
            summary = f"{count} running (expected {expected_min}-{expected_max})"
            icon = "✓" if status == "ok" else "✗"
            _append(lines, [f"- **{name}**: {summary} {icon}"])
    else:
        raw_lines = section.get("lines", [])
        if raw_lines:
            _append(lines, ["## Processes", "```", *raw_lines, "```"])


def _append_section_systemd(lines: list[str], plan_results: dict, context: dict) -> None:
    section = plan_results.get("systemd_units")

    if section and section["type"] == "plan":
        _append(lines, ["## Systemd units"])
        for item in section.get("items", []):
            unit = item.get("unit", "")
            status = item.get("status", "")
            icon = "✓" if status == "active" else "✗"
            _append(lines, [f"- `{unit}` → {status} {icon}"])
    else:
        systemd_failed = context.get("systemd_failed", [])
        if not section and not systemd_failed:
            return
        _append(lines, ["## Failed systemd units"])
        if systemd_failed:
            for unit in systemd_failed:
                _append(lines, [f"- `{unit}`"])
        elif section and section["type"] == "broad":
            broad_lines = section.get("lines", [])
            if broad_lines:
                for unit_line in broad_lines:
                    _append(lines, [f"- `{unit_line}`"])
            else:
                _append(lines, ["_None detected._"])
        else:
            _append(lines, ["_None detected._"])


def _append_section_network(lines: list[str], plan_results: dict) -> None:
    section = plan_results.get("network_ports")
    if not section:
        return

    if section["type"] == "plan":
        _append(lines, ["## Network ports"])
        for item in section.get("items", []):
            port = item.get("port", "")
            protocol = item.get("protocol", "tcp")
            status = item.get("status", "")
            icon = "✓" if status == "listening" else "✗"
            _append(lines, [f"- `{port}/{protocol}` → {status} {icon}"])
    else:
        raw_lines = section.get("lines", [])
        if raw_lines:
            _append(lines, ["## Network ports", "```", *raw_lines, "```"])


def _append_section_env(lines: list[str], plan_results: dict) -> None:
    section = plan_results.get("env_variables")
    if not section or section["type"] != "plan":
        return

    _append(lines, ["## Environment variables"])
    for item in section.get("items", []):
        name = item.get("name", "")
        value = item.get("value", "")
        status = item.get("status", "")
        if status == "set":
            _append(lines, [f"- `{name}` = `{value}` ✓"])
        else:
            _append(lines, [f"- `{name}` — unset ✗"])


def _append_section_health_commands(lines: list[str], plan_results: dict) -> None:
    section = plan_results.get("health_commands")
    if not section or section["type"] != "plan":
        return

    _append(lines, ["## Health commands"])
    for item in section.get("items", []):
        command = item.get("command", "")
        returncode = item.get("returncode", 0)
        stdout = item.get("stdout", "")
        stderr = item.get("stderr", "")
        icon = "✓" if returncode == 0 else "✗"
        _append(lines, [f"- `$ {command}` → exit {returncode} {icon}"])
        if stdout:
            _append(lines, ["  ```", *stdout.splitlines(), "  ```"])
        if stderr:
            _append(lines, ["  ```", *stderr.splitlines(), "  ```"])


def _append_section_charm_config(lines: list[str], context: dict) -> None:
    charm_config = context.get("charm_config", {})
    config_yaml = charm_config.get("config_yaml", "")
    if not config_yaml:
        return

    try:
        parsed = yaml.safe_load(config_yaml)
        options = (parsed or {}).get("options", {})
    except Exception:
        options = {}

    if not options:
        return

    _append(lines, ["## Charm config"])

    for key, opt in sorted(options.items()):
        default = opt.get("default", "")
        _append(lines, [f"- `{key}`: `{default}`"])


def _append_section_disk(lines: list[str], context: dict) -> None:
    disk = context.get("disk_usage", [])
    _append(lines, ["## Disk usage"])
    if disk:
        _append(lines, ["```", *disk, "```"])
    else:
        _append(lines, ["_Not available._"])


def _append_section_memory(lines: list[str], context: dict) -> None:
    memory = context.get("memory_summary", [])
    _append(lines, ["## Memory"])
    if memory:
        _append(lines, ["```", *memory, "```"])
    else:
        _append(lines, ["_Not available._"])


def _append_section_logs(lines: list[str], context: dict) -> None:
    unit_logs = context.get("unit_logs", [])
    _append(lines, ["## Recent unit logs"])
    _append(lines, ["_Showing only lines matching `error` or `warning` (case-insensitive), with a context window around the last match._"])
    _append(lines, ["_Logs are in chronological order._"])
    if unit_logs:
        _append(lines, ["```", *unit_logs, "```"])
    else:
        _append(lines, ["_No recent logs found._"])


def _append_section_tracing(lines: list[str], context: dict) -> None:
    events = context.get("tracing_events", [])
    if not events:
        return

    _append(lines, ["## Charm events (Ops tracing)"])
    _append(lines, ["_Events in chronological order. The most recent are at the bottom._"])

    rows = ["| Timestamp | Event | Kind | Error |", "|---|---|---|---|"]
    for evt in events:
        ts = evt.get("timestamp", "")
        name = evt.get("event", "")
        kind = evt.get("kind", "")
        exc = evt.get("exception_type", "")
        msg = evt.get("exception_message", "")
        error_col = f"`{exc}`: {msg}" if exc else ""
        rows.append(f"| `{ts}` | `{name}` | `{kind}` | {error_col} |")

    _append(lines, rows)


def _append_section_ss_connections(lines: list[str], context: dict) -> None:
    ss = context.get("ss_connections", [])
    if not ss:
        return
    _append(lines, ["## Network connections (listening + active)", "```", *ss, "```"])


def _append_section_firewall_rules(lines: list[str], context: dict) -> None:
    fw = context.get("firewall_rules", {})
    if not fw:
        return

    iptables = fw.get("iptables", [])
    if iptables:
        _append(lines, ["## Firewall rules (iptables — IPv4)", "```", *iptables, "```"])

    ufw = fw.get("ufw", [])
    if ufw:
        _append(lines, ["## Firewall rules (ufw)", "```", *ufw, "```"])

    nftables = fw.get("nftables", [])
    if nftables:
        _append(lines, ["## Firewall rules (nftables — IPv4)", "```", *nftables, "```"])
