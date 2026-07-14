"""Markdown report generation for Jaime incidents."""

import datetime
import logging
import os

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
    ai_suggestions: str = "",
    act_results: list | None = None,
) -> str:
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

    _append_section_log_files(lines, plan_results)
    _append_section_processes(lines, plan_results)
    _append_section_systemd(lines, plan_results, context)
    _append_section_network(lines, plan_results)
    _append_section_env(lines, plan_results)

    # Background sections
    _append_section_disk(lines, context)
    _append_section_memory(lines, context)
    _append_section_logs(lines, context)

    if ai_suggestions:
        _append(lines, [
            "## AI Diagnosis & Suggestions",
            "",
            ai_suggestions.strip(),
        ])

    if act_results:
        _append(lines, [
            "## Act mode: executed commands",
        ])
        for result in act_results:
            cmd = result.get("command", "")
            rc = result.get("returncode")
            stderr = result.get("stderr", "").strip()
            stdout = result.get("stdout", "").strip()
            status = f"exit {rc}" if rc is not None else stderr
            _append(lines, [
                f"### `{cmd}`",
                "",
                f"**Status:** {status}",
            ])
            if stdout:
                _append(lines, [
                    "```",
                    stdout,
                    "```",
                ])

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
    if unit_logs:
        _append(lines, ["```", *unit_logs, "```"])
    else:
        _append(lines, ["_No recent logs found._"])
