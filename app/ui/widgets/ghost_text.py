# -*- coding: utf-8 -*-
"""幽灵文本输入 — 内联 ghost text + chip 建议条。

用法:
    gf = GhostTextField(hint_text="输入...", field_name="title",
                        on_field_filled=callback, get_context=lambda: {...})

Page 键盘接入:
    page.on_keyboard_event = lambda e: handle_ghost_keyboard(e) or old_handler(e)
"""

import flet as ft
from app.config.theme import theme, s
from app.ui.widgets.ai_suggestion_bar import AISuggestionBar
from app.ui.services.ai_completion import AICompletionService
from app.core.logging import log


# 全局注册：有活跃幽灵文本的字段 → Tab 接受
_active_ghost_fields: list = []


def handle_ghost_keyboard(e: ft.KeyboardEvent) -> bool:
    """Ctrl+Space → 接受第一条活跃幽灵建议。Esc → 清除。"""
    if e.ctrl and e.key == " ":
        for gf in _active_ghost_fields:
            if gf._ghost_value:
                gf._accept_ghost()
                e.handled = True
                return True
    elif e.key == "Escape":
        for gf in _active_ghost_fields:
            if gf._ghost_value:
                gf._clear_ghost()
                e.handled = True
                return True
    return False


class GhostTextField(ft.Column):
    """AI 增强输入字段 — 内联幽灵文本 + 下方建议 chip 条。

    内联幽灵文本是一个灰色 Text，紧贴在 TextField 右侧（同一行），
    模拟 IDE inline completion 效果。
    """

    def __init__(
        self,
        hint_text: str = "",
        field_name: str = "title",
        multiline: bool = False,
        min_lines: int = 1,
        width: int | None = None,
        on_change=None,
        on_field_filled=None,
        get_context=None,
        **_kw,
    ):
        super().__init__(spacing=s(2), tight=True)

        self.field_name = field_name
        self._on_field_filled = on_field_filled
        self._get_context = get_context
        self._ghost_value = ""         # 幽灵补充文本
        self._ghost_target = field_name  # 幽灵文本的目标字段
        self._suggestions: list[dict] = []
        self._has_focus = False

        ff = theme.font_family

        # ── 幽灵文本（灰色，紧跟在输入框右侧）──
        self._ghost_text = ft.Text(
            "",
            size=s(12),
            color=theme.text_disabled,
            font_family=ff,
            italic=True,
        )

        # ── 输入框（透明背景 + 无边线；外层 Container 提供边框）──
        self.text_field = ft.TextField(
            hint_text=hint_text,
            border=ft.InputBorder.NONE,   # 无边线——外层 Container 画
            cursor_color=theme.info,
            cursor_width=1.5,
            text_style=ft.TextStyle(color="#e0e0e0", size=s(13), font_family=ff),
            hint_style=ft.TextStyle(color=theme.text_secondary, size=s(12), font_family=ff),
            bgcolor=ft.Colors.TRANSPARENT,
            dense=True,
            multiline=multiline,
            min_lines=min_lines,
            max_lines=min_lines + 3,
            content_padding=ft.padding.only(left=s(10), top=s(8), right=0, bottom=s(8)),
            width=width,
            on_change=self._on_text_change,
            on_focus=self._on_focus,
            on_blur=self._on_blur,
        )

        # ── 幽灵提示标签 ──
        self._tab_hint = ft.Text(
            "Ctrl+Space",
            size=s(9),
            color=ft.Colors.with_opacity(0.4, theme.text_disabled),
            font_family=ff,
            visible=False,
        )

        # ── 外层 Container（画边框，容纳 TextField + ghost + Tab hint）──
        self._outer = ft.Container(
            content=ft.Row([
                self.text_field,
                self._ghost_text,
                self._tab_hint,
                ft.Container(width=s(4)),  # 右侧留白
            ], spacing=s(2), tight=True,
               vertical_alignment=ft.CrossAxisAlignment.CENTER),
            border=ft.border.all(1, theme.border),
            border_radius=s(6),
            bgcolor=theme.card,
        )

        # ── AI 建议条 ──
        self.suggestion_bar = AISuggestionBar()

        # ── AI 补全服务 ──
        self._completion = AICompletionService(on_ready=self._on_suggestions_ready)
        self._user_on_change = on_change

        self.controls = [self._outer, self.suggestion_bar]

    # ── 公开属性 ──

    @property
    def value(self) -> str:
        return self.text_field.value or ""

    @value.setter
    def value(self, v: str):
        self.text_field.value = v or ""
        self._clear_ghost()

    @property
    def ghost_target(self) -> str:
        """幽灵文本的目标填充字段名。"""
        return self._ghost_target

    # ── 边框控制（兼容外部 _error / _clear 样式）──

    @property
    def border_color(self):
        return self._outer.border.color if hasattr(self._outer.border, 'color') else theme.border

    @border_color.setter
    def border_color(self, c):
        self._outer.border = ft.border.all(1, c)
        try: self._outer.update()
        except Exception: pass

    @property
    def hint_text(self):
        return self.text_field.hint_text

    @hint_text.setter
    def hint_text(self, t):
        self.text_field.hint_text = t
        try: self.text_field.update()
        except Exception: pass

    def update(self):
        try:
            self._outer.update()
            super().update()
        except Exception:
            pass

    # ── 内部 ──

    def _on_focus(self, e):
        self._has_focus = True
        _active_ghost_fields.append(self)
        log.trace("ghost.focus", field=self.field_name)
        # 聚焦时基于上下文触发 AI 补全（即使不输入）
        self._trigger_completion()

    def _on_blur(self, e):
        self._has_focus = False
        if self in _active_ghost_fields:
            _active_ghost_fields.remove(self)

    def _on_text_change(self, e):
        val = (e.control.value or "").strip()
        log.trace("ghost.input", field=self.field_name, text=val[:40])
        self._clear_ghost()

        if self._user_on_change:
            self._user_on_change(val)

        self._trigger_completion()

    def _trigger_completion(self):
        """基于当前字段值 + 全表单上下文触发 AI 补全。"""
        ctx = {}
        if self._get_context:
            ctx = self._get_context()
        self._completion.on_input_changed(self.value, self.field_name, ctx)

    def _on_suggestions_ready(self, suggestions: list[dict], source: str):
        """AI 返回建议 —— 智能过滤 + 排序。"""
        if source == "empty" or not suggestions:
            self._clear_all()
            return

        my_field = self.field_name

        # ── 约束字段只显示自己类型的 tip（ATA/注册号/区域/员工ID/优先级）──
        _constrained = {"ata_chapter", "aircraft_reg", "zone", "employee_id",
                        "employee_name", "task_type"}
        if my_field in _constrained:
            suggestions = [s for s in suggestions if s["field"] == my_field]
        # 描述/标题字段显示全部（自由文本字段需要跨字段上下文）

        if not suggestions:
            self._clear_all()
            return

        # 排序：当前字段优先
        sorted_sugs = sorted(suggestions, key=lambda s: (0 if s["field"] == my_field else 1))

        # 只在有意义时显示：当前字段非空 OR 上下文已有其他数据
        ctx = self._get_context() if self._get_context else {}
        has_context = any(v for k, v in ctx.items() if k != my_field and v)
        is_typing = bool(self.value)
        if not is_typing and not has_context:
            self._clear_all()
            return

        self._suggestions = sorted_sugs

        # 幽灵文本：取非当前字段的最优建议
        _ghost_order = {"description": 0, "ata_chapter": 1, "title": 2, "zone": 3, "task_type": 4,
                        "employee_name": 5}
        best = None
        best_score = 999
        for s in sorted_sugs:
            if s["field"] == my_field:
                continue
            score = _ghost_order.get(s["field"], 99)
            if score < best_score and s.get("value"):
                best_score = score
                best = s

        if best:
            self._ghost_value = best["value"]
            self._ghost_target = best["field"]
            self._ghost_text.value = best["value"]
            self._ghost_text.visible = True
            self._tab_hint.visible = True
            try:
                self._ghost_text.update()
                self._tab_hint.update()
            except Exception:
                pass

        # 所有建议显示为 chip（已排序，当前字段优先）
        self.suggestion_bar.show_suggestions(
            self._suggestions,
            on_chip_click=self._on_chip_clicked,
        )
        log.info("ghost.suggestions", field=self.field_name,
                 ghost=self._ghost_value[:20], chips=len(suggestions), source=source)

    def _on_chip_clicked(self, field: str, value: str):
        """点击 chip → 填入对应字段。"""
        log.info("ghost.chip_accept", field=field, value=value[:30])
        if self._on_field_filled:
            self._on_field_filled(field, value)
        self._clear_all()

    def _accept_ghost(self):
        """Tab 键：接受内联幽灵文本。"""
        if self._ghost_value and self._on_field_filled:
            log.info("ghost.tab_accept", target=self._ghost_target, value=self._ghost_value[:30])
            self._on_field_filled(self._ghost_target, self._ghost_value)
        self._clear_all()

    def _clear_ghost(self):
        """清除内联幽灵文本。"""
        self._ghost_value = ""
        self._ghost_target = self.field_name
        self._ghost_text.value = ""
        self._ghost_text.visible = False
        self._tab_hint.visible = False
        try:
            self._ghost_text.update()
            self._tab_hint.update()
        except Exception:
            pass

    def _clear_all(self):
        """清除幽灵文本 + chip 建议。"""
        self._clear_ghost()
        self._suggestions = []
        self.suggestion_bar.clear()
        self._completion.cancel()
