"""员工工作台 — 接单 / 提交验收."""

from datetime import datetime
import flet as ft

from app.config.theme import theme, s
from app.core.state import state
from app.core.services.employee_service import employee_service
from app.core.services.task_service import task_service
from app.core.models.task import TaskStatus
from app.ui.widgets.overlay_dimmer import OverlayDimmer
from app.ui.widgets.toast import Toast


class EmployeeWorkbench:
    """员工工作台 overlay 页面。

    两种状态：
    - 状态 A：未选择身份 → 员工下拉选择器
    - 状态 B：已选择身份 → 待接单 + 进行中任务列表
    """

    _panel: ft.Container | None = None
    _dimmer: OverlayDimmer | None = None
    _page: ft.Page | None = None
    _open: bool = False
    _body: ft.Container | None = None
    _state_listener = None

    # ── 打开 / 关闭 ──

    @classmethod
    def open(cls, page: ft.Page):
        if cls._open:
            return
        cls._page = page
        cls._open = True
        cls._build()
        cls._dimmer = OverlayDimmer.open(
            page, cls._panel,
            dim_opacity=0.65,
            on_dimmer_click=lambda: cls.close(),
            on_close=lambda: cls._on_external_close(),
        )
        # 订阅状态变更——看板移动任务时自动刷新
        cls._state_listener = lambda: cls._on_state_changed()
        state.subscribe(cls._state_listener)
        page.update()

    @classmethod
    def close(cls):
        if not cls._open:
            return
        cls._open = False
        if cls._state_listener:
            state.unsubscribe(cls._state_listener)
            cls._state_listener = None
        if cls._dimmer:
            cls._dimmer.close()
            cls._dimmer = None
        if cls._page:
            cls._page.update()

    @classmethod
    def _on_external_close(cls):
        """被其他弹窗顶掉时重置 _open 状态（dimmer 已被 OverlayDimmer 关闭）。"""
        cls._open = False
        cls._dimmer = None
        if cls._state_listener:
            state.unsubscribe(cls._state_listener)
            cls._state_listener = None

    @classmethod
    def _on_state_changed(cls):
        """状态变更后刷新任务列表。"""
        if not cls._open or not cls._page:
            return
        if state.current_employee_id:
            cls._rebuild_body_state_b()
            if cls._page:
                cls._page.update()

    # ── 构建 ──

    @classmethod
    def _build(cls):
        ff = theme.font_family
        PANEL_W, PANEL_H = 700, 740

        cls._header = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.PERSON_OUTLINE, size=s(18), color=theme.info),
                ft.Text("员工工作台", size=s(16), weight=ft.FontWeight.W_600,
                        color=theme.text_primary, font_family=ff),
                ft.Container(expand=True),
                ft.IconButton(
                    icon=ft.Icons.CLOSE, icon_size=s(16),
                    icon_color=theme.text_secondary,
                    width=s(28), height=s(28),
                    style=ft.ButtonStyle(
                        bgcolor=ft.Colors.TRANSPARENT,
                        overlay_color=theme.border_active,
                        shape=ft.RoundedRectangleBorder(radius=s(4)),
                    ),
                    on_click=lambda e: cls.close(),
                ),
            ], spacing=s(8), vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.padding.only(left=s(16), top=s(6), right=s(8), bottom=s(6)),
            bgcolor=theme.surface,
            border=ft.border.only(
                bottom=ft.BorderSide(1, theme.border)),
        )

        cls._body = ft.Container(
            padding=ft.padding.symmetric(horizontal=s(16), vertical=s(12)),
            expand=True,
        )
        if state.current_employee_id:
            cls._rebuild_body_state_b()
        else:
            cls._rebuild_body_state_a()

        cls._footer = ft.Container(
            content=ft.Row([
                ft.Container(expand=True),
                ft.TextButton(
                    "关闭",
                    style=ft.ButtonStyle(
                        bgcolor=ft.Colors.TRANSPARENT,
                        overlay_color=theme.border_active,
                        shape=ft.RoundedRectangleBorder(radius=s(6)),
                        padding=ft.padding.symmetric(horizontal=s(16), vertical=s(6)),
                    ),
                    on_click=lambda e: cls.close(),
                ),
            ], spacing=s(8)),
            padding=ft.padding.only(left=s(16), top=s(8), right=s(16), bottom=s(10)),
            bgcolor=theme.surface,
            border=ft.border.only(
                top=ft.BorderSide(1, theme.border)),
        )

        inner = ft.Container(
            content=ft.Column([
                cls._header,
                cls._body,
                cls._footer,
            ], spacing=0, tight=True, expand=True),
            bgcolor=theme.card,
            border_radius=s(10),
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            expand=True,
        )

        cls._panel = ft.Container(
            content=inner,
            width=PANEL_W, height=PANEL_H,
            border=ft.border.all(1, theme.border),
            border_radius=s(10),
            shadow=ft.BoxShadow(spread_radius=1, blur_radius=16,
                                 color=theme.dialog_shadow),
        )

    # ═══════════════════════════════
    # 状态 A：选择员工身份
    # ═══════════════════════════════

    @classmethod
    def _rebuild_body_state_a(cls):
        ff = theme.font_family
        cls._selected_emp_id = None

        employees = employee_service.get_available_employees()

        # ── 搜索框 ──
        cls._emp_search_field = ft.TextField(
            hint_text="按姓名、ID 或工种搜索...",
            border_color=theme.border,
            focused_border_color=theme.info,
            bgcolor=theme.card_hover,
            text_style=ft.TextStyle(color=theme.form_text, size=s(13), font_family=ff),
            hint_style=ft.TextStyle(color=theme.text_disabled, size=s(11), font_family=ff),
            border_radius=s(6),
            dense=True,
            autofocus=True,
            on_change=lambda e: cls._on_emp_search(e, cls._emp_search_field, employees, results_list, ff),
        )

        # ── 搜索结果列表 ──
        results_list = ft.Column(spacing=0, tight=True)
        # 初始显示全部
        cls._populate_emp_list(results_list, employees, ff, "")

        tip = ft.Text(
            "请选择您的员工身份以查看指派给您的任务",
            size=s(11), color=theme.text_secondary, font_family=ff,
            italic=True,
        )

        confirm_btn = ft.ElevatedButton(
            text="确认身份",
            icon=ft.Icons.CHECK_CIRCLE_OUTLINE,
            style=ft.ButtonStyle(
                bgcolor=theme.info,
                color=ft.Colors.WHITE,
                shape=ft.RoundedRectangleBorder(radius=s(6)),
                padding=ft.padding.symmetric(horizontal=s(16), vertical=s(8)),
            ),
            on_click=lambda e: cls._on_confirm_identity(),
        )

        cls._body.content = ft.Column([
            ft.Container(height=s(12)),
            ft.Icon(ft.Icons.BADGE_OUTLINED, size=s(34), color=theme.border_active),
            ft.Container(height=s(6)),
            tip,
            ft.Container(height=s(10)),
            ft.Container(content=cls._emp_search_field, width=580),
            ft.Container(height=s(8)),
            ft.Container(
                content=ft.Column([
                    results_list,
                ], spacing=0, scroll=ft.ScrollMode.AUTO),
                width=580,
                bgcolor=theme.surface,
                border_radius=s(6),
                border=ft.border.all(1, theme.border),
                expand=True,
            ),
            ft.Container(height=s(10)),
            confirm_btn,
            ft.Container(height=s(10)),
        ], spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER)

    @classmethod
    def _populate_emp_list(cls, results_list, employees, ff, filter_text):
        """填充员工列表。"""
        results_list.controls.clear()
        q = filter_text.lower().strip() if filter_text else ""
        filtered = employees
        if q:
            filtered = [e for e in employees
                        if q in e["name"] or q in e["employee_id"].lower()
                        or q in e.get("trade", "")]

        for emp in filtered:
            certs = "+".join(emp.get("certifications", [])[:2])
            label = f"{emp['name']}  {emp['employee_id']}  {emp['trade']}"
            if certs:
                label += f"  {certs}"

            is_selected = cls._selected_emp_id == emp["employee_id"]
            bg = theme.border_active if is_selected else theme.card

            results_list.controls.append(
                ft.Container(
                    content=ft.Text(label, size=s(13), font_family=ff,
                                    color=theme.text_primary),
                    bgcolor=bg,
                    padding=ft.padding.symmetric(horizontal=s(14), vertical=s(12)),
                    border_radius=s(4),
                    on_click=lambda e, eid=emp["employee_id"]: cls._on_emp_select(
                        eid, results_list, employees, ff, cls._emp_search_field),
                )
            )

    @classmethod
    def _on_emp_select(cls, eid, results_list, employees, ff, search_field=None):
        """选中某个员工。"""
        cls._selected_emp_id = eid
        cls._populate_emp_list(results_list, employees, ff, "")
        if search_field:
            emp = employee_service.get_employee(eid)
            if emp:
                search_field.value = f"{emp['name']} ({emp['employee_id']})"
                search_field.update()

    @classmethod
    def _on_emp_search(cls, e, search_field, employees, results_list, ff):
        """搜索过滤。"""
        cls._populate_emp_list(results_list, employees, ff,
                               search_field.value or "")

    @classmethod
    def _on_confirm_identity(cls):
        emp_id = cls._selected_emp_id
        if not emp_id:
            Toast.show(cls._page, "请先选择员工", "warning")
            return
        emp = employee_service.get_employee(emp_id)
        if not emp:
            Toast.show(cls._page, "员工不存在", "warning")
            return
        state.current_employee_id = emp_id
        state.current_employee_name = emp["name"]
        cls._rebuild_body_state_b()
        cls._page.update()
        Toast.show(cls._page, f"已切换为 {emp['name']} ({emp_id})", "success")

    # ═══════════════════════════════
    # 状态 B：任务列表
    # ═══════════════════════════════

    @classmethod
    def _rebuild_body_state_b(cls):
        ff = theme.font_family
        emp = employee_service.get_employee(state.current_employee_id)
        if not emp:
            # 员工数据异常，退回选择
            state.current_employee_id = ""
            state.current_employee_name = ""
            cls._rebuild_body_state_a()
            return

        # ── 身份信息行 ──
        certs = "+".join(emp.get("certifications", []))
        shift_label = {"day": "白班", "night": "夜班"}.get(emp.get("shift", ""), "")
        info_text = f"{emp['name']} ({emp['employee_id']}) · {emp['trade']}"
        if certs:
            info_text += f" · {certs}"
        if shift_label:
            info_text += f" · {shift_label}"

        info_row = ft.Row([
            ft.Container(
                content=ft.Icon(ft.Icons.ACCOUNT_CIRCLE, size=s(18), color=theme.info),
            ),
            ft.Text(info_text, size=s(12), color=theme.text_primary, font_family=ff),
            ft.Container(expand=True),
            ft.TextButton(
                "切换身份",
                icon=ft.Icons.SWAP_HORIZ,
                style=ft.ButtonStyle(
                    bgcolor=ft.Colors.TRANSPARENT,
                    overlay_color=theme.border_active,
                    shape=ft.RoundedRectangleBorder(radius=s(6)),
                    padding=ft.padding.symmetric(horizontal=s(8), vertical=s(4)),
                ),
                on_click=lambda e: cls._on_switch_identity(),
            ),
        ], spacing=s(6), vertical_alignment=ft.CrossAxisAlignment.CENTER)

        # ── 待接单区域 ──
        ready_tasks = [
            t for t in state.get_tasks_by_column("ready")
            if t.employee_id == state.current_employee_id
        ]
        ready_section = cls._build_task_section(
            "📋 待接单", ready_tasks, "ready",
            empty_text="暂无待接单任务",
        )

        # ── 进行中区域 ──
        in_progress_tasks = [
            t for t in state.get_tasks_by_column("in_progress")
            if t.employee_id == state.current_employee_id
        ]
        in_progress_section = cls._build_task_section(
            "🔧 进行中", in_progress_tasks, "in_progress",
            empty_text="暂无进行中的任务",
        )

        summary = ft.Text(
            f"待接单 {len(ready_tasks)} 项 · 进行中 {len(in_progress_tasks)} 项",
            size=s(11), color=theme.text_secondary, font_family=ff,
        )

        cls._body.content = ft.Column([
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

    @classmethod
    def _on_switch_identity(cls):
        state.current_employee_id = ""
        state.current_employee_name = ""
        cls._rebuild_body_state_a()
        cls._page.update()

    # ═══════════════════════════════
    # 任务区域构建
    # ═══════════════════════════════

    @classmethod
    def _build_task_section(cls, title: str, tasks: list, section_type: str,
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
        for task in tasks:
            cards.append(cls._make_task_card(task, section_type))

        return ft.Container(
            content=ft.Column([header] + cards, spacing=s(6)),
            bgcolor=theme.surface,
            border_radius=s(8),
            padding=ft.padding.all(s(12)),
        )

    # ═══════════════════════════════
    # 任务卡片
    # ═══════════════════════════════

    @classmethod
    def _make_task_card(cls, task, section_type: str) -> ft.Container:
        ff = theme.font_family
        pc = theme.priority_color(task.priority.value)

        # ── 左色带 + 内容 ──
        left_bar = ft.Container(width=s(4), bgcolor=pc,
                                border_radius=s(2), height=s(48))

        title_text = task.title[:45] + "…" if len(task.title) > 46 else task.title
        title = ft.Text(title_text, size=s(13), weight=ft.FontWeight.W_500,
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

        info_col = ft.Column([title, subtitle], spacing=s(2), tight=True,
                             expand=True,
                             alignment=ft.MainAxisAlignment.CENTER)

        # ── 操作按钮 ──
        if section_type == "ready":
            btn = ft.ElevatedButton(
                text="接单",
                icon=ft.Icons.DOWNLOAD_DONE,
                style=ft.ButtonStyle(
                    bgcolor=theme.success,
                    color=ft.Colors.WHITE,
                    shape=ft.RoundedRectangleBorder(radius=s(5)),
                    padding=ft.padding.symmetric(horizontal=s(10), vertical=s(4)),
                ),
                on_click=lambda e, t=task: cls._act_accept(t),
            )
        else:
            # in_progress
            done, total = task.checklist_progress()
            cl_text = f"清单 {done}/{total}" if total > 0 else ""
            btn_row_children = []
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
                    ),
                    on_click=lambda e, t=task: cls._act_submit(t),
                ),
            )
            btn = ft.Row(btn_row_children, spacing=s(8),
                        vertical_alignment=ft.CrossAxisAlignment.CENTER)

        # ── 组装 ──
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
            on_hover=lambda e, c=None: cls._on_card_hover(e),
        )

    @staticmethod
    def _on_card_hover(e):
        if e.control and hasattr(e.control, 'bgcolor'):
            if e.data == "true":
                e.control.bgcolor = theme.card_hover
            else:
                e.control.bgcolor = theme.card
            e.control.update()

    # ═══════════════════════════════
    # 接单
    # ═══════════════════════════════

    @classmethod
    def _act_accept(cls, task):
        tid = task.id
        t = state.get_task(tid)
        if not t:
            Toast.show(cls._page, "任务不存在", "warning")
            return

        # 1. 校验员工可用
        if not employee_service.validate(state.current_employee_id):
            Toast.show(cls._page, "当前员工不可用", "warning")
            return

        # 2. 校验任务状态
        if t.status != TaskStatus.READY:
            Toast.show(cls._page, "任务状态已变化，请刷新", "warning")
            return

        # 3. 校验归属
        if t.employee_id != state.current_employee_id:
            Toast.show(cls._page, "该任务未指派给您", "warning")
            return

        # 4. WIP 检查
        in_progress_col = state._columns.get("in_progress")
        if in_progress_col and in_progress_col.wip_limit:
            current_count = len(state.get_tasks_by_column("in_progress"))
            if current_count >= in_progress_col.wip_limit:
                Toast.show(
                    cls._page,
                    f"执行中列已达上限 ({in_progress_col.wip_limit})，请先完成现有任务",
                    "warning",
                )
                return

        # 5. 确认弹窗
        cls._show_confirm_dialog(t)

    @classmethod
    def _show_confirm_dialog(cls, task):
        """接单确认 — 内联替换 body 内容，不依赖 AlertDialog."""
        ff = theme.font_family

        # 保存原 body 内容
        _prev_body = cls._body.content

        def do_accept(e):
            try:
                if not task.planned_start:
                    task_service.update_task(
                        task.id, planned_start=datetime.now())
                task_service.move_task(
                    task.id, "in_progress",
                    changed_by=state.current_employee_name,
                )
                cls._rebuild_body_state_b()
                cls._page.update()
                Toast.show(cls._page, "已接单，任务进入执行中", "success")
            except Exception as ex:
                cls._body.content = _prev_body
                cls._page.update()
                Toast.show(cls._page, str(ex), "warning")

        def cancel(e):
            cls._body.content = _prev_body
            cls._page.update()

        content = ft.Column([
            ft.Container(height=s(40)),
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
                ft.ElevatedButton(
                    text="取消",
                    style=ft.ButtonStyle(
                        bgcolor=theme.border_active,
                        color=theme.text_primary,
                        shape=ft.RoundedRectangleBorder(radius=s(6)),
                    ),
                    on_click=cancel,
                ),
                ft.ElevatedButton(
                    text="确认接单",
                    icon=ft.Icons.CHECK_CIRCLE_OUTLINE,
                    style=ft.ButtonStyle(
                        bgcolor=theme.success,
                        color=ft.Colors.WHITE,
                        shape=ft.RoundedRectangleBorder(radius=s(6)),
                    ),
                    on_click=do_accept,
                ),
            ], spacing=s(12), alignment=ft.MainAxisAlignment.CENTER),
            ft.Container(expand=True),
        ], spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER)

        cls._body.content = content
        cls._page.update()

    # ═══════════════════════════════
    # 提交验收
    # ═══════════════════════════════

    @classmethod
    def _act_submit(cls, task):
        tid = task.id
        t = state.get_task(tid)
        if not t:
            Toast.show(cls._page, "任务不存在", "warning")
            return

        # 1. 校验任务状态
        if t.status != TaskStatus.IN_PROGRESS:
            Toast.show(cls._page, "任务状态已变化，请刷新", "warning")
            return

        # 2. 校验归属
        if t.employee_id != state.current_employee_id:
            Toast.show(cls._page, "该任务未指派给您", "warning")
            return

        # 3. checklist 进度警告（不阻断）
        done, total = t.checklist_progress()
        if total > 0 and done < total:
            Toast.show(
                cls._page,
                f"检查清单未完成 ({done}/{total})，请确认是否继续提交",
                "warning",
            )

        # 4. 打开提交弹窗
        from app.ui.dialogs.submit_dialog import open as dlg_submit
        dlg_submit(cls._page, tid, changed_by=state.current_employee_name)
