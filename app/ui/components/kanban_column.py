"""看板列组件 — 列间拖拽 + 列内排序（卡片级 DragTarget）.

架构规则（Flet 0.28.3 限制）：
1. 不能有列级 DragTarget 包裹 Draggable → 否则同列 on_accept 全抑制
2. Draggable 不设 on_drag_update → 此版本不存在
3. 每张卡片 = DragTarget(Draggable(TaskCard))
   - Draggable 是 DragTarget 的子孙，但拖到其他卡片的 DragTarget 时
     目标 DragTarget 不是该 Draggable 的祖先 → on_accept 正常触发

插入位置算法（关键简化）：
  拖到卡片 K 上 → insert_idx = K 的下标
  同列时从 src_idx 移除后，目标卡片下标天然已偏移到位
  跨列时无移除，直接插入目标下标
"""

import json

import flet as ft
from app.config.constants import ALLOWED_TRANSITIONS
from app.config.theme import theme, s
from app.core.models.kanban import ColumnConfig
from app.core.models.task import Task
from app.ui.components.task_card import TaskCard

# 模块级拖拽上下文
_drag_ctx: dict | None = None


class KanbanColumn(ft.Container):
    """看板列。

    控件层级（每张卡片 = 放置目标 + 拖拽源）——

      ListView (spacing=8, padding=8)
        DragTarget(data={"col":cid, "idx":0})     ← 放到此处 = 插到 Card_0 前
          Draggable(data={"tid":.., "col":cid, "idx":0})
            TaskCard
        DragTarget(data={"col":cid, "idx":1})
          Draggable(...)
            TaskCard
        ...
        DragTarget(data={"col":cid, "idx":N})     ← 底部放置区 = 插到队尾
          Container("拖放到此处")

    没有列级 DragTarget！否则同列的 Draggable 被视为其子孙
    → 所有 DragTarget.on_accept 全被抑制。
    """

    def __init__(self, column: ColumnConfig, tasks: list[Task],
                 on_card_click=None, on_card_context_menu=None,
                 on_drop=None, on_column_menu=None):
        self.column = column
        self._on_cc = on_card_click
        self._on_ccm = on_card_context_menu
        self._on_drop = on_drop
        self._on_cm = on_column_menu
        self._collapsed = False

        # 列边框高亮
        self._drag_over_count = 0
        self._allowed = True  # 当前拖拽是否允许放入本列

        # 所有卡片级 DragTarget 引用（用于高亮清除）
        self._card_targets: list[ft.DragTarget] = []
        # 当前高亮的目标
        self._highlighted_target: ft.DragTarget | None = None

        self.card_list = ft.ListView(
            controls=self._build_cards(tasks),
            spacing=s(8),
            padding=ft.padding.all(s(8)),
            expand=True,
        )

        self._body = ft.Container(
            content=ft.Column([
                ft.Divider(height=1, color=theme.divider),
                ft.Container(content=self.card_list, expand=True),
            ], spacing=0),
            expand=True,
        )

        super().__init__(
            content=ft.Column([self._header(), self._body], spacing=0),
            width=theme.column_width,
            bgcolor=theme.surface,
            border_radius=s(10),
            animate=ft.Animation(200, ft.AnimationCurve.EASE_OUT),
        )

    # ═══════════════════════ 构建 ═══════════════════════

    def _build_cards(self, tasks: list[Task]):
        self._card_targets.clear()
        self._highlighted_target = None
        cards = []

        for i, t in enumerate(tasks):
            dt = ft.DragTarget(
                content=ft.Draggable(
                    content=TaskCard(t, on_click=self._on_cc,
                                    on_context_menu=self._on_ccm),
                    data=json.dumps(
                        {"tid": t.id, "col": self.column.id, "idx": i}),
                    content_feedback=TaskCard(t, ghost=True),
                    content_when_dragging=TaskCard(t, ghost=True),
                    on_drag_start=self._on_drag_start,
                    on_drag_complete=self._on_drag_complete,
                ),
                data=json.dumps({"col": self.column.id, "idx": i}),
                on_accept=self._on_card_drop,
                on_will_accept=self._on_card_will_accept,
                on_leave=self._on_card_leave,
            )
            self._card_targets.append(dt)
            cards.append(dt)

        # 底部放置区：idx = len(tasks) → 追加到队尾
        bottom_zone = ft.DragTarget(
            content=ft.Container(
                height=s(56),
                border_radius=s(8),
                border=ft.border.all(
                    1, ft.Colors.with_opacity(0.06, ft.Colors.WHITE)),
                content=ft.Row([
                    ft.Icon(ft.Icons.ADD, size=s(12),
                            color=theme.text_disabled),
                    ft.Text("拖放到此处", size=s(10),
                            color=theme.text_disabled,
                            font_family=theme.font_family),
                ], spacing=s(4), alignment=ft.MainAxisAlignment.CENTER),
                alignment=ft.alignment.center,
            ),
            data=json.dumps({"col": self.column.id, "idx": len(tasks)}),
            on_accept=self._on_card_drop,
            on_will_accept=self._on_bottom_will_accept,
            on_leave=self._on_bottom_leave,
        )
        self._card_targets.append(bottom_zone)
        cards.append(bottom_zone)
        return cards

    # ═══════════════════════ 列头 ═══════════════════════

    def _header(self):
        col = self.column
        ff = theme.font_family
        wc = wcol = theme.text_secondary
        txt = ""
        if col.wip_limit:
            txt = f" {col.task_count}/{col.wip_limit}"
            if col.wip_exceeded:
                wcol = theme.error
            elif col.wip_percentage > 0.7:
                wcol = theme.warning

        return ft.Container(
            content=ft.Row([
                ft.Container(width=3, height=s(18),
                             bgcolor=theme.column_header, border_radius=2),
                ft.Text(col.title, size=theme.font_sm,
                        weight=ft.FontWeight.W_600,
                        color=theme.text_primary, font_family=ff),
                ft.Text(txt, size=theme.font_xs, color=wcol,
                        weight=ft.FontWeight.W_600
                        if col.wip_exceeded else ft.FontWeight.W_400,
                        font_family=ff),
                ft.Container(expand=True),
                ft.IconButton(
                    icon=ft.Icons.MORE_HORIZ, icon_size=s(16),
                    icon_color=theme.text_disabled,
                    tooltip=ft.Tooltip(
                        message=f"{col.title} — 排序/折叠",
                        bgcolor=theme.card,
                        text_style=ft.TextStyle(font_family=ff)),
                    on_click=lambda e: self._on_cm
                    and self._on_cm(col.id)),
                ft.IconButton(
                    icon=ft.Icons.EXPAND_LESS if not self._collapsed
                    else ft.Icons.EXPAND_MORE,
                    icon_size=s(16), icon_color=theme.text_disabled,
                    tooltip=ft.Tooltip(
                        message="折叠/展开", bgcolor=theme.card,
                        text_style=ft.TextStyle(font_family=ff)),
                    on_click=self._toggle_collapse),
            ], spacing=s(6)),
            padding=ft.padding.only(left=s(12), top=s(6),
                                    right=s(6), bottom=s(6)),
        )

    def _toggle_collapse(self, e):
        self._collapsed = not self._collapsed
        cols = self.content.controls
        header_row = cols[0].content
        if self._collapsed:
            cols[1].visible = False
            for ctrl in header_row.controls:
                if isinstance(ctrl, ft.IconButton) and ctrl.icon in (
                    ft.Icons.EXPAND_LESS, ft.Icons.EXPAND_MORE
                ):
                    ctrl.icon = ft.Icons.EXPAND_MORE
        else:
            cols[1].visible = True
            for ctrl in header_row.controls:
                if isinstance(ctrl, ft.IconButton) and ctrl.icon in (
                    ft.Icons.EXPAND_LESS, ft.Icons.EXPAND_MORE
                ):
                    ctrl.icon = ft.Icons.EXPAND_LESS
        self.update()

    # ═══════════════════════ 拖拽事件 ═══════════════════════

    def _on_drag_start(self, e):
        global _drag_ctx
        try:
            _drag_ctx = json.loads(e.control.data)
        except (json.JSONDecodeError, TypeError):
            _drag_ctx = None

    def _on_drag_complete(self, e):
        """拖拽结束 — 清理全局状态和高亮。"""
        global _drag_ctx
        _drag_ctx = None
        self._drag_over_count = 0
        self._clear_column_highlight()
        self._clear_highlight()
        if self.page:
            self.update()

    def _on_card_drop(self, e):
        """卡片级 DragTarget.on_accept — 列内排序 + 跨列移动。"""
        global _drag_ctx
        ctx = _drag_ctx
        _drag_ctx = None
        self._drag_over_count = 0
        self._clear_column_highlight()
        self._clear_highlight()

        if not ctx or not self._on_drop:
            return

        tid = ctx.get("tid")
        src_col = ctx.get("col")
        src_idx = ctx.get("idx")

        try:
            target = json.loads(e.control.data)
        except (json.JSONDecodeError, TypeError):
            return
        target_col = target["col"]
        target_idx = target["idx"]

        if not tid:
            return

        # 跨列不可达 → 静默拒绝（红色边框已提示用户）
        if src_col != target_col and not self._is_transition_allowed(src_col):
            return

        # ── 插入位置 ──
        if src_col == target_col and src_idx is not None:
            if src_idx == target_idx:
                return
            insert_idx = target_idx
        else:
            insert_idx = target_idx

        self._on_drop(tid, target_col, insert_idx)

        if self.page:
            self.update()

    # ═══════════════════════ 状态转换检查 ═══════════════════════

    def _is_transition_allowed(self, src_col: str) -> bool:
        """检查从 src_col 到本列是否允许。同列永远允许。"""
        if src_col == self.column.id:
            return True
        allowed = ALLOWED_TRANSITIONS.get(src_col, [])
        return self.column.id in allowed

    # ═══════════════════════ 视觉：列边框 ═══════════════════════

    def _show_column_border(self):
        """根据当前拖拽上下文显示列边框（蓝=可放，红=不可达）。"""
        src_col = _drag_ctx.get("col") if _drag_ctx else None
        if src_col and src_col != self.column.id:
            self._allowed = self._is_transition_allowed(src_col)
        else:
            self._allowed = True  # 同列 / 无上下文
        color = theme.info if self._allowed else theme.error
        self.border = ft.border.all(2, color)
        if self.page:
            self.update()

    def _inc_drag_over(self):
        self._drag_over_count += 1
        if self._drag_over_count == 1:
            self._show_column_border()

    def _dec_drag_over(self):
        self._drag_over_count = max(0, self._drag_over_count - 1)
        if self._drag_over_count == 0:
            self._clear_column_highlight()

    def _clear_column_highlight(self):
        self.border = None
        self._drag_over_count = 0
        self._allowed = True

    # ═══════════════════════ 视觉：卡片 DragTarget ═══════════════════════

    def _on_card_will_accept(self, e):
        """拖入卡片 → 列边框 + 卡片上边框高亮。"""
        self._inc_drag_over()
        self._clear_highlight()
        self._highlighted_target = e.control
        border_color = theme.info if self._allowed else theme.error
        try:
            card = e.control.content.content  # DragTarget → Draggable → TaskCard
            if isinstance(card, ft.Container):
                card.border = ft.border.only(
                    top=ft.BorderSide(width=3, color=border_color))
                card.update()
        except Exception:
            pass

    def _on_card_leave(self, e):
        self._dec_drag_over()
        try:
            card = e.control.content.content
            if isinstance(card, ft.Container):
                card.border = None
                card.update()
        except Exception:
            pass
        if self._highlighted_target is e.control:
            self._highlighted_target = None

    # ── 底部放置区视觉 ──

    def _on_bottom_will_accept(self, e):
        self._inc_drag_over()
        self._clear_highlight()
        self._highlighted_target = e.control
        border_color = theme.info if self._allowed else theme.error
        try:
            e.control.content.border = ft.border.all(2, border_color)
            e.control.content.update()
        except Exception:
            pass

    def _on_bottom_leave(self, e):
        self._dec_drag_over()
        try:
            e.control.content.border = ft.border.all(
                1, ft.Colors.with_opacity(0.06, ft.Colors.WHITE))
            e.control.content.update()
        except Exception:
            pass
        if self._highlighted_target is e.control:
            self._highlighted_target = None

    # ═══════════════════════ 清理 ═══════════════════════

    def _clear_highlight(self):
        if self._highlighted_target is not None:
            try:
                dt = self._highlighted_target
                inner = dt.content.content if hasattr(dt.content, 'content') else dt.content
                if isinstance(inner, ft.Container):
                    inner.border = None
                    inner.update()
            except Exception:
                pass
            self._highlighted_target = None

    # ═══════════════════════ 公开接口 ═══════════════════════

    def update_tasks(self, tasks: list[Task]):
        self.card_list.controls = self._build_cards(tasks)
        self.column.task_count = len(tasks)
        self.update()
