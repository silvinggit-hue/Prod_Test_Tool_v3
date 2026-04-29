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
        self._submitted_device_ips: set[str] = set()

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

    def mark_task_submitted(self, device_ip: str | None) -> None:
        if not device_ip:
            return
        with self._lock:
            self._submitted_device_ips.add(device_ip)

    def mark_task_finished(self, device_ip: str | None) -> None:
        if not device_ip:
            return
        with self._lock:
            self._submitted_device_ips.discard(device_ip)

    def _has_pending_connect_for_device(self, device_ip: str) -> bool:
        for _lane, queue in self._queues.items():
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

    def _pop_next_ready_task_for_lane(self, lane: TaskLane, now: float) -> TaskSpec | None:
        queue = self._queues[lane]

        while queue:
            item = queue[0]
            if item.due_at and item.due_at > now:
                return None

            task = item.task
            if not task.device_ip:
                heapq.heappop(queue)
                continue

            actor = self.registry.get_actor(task.device_ip)
            if actor is None:
                heapq.heappop(queue)
                continue

            if task.device_ip in self._submitted_device_ips:
                return None

            if self._is_blocked_by_connect_prerequisite(task):
                return None

            if not actor.can_accept_task(task):
                return None

            heapq.heappop(queue)
            self._submitted_device_ips.add(task.device_ip)
            return task

        return None

    def dispatch_ready_tasks(
        self,
        *,
        connect_limit: int = 8,
        other_limit: int = 4,
    ) -> list[TaskSpec]:
        now = time.time()
        selected: list[TaskSpec] = []

        with self._lock:
            connect_count = 0
            other_count = 0

            while True:
                picked_any = False

                for lane in LANE_ORDER:
                    if lane == TaskLane.CONNECT and connect_count >= connect_limit:
                        continue
                    if lane != TaskLane.CONNECT and other_count >= other_limit:
                        continue

                    task = self._pop_next_ready_task_for_lane(lane, now)
                    if task is None:
                        continue

                    selected.append(task)
                    picked_any = True

                    if lane == TaskLane.CONNECT:
                        connect_count += 1
                    else:
                        other_count += 1

                    # lane priority를 유지하기 위해 한 번에 하나씩만 뽑고 다시 처음부터 본다.
                    break

                if not picked_any:
                    break

        return selected

    def dispatch_once(self) -> bool:
        tasks = self.dispatch_ready_tasks(connect_limit=1, other_limit=1)
        return bool(tasks)

    def run_until_idle(self, max_steps: int = 1000) -> int:
        steps = 0
        while steps < max_steps:
            tasks = self.dispatch_ready_tasks(connect_limit=1, other_limit=1)
            if not tasks:
                break
            # 이전 Step unit test 호환용: 여기서는 실행하지 않고 "dispatch 가능 여부"만 센다.
            for task in tasks:
                self.mark_task_finished(task.device_ip)
            steps += len(tasks)
        return steps