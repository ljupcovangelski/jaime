"""Abstract AI provider interface."""

from abc import ABC, abstractmethod

from jaime.incident import UsageMetadata


class AIProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str) -> tuple[str, UsageMetadata]:
        """Generate a response for the given prompt.

        Returns a tuple of (response_text, usage_metadata).
        """
        ...

    def check(self) -> str | None:
        """Lightweight connectivity check.

        Returns None on success, or an error message string on failure.
        """
        return None
