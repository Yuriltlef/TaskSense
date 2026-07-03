# -*- coding: utf-8 -*-
"""任务详情面板."""

import flet as ft
from app.config.theme import theme, s
from app.core.models.task import Task
from app.ui.widgets.badge import ATABadge, PriorityBadge, StatusBadge, TaskTypeBadge


class SidePanel(ft.Container):
    def __init__(self, on_close=None, on_edit=None, **_kw):
        super().__init__(
            width=theme.side_panel_width, bgcolor=theme.surface,
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
            style=ft.ButtonStyle(
                bgcolor=ft.Colors.TRANSPARENT,
                overlay_color=ft.Colors.RED_900,
                shape=ft.RoundedRectangleBorder(radius=s(4))),
            on_click=lambda e: self.close())
        edit_btn = ft.IconButton(
            icon=ft.Icons.EDIT_OUTLINED, icon_size=s(16),
            icon_color=theme.text_secondary,
            tooltip=ft.Tooltip(message="Edit", bgcolor=theme.card,
                text_style=ft.TextStyle(color=ft.Colors.WHITE, font_family=theme.font_family)),
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
                    PriorityBadge(t.priority.value if hasattr(t.priority, "value") else str(t.priority), size="md"),
                    StatusBadge(t.status.value if hasattr(t.status, "value") else str(t.status), size="md"),
                    TaskTypeBadge(t.task_type.value if hasattr(t.task_type, "value") else str(t.task_type), size="md"),
                    ATABadge(t.ata_chapter, "md") if t.ata_chapter
                    else ft.Text(""),
                ], spacing=s(6), wrap=True),
                ft.Container(height=s(6)),
                ft.Text(f"工卡号  {t.work_order_id or t.id}", size=s(13),
                        color=theme.text_primary, font_family=ff,
                        weight=ft.FontWeight.W_700,
                        text_align=ft.TextAlign.CENTER),
            ], spacing=0, tight=True, alignment=ft.MainAxisAlignment.CENTER,
               horizontal_alignment=ft.CrossAxisAlignment.CENTER),
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

        emp_display = t.assignee or "未分配"
        if t.employee_name:
            emp_display = t.employee_name
        if t.employee_id:
            emp_display += f" ({t.employee_id})"
        time_items = [_kv("负责人", emp_display, icon=ft.Icons.PERSON_OUTLINED)]
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
        # 计划时间
        if t.planned_start:
            time_items.append(_kv("计划开始",
                                   t.planned_start.strftime("%Y-%m-%d %H:%M"),
                                   icon=ft.Icons.PLAY_ARROW_OUTLINED))
        if t.planned_end:
            time_items.append(_kv("计划完成",
                                   t.planned_end.strftime("%Y-%m-%d %H:%M"),
                                   icon=ft.Icons.STOP_OUTLINED))
        # 剩余时间倒计时
        if t.status.value in ("ready", "in_progress") and t.planned_end:
            rem = t.remaining_time
            if rem is not None:
                if rem < 0:
                    cd_label = "已逾期"
                    cd_color = theme.error
                    rem_str = f"-{int(abs(rem) // 60)}h {int(abs(rem) % 60)}m"
                else:
                    cd_label = "剩余时间"
                    cd_color = theme.success if rem > 14400 else (
                        theme.warning if rem > 3600 else theme.error)
                    rem_str = f"{int(rem // 60)}h {int(rem % 60)}m"
                time_items.append(_kv(cd_label, rem_str, color=cd_color,
                                       icon=ft.Icons.TIMER_OUTLINED))
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

        # ── 阻塞状态 ──
        if t.is_blocked or t.status.value == "parts_hold":
            block_items = [
                ft.Row([
                    ft.Icon(ft.Icons.BLOCK_OUTLINED, size=s(14), color=theme.error),
                    ft.Text("任务已阻塞", size=s(12), color=theme.error,
                            weight=ft.FontWeight.W_600, font_family=ff),
                ], spacing=s(6)),
            ]
            if t.block_reason:
                block_items.append(
                    ft.Text(f"原因: {t.block_reason}", size=s(11),
                            color=theme.text_secondary, font_family=ff))
            # 取消阻塞按钮
            block_items.append(ft.Container(height=s(6)))
            block_items.append(
                ft.ElevatedButton("取消阻塞", icon=ft.Icons.LOCK_OPEN_OUTLINED,
                    style=ft.ButtonStyle(
                        bgcolor=theme.error, color=ft.Colors.WHITE,
                        shape=ft.RoundedRectangleBorder(radius=s(6)),
                        padding=ft.padding.symmetric(horizontal=s(14), vertical=s(6)),
                        text_style=ft.TextStyle(size=s(11), font_family=ff)),
                    on_click=lambda e, tid=t.id: self._unblock(tid)))
            sections.append(_section("阻塞状态", block_items))

        # ── 交接班日志 ──
        if t.shift_handover_log:
            sections.append(_section("交接班日志", [
                ft.Text(t.shift_handover_log, size=s(12), color="#c0c0c0", font_family=ff),
            ]))

        # ── AI 审核区域（仅 inspection 状态）──
        if t.status.value == "inspection":
            sections.append(self._build_ai_review(t, ff))

        body = ft.Column([badges] + sections, spacing=g, tight=True)

        return ft.Column([
            header,
            ft.ListView([
                ft.Container(body, padding=ft.padding.only(
                    left=g, right=g, top=s(4), bottom=s(12))),
            ], spacing=0, expand=True, padding=0),
        ], spacing=0, tight=True, expand=True)

    def _unblock(self, task_id: str):
        """取消阻塞，返回就绪列。"""
        from app.core.services.task_service import task_service
        from app.ui.widgets.toast import Toast
        try:
            task_service.unblock_task(task_id, user="user")
            # 刷新面板
            from app.core.state import state
            t = state.get_task(task_id)
            if t:
                self.open_task(t)
            Toast.show(self.page, "已取消阻塞，任务返回就绪列", "success")
        except Exception as e:
            from app.ui.widgets.toast import Toast
            Toast.show(self.page, f"取消失败: {e}", "error")

    def _build_ai_review(self, t, ff):
        """AI 审核区域 — 调用 Agent + JSON 美化渲染。"""
        import json, re, threading
        s_ = s

        # ── 加载动画 ──
        progress = ft.ProgressRing(width=s_(14), height=s_(14), visible=False)
        status_text = ft.Text("", size=s_(11), color=theme.text_secondary, font_family=ff)

        # ── 辅助：迷你分区 ──
        def _mini_section(title: str, items: list, ff_: str, s__):
            return ft.Container(
                ft.Column([
                    ft.Text(title, size=s__(10), weight=ft.FontWeight.W_600,
                            color=theme.text_secondary, font_family=ff_),
                    ft.Container(height=s__(4)),
                    ft.Column(items, spacing=s__(4), tight=True),
                ], spacing=0, tight=True),
                bgcolor="#0a0a0a",
                border_radius=s__(6),
                padding=ft.padding.all(s__(8)),
            )

        # ── 结果容器 ──
        result_col = ft.Column([], spacing=s_(8), tight=True, visible=False)
        error_text = ft.Text("", size=s_(11), color=theme.error, font_family=ff, visible=False)

        def _parse_response(raw: str) -> dict | None:
            """尝试解析 AI 返回的 JSON。"""
            if not raw:
                return None
            # 去掉 ```json ... ``` 围栏
            m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', raw, re.DOTALL)
            if m:
                raw = m.group(1)
            # 找第一个 JSON 对象
            m = re.search(r'\{[^{}]*\}', raw, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group())
                except json.JSONDecodeError:
                    pass
            return None

        def _render_json(data: dict):
            """将 JSON 评审结果渲染为美化卡片。"""
            result_col.controls.clear()

            rec = data.get("recommendation", "")
            conf = data.get("confidence", 0)
            summary = data.get("summary", "")
            reasons = data.get("reasons", [])
            missing = data.get("missing_items", [])
            comp_notes = data.get("compliance_notes", "")
            actions = data.get("suggested_actions", [])
            risk = data.get("risk_level", "")

            rec_config = {
                "approve": ("✅ 建议通过", theme.success, ft.Icons.CHECK_CIRCLE_OUTLINE),
                "reject": ("🔴 建议驳回", theme.error, ft.Icons.CANCEL_OUTLINED),
                "need_more_info": ("⚠ 需要补充信息", theme.warning, ft.Icons.INFO_OUTLINE),
            }
            rec_label, rec_color, rec_icon = rec_config.get(rec, ("📋 审核意见", theme.info, ft.Icons.PSYCHOLOGY_OUTLINED))

            # 标题行：结论 + 置信度
            result_col.controls.append(
                ft.Container(
                    ft.Row([
                        ft.Icon(rec_icon, size=s_(16), color=rec_color),
                        ft.Text(rec_label, size=s_(13), weight=ft.FontWeight.W_600,
                                color=rec_color, font_family=ff),
                        ft.Container(expand=True),
                        ft.Text(f"置信度 {conf:.0%}" if isinstance(conf, (int, float)) else "",
                                size=s_(10), color=theme.text_secondary, font_family=ff),
                    ], spacing=s_(6)),
                    bgcolor=ft.Colors.with_opacity(0.08, rec_color),
                    border_radius=s_(6),
                    padding=ft.padding.all(s_(10)),
                )
            )

            # 摘要
            if summary:
                result_col.controls.append(
                    ft.Text(summary, size=s_(11), color="#c0c0c0", font_family=ff))

            # 原因
            if reasons:
                items = []
                for r in reasons:
                    items.append(ft.Row([
                        ft.Text("•", size=s_(11), color=theme.text_secondary, font_family=ff),
                        ft.Text(r, size=s_(11), color="#c0c0c0", font_family=ff),
                    ], spacing=s_(6)))
                result_col.controls.append(_mini_section("驳回原因" if rec == "reject" else "审核要点", items, ff, s_))

            # 缺失项
            if missing:
                items = []
                for m in missing:
                    items.append(ft.Row([
                        ft.Icon(ft.Icons.ERROR_OUTLINE, size=s_(12), color=theme.warning),
                        ft.Text(m, size=s_(11), color=theme.warning, font_family=ff),
                    ], spacing=s_(6)))
                result_col.controls.append(_mini_section("缺失项", items, ff, s_))

            # 合规说明
            if comp_notes:
                result_col.controls.append(_mini_section("合规说明", [
                    ft.Text(comp_notes, size=s_(10), color=theme.text_secondary, font_family=ff),
                ], ff, s_))

            # 建议操作
            if actions:
                items = []
                for i, a in enumerate(actions, 1):
                    items.append(ft.Row([
                        ft.Text(f"{i}.", size=s_(11), color=theme.info, font_family=ff),
                        ft.Text(a, size=s_(11), color="#c0c0c0", font_family=ff),
                    ], spacing=s_(6)))
                result_col.controls.append(_mini_section("建议操作", items, ff, s_))

            # 风险等级
            if risk:
                risk_colors = {"low": theme.success, "medium": theme.warning, "high": theme.error}
                rc = risk_colors.get(risk, theme.text_secondary)
                result_col.controls.append(
                    ft.Container(
                        ft.Row([
                            ft.Icon(ft.Icons.WARNING_AMBER_OUTLINED, size=s_(12), color=rc),
                            ft.Text(f"风险等级: {risk.upper()}", size=s_(10),
                                    color=rc, weight=ft.FontWeight.W_600, font_family=ff),
                        ], spacing=s_(6)),
                        bgcolor=ft.Colors.with_opacity(0.06, rc),
                        border_radius=s_(6),
                        padding=ft.padding.symmetric(horizontal=s_(10), vertical=s_(6)),
                    )
                )

        def _render_text(raw: str):
            """纯文本回退渲染。"""
            result_col.controls.clear()
            result_col.controls.append(
                ft.Text(raw, size=s_(11), color="#c0c0c0", font_family=ff))

        def _ai_suggest(e):
            progress.visible = True; status_text.value = "正在分析提交材料..."; status_text.visible = True
            result_col.visible = False; error_text.visible = False
            progress.update(); status_text.update(); result_col.update()
            try:
                from app.ui.services.agent_service import AgentService
                result = AgentService.review_submission(t.id)
                data = _parse_response(result)
                if data:
                    _render_json(data)
                else:
                    _render_text(result)
                result_col.visible = True
            except Exception as ex:
                error_text.value = f"获取失败: {ex}"
                error_text.visible = True
            progress.visible = False; status_text.visible = False
            progress.update(); status_text.update(); result_col.update(); error_text.update()

        def _reject(e):
            from app.core.services.task_service import task_service
            from app.ui.widgets.toast import Toast
            try:
                task_service.move_task(t.id, "in_progress", changed_by="reviewer")
                from app.core.models.log_entry import LogType
                from app.core.services.log_service import log_service
                log_service.log(LogType.REVIEW_REJECT, task_id=t.id,
                                task_title=t.title, user="reviewer",
                                description="审核驳回，返回执行中")
                Toast.show(self.page, "已驳回，任务返回执行中", "warning")
                self.close()
            except Exception as ex:
                Toast.show(self.page, f"操作失败: {ex}", "error")

        def _approve(e):
            from app.core.services.task_service import task_service
            from app.ui.widgets.toast import Toast
            try:
                task_service.move_task(t.id, "completed", changed_by="reviewer")
                from app.core.models.log_entry import LogType
                from app.core.services.log_service import log_service
                log_service.log(LogType.REVIEW_APPROVE, task_id=t.id,
                                task_title=t.title, user="reviewer",
                                description="审核通过")
                Toast.show(self.page, "审核通过，任务已完成", "success")
                self.close()
            except Exception as ex:
                Toast.show(self.page, f"操作失败: {ex}", "error")

        return ft.Container(
            ft.Column([
                ft.Text("AI 审核", size=s_(11), weight=ft.FontWeight.W_600,
                        color=theme.text_primary, font_family=ff),
                ft.Container(height=s_(6)),
                ft.Row([progress, status_text], spacing=s_(8)),
                result_col,
                error_text,
                ft.Container(height=s_(8)),
                ft.Row([
                    ft.ElevatedButton("AI 建议", icon=ft.Icons.PSYCHOLOGY_OUTLINED,
                        on_click=_ai_suggest,
                        style=ft.ButtonStyle(
                            bgcolor=theme.info, color=ft.Colors.WHITE,
                            shape=ft.RoundedRectangleBorder(radius=s_(6)),
                            padding=ft.padding.symmetric(horizontal=s_(12), vertical=s_(6)),
                            text_style=ft.TextStyle(size=s_(11), font_family=ff))),
                    ft.OutlinedButton("驳回", icon=ft.Icons.CANCEL_OUTLINED,
                        on_click=_reject,
                        style=ft.ButtonStyle(
                            color=theme.error,
                            side=ft.BorderSide(1, theme.error),
                            shape=ft.RoundedRectangleBorder(radius=s_(6)),
                            padding=ft.padding.symmetric(horizontal=s_(12), vertical=s_(6)),
                            text_style=ft.TextStyle(size=s_(11), font_family=ff))),
                    ft.ElevatedButton("同意", icon=ft.Icons.CHECK_OUTLINED,
                        on_click=_approve,
                        style=ft.ButtonStyle(
                            bgcolor=theme.success, color=ft.Colors.WHITE,
                            shape=ft.RoundedRectangleBorder(radius=s_(6)),
                            padding=ft.padding.symmetric(horizontal=s_(12), vertical=s_(6)),
                            text_style=ft.TextStyle(size=s_(11), font_family=ff))),
                ], spacing=s_(8)),
            ], spacing=0, tight=True),
            bgcolor="#111111",
            border_radius=s_(8),
            padding=ft.padding.all(s_(12)),
        )