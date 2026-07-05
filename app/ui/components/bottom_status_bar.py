# -*- coding: utf-8 -*-
"""底部状态栏 — 显示活跃任务 + 报告/审核入口。"""

import flet as ft
from typing import Callable

from app.config.theme import theme, s


class BottomStatusBar(ft.Container):
    """底部状态栏组件。

    左侧：活跃任务标签（图标+名称+进度条+状态+圆形红色取消按钮）
    右侧：报告/审核入口（白色图标+文字，悬浮高亮，方形无圆角）

    回调：
        on_task_click(task_id) — 点击任务标签
        on_task_cancel(task_id) — 点击任务取消按钮
        on_report_click() — 点击报告入口
        on_review_click() — 点击审核入口
    """

    BAR_H = 38

    # 悬浮高亮色
    HOVER_BG = "#222222"
    TAG_BG = theme.panel_dark
    CANCEL_BG = "#cc3333"
    CANCEL_HOVER = "#e04444"

    def __init__(
        self,
        on_task_click: Callable = None,
        on_task_cancel: Callable = None,
        on_report_click: Callable = None,
        on_review_click: Callable = None,
    ):
        self.on_task_click = on_task_click or (lambda tid: None)
        self.on_task_cancel = on_task_cancel or (lambda tid: None)
        self.on_report_click = on_report_click or (lambda: None)
        self.on_review_click = on_review_click or (lambda: None)

        self._has_report = False
        self._has_review = False

        ff = theme.font_family

        # ── 左侧任务区域 ──
        self._task_row = ft.Row([], spacing=s(4), scroll=ft.ScrollMode.AUTO)

        # ── 右侧入口（白色图标 + 文字，方形无圆角，悬浮高亮）──
        report_icon = ft.Icon(ft.Icons.ASSESSMENT_OUTLINED, size=s(14),
                              color=theme.text_secondary)
        report_label = ft.Text("报表记录", size=s(10), font_family=ff,
                               color=theme.text_secondary)

        def _on_report_hover(e):
            self._report_entry.bgcolor = self.HOVER_BG if e.data == "true" else None
            try: self._report_entry.update()
            except Exception: pass

        self._report_entry = ft.Container(
            content=ft.Row([report_icon, report_label], spacing=s(3),
                           vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.padding.symmetric(horizontal=s(8)),
            border_radius=0,
            alignment=ft.alignment.center,
            on_hover=_on_report_hover,
            on_click=lambda e: self.on_report_click(),
        )
        self._report_icon = report_icon
        self._report_label = report_label

        review_icon = ft.Icon(ft.Icons.FACT_CHECK_OUTLINED, size=s(14),
                              color=theme.text_secondary)
        review_label = ft.Text("审核记录", size=s(10), font_family=ff,
                               color=theme.text_secondary)

        def _on_review_hover(e):
            self._review_entry.bgcolor = self.HOVER_BG if e.data == "true" else None
            try: self._review_entry.update()
            except Exception: pass

        self._review_entry = ft.Container(
            content=ft.Row([review_icon, review_label], spacing=s(3),
                           vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.padding.symmetric(horizontal=s(8)),
            border_radius=0,
            alignment=ft.alignment.center,
            on_hover=_on_review_hover,
            on_click=lambda e: self.on_review_click(),
        )
        self._review_icon = review_icon
        self._review_label = review_label

        # 右侧竖线分隔
        divider = ft.Container(width=s(1), bgcolor=theme.border)

        self._entry_row = ft.Row(
            [divider, self._report_entry, self._review_entry],
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.STRETCH,
        )

        # ── 主布局 ──
        inner = ft.Row(
            [
                ft.Container(
                    content=self._task_row,
                    expand=True,
                    padding=ft.padding.only(left=s(10)),
                ),
                self._entry_row,
                ft.Container(width=s(8)),
            ],
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        super().__init__(
            content=inner,
            height=self.BAR_H,
            bgcolor=theme.surface,
            border=ft.border.only(top=ft.BorderSide(1, theme.border)),
        )

    # ── 任务管理 ──

    def set_tasks(self, tasks: list[dict]):
        """更新左侧任务标签列表。

        tasks: [{id, label, status, progress}]  progress 为 0.0~1.0 或 None(不确定)
        """
        self._task_row.controls.clear()
        ff = theme.font_family

        for t in tasks:
            tid = t.get("id", "")
            label = t.get("label", "")
            status = t.get("status", "")
            progress = t.get("progress", None)

            # ── 微型进度条 ──
            pb = ft.ProgressBar(
                width=s(36), height=s(3),
                value=progress,
                color=theme.info if progress is None else (
                    theme.success if (progress or 0) >= 1.0 else theme.info),
                bgcolor=theme.card_hover,
            )

            # ── 状态文字颜色 ──
            status_color = theme.text_secondary
            if "失败" in status or "取消" in status:
                status_color = theme.error
            elif "完成" in status:
                status_color = theme.success

            # ── 圆形取消按钮（默认灰色，悬浮变红）──
            cancel_btn = ft.Container(
                content=ft.Icon(ft.Icons.CLOSE, size=s(12), color=theme.text_disabled),
                width=s(16), height=s(16),
                border_radius=s(8),
                bgcolor=ft.Colors.TRANSPARENT,
                alignment=ft.alignment.center,
                on_hover=self._make_cancel_hover(),
                on_click=lambda e, tid=tid: self.on_task_cancel(tid),
            )

            # ── 任务标签（方形无圆角，悬浮高亮，填满高度）──
            tag = ft.Container(
                content=ft.Row(
                    [
                        ft.Text(f"⚙ {label}", size=s(10),
                                color=theme.text_primary, font_family=ff),
                        pb,
                        ft.Text(status, size=s(9), color=status_color, font_family=ff),
                        cancel_btn,
                    ],
                    spacing=s(5),
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                height=self.BAR_H,
                bgcolor=self.TAG_BG,
                border_radius=0,
                padding=ft.padding.only(left=s(7), top=s(2), right=s(4), bottom=s(2)),
                alignment=ft.alignment.center_left,
                on_hover=self._make_tag_hover(),
                on_click=lambda e, tid=tid: self.on_task_click(tid),
            )
            self._task_row.controls.append(tag)

        if not tasks:
            self._task_row.controls.append(
                ft.Text("无正在运行的任务", size=s(10),
                        color=theme.text_disabled, font_family=ff)
            )

        try:
            self._task_row.update()
        except Exception:
            pass

    @staticmethod
    def _make_tag_hover():
        def _hover(e):
            ctrl = e.control
            ctrl.bgcolor = BottomStatusBar.HOVER_BG if e.data == "true" else BottomStatusBar.TAG_BG
            try: ctrl.update()
            except Exception: pass
        return _hover

    @staticmethod
    def _make_cancel_hover():
        def _hover(e):
            ctrl = e.control
            if e.data == "true":
                ctrl.bgcolor = BottomStatusBar.CANCEL_BG
                ctrl.content.color = ft.Colors.WHITE
            else:
                ctrl.bgcolor = ft.Colors.TRANSPARENT
                ctrl.content.color = theme.text_disabled
            try: ctrl.update()
            except Exception: pass
        return _hover

    # ── 入口按钮状态 ──

    def set_has_report(self, has: bool):
        """有报表结果时高亮图标。"""
        self._has_report = has
        c = theme.info if has else theme.text_secondary
        self._report_icon.color = c
        self._report_label.color = c
        try:
            self._report_entry.update()
        except Exception:
            pass

    def set_has_review(self, has: bool):
        """有审核结果时高亮图标。"""
        self._has_review = has
        c = theme.info if has else theme.text_secondary
        self._review_icon.color = c
        self._review_label.color = c
        try:
            self._review_entry.update()
        except Exception:
            pass
