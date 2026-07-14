"""Context collection for Jaime incidents.

Collects bounded diagnostics from the local machine without modifying
any state. All collection is read-only and bounded by time and line count.
"""

import datetime
import logging
import os
import subprocess

logger = logging.getLogger(__name__)

# Safe bounded defaults
_DEFAULT_LOG_WINDOW_MINUTES = 30
_DEFAULT_MAX_LINES = 500
_JUJU_LOG_DIR = "/var/log/juju"


def _run(cmd: list[str], timeout: int = 10) -> str:
    """Run a command and return its stdout. Returns empty string on failure."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout
    except Exception as e:
        logger.debug("collection command %s failed: %s", cmd, e)
        return ""


def _tail_lines(text: str, max_lines: int) -> list[str]:
    """Return the last max_lines lines of text."""
    lines = text.splitlines()
    return lines[-max_lines:] if len(lines) > max_lines else lines


def collect_unit_logs(
    unit_name: str,
    log_window_minutes: int = _DEFAULT_LOG_WINDOW_MINUTES,
    max_lines: int = _DEFAULT_MAX_LINES,
) -> list[str]:
    """Read recent lines from the principal unit's Juju log file.

    Bounded by log_window_minutes (recency) and max_lines (volume).
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

    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        minutes=log_window_minutes
    )

    recent = []
    for line in raw_lines:
        # Juju log format: "2026-07-14 10:00:00 LEVEL ..."
        # Parse the timestamp prefix to filter by window.
        try:
            ts_str = line[:19]
            ts = datetime.datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=datetime.timezone.utc
            )
            if ts >= cutoff:
                recent.append(line.rstrip())
        except ValueError:
            # Line doesn't start with a timestamp — include it (continuation line)
            if recent:
                recent.append(line.rstrip())

    return _tail_lines("\n".join(recent), max_lines)


def collect_systemd_failed() -> list[str]:
    """Return a list of failed systemd units."""
    output = _run(["systemctl", "--failed", "--no-legend", "--plain"])
    lines = [l.strip() for l in output.splitlines() if l.strip()]
    return lines


def collect_disk_usage() -> list[str]:
    """Return disk usage summary lines."""
    output = _run(["df", "-h", "--output=source,size,used,avail,pcent,target"])
    return [l.rstrip() for l in output.splitlines() if l.strip()]


def collect_memory_summary() -> list[str]:
    """Return memory summary lines."""
    output = _run(["free", "-h"])
    return [l.rstrip() for l in output.splitlines() if l.strip()]


def collect_context(
    unit_name: str,
    log_window_minutes: int = _DEFAULT_LOG_WINDOW_MINUTES,
    max_lines: int = _DEFAULT_MAX_LINES,
) -> dict:
    """Collect all context for an incident. Returns a plain dict."""
    return {
        "unit_logs": collect_unit_logs(unit_name, log_window_minutes, max_lines),
        "systemd_failed": collect_systemd_failed(),
        "disk_usage": collect_disk_usage(),
        "memory_summary": collect_memory_summary(),
        "collected_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
