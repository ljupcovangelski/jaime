"""Principal unit status tracking for Jaime."""

import json
import logging
import os

logger = logging.getLogger(__name__)

_DEFAULT_STATE_PATH = "/var/lib/jaime/status-state.json"


class StatusTracker:
    """Persist per-unit status observations across hook invocations.

    State file schema::

        {
            "postgresql/0": {
                "status": "blocked",
                "since": "2026-07-14T09:37:54+00:00",
                "increment": 3,
                "incident": {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "opened_at": "2026-07-14T09:39:39+00:00"
                },
                "last_reported": "2026-07-14T09:39:39+00:00"
            }
        }

    The increment resets to 1 when the status or since changes (new episode).
    incident and last_reported are cleared on a new episode.
    """

    def __init__(self, state_path: str = _DEFAULT_STATE_PATH):
        self._path = state_path
        self._state: dict = self._load()

    def _load(self) -> dict:
        try:
            with open(self._path) as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
        except Exception as e:
            logger.warning("could not load status state from %s: %s", self._path, e)
            return {}

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            with open(self._path, "w") as f:
                json.dump(self._state, f)
        except Exception as e:
            logger.warning("could not save status state to %s: %s", self._path, e)

    def observe(self, unit: str, status: str, since: str) -> int:
        """Record a status observation for a unit.

        A change in either ``status`` or ``since`` is treated as a new episode:
        the increment, incident, and last_reported are all reset.

        Returns the current increment.
        """
        previous = self._state.get(unit, {})
        new_episode = (
            previous.get("status") != status
            or previous.get("since") != since
        )
        if new_episode:
            self._state[unit] = {"status": status, "since": since, "increment": 1}
        else:
            self._state[unit] = {
                "status": status,
                "since": since,
                "increment": previous.get("increment", 0) + 1,
                "incident": previous.get("incident"),
                "last_reported": previous.get("last_reported"),
            }
        self._save()
        return self._state[unit]["increment"]

    def record_reported(self, unit: str, timestamp: str, incident_dict: dict) -> None:
        """Record that an incident was opened and reported for this unit."""
        if unit in self._state:
            self._state[unit]["last_reported"] = timestamp
            self._state[unit]["incident"] = incident_dict
            self._save()

    def close_incident(self, unit: str, closed_incident_dict: dict) -> None:
        """Record the closed incident for a unit."""
        if unit in self._state:
            self._state[unit]["incident"] = closed_incident_dict
            self._save()

    def update_incident(self, unit: str, incident_dict: dict) -> None:
        """Update the stored incident dict (e.g. to attach a suggestion)."""
        if unit in self._state:
            self._state[unit]["incident"] = incident_dict
            self._save()

    def has_open_incident(self, unit: str) -> bool:
        """Return True if there is an open (not yet closed) incident for a unit."""
        incident = self._state.get(unit, {}).get("incident")
        if not incident:
            return False
        return incident.get("closed_at") is None

    def last_reported(self, unit: str) -> str | None:
        """Return the ISO timestamp of the last reported incident, or None."""
        return self._state.get(unit, {}).get("last_reported")

    def current_incident(self, unit: str) -> dict | None:
        """Return the current incident dict for a unit, or None."""
        return self._state.get(unit, {}).get("incident")
