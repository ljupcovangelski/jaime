"""Structured JSONL audit logger for Jaime.

All incident lifecycle events are appended to a single append-only JSONL file.
Each line is a self-contained JSON object. The file is never truncated by Jaime.
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

_DEFAULT_AUDIT_LOG_PATH = "/var/log/jaime/events.jsonl"


def write_event(event: dict, audit_log_path: str = "") -> None:
    """Append a structured event to the JSONL audit log.

    Falls back to _DEFAULT_AUDIT_LOG_PATH if audit_log_path is empty.
    Does not raise on failure — logs a warning instead.
    """
    path = audit_log_path or _DEFAULT_AUDIT_LOG_PATH
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a") as f:
            f.write(json.dumps(event) + "\n")
    except Exception as e:
        logger.warning("could not write audit event to %s: %s", path, e)
