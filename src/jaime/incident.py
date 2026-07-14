"""Incident model for Jaime."""

import dataclasses
import datetime
import uuid


@dataclasses.dataclass(frozen=True)
class Incident:
    """An incident for a principal unit.

    Attributes:
        id:        Stable UUID assigned when the incident is first opened.
        opened_at: ISO 8601 timestamp (UTC) when the incident was opened.
        closed_at: ISO 8601 timestamp (UTC) when the incident was closed, or None.
    """

    id: str
    opened_at: str
    closed_at: str | None = None

    @classmethod
    def open(cls) -> "Incident":
        """Create a new incident with a fresh UUID and the current UTC time."""
        return cls(
            id=str(uuid.uuid4()),
            opened_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )

    def close(self) -> "Incident":
        """Return a closed copy of this incident with the current UTC time."""
        return dataclasses.replace(
            self,
            closed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )

    @property
    def is_open(self) -> bool:
        return self.closed_at is None

    def to_dict(self) -> dict:
        d = {"id": self.id, "opened_at": self.opened_at}
        if self.closed_at is not None:
            d["closed_at"] = self.closed_at
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Incident":
        return cls(
            id=d["id"],
            opened_at=d["opened_at"],
            closed_at=d.get("closed_at"),
        )
