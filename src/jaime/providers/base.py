"""Abstract AI provider interface."""

from abc import ABC, abstractmethod


class AIProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str) -> str:
        ...

    def check(self) -> str | None:
        """Lightweight connectivity check.

        Returns None on success, or an error message string on failure.
        """
        return None
