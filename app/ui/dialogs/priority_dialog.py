# -*- coding: utf-8 -*-
"""优先级选择弹窗（拖放 + 右键复用）。col=None→仅更新优先级不移动列。"""
import flet as ft
from app.config.theme import theme, s
from app.core.models.task import Priority
from app.core.services.task_service import task_service
from app.core.state import state
from app.ui.widgets.toast import Toast
from app.ui.components.modal_dialog import ModalDialog
from app.ui.services.dialog_builder import header as dlg_header, footer as dlg_footer


def open(page: ft.Page, tid: str, col: str = None, index: int = -1):
    ff = theme.font_family
    options = [
        ("aog", "AOG", "立即排故", theme.priority_aog),
        ("cat_a", "Cat A", "当日完成", theme.priority_cat_a),
        ("cat_b", "Cat B", "72 小时内", theme.priority_cat_b),
        ("cat_c", "Cat C", "10 天内", theme.priority_cat_c),
        ("cat_d", "Cat D", "120 天内", theme.priority_cat_d),
    ]
    t = state.get_task(tid)
    current_pri = t.priority.value if t else "cat_c"
    init_val = current_pri if current_pri in [o[0] for o in options] else "cat_c"
    selected = {"val": init_val}

    chips = []
    for val, label, desc, color in options:
        sel = val == selected["val"]
        chips.append(ft.Container(
            content=ft.Column([
                ft.Row([ft.Icon(ft.Icons.FLAG_OUTLINED, size=s(14), color=color),
                        ft.Text(label, size=s(13), weight=ft.FontWeight.W_600,
                                color=color if sel else theme.text_primary, font_family=ff),
                ], spacing=s(6)),
                ft.Text(desc, size=s(11), color=theme.text_secondary, font_family=ff),
            ], spacing=s(2), tight=True),
            padding=ft.padding.all(s(10)), border_radius=s(6),
            border=ft.border.all(1.5, color if sel else theme.border),
            bgcolor=ft.Colors.with_opacity(0.06, color) if sel else theme.card,
            on_click=lambda e, v=val: _select(v), ink=True, width=150,
        ))

    def _select(v):
        selected["val"] = v
        for i, chip in enumerate(chips):
            s_sel = options[i][0] == v; clr = options[i][3]
            chip.border = ft.border.all(1.5, clr if s_sel else theme.border)
            chip.bgcolor = ft.Colors.with_opacity(0.06, clr) if s_sel else theme.card
            chip.content.controls[0].controls[1].color = clr if s_sel else theme.text_primary
            chip.update()

    def _confirm(_):
        priority = selected["val"]
        try:
            task_service.update_task(tid, priority=Priority(priority))
            if col is not None:
                task_service.move_task(tid, col, index=index)
                labels = {"aog": "AOG", "cat_a": "Cat A", "cat_b": "Cat B",
                          "cat_c": "Cat C", "cat_d": "Cat D"}
                Toast.show(page, f"已分类 — {labels.get(priority, priority)}", "success")
            else:
                Toast.show(page, "优先级已更新", "success")
        except Exception as e:
            Toast.show(page, str(e), "warning")
        dlg.close()

    form = ft.Container(
        ft.Column([
            ft.Row(chips[:3], spacing=s(8), alignment=ft.MainAxisAlignment.CENTER),
            ft.Row(chips[3:], spacing=s(8), alignment=ft.MainAxisAlignment.CENTER),
        ], spacing=s(8), tight=True),
        padding=ft.padding.all(s(14)),
    )
    content = ft.Column([
        dlg_header(ft.Icons.FLAG_OUTLINED, "确认优先级", lambda e: dlg.close()),
        form,
        dlg_footer("取消", "确认", _confirm, on_cancel=lambda e: dlg.close()),
    ], spacing=0, tight=True)
    dlg = ModalDialog(page, content, width=540)
    dlg.open()
