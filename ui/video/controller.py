from __future__ import annotations

from typing import Callable

from PyQt5.QtWidgets import QMessageBox

from application.core.app_supervisor import AppSupervisor
from application.core.video_coordinator import VideoCoordinator, VideoPagePlan
from ui.video.window import VideoWindow


class VideoWindowController:
    def __init__(
        self,
        *,
        window: VideoWindow,
        supervisor: AppSupervisor,
        checked_ips_provider: Callable[[], list[str]],
        selected_ips_provider: Callable[[], list[str]],
        focused_ip_provider: Callable[[], str | None],
        on_log: Callable[[str], None] | None = None,
        on_result: Callable[[str], None] | None = None,
    ) -> None:
        self.window = window
        self.supervisor = supervisor
        self.checked_ips_provider = checked_ips_provider
        self.selected_ips_provider = selected_ips_provider
        self.focused_ip_provider = focused_ip_provider
        self.on_log = on_log
        self.on_result = on_result

        self.coordinator = VideoCoordinator(page_size=10)

        self._current_page = 0
        self._current_plan: VideoPagePlan | None = None

    def bind(self) -> None:
        self.window.prev_page_requested.connect(self._on_prev_page_requested)
        self.window.next_page_requested.connect(self._on_next_page_requested)
        self.window.refresh_requested.connect(self._on_refresh_requested)
        self.window.closed.connect(self._on_window_closed)

    def open_window(self) -> None:
        self._current_page = 0
        plan = self._build_plan()
        if plan.target_count <= 0:
            QMessageBox.information(self.window, "Video", "영상으로 볼 수 있는 연결 장비가 없습니다.")
            return

        self._apply_plan(plan)
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def _build_plan(self) -> VideoPagePlan:
        return self.coordinator.build_plan(
            registry=self.supervisor.registry,
            checked_ips=self.checked_ips_provider(),
            selected_ips=self.selected_ips_provider(),
            focused_ip=self.focused_ip_provider(),
            page_index=self._current_page,
        )

    def _apply_plan(self, plan: VideoPagePlan) -> None:
        self._current_plan = plan
        self._current_page = plan.current_page

        self.window.update_header(
            mode_label=plan.mode_label,
            target_count=plan.target_count,
            current_page=plan.current_page,
            page_count=plan.page_count,
        )
        self.window.set_tiles(plan.items)

        self.supervisor.set_current_video_page(plan.current_page)
        for ip in plan.visible_ips:
            self.supervisor.enqueue_status_poll(ip, hot=True)

        if self.on_log is not None:
            self.on_log(
                f"video page applied: mode={plan.mode_label} page={plan.current_page + 1}/{plan.page_count} "
                f"targets={len(plan.visible_ips)}"
            )

    def _on_prev_page_requested(self) -> None:
        if self._current_plan is None:
            return
        if self._current_page <= 0:
            return

        self._current_page -= 1
        self._apply_plan(self._build_plan())

    def _on_next_page_requested(self) -> None:
        if self._current_plan is None:
            return
        if self._current_page + 1 >= self._current_plan.page_count:
            return

        self._current_page += 1
        self._apply_plan(self._build_plan())

    def _on_refresh_requested(self) -> None:
        plan = self._build_plan()
        if plan.target_count <= 0:
            self.window.stop_all_tiles()
            self.window.update_header(
                mode_label="현재 장비",
                target_count=0,
                current_page=0,
                page_count=1,
            )
            if self.on_result is not None:
                self.on_result("Video 대상 장비가 없습니다.")
            return

        self._apply_plan(plan)
        if self.on_result is not None:
            self.on_result("영상 새로고침")

    def _on_window_closed(self) -> None:
        self._current_page = 0
        self._current_plan = None