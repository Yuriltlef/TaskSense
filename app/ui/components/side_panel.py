# -*- coding: utf-8 -*-
"""任务详情面板."""

import flet as ft
from app.config.theme import theme, s
from app.core.models.task import Task
from app.ui.widgets.badge import ATABadge, PriorityBadge, StatusBadge, TaskTypeBadge


class SidePanel(ft.Container):
    def __init__(self, on_close=None, on_edit=None, **_kw):
        super().__init__(
            width=theme.side_panel_width, bgcolor="#161616",
            border=ft.border.only(left=ft.BorderSide(1, theme.border)),
            visible=False, padding=0,
        )
        self._on_close = on_close
        self._on_edit = on_edit
        self._task = None

    @property
    def is_open(self): return self.visible

    def open_task(self, task: Task):
        self._task = task; self.visible = True
        self.content = self._build(); self.update()

    def close(self):
        self.visible = False; self._task = None; self.update()
        if self._on_close: self._on_close()

    def toggle_task(self, task: Task):
        if self.visible and self._task and self._task.id == task.id:
            self.close()
        else:
            self.open_task(task)

    def _build(self):
        t = self._task
        if not t:
            return ft.Text("No data", color=theme.text_disabled)
        ff = theme.font_family
        g = s(16)

        close_btn = ft.IconButton(
            icon=ft.Icons.CLOSE, icon_size=s(16),
            icon_color=theme.text_secondary,
            on_click=lambda e: self.close())
        edit_btn = ft.IconButton(
            icon=ft.Icons.EDIT_OUTLINED, icon_size=s(16),
            icon_color=theme.text_secondary,
            tooltip=ft.Tooltip(message="Edit", bgcolor=theme.card),
            on_click=lambda e: self._on_edit and self._on_edit(t))

        header = ft.Container(
            ft.Row([
                ft.Text("任务详情", size=s(14), weight=ft.FontWeight.W_600,
                        color=theme.text_primary, font_family=ff),
                ft.Container(expand=True),
                edit_btn, close_btn,
            ], spacing=s(4)),
            padding=ft.padding.only(
                left=g, top=s(6), right=s(4), bottom=s(6)),
            border=ft.border.only(
                bottom=ft.BorderSide(1, theme.border)),
        )

        badges = ft.Container(
            ft.Column([
                ft.Row([
                    PriorityBadge(t.priority.value if hasattr(t.priority, "value") else str(t.priority)),
                    StatusBadge(t.status.value if hasattr(t.status, "value") else str(t.status)),
                    TaskTypeBadge(t.task_type.value if hasattr(t.task_type, "value") else str(t.task_type)),
                    ATABadge(t.ata_chapter) if t.ata_chapter
                    else ft.Text(""),
                ], spacing=s(6), wrap=True),
                ft.Container(height=s(4)),
                ft.Text(f"工卡号  {t.id}", size=s(10),
                        color=theme.text_disabled, font_family=ff),
            ], spacing=0, tight=True),
            padding=ft.padding.only(
                left=g, right=g, top=s(10), bottom=s(6)),
        )

        def _lbl(txt):
            return ft.Text(txt, size=s(10),
                           color=theme.text_secondary, font_family=ff)

        def _val(value, icon=None, color=None):
            c = color or theme.text_primary
            row_ctrls = []
            if icon:
                row_ctrls.append(ft.Icon(icon, size=s(13), color=c))
            row_ctrls.append(ft.Text(str(value), size=s(12), color=c, font_family=ff))
            return ft.Row(row_ctrls, spacing=s(6))

        def _section(title, children):
            return ft.Container(
                ft.Column([
                    ft.Text(title, size=s(11),
                            weight=ft.FontWeight.W_600,
                            color=theme.text_primary, font_family=ff),
                    ft.Container(height=s(6)),
                    ft.Column(children, spacing=s(6), tight=True),
                ], spacing=0, tight=True),
                bgcolor="#111111",
                border_radius=s(8),
                padding=ft.padding.all(s(12)),
            )

        def _kv(label, value, icon=None, color=None):
            return ft.Container(
                ft.Column([
                    _lbl(label),
                    _val(value, icon=icon, color=color),
                ], spacing=s(2), tight=True),
            )

        def _kv2(label_a, val_a, label_b, val_b):
            return ft.Container(
                ft.Row([
                    ft.Container(ft.Column([
                        _lbl(label_a),
                        _val(val_a),
                    ], spacing=s(2), tight=True), expand=True),
                    ft.Container(ft.Column([
                        _lbl(label_b),
                        _val(val_b),
                    ], spacing=s(2), tight=True), expand=True),
                ], spacing=s(12)),
            )

        sections = []

        info_fields = [_kv("标题", t.title)]
        reg_text = str(t.aircraft_reg) if t.aircraft_reg else ""
        if t.aircraft_model:
            reg_text += f" / {t.aircraft_model}"
        sections.append(_section("基本信息", [
            _kv("标题", t.title),
            _kv2("飞机注册号", reg_text or "未指定", "ATA 章节", t.ata_chapter or "未分类"),
            _kv2("区域", t.zone or "未指定", "故障码", t.fault_code or "无"),
        ]))

        time_items = [_kv("负责人", t.assignee or "未分配",
                           icon=ft.Icons.PERSON_OUTLINED)]
        time_items.append(_kv2("预估工时",
                               f"{t.estimated_hours}h" if t.estimated_hours else "未设置",
                               "实际工时",
                               f"{t.actual_hours}h" if t.actual_hours else "未设置"))
        if t.created_by or t.inspector:
            time_items.append(_kv2("创建者", t.created_by or "-",
                                   "检查员 (RII)", t.inspector or "-"))
        if t.due_date:
            dc = theme.error if t.is_overdue else theme.info
            ds = t.due_date.strftime("%Y-%m-%d")
            overdue_label = " (已逾期)" if t.is_overdue else ""
            time_items.append(_kv("完成期限",
                                   f"{ds}{overdue_label}",
                                   icon=ft.Icons.CALENDAR_TODAY_OUTLINED,
                                   color=dc))
        time_items.append(_kv("创建时间", t.created_at.strftime("%Y-%m-%d %H:%M")))
        time_items.append(_kv("最后更新", t.updated_at.strftime("%Y-%m-%d %H:%M")))
        sections.append(_section("人员与时间", time_items))

        if t.description:
            sections.append(ft.Container(
                ft.Column([
                    ft.Text("任务描述", size=s(11),
                            weight=ft.FontWeight.W_600,
                            color=theme.text_primary, font_family=ff),
                    ft.Container(height=s(6)),
                    ft.Text(t.description, size=s(12),
                            color="#c0c0c0", font_family=ff),
                ], spacing=0, tight=True),
                bgcolor="#111111",
                border_radius=s(8),
                padding=ft.padding.all(s(12)),
            ))

        done, total = t.checklist_progress()
        if total > 0:
            pct = done / total
            sections.append(ft.Container(
                ft.Column([
                    ft.Text(f"检查清单 ({done}/{total})", size=s(11),
                            weight=ft.FontWeight.W_600,
                            color=theme.text_primary, font_family=ff),
                    ft.Container(height=s(6)),
                    ft.ProgressBar(
                        value=pct, color=theme.success,
                        bgcolor=theme.border, height=s(4)),
                ], spacing=0, tight=True),
                bgcolor="#111111",
                border_radius=s(8),
                padding=ft.padding.all(s(12)),
            ))

        tags = []
        if t.is_rii:
            tags.append(ft.Container(
                ft.Row([
                    ft.Icon(ft.Icons.WARNING_AMBER, size=s(13), color=theme.error),
                    ft.Text("必检项目 (RII)", size=s(11), color=theme.error,
                            weight=ft.FontWeight.W_600, font_family=ff),
                ], spacing=s(6)),
                padding=ft.padding.symmetric(horizontal=s(10), vertical=s(6)),
                border_radius=s(6),
                border=ft.border.all(1, ft.Colors.with_opacity(0.25, theme.error)),
                bgcolor=ft.Colors.with_opacity(0.06, theme.error),
            ))
        if not t.parts_available:
            tags.append(ft.Container(
                ft.Row([
                    ft.Icon(ft.Icons.INVENTORY_2_OUTLINED, size=s(13),
                            color=theme.warning),
                    ft.Text("零件待确认", size=s(11), color=theme.warning,
                            font_family=ff),
                ], spacing=s(6)),
                padding=ft.padding.symmetric(horizontal=s(10), vertical=s(6)),
                border_radius=s(6),
                border=ft.border.all(1, ft.Colors.with_opacity(0.25, theme.warning)),
                bgcolor=ft.Colors.with_opacity(0.06, theme.warning),
            ))
        if tags:
            sections.append(ft.Container(
                ft.Column(tags, spacing=s(6), tight=True),
                padding=ft.padding.only(left=g, right=g, top=s(0), bottom=s(8)),
            ))

        body = ft.Column([badges] + sections, spacing=g, tight=True)

        return ft.ListView([header, ft.Container(
            body, padding=ft.padding.only(
                left=g, right=g, top=s(4), bottom=s(12))),
        ], spacing=0, expand=True, padding=0)