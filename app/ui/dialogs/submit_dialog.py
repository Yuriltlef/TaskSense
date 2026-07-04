"""提交验收弹窗."""
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

    result_f = ft.TextField(
        label="交接班日志", hint_text="描述完成情况、发现的问题、遗留事项...",
        multiline=True, min_lines=4, max_lines=8,
        border_color=theme.border, focused_border_color=theme.info,
        text_style=ft.TextStyle(color="#e0e0e0", size=s(12), font_family=ff),
        bgcolor=theme.card)
    hours_f = ft.TextField(
        label="实际工时 (h)", hint_text="如 3.5", width=150,
        border_color=theme.border, focused_border_color=theme.info,
        text_style=ft.TextStyle(color="#e0e0e0", size=s(12), font_family=ff),
        bgcolor=theme.card)
    if t.shift_handover_log: result_f.value = t.shift_handover_log
    if t.actual_hours: hours_f.value = str(t.actual_hours)

    for fld in [result_f, hours_f]:
        fld.text_style = ft.TextStyle(color="#e0e0e0", size=s(12), font_family=ff)
        fld.hint_style = ft.TextStyle(color=theme.text_secondary, size=s(11), font_family=ff)
        fld.border_radius = s(6)
        fld.content_padding = ft.padding.only(left=s(10), top=s(8), right=s(10), bottom=s(8))
        fld.dense = True

    def submit(_):
        result = (result_f.value or "").strip()
        if not result: Toast.show(page, "请填写交接班日志", "warning"); return
        try: actual_hours = float(hours_f.value or "0")
        except ValueError: actual_hours = 0
        try:
            task_service.update_task(tid, shift_handover_log=result, actual_hours=actual_hours)
            task_service.move_task(tid, "inspection", changed_by="user")
            dlg.close()
            from app.core.models.log_entry import LogType
            from app.core.services.log_service import log_service
            log_service.log(LogType.SUBMISSION, task_id=tid, task_title=t.title,
                           user="user", description=f"提交验收: {result[:60]}...")
            Toast.show(page, "已提交验收，等待审核", "success")
        except Exception as e: Toast.show(page, str(e), "warning")

    body = ft.Container(ft.Column([
        ft.Text(t.title[:40], size=s(13), weight=ft.FontWeight.W_500,
                color=theme.text_primary, font_family=ff),
        ft.Text("交接班日志将作为 AI 审核的提交材料", size=s(11),
                color=theme.text_secondary, font_family=ff),
        ft.Container(height=s(10)), result_f, ft.Container(height=s(8)), hours_f,
    ], spacing=0, tight=True), padding=ft.padding.all(s(14)))
    content = ft.Column([
        dlg_header(ft.Icons.ASSIGNMENT_TURNED_IN_OUTLINED, "提交验收", lambda e: dlg.close()),
        body, dlg_footer("取消", "提交验收", submit, on_cancel=lambda e: dlg.close()),
    ], spacing=0, tight=True)
    dlg = ModalDialog(page, content, width=480)
    dlg.open()
