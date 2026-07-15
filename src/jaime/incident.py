"""Incident and Suggestion models for Jaime."""

import dataclasses
import datetime
import uuid


@dataclasses.dataclass(frozen=True)
class Suggestion:
    """An AI-generated suggestion attached to an incident.

    Attributes:
        description:   The LLM's analysis and diagnosis text.
        commands:      Commands parsed from the LLM response.
        generated_at:  ISO 8601 timestamp (UTC) when the suggestion was created.
        context_hash:  SHA-256 of the additional-context string, or empty if none.
    """

    description: str
    commands: tuple[str, ...]
    generated_at: str
    context_hash: str = ""

    @classmethod
    def from_llm(cls, description: str, commands: list[str],
                 context_hash: str = "") -> "Suggestion":
        """Create a Suggestion from LLM output."""
        return cls(
            description=description,
            commands=tuple(commands),
            generated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            context_hash=context_hash,
        )

    def to_dict(self) -> dict:
        return {
            "description": self.description,
            "commands": list(self.commands),
            "generated_at": self.generated_at,
            "context_hash": self.context_hash,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Suggestion":
        return cls(
            description=d["description"],
            commands=tuple(d.get("commands", [])),
            generated_at=d["generated_at"],
            context_hash=d.get("context_hash", ""),
        )


@dataclasses.dataclass(frozen=True)
class Incident:
    """An incident for a principal unit.

    Attributes:
        id:         Stable UUID assigned when the incident is first opened.
        opened_at:  ISO 8601 timestamp (UTC) when the incident was opened.
        closed_at:  ISO 8601 timestamp (UTC) when the incident was closed, or None.
        suggestion: AI-generated suggestion, or None if not yet produced.
    """

    id: str
    opened_at: str
    closed_at: str | None = None
    suggestion: Suggestion | None = None

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

    def attach_suggestion(self, suggestion: Suggestion) -> "Incident":
        """Return a copy of this incident with the suggestion attached."""
        return dataclasses.replace(self, suggestion=suggestion)

    @property
    def is_open(self) -> bool:
        return self.closed_at is None

    def to_dict(self) -> dict:
        d = {"id": self.id, "opened_at": self.opened_at}
        if self.closed_at is not None:
            d["closed_at"] = self.closed_at
        if self.suggestion is not None:
            d["suggestion"] = self.suggestion.to_dict()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Incident":
        suggestion = None
        if "suggestion" in d:
            suggestion = Suggestion.from_dict(d["suggestion"])
        return cls(
            id=d["id"],
            opened_at=d["opened_at"],
            closed_at=d.get("closed_at"),
            suggestion=suggestion,
        )
