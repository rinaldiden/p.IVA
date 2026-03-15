"""Data models for Agent9 Notifier & Supervisor."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class NotifyResult:
    """Result of a notification dispatch."""

    success: bool
    channel: str = ""
    message_id: str = ""
    dry_run: bool = True
    error: str = ""


@dataclass
class AgentHealth:
    """Health status of a single agent."""

    name: str
    status: str = "ok"  # "ok", "error", "timeout", "stub"
    last_check: str = ""
    message: str = ""


@dataclass
class StepResult:
    """Result of a single pipeline step."""

    agent_name: str
    success: bool
    result: dict = field(default_factory=dict)
    error: str = ""
    duration_ms: float = 0.0


@dataclass
class PipelineResult:
    """Result of a full pipeline run."""

    steps: list[StepResult] = field(default_factory=list)
    success: bool = True
    errors: list[str] = field(default_factory=list)
    duration_ms: float = 0.0


@dataclass
class PipelineStatus:
    """Current status of a running pipeline."""

    profile_id: str = ""
    current_step: str = ""
    completed_steps: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""
    status: str = "idle"  # "idle", "running", "completed", "failed"
