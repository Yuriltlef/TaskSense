"""阻塞任务弹窗."""
import flet as ft
from app.config.theme import theme, s
from app.core.services.task_service import task_service
from app.core.state import state
from app.ui.widgets.toast import Toast
from app.ui.components.modal_dialog import ModalDialog
from app.ui.services.dialog_builder import header as dlg_header, footer as dlg_footer


def open(page: ft.Page, tid: str):
    t = state.get_task(tid)
    if not t: return
    ff = theme.font_family

    reason_f = ft.TextField(
        hint_text="如：等待航材、缺工具、等待排故方案...",
        multiline=True, min_lines=3, max_lines=6,
        border_color=theme.border, focused_border_color=theme.warning,
        text_style=ft.TextStyle(color="#e0e0e0", size=s(12), font_family=ff),
        hint_style=ft.TextStyle(color=theme.text_secondary, size=s(11), font_family=ff),
        bgcolor=theme.card, dense=True, border_radius=s(6),
        content_padding=ft.padding.only(left=s(10), top=s(8), right=s(10), bottom=s(8)))

    def _do_block(_):
        reason = (reason_f.value or "").strip()
        if not reason: Toast.show(page, "请填写阻塞原因", "warning"); return
        try:
            task_service.block_task(tid, reason=reason, user="user")
            dlg.close(); Toast.show(page, "已阻塞", "success")
        except Exception as e: Toast.show(page, str(e), "warning")

    body = ft.Container(ft.Column([
        ft.Text(t.title[:40], size=s(13), weight=ft.FontWeight.W_500,
                color=theme.text_primary, font_family=ff),
        ft.Container(height=s(10)), reason_f,
    ], spacing=0, tight=True), padding=ft.padding.all(s(14)))
    content = ft.Column([
        dlg_header(ft.Icons.BLOCK_OUTLINED, "阻塞任务", lambda e: dlg.close()),
        body, dlg_footer("取消", "确认阻塞", _do_block, on_cancel=lambda e: dlg.close(),
                         confirm_color=theme.warning),
    ], spacing=0, tight=True)
    dlg = ModalDialog(page, content, width=460)
    dlg.open()
