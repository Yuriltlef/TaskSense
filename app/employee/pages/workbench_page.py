"""工作台页 — 任务列表 + 接单 / 提交验收 / 阻塞.

所有写操作通过 SocketClient 发送给主应用处理，
主应用执行后立即保存并返回最新状态，本页面读取状态并刷新。
"""

import flet as ft

from app.config.theme import theme, s
from app.core.state import state
from app.core.services.employee_service import employee_service
from app.core.services.socket_client import SocketClient
from app.core.models.task import TaskStatus
from app.ui.widgets.toast import Toast
from app.ui.widgets.overlay_dimmer import OverlayDimmer


class WorkbenchPage:
    """员工任务工作台页面（独立窗口内的状态 B）。

    用法:
        wb = WorkbenchPage(page, eid, ename, client, on_switch)
        container = wb.build()
    """

    def __init__(self, page: ft.Page, employee_id: str, employee_name: str,
                 client: SocketClient, on_switch):
        self._page = page
        self._employee_id = employee_id
        self._employee_name = employee_name
        self._client = client        # SocketClient 实例
        self._on_switch = on_switch  # 切换登录回调
        self._body: ft.Column | None = None
        self._body_container: ft.Container | None = None

    def build(self) -> ft.Container:
        """构建完整页面容器。首次调用后 _body_container 指向树中容器。"""
        self._body_container = ft.Container(
            content=self._build_content(),
            expand=True,
            bgcolor=theme.bg,
            padding=ft.padding.symmetric(horizontal=s(16), vertical=s(12)),
        )
        return self._body_container

    def _build_content(self) -> ft.Column:
        ff = theme.font_family
        emp = employee_service.get_employee(self._employee_id)

        # ── 身份信息行 ──
        certs = "+".join(emp.get("certifications", [])) if emp else ""
        shift_label = {"day": "白班", "night": "夜班"}.get(
            emp.get("shift", ""), "") if emp else ""
        info_text = f"{self._employee_name} ({self._employee_id})"
        if emp:
            info_text += f" · {emp['trade']}"
            if certs:
                info_text += f" · {certs}"
            if shift_label:
                info_text += f" · {shift_label}"

        info_row = ft.Row([
            ft.Container(
                content=ft.Icon(ft.Icons.ACCOUNT_CIRCLE, size=s(18),
                                color=theme.info),
            ),
            ft.Text(info_text, size=s(12), color=theme.text_primary, font_family=ff),
            ft.Container(expand=True),
            ft.TextButton(
                "切换登录",
                icon=ft.Icons.SWAP_HORIZ,
                style=ft.ButtonStyle(
                    bgcolor=ft.Colors.TRANSPARENT,
                    color=theme.text_primary,
                    overlay_color=theme.border_active,
                    shape=ft.RoundedRectangleBorder(radius=s(6)),
                    padding=ft.padding.symmetric(horizontal=s(8), vertical=s(4)),
                    text_style=ft.TextStyle(size=s(12), font_family=ff),
                ),
                on_click=lambda e: self._on_switch(),
            ),
        ], spacing=s(6), vertical_alignment=ft.CrossAxisAlignment.CENTER)

        # ── 任务区域 ──
        ready_tasks = self._get_ready_tasks()
        in_progress_tasks = self._get_in_progress_tasks()

        ready_section = self._build_task_section(
            "📋 待接单", ready_tasks, "ready",
            empty_text="暂无待接单任务",
        )

        in_progress_section = self._build_task_section(
            "🔧 进行中", in_progress_tasks, "in_progress",
            empty_text="暂无进行中的任务",
        )

        summary = ft.Text(
            f"待接单 {len(ready_tasks)} 项 · 进行中 {len(in_progress_tasks)} 项",
            size=s(11), color=theme.text_secondary, font_family=ff,
        )

        return ft.Column([
            info_row,
            ft.Container(height=s(10)),
            ft.Divider(height=1, color=theme.border),
            ft.Container(height=s(10)),
            ready_section,
            ft.Container(height=s(12)),
            in_progress_section,
            ft.Container(expand=True),
            ft.Container(
                content=summary,
                padding=ft.padding.only(top=s(8)),
                alignment=ft.alignment.center,
            ),
        ], spacing=0, scroll=ft.ScrollMode.AUTO, expand=True)

    # ── 数据获取 ──

    def _get_ready_tasks(self) -> list:
        return [t for t in state.get_tasks_by_column("ready")
                if t.employee_id == self._employee_id]

    def _get_in_progress_tasks(self) -> list:
        return [t for t in state.get_tasks_by_column("in_progress")
                if t.employee_id == self._employee_id]

    # ── 任务区域构建 ──

    def _build_task_section(self, title: str, tasks: list, section_type: str,
                            empty_text: str) -> ft.Container:
        ff = theme.font_family

        header = ft.Row([
            ft.Text(title, size=s(13), weight=ft.FontWeight.W_600,
                    color=theme.text_primary, font_family=ff),
            ft.Container(
                content=ft.Text(
                    str(len(tasks)), size=s(11),
                    color=theme.text_secondary, font_family=ff,
                ),
                bgcolor=theme.border_active,
                border_radius=s(10),
                padding=ft.padding.symmetric(horizontal=s(8), vertical=s(2)),
            ),
        ], spacing=s(8), vertical_alignment=ft.CrossAxisAlignment.CENTER)

        if not tasks:
            empty = ft.Container(
                content=ft.Text(empty_text, size=s(12),
                                color=theme.text_disabled, font_family=ff,
                                italic=True),
                padding=ft.padding.symmetric(horizontal=s(4), vertical=s(12)),
            )
            return ft.Container(
                content=ft.Column([header, empty], spacing=s(4)),
                bgcolor=theme.surface,
                border_radius=s(8),
                padding=ft.padding.all(s(12)),
            )

        cards = []
        for t in tasks:
            cards.append(self._make_task_card(t, section_type))

        return ft.Container(
            content=ft.Column([header] + cards, spacing=s(6)),
            bgcolor=theme.surface,
            border_radius=s(8),
            padding=ft.padding.all(s(12)),
        )

    # ── 任务卡片 ──

    def _make_task_card(self, task, section_type: str) -> ft.Container:
        ff = theme.font_family
        pc = theme.priority_color(task.priority.value)

        left_bar = ft.Container(width=s(4), bgcolor=pc,
                                border_radius=s(2), height=s(48))

        title_text = task.title[:45] + "…" if len(task.title) > 46 else task.title
        title_w = ft.Text(title_text, size=s(13), weight=ft.FontWeight.W_500,
                          color=theme.text_primary, font_family=ff,
                          max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)

        ac_info_parts = [task.work_order_id] if task.work_order_id else []
        if task.aircraft_reg:
            ac_info_parts.append(task.aircraft_reg)
        if task.ata_chapter:
            ac_info_parts.append(f"ATA {task.ata_chapter}")
        ac_info = " · ".join(ac_info_parts) if ac_info_parts else "未指定"
        subtitle = ft.Text(ac_info, size=s(11), color=theme.text_secondary,
                           font_family=ff, max_lines=1,
                           overflow=ft.TextOverflow.ELLIPSIS)

        info_col = ft.Column([title_w, subtitle], spacing=s(2), tight=True,
                             expand=True,
                             alignment=ft.MainAxisAlignment.CENTER)

        btn_text_style = ft.TextStyle(size=s(12), font_family=ff)

        if section_type == "ready":
            btn = ft.ElevatedButton(
                text="接单",
                icon=ft.Icons.DOWNLOAD_DONE,
                style=ft.ButtonStyle(
                    bgcolor=theme.success,
                    color=ft.Colors.WHITE,
                    shape=ft.RoundedRectangleBorder(radius=s(5)),
                    padding=ft.padding.symmetric(horizontal=s(10), vertical=s(4)),
                    text_style=btn_text_style,
                ),
                on_click=lambda e, t=task: self._act_accept(t),
            )
        else:
            # in_progress — 阻塞 + 提交验收
            done, total = task.checklist_progress()
            cl_text = f"清单 {done}/{total}" if total > 0 else ""
            btn_row_children = []

            # 黄色阻塞按钮
            btn_row_children.append(
                ft.ElevatedButton(
                    text="阻塞",
                    icon=ft.Icons.BLOCK,
                    style=ft.ButtonStyle(
                        bgcolor=theme.warning,
                        color=ft.Colors.WHITE,
                        shape=ft.RoundedRectangleBorder(radius=s(5)),
                        padding=ft.padding.symmetric(horizontal=s(10), vertical=s(4)),
                        text_style=btn_text_style,
                    ),
                    on_click=lambda e, t=task: self._act_block(t),
                ),
            )

            if cl_text:
                progress_pct = done / total if total > 0 else 0
                cl_color = theme.success if progress_pct == 1.0 else theme.warning
                btn_row_children.append(
                    ft.Text(cl_text, size=s(10), color=cl_color, font_family=ff),
                )
            btn_row_children.append(
                ft.ElevatedButton(
                    text="提交验收",
                    icon=ft.Icons.ASSIGNMENT_TURNED_IN_OUTLINED,
                    style=ft.ButtonStyle(
                        bgcolor=theme.info,
                        color=ft.Colors.WHITE,
                        shape=ft.RoundedRectangleBorder(radius=s(5)),
                        padding=ft.padding.symmetric(horizontal=s(10), vertical=s(4)),
                        text_style=btn_text_style,
                    ),
                    on_click=lambda e, t=task: self._act_submit(t),
                ),
            )
            btn = ft.Row(btn_row_children, spacing=s(8),
                        vertical_alignment=ft.CrossAxisAlignment.CENTER)

        content_row = ft.Row([
            left_bar,
            ft.Container(width=s(8)),
            info_col,
            ft.Container(width=s(8)),
            btn,
        ], spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER)

        return ft.Container(
            content=content_row,
            bgcolor=theme.card,
            border_radius=s(6),
            padding=ft.padding.symmetric(horizontal=s(10), vertical=s(8)),
            animate=ft.Animation(150, ft.AnimationCurve.EASE_OUT),
            on_hover=self._on_card_hover,
        )

    @staticmethod
    def _on_card_hover(e):
        if e.control and hasattr(e.control, 'bgcolor'):
            if e.data == "true":
                e.control.bgcolor = theme.card_hover
            else:
                e.control.bgcolor = theme.card
            e.control.update()

    # ── 刷新 ──

    def refresh(self):
        """重新加载状态并刷新 UI（原地更新，不替换容器）。"""
        if self._body_container is not None:
            self._body_container.content = self._build_content()
            self._body_container.update()

    # ── 工具函数 ──

    def _validate_task(self, task, expected_status: TaskStatus) -> bool:
        """校验任务状态和归属，返回是否通过。"""
        t = state.get_task(task.id)
        if not t:
            Toast.show(self._page, "任务不存在", "warning")
            return False
        if not employee_service.validate(self._employee_id):
            Toast.show(self._page, "当前员工不可用", "warning")
            return False
        if t.status != expected_status:
            Toast.show(self._page, "任务状态已变化，请刷新", "warning")
            return False
        if t.employee_id != self._employee_id:
            Toast.show(self._page, "该任务未指派给您", "warning")
            return False
        return True

    def _send_and_wait(self, action: str, task_id: str, params: dict | None = None) -> dict | None:
        """通过 socket 发送命令到主应用。
        返回最新状态字典，失败返回 None。
        """
        try:
            return self._client.send_command(
                action=action,
                task_id=task_id,
                employee_id=self._employee_id,
                employee_name=self._employee_name,
                params=params,
            )
        except Exception as e:
            Toast.show(self._page, f"发送命令失败: {e}", "warning")
            return None

    # ── 接单 ──

    def _act_accept(self, task):
        if not self._validate_task(task, TaskStatus.READY):
            return

        in_progress_col = state._columns.get("in_progress")
        if in_progress_col and in_progress_col.wip_limit:
            current_count = len(state.get_tasks_by_column("in_progress"))
            if current_count >= in_progress_col.wip_limit:
                Toast.show(self._page,
                    f"执行中列已达上限 ({in_progress_col.wip_limit})，请先完成现有任务",
                    "warning")
                return

        self._show_confirm_dialog(task)

    def _show_confirm_dialog(self, task):
        """接单确认 — OverlayDimmer 模态弹窗。"""
        ff = theme.font_family
        PANEL_W, PANEL_H = 440, 360
        close_ref = [None]
        btn_st = ft.TextStyle(size=s(12), font_family=ff)

        def do_accept(e):
            state_dict = self._send_and_wait("accept_task", task.id)
            if state_dict is not None:
                from app.core.state import state as app_state
                app_state.load_from_dict(state_dict)
                if close_ref[0]:
                    close_ref[0].close()
                    close_ref[0] = None
                self.refresh()
                Toast.show(self._page, "已接单，任务进入执行中", "success")

        def cancel(e):
            if close_ref[0]:
                close_ref[0].close()
                close_ref[0] = None

        content = ft.Column([
            ft.Container(height=s(30)),
            ft.Icon(ft.Icons.HELP_OUTLINE, size=s(36), color=theme.info),
            ft.Container(height=s(12)),
            ft.Text("确认接单", size=s(15), weight=ft.FontWeight.W_600,
                    color=theme.text_primary, font_family=ff),
            ft.Container(height=s(10)),
            ft.Text(f"任务: {task.title[:50]}", size=s(12),
                    color=theme.text_secondary, font_family=ff),
            ft.Text(
                f"{task.aircraft_reg or '未指定'} · ATA {task.ata_chapter or '无'} · 计划 {task.estimated_hours}h",
                size=s(11), color=theme.text_disabled, font_family=ff,
            ),
            ft.Container(height=s(8)),
            ft.Text("确认接单后将开始计时，任务移至「执行中」",
                    size=s(11), color=theme.warning, font_family=ff),
            ft.Container(height=s(20)),
            ft.Row([
                ft.ElevatedButton(text="取消", style=ft.ButtonStyle(
                    bgcolor=theme.border_active, color=theme.text_primary,
                    shape=ft.RoundedRectangleBorder(radius=s(6)),
                    text_style=btn_st), on_click=cancel),
                ft.ElevatedButton(text="确认接单", icon=ft.Icons.CHECK_CIRCLE_OUTLINE,
                    style=ft.ButtonStyle(
                        bgcolor=theme.success, color=ft.Colors.WHITE,
                        shape=ft.RoundedRectangleBorder(radius=s(6)),
                        text_style=btn_st), on_click=do_accept),
            ], spacing=s(12), alignment=ft.MainAxisAlignment.CENTER),
            ft.Container(expand=True),
        ], spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER)

        panel = ft.Container(
            content=ft.Container(content=content, bgcolor=theme.card,
                border_radius=s(10), padding=ft.padding.all(s(20))),
            width=PANEL_W, height=PANEL_H,
            border=ft.border.all(1, theme.border),
            border_radius=s(10),
            shadow=ft.BoxShadow(spread_radius=1, blur_radius=16,
                                 color=theme.dialog_shadow),
        )
        close_ref[0] = OverlayDimmer.open(
            self._page, panel, dim_opacity=0.5, on_dimmer_click=cancel)

    # ── 提交验收 ──

    def _act_submit(self, task):
        if not self._validate_task(task, TaskStatus.IN_PROGRESS):
            return

        done, total = task.checklist_progress()
        if total > 0 and done < total:
            Toast.show(self._page,
                f"检查清单未完成 ({done}/{total})，请确认是否继续提交", "warning")

        self._show_submit_dialog(task)

    def _show_submit_dialog(self, task):
        """提交验收 — OverlayDimmer 模态弹窗（含提交日志表单）。"""
        ff = theme.font_family
        PANEL_W, PANEL_H = 520, 480
        close_ref = [None]
        btn_st = ft.TextStyle(size=s(12), font_family=ff)

        log_field = ft.TextField(
            label="提交日志",
            hint_text="描述完成情况、发现的问题、遗留事项...",
            multiline=True, min_lines=4, max_lines=8,
            border_color=theme.border,
            focused_border_color=theme.info,
            bgcolor=theme.card_hover,
            text_style=ft.TextStyle(color=theme.form_text, size=s(13), font_family=ff),
            hint_style=ft.TextStyle(color=theme.text_disabled, size=s(11), font_family=ff),
            border_radius=s(6),
            content_padding=ft.padding.all(s(10)),
            dense=True,
            autofocus=True,
        )
        hours_field = ft.TextField(
            label="实际工时 (h)",
            hint_text="如 3.5",
            width=150,
            border_color=theme.border,
            focused_border_color=theme.info,
            bgcolor=theme.card_hover,
            text_style=ft.TextStyle(color=theme.form_text, size=s(13), font_family=ff),
            hint_style=ft.TextStyle(color=theme.text_disabled, size=s(11), font_family=ff),
            border_radius=s(6),
            content_padding=ft.padding.all(s(10)),
            dense=True,
        )
        if task.shift_handover_log:
            log_field.value = task.shift_handover_log
        if task.actual_hours:
            hours_field.value = str(task.actual_hours)

        def do_submit(e):
            log = (log_field.value or "").strip()
            if not log:
                Toast.show(self._page, "请填写提交日志", "warning")
                return
            try:
                actual_hours = float(hours_field.value or "0")
            except ValueError:
                actual_hours = 0

            state_dict = self._send_and_wait("submit_task", task.id, {
                "handover_log": log,
                "actual_hours": actual_hours,
            })
            if state_dict is not None:
                from app.core.state import state as app_state
                app_state.load_from_dict(state_dict)
                if close_ref[0]:
                    close_ref[0].close()
                    close_ref[0] = None
                self.refresh()
                Toast.show(self._page, "已提交验收请求", "success")

        def cancel(e):
            if close_ref[0]:
                close_ref[0].close()
                close_ref[0] = None

        content = ft.Column([
            ft.Container(height=s(16)),
            ft.Icon(ft.Icons.ASSIGNMENT_TURNED_IN_OUTLINED, size=s(36), color=theme.info),
            ft.Container(height=s(8)),
            ft.Text("提交验收", size=s(15), weight=ft.FontWeight.W_600,
                    color=theme.text_primary, font_family=ff),
            ft.Container(height=s(4)),
            ft.Text(f"任务: {task.title[:50]}", size=s(12),
                    color=theme.text_secondary, font_family=ff),
            ft.Container(height=s(10)),
            log_field,
            ft.Container(height=s(8)),
            hours_field,
            ft.Container(height=s(14)),
            ft.Row([
                ft.ElevatedButton(text="取消", style=ft.ButtonStyle(
                    bgcolor=theme.border_active, color=theme.text_primary,
                    shape=ft.RoundedRectangleBorder(radius=s(6)),
                    text_style=btn_st), on_click=cancel),
                ft.ElevatedButton(text="提交验收",
                    icon=ft.Icons.ASSIGNMENT_TURNED_IN_OUTLINED,
                    style=ft.ButtonStyle(
                        bgcolor=theme.info, color=ft.Colors.WHITE,
                        shape=ft.RoundedRectangleBorder(radius=s(6)),
                        text_style=btn_st), on_click=do_submit),
            ], spacing=s(12), alignment=ft.MainAxisAlignment.CENTER),
            ft.Container(expand=True),
        ], spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER)

        panel = ft.Container(
            content=ft.Container(content=content, bgcolor=theme.card,
                border_radius=s(10), padding=ft.padding.all(s(20))),
            width=PANEL_W, height=PANEL_H,
            border=ft.border.all(1, theme.border),
            border_radius=s(10),
            shadow=ft.BoxShadow(spread_radius=1, blur_radius=16,
                                 color=theme.dialog_shadow),
        )
        close_ref[0] = OverlayDimmer.open(
            self._page, panel, dim_opacity=0.5, on_dimmer_click=cancel)

    # ── 阻塞 ──

    def _act_block(self, task):
        if not self._validate_task(task, TaskStatus.IN_PROGRESS):
            return
        self._show_block_dialog(task)

    def _show_block_dialog(self, task):
        """阻塞原因 — OverlayDimmer 模态弹窗。"""
        ff = theme.font_family
        PANEL_W, PANEL_H = 520, 440
        close_ref = [None]
        btn_st = ft.TextStyle(size=s(12), font_family=ff)

        reason_field = ft.TextField(
            hint_text="请输入阻塞原因（如：缺料、待排故、等工具...）",
            multiline=True, min_lines=3, max_lines=5,
            border_color=theme.border,
            focused_border_color=theme.warning,
            bgcolor=theme.card_hover,
            text_style=ft.TextStyle(color=theme.form_text, size=s(13), font_family=ff),
            hint_style=ft.TextStyle(color=theme.text_disabled, size=s(11), font_family=ff),
            border_radius=s(6),
            content_padding=ft.padding.all(s(10)),
            dense=True, autofocus=True,
        )

        def do_block(e):
            reason = (reason_field.value or "").strip()
            if not reason:
                Toast.show(self._page, "请输入阻塞原因", "warning")
                return
            state_dict = self._send_and_wait("block_task", task.id, {"reason": reason})
            if state_dict is not None:
                from app.core.state import state as app_state
                app_state.load_from_dict(state_dict)
                if close_ref[0]:
                    close_ref[0].close()
                    close_ref[0] = None
                self.refresh()
                Toast.show(self._page, "已发送阻塞请求", "success")

        def cancel(e):
            if close_ref[0]:
                close_ref[0].close()
                close_ref[0] = None

        content = ft.Column([
            ft.Container(height=s(20)),
            ft.Icon(ft.Icons.BLOCK, size=s(36), color=theme.warning),
            ft.Container(height=s(12)),
            ft.Text("确认阻塞任务", size=s(15), weight=ft.FontWeight.W_600,
                    color=theme.text_primary, font_family=ff),
            ft.Container(height=s(8)),
            ft.Text(f"任务: {task.title[:50]}", size=s(12),
                    color=theme.text_secondary, font_family=ff),
            ft.Text(f"{task.aircraft_reg or '未指定'} · ATA {task.ata_chapter or '无'} · 计划 {task.estimated_hours}h",
                    size=s(11), color=theme.text_disabled, font_family=ff),
            ft.Container(height=s(12)),
            ft.Container(content=reason_field, width=480),
            ft.Container(height=s(6)),
            ft.Text("阻塞后任务将移至「阻塞中」列", size=s(11),
                    color=theme.warning, font_family=ff),
            ft.Container(height=s(16)),
            ft.Row([
                ft.ElevatedButton(text="取消", style=ft.ButtonStyle(
                    bgcolor=theme.border_active, color=theme.text_primary,
                    shape=ft.RoundedRectangleBorder(radius=s(6)),
                    text_style=btn_st), on_click=cancel),
                ft.ElevatedButton(text="确认阻塞", icon=ft.Icons.BLOCK,
                    style=ft.ButtonStyle(
                        bgcolor=theme.warning, color=ft.Colors.WHITE,
                        shape=ft.RoundedRectangleBorder(radius=s(6)),
                        text_style=btn_st), on_click=do_block),
            ], spacing=s(12), alignment=ft.MainAxisAlignment.CENTER),
            ft.Container(expand=True),
        ], spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER)

        panel = ft.Container(
            content=ft.Container(content=content, bgcolor=theme.card,
                border_radius=s(10), padding=ft.padding.all(s(20))),
            width=PANEL_W, height=PANEL_H,
            border=ft.border.all(1, theme.border),
            border_radius=s(10),
            shadow=ft.BoxShadow(spread_radius=1, blur_radius=16,
                                 color=theme.dialog_shadow),
        )
        close_ref[0] = OverlayDimmer.open(
            self._page, panel, dim_opacity=0.5, on_dimmer_click=cancel)
