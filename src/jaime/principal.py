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
                "increment": 3,
                "last_reported": "2026-07-13T16:01:46+00:00"
            }
        }

    The increment resets to 1 when the status changes.
    last_reported is set when an incident event is emitted and used to
    enforce the cooldown period.
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

        ``since`` is the ISO timestamp from goal-state marking when the current
        status began. A change in either ``status`` or ``since`` is treated as
        a new episode: the increment and last_reported are both reset.

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
                "last_reported": previous.get("last_reported"),
            }
        self._save()
        return self._state[unit]["increment"]

    def record_reported(self, unit: str, timestamp: str) -> None:
        """Record that an incident event was emitted for this unit."""
        if unit in self._state:
            self._state[unit]["last_reported"] = timestamp
            self._save()

    def last_reported(self, unit: str) -> str | None:
        """Return the ISO timestamp of the last reported incident, or None."""
        return self._state.get(unit, {}).get("last_reported")
