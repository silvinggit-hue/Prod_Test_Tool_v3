from __future__ import annotations

from domain.models.device_snapshot import DeviceSnapshot


def map_result_text(snapshot: DeviceSnapshot) -> str:
    cmd = snapshot.command

    if cmd.inflight:
        if cmd.progress_text:
            return cmd.progress_text
        if cmd.current_task_kind:
            return f"{cmd.current_task_kind} running"
        return "running"

    if cmd.last_result == "error":
        detail = (cmd.last_error_detail or "").strip()
        kind = (cmd.last_error_kind or "").strip()
        if detail:
            return detail
        if kind:
            return kind
        return "error"

    if cmd.last_message:
        return cmd.last_message

    if snapshot.connected:
        return "ready"

    return "-"