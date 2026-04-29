from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from domain.enums.command import CommandKind, TaskLane


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    device_ip: str | None
    command: CommandKind
    lane: TaskLane
    priority: int = 0
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: float | None = None
    due_at: float | None = None