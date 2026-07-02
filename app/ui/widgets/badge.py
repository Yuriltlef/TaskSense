"""徽章组件."""
from __future__ import annotations

import flet as ft
from app.config.theme import theme


class Badge(ft.Container):
    def __init__(self, text: str, color="#808080", bg_color=None,
                 icon=None, size="sm", tooltip=None):
        fs = {"xs": 10, "sm": 11, "md": 12, "lg": 14}.get(size, 11)
        # (vertical, horizontal)
        pad = {"xs": (2, 6), "sm": (3, 8), "md": (4, 10), "lg": (5, 12)}.get(size, (3, 8))

        content = ft.Text(text, size=round(fs * 1.5),
                          color=color, weight=ft.FontWeight.W_600,
                          font_family=theme.font_family)
        if icon:
            content = ft.Row([ft.Text(icon, size=round(fs * 1.5)), content], spacing=2)

        super().__init__(
            content=content,
            padding=ft.padding.only(left=pad[1], top=pad[0],
                                    right=pad[1], bottom=pad[0]),
            border_radius=theme.radius_sm,
            bgcolor=bg_color or self._alpha(color, 0.15),
            tooltip=tooltip or text,
        )

    @staticmethod
    def _alpha(hex_color: str, alpha: float) -> str:
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"#{int(255 * alpha):02x}{r:02x}{g:02x}{b:02x}"


class PriorityBadge(Badge):
    def __init__(self, priority: str, size="sm"):
        c = theme.priority_color(priority)
        labels = {"aog": "AOG", "cat_a": "CAT A", "cat_b": "CAT B",
                  "cat_c": "CAT C", "cat_d": "CAT D"}
        tips = {"aog": "AOG — 立即修复", "cat_a": "当日修复",
                "cat_b": "72h 内", "cat_c": "10 天内", "cat_d": "120 天内"}
        super().__init__(text=labels.get(priority, priority.upper()),
                         color=c, size=size, tooltip=tips.get(priority, ""))


class ATABadge(Badge):
    def __init__(self, ata_chapter: str, size="sm"):
        c = theme.ata_category_color(ata_chapter)
        super().__init__(
            text=f"ATA {ata_chapter}" if ata_chapter else "ATA ?",
            color=c, size=size, tooltip=f"ATA: {ata_chapter}")


class TaskTypeBadge(Badge):
    def __init__(self, task_type: str, size="sm"):
        c = theme.task_type_color(task_type)
        icons = {"troubleshoot": "🔧", "inspection": "🔍", "servicing": "🛢️",
                 "removal_install": "🔩", "test": "📏", "repair": "🔨"}
        labels = {"troubleshoot": "排故", "inspection": "检查",
                  "servicing": "勤务", "removal_install": "拆装",
                  "test": "测试", "repair": "修复"}
        super().__init__(text=labels.get(task_type, task_type),
                         color=c, icon=icons.get(task_type), size=size)


class StatusBadge(Badge):
    def __init__(self, status: str, size="sm"):
        colors = {"backlog": theme.text_disabled, "triage": theme.info,
                  "scheduled": theme.priority_cat_c, "ready": theme.success,
                  "in_progress": theme.warning, "inspection": theme.type_removal_install,
                  "parts_hold": theme.priority_cat_a, "completed": theme.success,
                  "archived": theme.text_disabled}
        labels = {"backlog": "待处理", "triage": "分类中", "scheduled": "已排程",
                  "ready": "就绪", "in_progress": "执行中", "inspection": "验收中",
                  "parts_hold": "阻塞中", "completed": "已完成", "archived": "已归档"}
        super().__init__(text=labels.get(status, status),
                         color=colors.get(status, theme.text_disabled), size=size)
