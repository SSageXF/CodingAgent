"""EvidenceCoder: a small, locally executing coding agent."""

from .engine import AgentResult, Engine, RunStatus
from .settings import Settings

__all__ = ["AgentResult", "Engine", "RunStatus", "Settings"]
__version__ = "0.2.0"
