from __future__ import annotations

import time
import uuid

from domain.enums.command import CommandKind, TaskLane
from domain.models.phase1 import Phase1Request
from domain.models.tasks import TaskSpec


def _task_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class CommandFactory:
    @staticmethod
    def connect(device_ip: str, request: Phase1Request, *, priority: int = 50) -> TaskSpec:
        return TaskSpec(
            task_id=_task_id("connect"),
            device_ip=device_ip,
            command=CommandKind.CONNECT,
            lane=TaskLane.CONNECT,
            priority=priority,
            payload={"request": request},
            created_at=time.time(),
        )

    @staticmethod
    def info_load(device_ip: str, *, priority: int = 40) -> TaskSpec:
        return TaskSpec(
            task_id=_task_id("info"),
            device_ip=device_ip,
            command=CommandKind.INFO_LOAD,
            lane=TaskLane.INFO,
            priority=priority,
            payload={},
            created_at=time.time(),
        )

    @staticmethod
    def status_poll(device_ip: str, *, hot: bool, priority: int | None = None) -> TaskSpec:
        lane = TaskLane.POLL_HOT if hot else TaskLane.POLL_WARM
        default_priority = 20 if hot else 10
        return TaskSpec(
            task_id=_task_id("poll"),
            device_ip=device_ip,
            command=CommandKind.STATUS_POLL,
            lane=lane,
            priority=priority if priority is not None else default_priority,
            payload={"hot": hot},
            created_at=time.time(),
        )

    @staticmethod
    def control(
        device_ip: str,
        *,
        handler: str,
        kwargs: dict | None = None,
        priority: int = 100,
    ) -> TaskSpec:
        return TaskSpec(
            task_id=_task_id("control"),
            device_ip=device_ip,
            command=CommandKind.CONTROL,
            lane=TaskLane.CONTROL,
            priority=priority,
            payload={"handler": handler, "kwargs": dict(kwargs or {})},
            created_at=time.time(),
        )