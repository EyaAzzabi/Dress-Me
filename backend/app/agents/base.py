from abc import ABC, abstractmethod
from typing import Any


class BaseAgent(ABC):
    """Common interface every specialized agent implements."""

    name: str

    @abstractmethod
    def run(self, **kwargs: Any) -> dict[str, Any]:
        """Execute the agent's task and return a structured result."""
