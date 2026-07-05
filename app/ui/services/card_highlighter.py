# -*- coding: utf-8 -*-
"""卡片高亮管理器 — 右键选中蓝色描边 + AI 运行橙色描边。

用法：
    CardHighlighter.init(kanban_board)          # board_page.build() 中注册看板引用
    CardHighlighter.select(tid)                 # 右键打开菜单时
    CardHighlighter.deselect()                  # 菜单关闭/动作执行后
    CardHighlighter.set_ai_running(tid)         # AI 工具开始运行
    CardHighlighter.clear_ai_running()          # AI 工具结束
"""

import flet as ft
from app.config.theme import theme


class CardHighlighter:
    """管理任务卡片高亮状态。

    类级别单例 — 所有 TaskCard 实例在 __init__ 中检查本类的状态来设置初始 border，
    运行时通过 _find_card 在控件树中定位卡片并直接 .update()。
    """

    _selected_tid: str | None = None    # 右键选中 → 蓝色
    _ai_active_tid: str | None = None   # AI 运行中 → 橙色
    _kanban_board = None                # KanbanBoard 引用（控件树入口）

    # ── 初始化 ──

    @classmethod
    def init(cls, kanban_board):
        """注册看板引用（board_page.build() 中调用）。"""
        cls._kanban_board = kanban_board

    # ── 查询（TaskCard.__init__ 调用）──

    @classmethod
    def get_highlight(cls, tid: str) -> str | None:
        """返回该任务应有的高亮颜色，无高亮返回 None。橙色优先级高于蓝色。"""
        if tid == cls._ai_active_tid:
            return theme.warning
        if tid == cls._selected_tid:
            return theme.info
        return None

    # ── 卡片定位 ──

    @classmethod
    def _find_card(cls, tid: str):
        """在控件树中定位 TaskCard（DragTarget→Draggable→GestureDetector→TaskCard）。"""
        if not cls._kanban_board:
            return None
        try:
            from app.ui.components.task_card import TaskCard
            for col in cls._kanban_board._columns.values():
                for dt in getattr(col, 'card_list', ft.ListView()).controls:
                    if not isinstance(dt, ft.DragTarget):
                        continue
                    try:
                        card = dt.content.content.content
                        if isinstance(card, TaskCard) and \
                                getattr(card, 'task', None) and card.task.id == tid:
                            return card
                    except (AttributeError, IndexError):
                        continue
        except Exception:
            pass
        return None

    @classmethod
    def _apply(cls, tid: str, color: str | None):
        """对指定卡片设置 border 并 update。color=None 则清除。

        同时重置 bgcolor/scale/shadow——高亮期间 hover 事件被抑制，
        leave 事件不会触发，必须手动清理冻结的 hover 状态。
        """
        from app.config.theme import theme
        card = cls._find_card(tid)
        if card:
            card._highlight = color
            if color:
                # 清理冻结的 hover 状态后应用高亮
                card.bgcolor = theme.card
                card.scale = 1.0
                card.shadow = ft.BoxShadow(
                    spread_radius=0, blur_radius=4,
                    color="#00000030", offset=ft.Offset(0, 1))
                card.border = ft.border.all(2, color)
            else:
                card.border = None
                card.bgcolor = theme.card
                card.scale = 1.0
                card.shadow = ft.BoxShadow(
                    spread_radius=0, blur_radius=4,
                    color="#00000030", offset=ft.Offset(0, 1))
            try:
                card.update()
            except Exception:
                pass

    # ── 蓝色：右键选中 ──

    @classmethod
    def select(cls, tid: str):
        """选中卡片（蓝色描边）。自动清除旧选中。"""
        if cls._selected_tid and cls._selected_tid != tid:
            cls._apply(cls._selected_tid, None)
        cls._selected_tid = tid
        cls._apply(tid, theme.info)

    @classmethod
    def deselect(cls):
        """清除选中高亮。"""
        if cls._selected_tid:
            cls._apply(cls._selected_tid, None)
        cls._selected_tid = None

    # ── 橙色：AI 运行 ──

    @classmethod
    def set_ai_running(cls, tid: str):
        """标记卡片 AI 运行中（橙色描边）。"""
        cls._ai_active_tid = tid
        cls._apply(tid, theme.warning)

    @classmethod
    def clear_ai_running(cls):
        """清除 AI 运行高亮。"""
        if cls._ai_active_tid:
            cls._apply(cls._ai_active_tid, None)
        cls._ai_active_tid = None
