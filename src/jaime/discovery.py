"""Co-located unit discovery via the Juju agents directory on the local machine.

Uses filesystem introspection of /var/lib/juju/agents/ to discover all units
co-located on the same machine as jaime.  This avoids the Juju hook-tool
sandbox limitation where goal_state() only returns units directly related to
the executing charm.

Workload status reading
=======================

* Juju 2.x:      ``<agent_dir>/unit-<name>/state`` is a flat JSON file.
* Juju 3.x:      workload status is **not** stored locally on the machine
                 (only deployer/bundles metadata is in ``state/``).  The
                 ``juju show-unit --format=json`` subprocess call is tried as
                 a best-effort fallback for related principal units only;
                 non-related co-located units (e.g. other subordinates on the
                 same machine) cannot have their workload status read without
                 a direct relation.

                 For the related principal unit, ``goal_state()`` in the charm
                 is the reliable mechanism.
"""

import json
import logging
import os
import subprocess

logger = logging.getLogger(__name__)

_AGENTS_DIR = "/var/lib/juju/agents"


def discover_colocated_units(skip_unit: str | None = None) -> list[str]:
    """Return a list of co-located unit names (``app/n``) on this machine.

    Scans ``/var/lib/juju/agents/`` for ``unit-*`` directories.  The
    ``skip_unit`` argument (e.g. ``"jaime/0"``) is excluded from the result.
    The machine-0 agent directory is always skipped.

    Returns an empty list when the agents directory is missing or unreadable.
    """
    try:
        entries = sorted(os.listdir(_AGENTS_DIR))
    except FileNotFoundError:
        logger.debug("agents directory not found: %s", _AGENTS_DIR)
        return []
    except PermissionError:
        logger.debug("permission denied reading: %s", _AGENTS_DIR)
        return []
    except Exception as e:
        logger.debug("could not list %s: %s", _AGENTS_DIR, e)
        return []

    units: list[str] = []
    for name in entries:
        if not name.startswith("unit-"):
            continue
        unit_name = name[len("unit-"):].replace("-", "/", 1)
        if skip_unit and unit_name == skip_unit:
            continue
        units.append(unit_name)

    if units:
        logger.info("discovered co-located units: %s", units)
    else:
        logger.debug("no co-located units found in %s", _AGENTS_DIR)
    return units


def read_unit_workload_status(unit_name: str) -> dict | None:
    """Read the workload status for a co-located unit from the filesystem.

    Handles several Juju agent state layouts:

    * Juju 2.x — ``<agent_dir>/unit-<name>/state`` is a flat JSON file with
      ``workload-status.{current,message,since}`` keys.
    * Juju 3.x — ``state`` is a directory containing ``uniter`` (JSON) with
      a ``status`` field ``{status,info,since}``.

    Returns a dict with keys ``current``, ``message``, ``since``, or ``None``
    if none of the state locations exist, are unreadable, or lack workload info.
    """
    tag = "unit-" + unit_name.replace("/", "-")
    base = os.path.join(_AGENTS_DIR, tag)

    # Juju 2.x: flat state file
    flat_state = os.path.join(base, "state")
    try:
        if os.path.isfile(flat_state):
            with open(flat_state) as f:
                data = json.load(f)
            ws = data.get("workload-status", {})
            if ws and "current" in ws:
                logger.info("read workload status for %s: %s (juju2 format)", unit_name, ws["current"])
                return {
                    "current": ws["current"],
                    "message": ws.get("message", ""),
                    "since": ws.get("since", ""),
                }
    except (json.JSONDecodeError, OSError) as e:
        logger.debug("could not read flat state for %s at %s: %s", unit_name, flat_state, e)

    # Juju 3.x: state/ is a directory — enumerate and try candidates
    state_dir = os.path.join(base, "state")
    if os.path.isdir(state_dir):
        try:
            state_entries = os.listdir(state_dir)
        except OSError as e:
            logger.debug("could not list state dir for %s at %s: %s", unit_name, state_dir, e)
            state_entries = []

        if state_entries:
            logger.debug("state directory contents for %s: %s", unit_name, state_entries)

        for candidate in ("uniter", "uniter.state", "agent.state"):
            try:
                path = os.path.join(state_dir, candidate)
                if not os.path.isfile(path):
                    continue
                with open(path) as f:
                    data = json.load(f)
                # Try Juju 3.x uniter state format: data.status.{status,info,since}
                st = data.get("status", {})
                if isinstance(st, dict) and "status" in st:
                    logger.info("read workload status for %s: %s (juju3, %s)",
                                unit_name, st["status"], candidate)
                    return {
                        "current": st["status"],
                        "message": st.get("info", ""),
                        "since": st.get("since", ""),
                    }
                # Try data.workload-status as fallback (some Juju 3.x variants)
                ws = data.get("workload-status", {})
                if isinstance(ws, dict) and "current" in ws:
                    logger.info("read workload status for %s: %s (juju3 fallback, %s)",
                                unit_name, ws["current"], candidate)
                    return {
                        "current": ws["current"],
                        "message": ws.get("message", ""),
                        "since": ws.get("since", ""),
                    }
            except (json.JSONDecodeError, OSError) as e:
                logger.debug("could not read %s for %s: %s", candidate, unit_name, e)

    # Final fallback: try juju show-unit --format=json
    # This may work in deployments where the juju CLI has controller credentials.
    try:
        result = subprocess.run(
            ["juju", "show-unit", unit_name, "--format=json"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and result.stdout:
            data = json.loads(result.stdout)
            # Format: {unit_name: {workload-status: {current, message, since}, ...}}
            unit_data = data.get(unit_name, {})
            ws = unit_data.get("workload-status", {})
            if isinstance(ws, dict) and "current" in ws:
                logger.info("read workload status for %s: %s (juju show-unit)",
                            unit_name, ws["current"])
                return {
                    "current": ws["current"],
                    "message": ws.get("message", ""),
                    "since": ws.get("since", ""),
                }
    except FileNotFoundError:
        logger.debug("juju CLI not found, cannot run show-unit for %s", unit_name)
    except subprocess.TimeoutExpired:
        logger.debug("juju show-unit timed out for %s", unit_name)
    except (json.JSONDecodeError, OSError) as e:
        logger.debug("juju show-unit failed for %s: %s", unit_name, e)

    logger.debug("no workload status found for %s (tried file system and juju CLI)",
                 unit_name)
    return None
