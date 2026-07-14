"""Markdown report generation for Jaime incidents."""

import datetime
import logging
import os

logger = logging.getLogger(__name__)

_DEFAULT_REPORT_DIR = "/var/log/jaime/reports"


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
    """Generate a Markdown incident report and write it to disk.

    If ai_suggestions is provided, appends an '## AI Diagnosis & Suggestions' section.
    If act_results is provided, appends an '## Act mode: executed commands' section.

    Falls back to _DEFAULT_REPORT_DIR if report_dir is empty.
    Returns the path of the written report file.
    """
    report_dir = report_dir or _DEFAULT_REPORT_DIR
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    lines = []

    lines += [
        "# Incident Report",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Incident ID | `{incident_id}` |",
        f"| Unit | `{unit_name}` |",
        f"| Workload status | `{workload}` |",
        f"| First seen | `{first_seen}` |",
        f"| Report generated | `{now}` |",
        "",
    ]

    # Systemd failed units
    systemd_failed = context.get("systemd_failed", [])
    lines.append("## Failed systemd units")
    lines.append("")
    if systemd_failed:
        for unit in systemd_failed:
            lines.append(f"- `{unit}`")
    else:
        lines.append("_None detected._")
    lines.append("")

    # Disk usage
    disk = context.get("disk_usage", [])
    lines.append("## Disk usage")
    lines.append("")
    if disk:
        lines.append("```")
        lines += disk
        lines.append("```")
    else:
        lines.append("_Not available._")
    lines.append("")

    # Memory
    memory = context.get("memory_summary", [])
    lines.append("## Memory")
    lines.append("")
    if memory:
        lines.append("```")
        lines += memory
        lines.append("```")
    else:
        lines.append("_Not available._")
    lines.append("")

    # Unit logs
    unit_logs = context.get("unit_logs", [])
    lines.append("## Recent unit logs")
    lines.append("")
    if unit_logs:
        lines.append("```")
        lines += unit_logs
        lines.append("```")
    else:
        lines.append("_No recent logs found._")
    lines.append("")

    # AI suggestions (suggest / act mode)
    if ai_suggestions:
        lines.append("## AI Diagnosis & Suggestions")
        lines.append("")
        lines.append(ai_suggestions.strip())
        lines.append("")

    # Act mode execution results
    if act_results:
        lines.append("## Act mode: executed commands")
        lines.append("")
        for result in act_results:
            cmd = result.get("command", "")
            rc = result.get("returncode")
            stderr = result.get("stderr", "").strip()
            stdout = result.get("stdout", "").strip()
            status = f"exit {rc}" if rc is not None else stderr
            lines.append(f"### `{cmd}`")
            lines.append("")
            lines.append(f"**Status:** {status}")
            if stdout:
                lines.append("")
                lines.append("```")
                lines.append(stdout)
                lines.append("```")
            lines.append("")

    content = "\n".join(lines)

    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(report_dir, f"{incident_id}.md")
    with open(report_path, "w") as f:
        f.write(content)

    logger.debug("report written to %s", report_path)
    return report_path
