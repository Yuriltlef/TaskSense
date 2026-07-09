"""筛选弹窗 — 多条件组合筛选."""
from datetime import datetime
import flet as ft
from app.config.theme import theme, s
from app.core.models.kanban import FilterState
from app.core.services.board_service import board_service
from app.ui.widgets.toast import Toast
from app.ui.components.modal_dialog import ModalDialog
from app.ui.services.dialog_builder import (
    header as dlg_header, footer as dlg_footer,
    make_date_picker,
)


def open(page: ft.Page):
    ff = theme.font_family
    f = board_service.get_board().filters

    # ── 从实际任务中提取 ATA 章节选项 ──
    from app.core.state import state as app_state
    ata_sections: set[str] = set()
    ata_labels: dict[str, str] = {}
    for t in app_state.get_all_tasks():
        section = t.ata_section or (t.ata_chapter.split("-")[0] if t.ata_chapter else "")
        if section:
            ata_sections.add(section)
    ata_options = [(section, f"ATA {section}") for section in sorted(ata_sections)]

    # ── 下拉 ──
    _opt_style = ft.TextStyle(color=theme.form_text, size=s(12), font_family=ff)

    def _dd(options, current=""):
        return ft.Dropdown(
            dense=True,
            options=[ft.dropdown.Option(k, v, text_style=_opt_style) for k, v in options],
            border_color=theme.border, focused_border_color=theme.info,
            bgcolor=theme.card, border_radius=s(6),
            text_style=_opt_style,
            value=current,
        )

    ata_dd = _dd(ata_options,
                  f.ata_chapters[0] if f.ata_chapters else "")
    pri_dd = _dd([("aog", "AOG"), ("cat_a", "Cat A"),
                   ("cat_b", "Cat B"), ("cat_c", "Cat C")],
                  f.priorities[0] if f.priorities else "")
    type_dd = _dd([("troubleshoot", "排故"), ("inspection", "检查"),
                    ("servicing", "勤务"), ("removal_install", "拆装"), ("test", "测试"),
                    ("repair", "修理")],
                  f.task_types[0] if f.task_types else "")
    status_dd = _dd([("backlog", "待处理"), ("triage", "分类中"),
                      ("scheduled", "已排程"), ("ready", "就绪"), ("in_progress", "执行中"),
                      ("inspection", "检查中"), ("parts_hold", "待零件"),
                      ("completed", "已完成")],
                    f.statuses[0] if f.statuses else "")

    # ── 文本输入 ──
    def _tf(hint="", current=""):
        return ft.TextField(
            dense=True, hint_text=hint, value=current,
            border_color=theme.border, focused_border_color=theme.info,
            bgcolor=theme.card, border_radius=s(6),
            text_style=ft.TextStyle(color=theme.form_text, size=s(12), font_family=ff),
            hint_style=ft.TextStyle(color=theme.text_disabled, size=s(12), font_family=ff),
        )

    emp_f = _tf("员工 ID，如 ZH001", f.employee_ids[0] if f.employee_ids else "")
    assignee_f = _tf("负责人姓名", f.assignees[0] if f.assignees else "")

    # ── 日期 ──
    start_from_ctrl, start_from_state, _, _ = make_date_picker(
        page, f.start_date_from)
    start_to_ctrl, start_to_state, _, _ = make_date_picker(
        page, f.start_date_to)
    due_from_ctrl, due_from_state, _, _ = make_date_picker(
        page, f.due_date_from)
    due_to_ctrl, due_to_state, _, _ = make_date_picker(
        page, f.due_date_to)

    def _section(title_text, *ctrls):
        return ft.Column([
            ft.Text(title_text, size=s(12), color=theme.text_primary,
                    font_family=ff, weight=ft.FontWeight.W_500),
            ft.Container(height=s(4)),
            *ctrls,
            ft.Container(height=s(10)),
        ], spacing=0, tight=True)

    def _date_row(from_ctrl, to_ctrl, from_state, to_state):
        return ft.Row([
            ft.Container(content=from_ctrl, expand=True),
            ft.Text("—", size=s(11), color=theme.text_secondary),
            ft.Container(content=to_ctrl, expand=True),
        ], spacing=s(6))

    # ── 按钮 ──

    def _apply(_):
        fs = FilterState()
        if ata_dd.value:
            fs.ata_chapters = [ata_dd.value]
        if pri_dd.value:
            fs.priorities = [pri_dd.value]
        if type_dd.value:
            fs.task_types = [type_dd.value]
        if status_dd.value:
            fs.statuses = [status_dd.value]
        eid = (emp_f.value or "").strip()
        if eid:
            fs.employee_ids = [eid]
        aname = (assignee_f.value or "").strip()
        if aname:
            fs.assignees = [aname]
        if start_from_state.get("date"):
            fs.start_date_from = start_from_state["date"]
        if start_to_state.get("date"):
            fs.start_date_to = start_to_state["date"]
        if due_from_state.get("date"):
            fs.due_date_from = due_from_state["date"]
        if due_to_state.get("date"):
            fs.due_date_to = due_to_state["date"]
        board_service.set_filters(fs)
        dlg.close()
        Toast.show(page, f"筛选已应用 ({fs.active_filter_count} 项)", "info")

    def _clear(_):
        board_service.set_filters(FilterState())
        dlg.close()
        Toast.show(page, "筛选已清除", "info")

    # ── 布局（双列利用宽弹窗）──
    def _two_col(left_ctrls, right_ctrls):
        return ft.Row([
            ft.Column(left_ctrls, spacing=s(6), tight=True, expand=True),
            ft.Container(width=s(16)),
            ft.Column(right_ctrls, spacing=s(6), tight=True, expand=True),
        ], spacing=0, vertical_alignment=ft.CrossAxisAlignment.START)

    form = ft.Container(
        ft.Column([
            _two_col(
                [_section("ATA 章节", ata_dd),
                 _section("优先级", pri_dd),
                 _section("状态", status_dd)],
                [_section("任务类型", type_dd),
                 _section("员工 ID", emp_f),
                 _section("负责人", assignee_f)],
            ),
            ft.Container(height=s(8)),
            _two_col(
                [_section("计划开始时间 (从)",
                          start_from_ctrl),
                 _section("计划开始时间 (到)",
                          start_to_ctrl)],
                [_section("截止时间 (从)",
                          due_from_ctrl),
                 _section("截止时间 (到)",
                          due_to_ctrl)],
            ),
        ], spacing=0, tight=True, scroll=ft.ScrollMode.AUTO),
        padding=ft.padding.all(s(14)),
        height=440,
    )

    content = ft.Column([
        dlg_header(ft.Icons.FILTER_ALT_OUTLINED, "筛选任务", lambda e: dlg.close()),
        form,
        dlg_footer("清除", "应用筛选", _apply, on_cancel=_clear),
    ], spacing=0, tight=True)
    dlg = ModalDialog(page, content, width=840)
    dlg.open()
