from __future__ import annotations

import heapq
import itertools
import threading
import time
from dataclasses import dataclass, field

from application.core.device_registry import DeviceRegistry
from domain.enums.command import CommandKind, TaskLane
from domain.errors.app_error import AppError
from domain.models.tasks import TaskSpec


LANE_ORDER: tuple[TaskLane, ...] = (
    TaskLane.CONTROL,
    TaskLane.CONNECT,
    TaskLane.INFO,
    TaskLane.POLL_HOT,
    TaskLane.POLL_WARM,
    TaskLane.FIRMWARE,
    TaskLane.UDP_ADMIN,
)


@dataclass(order=True)
class _QueueItem:
    sort_key: tuple[int, int, float] = field(init=False, repr=False)
    priority: int
    sequence: int
    due_at: float
    task: TaskSpec = field(compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "sort_key", (-self.priority, self.sequence, self.due_at))


class TaskScheduler:
    def __init__(self, *, registry: DeviceRegistry) -> None:
        self.registry = registry
        self._queues: dict[TaskLane, list[_QueueItem]] = {lane: [] for lane in LANE_ORDER}
        self._sequence = itertools.count(1)
        self._lock = threading.RLock()

    def enqueue(self, task: TaskSpec) -> None:
        due_at = float(task.due_at) if task.due_at is not None else 0.0
        item = _QueueItem(
            priority=int(task.priority),
            sequence=next(self._sequence),
            due_at=due_at,
            task=task,
        )
        with self._lock:
            heapq.heappush(self._queues[task.lane], item)

    def queue_size(self, lane: TaskLane | None = None) -> int:
        with self._lock:
            if lane is None:
                return sum(len(items) for items in self._queues.values())
            return len(self._queues[lane])

    def _has_pending_connect_for_device(self, device_ip: str) -> bool:
        for lane, queue in self._queues.items():
            for item in queue:
                task = item.task
                if task.device_ip == device_ip and task.command == CommandKind.CONNECT:
                    return True
        return False

    def _is_blocked_by_connect_prerequisite(self, task: TaskSpec) -> bool:
        if task.command == CommandKind.CONNECT:
            return False

        if not task.device_ip:
            return False

        actor = self.registry.get_actor(task.device_ip)
        snapshot = self.registry.get_snapshot(task.device_ip)

        if actor is None or snapshot is None:
            return False

        has_session = False
        if hasattr(actor, "has_session") and callable(actor.has_session):
            try:
                has_session = bool(actor.has_session())
            except Exception:
                has_session = False

        if has_session or snapshot.connected:
            return False

        return self._has_pending_connect_for_device(task.device_ip)

    def dispatch_once(self) -> bool:
        now = time.time()
        selected_task: TaskSpec | None = None

        with self._lock:
            for lane in LANE_ORDER:
                queue = self._queues[lane]
                if not queue:
                    continue

                item = queue[0]
                if item.due_at and item.due_at > now:
                    continue

                task = item.task
                if not task.device_ip:
                    heapq.heappop(queue)
                    continue

                actor = self.registry.get_actor(task.device_ip)
                if actor is None:
                    heapq.heappop(queue)
                    raise AppError(kind="state", message="actor not found", detail=task.device_ip)

                if self._is_blocked_by_connect_prerequisite(task):
                    continue

                if not actor.can_accept_task(task):
                    continue

                heapq.heappop(queue)
                selected_task = task
                break

        if selected_task is None:
            return False

        actor = self.registry.get_actor(selected_task.device_ip)
        if actor is None:
            raise AppError(kind="state", message="actor missing before execution", detail=selected_task.device_ip)

        actor.execute_task(selected_task)
        return True