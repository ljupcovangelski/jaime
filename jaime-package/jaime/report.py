"""Markdown report generation for Jaime incidents.

A report captures the machine context at the time of the incident:
logs, systemd state, disk, memory. It is the input provided to the LLM
in suggest/act mode. It does not contain LLM output.
"""

import datetime
import logging
import os

import yaml

from jaime.logutils import deduplicate_lines

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
        f"- incident: {incident_id}",
        f"- unit: {unit_name}",
        f"- status: {workload}",
        f"- first-seen: {first_seen}",
        f"- generated: {now}",
    ])

    plan_results = context.get("plan_results", {})

    _append_section_summary(lines, workload, context, plan_results)
    _append_section_network(lines, plan_results)
    _append_section_ss_connections(lines, context)
    _append_section_firewall_rules(lines, context)
    _append_section_log_files(lines, plan_results)
    _append_section_processes(lines, plan_results)
    _append_section_systemd(lines, plan_results, context)
    _append_section_env(lines, plan_results)
    _append_section_health_commands(lines, plan_results)

    # Background sections
    _append_section_k8s_pod(lines, context)
    _append_section_k8s_events(lines, context)
    _append_section_k8s_resource_usage(lines, context)
    _append_section_juju_config(lines, context)
    _append_section_charm_config(lines, context)
    _append_section_disk(lines, context)
    _append_section_memory(lines, context)
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


def _append_section_summary(lines: list[str], workload: str,
                             context: dict, plan_results: dict) -> None:
    """Compact executive summary — highest-signal content first.

    Surfaces error/warning log lines and explicitly-set config options
    so the LLM can form a diagnosis before reading the full detail sections.
    """
    summary = ["## Executive summary", f"Unit is in **{workload}** state."]

    # Most recent error/warning log lines (up to 10), deduplicated so a burst
    # of identical failures (e.g. health-check errors firing every few seconds)
    # cannot push the causal error out of the summary.
    unit_logs = context.get("unit_logs", [])
    error_lines = [
        line for line in unit_logs
        if "ERROR" in line.upper() or "WARNING" in line.upper()
    ]
    error_lines = deduplicate_lines(error_lines)[-10:]
    if error_lines:
        summary.append("")
        summary.append("**Recent errors/warnings:**")
        summary.append("```")
        summary.extend(error_lines)
        summary.append("```")

    # Operator-changed Juju config options (k8s: from Application.Get).
    # These show operator intent and are often directly tied to the incident.
    juju_config = context.get("juju_config", {})
    user_changed = {
        k: v for k, v in juju_config.items() if v.get("source") == "user"
    }
    if user_changed:
        summary.append("")
        summary.append("**Config changed from default by operator:**")
        for k, v in sorted(user_changed.items()):
            summary.append(
                f"- `{k}`: `{v.get('value')}` (default: `{v.get('default')}`)"
            )

    # Charm config options that are explicitly set (non-empty, non-False).
    charm_config = context.get("charm_config", {})
    config_yaml = charm_config.get("config_yaml", "")
    if config_yaml:
        try:
            parsed = yaml.safe_load(config_yaml)
            options = (parsed or {}).get("options", {})
            set_options = {
                k: v.get("default")
                for k, v in options.items()
                if v.get("default") not in (None, "", False, "False", "false")
            }
            if set_options:
                summary.append("")
                summary.append("**Explicitly enabled config options:**")
                for k, v in sorted(set_options.items()):
                    summary.append(f"- `{k}`: `{v}`")
        except Exception:
            pass

    _append(lines, summary)


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
    except Exception as e:
        logger.debug("could not parse charm config YAML: %s", e)
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
        # Filter out snap mount lines — they always show 100% and are not
        # relevant to workload disk health.
        filtered = [line for line in disk if "/snap/" not in line]
        _append(lines, ["```", *filtered, "```"])
    else:
        _append(lines, ["_Not available._"])


def _append_section_memory(lines: list[str], context: dict) -> None:
    memory = context.get("memory_summary", [])
    _append(lines, ["## Memory"])
    if not memory:
        _append(lines, ["_Not available._"])
        return

    # Parse `free -h` output into compact single lines per row.
    # Format: "Mem:  total  used  free  shared  buff/cache  available"
    summary_lines = []
    for line in memory:
        parts = line.split()
        if not parts:
            continue
        label = parts[0].rstrip(":")
        if label in ("Mem", "Swap") and len(parts) >= 3:
            total = parts[1]
            used = parts[2]
            available = parts[6] if label == "Mem" and len(parts) >= 7 else parts[3]
            if label == "Mem":
                summary_lines.append(f"RAM: {used} used / {total} total ({available} available)")
            else:
                summary_lines.append(f"Swap: {used} used / {total} total")

    if summary_lines:
        _append(lines, summary_lines)
    else:
        # Fallback to raw output if parsing failed.
        _append(lines, ["```", *memory, "```"])


def _append_section_logs(lines: list[str], context: dict) -> None:
    unit_logs = context.get("unit_logs", [])
    _append(lines, ["## Recent unit logs"])
    _append(lines, [
        "_Showing only lines matching `error` or `warning` (case-insensitive), "
        "with a context window around the last match._"
    ])
    _append(lines, ["_Logs are in chronological order._"])
    if unit_logs:
        _append(lines, ["```", *unit_logs, "```"])
    else:
        _append(lines, ["_No recent logs found._"])


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


def _append_section_juju_config(lines: list[str], context: dict) -> None:
    """Render the application's Juju config (from Application.Get).

    Each option maps to {default, description, source, type, value}.
    Options the operator explicitly changed (source=user) are called out
    first — they are the most diagnostic-relevant.
    """
    options = context.get("juju_config", {})
    if not options:
        return

    _append(lines, ["## Juju application config"])

    changed = {k: v for k, v in options.items() if v.get("source") == "user"}
    if changed:
        _append(lines, ["**Changed from default:**"])
        for key, opt in sorted(changed.items()):
            _append(lines, [
                f"- `{key}`: `{opt.get('value')}` (default: `{opt.get('default')}`)"
            ])

    _append(lines, ["**All options:**", "```"])
    for key, opt in sorted(options.items()):
        marker = " *" if opt.get("source") == "user" else ""
        _append(lines, [f"{key}: {opt.get('value')}{marker}"])
    _append(lines, ["```", "_(* = changed from default)_"])


def _append_section_k8s_pod(lines: list[str], context: dict) -> None:
    pod = context.get("k8s_pod", {})
    if not pod:
        return

    _append(lines, ["## Kubernetes pod"])
    _append(lines, [
        f"- name: `{pod.get('name', '')}`",
        f"- phase: `{pod.get('phase', 'unknown')}`",
    ])
    if pod.get("node"):
        _append(lines, [f"- node: `{pod['node']}`"])
    if pod.get("pod_ip"):
        _append(lines, [f"- pod IP: `{pod['pod_ip']}`"])
    if pod.get("qos"):
        _append(lines, [f"- QoS class: `{pod['qos']}`"])
    conditions = pod.get("conditions", [])
    if conditions:
        _append(lines, [f"- conditions: {', '.join(conditions)}"])

    containers = pod.get("containers", [])
    if containers:
        _append(lines, ["", "**Containers:**", ""])
        for c in containers:
            icon = "✓" if c.get("ready") else "✗"
            _append(lines, [
                f"- `{c.get('name')}` ({c.get('state', '?')}) "
                f"ready={c.get('ready')} restarts={c.get('restartCount')} {icon}",
                f"  image: `{c.get('image', '')}`",
            ])
            if c.get("resources"):
                _append(lines, [f"  resources: {c['resources']}"])
            for probe_kind in ("liveness", "readiness"):
                if c.get(probe_kind):
                    _append(lines, [f"  {probe_kind}: {c[probe_kind]}"])

    volumes = pod.get("volumes", [])
    if volumes:
        _append(lines, ["", "**Volumes:**", ""])
        for v in volumes:
            mounts = f" → {', '.join(v['mounts'])}" if v.get("mounts") else ""
            _append(lines, [f"- `{v['name']}`: {v['source']}{mounts}"])


def _append_section_k8s_events(lines: list[str], context: dict) -> None:
    events = context.get("k8s_events", [])
    if not events:
        return
    _append(lines, ["## Kubernetes events", "```", *events, "```"])


def _append_section_k8s_resource_usage(lines: list[str], context: dict) -> None:
    usage = context.get("k8s_resource_usage", [])
    if not usage:
        return
    _append(lines, ["## Resource usage (metrics-server)", "```", *usage, "```"])
