"""排程弹窗."""
import flet as ft
from app.config.theme import theme, s
from app.core.services.task_service import task_service
from app.core.state import state
from app.ui.widgets.toast import Toast
from app.ui.components.modal_dialog import ModalDialog
from app.ui.services.dialog_builder import (
    header as dlg_header, footer as dlg_footer,
    make_field, make_label, make_col, make_date_picker,
    clamp_time_field, build_datetime,
)


def open(page: ft.Page, tid: str, col=None, index=-1, move_to=True):
    ff = theme.font_family

    def _field(hint="", width=None):
        return make_field(hint=hint, width=width)

    def _label(text, required=False):
        return make_label(text, required)

    def _col(lbl, ctrl):
        return make_col(lbl, ctrl)

    hours_f = _field("计划工时 (h)，如 4.5", width=220)
    assignee_id_f = _field("员工 ID，如 ZH001")
    assignee_name_f = _field("姓名，如 张工")

    # 员工 ID 自动补全（与新建任务弹窗逻辑一致）
    def _on_emp_id(e):
        val = (e.control.value or "").strip()
        if not val:
            assignee_name_f.value = ""
            try: assignee_name_f.update()
            except Exception: pass
            return
        from app.core.services.employee_service import employee_service
        emp = employee_service.get_employee(val)
        if emp and emp.get("available", True):
            assignee_name_f.value = emp["name"]
        elif emp:
            assignee_name_f.value = emp["name"] + "(不可用)"
        else:
            assignee_name_f.value = "未知员工"
        try: assignee_name_f.update()
        except Exception: pass
    assignee_id_f.on_change = _on_emp_id
    start_hour_f = _field("08", width=s(62))
    start_min_f = _field("00", width=s(62))
    due_hour_f = _field("17", width=s(62))
    due_min_f = _field("00", width=s(62))

    def _clamp_tf(tf, hi):
        clamp_time_field(tf, hi); tf.update()
    for _tf, _hi in [(start_hour_f, 23), (start_min_f, 59),
                      (due_hour_f, 23), (due_min_f, 59)]:
        _tf.on_blur = lambda e, t=_tf, h=_hi: _clamp_tf(t, h)

    from app.ui.services.dialog_builder import make_date_picker as _mkdp

    t = state.get_task(tid)
    start_date_ctrl, start_date_state, start_date_err, start_date_clr = _mkdp(
        page, t.planned_start if t else None, on_pick_callback=lambda: _recalc())
    due_date_ctrl, due_date_state, due_date_err, due_date_clr = _mkdp(
        page, t.planned_end if t else None, on_pick_callback=lambda: _recalc())
    if t:
        if t.planned_start:
            start_hour_f.value = t.planned_start.strftime("%H")
            start_min_f.value = t.planned_start.strftime("%M")
        if t.planned_end:
            due_hour_f.value = t.planned_end.strftime("%H")
            due_min_f.value = t.planned_end.strftime("%M")
        if t.estimated_hours:
            hours_f.value = str(t.estimated_hours)
        if t.employee_id:
            assignee_id_f.value = t.employee_id
        if t.employee_name:
            assignee_name_f.value = t.employee_name

    def _get_dt(date_state, h_f, m_f):
        return build_datetime(date_state, h_f, m_f)

    def _recalc():
        sd = _get_dt(start_date_state, start_hour_f, start_min_f)
        due_h = (due_hour_f.value or "").strip()
        due_m = (due_min_f.value or "").strip()
        if due_h and due_m:
            ed = _get_dt(due_date_state, due_hour_f, due_min_f)
        else:
            ed = None
        if sd and ed:
            diff = (ed - sd).total_seconds() / 3600
            if diff > 0:
                hours_f.value = f"{diff:.1f}"; hours_f.update()
            else:
                due_date_state["date"] = None
                due_hour_f.value = ""; due_min_f.value = ""
                try: due_hour_f.update(); due_min_f.update()
                except Exception: pass
                due_date_clr()
                hours_f.value = ""
                try: hours_f.update()
                except Exception: pass
                Toast.show(page, "完成时间必须晚于开始时间", "warning")

    for _tf, _hi in [(start_hour_f, 23), (start_min_f, 59),
                      (due_hour_f, 23), (due_min_f, 59)]:
        _prev = _tf.on_blur
        _tf.on_blur = lambda e, t=_tf, h=_hi, p=_prev: (_clamp_tf(t, h), _recalc())

    def _confirm(_):
        start_dt = _get_dt(start_date_state, start_hour_f, start_min_f)
        due_dt = _get_dt(due_date_state, due_hour_f, due_min_f)
        hs = (hours_f.value or "").strip()
        aid = (assignee_id_f.value or "").strip()
        aname = (assignee_name_f.value or "").strip()
        start_date_clr(); due_date_clr()
        for c, h in [(hours_f, "计划工时 (h)，如 4.5"), (assignee_id_f, "员工 ID，如 ZH001"), (assignee_name_f, "姓名，如 张工")]:
            c.border_color = theme.border; c.hint_text = h
        # 日期和时间都必须填写
        start_has_date = bool(start_date_state.get("date"))
        start_has_time = bool((start_hour_f.value or "").strip()) and bool((start_min_f.value or "").strip())
        if not start_has_date:
            start_date_err("请选择开始日期"); return
        if not start_has_time:
            start_date_err("请填写开始时间（时/分）"); return

        due_has_date = bool(due_date_state.get("date"))
        due_has_time = bool((due_hour_f.value or "").strip()) and bool((due_min_f.value or "").strip())
        if not due_has_date:
            due_date_err("请选择完成日期"); return
        if not due_has_time:
            due_date_err("请填写完成时间（时/分）"); return

        if not start_dt: return
        if not due_dt: return
        if not hs: hours_f.border_color = theme.error; hours_f.hint_text = "请输入计划工时"; hours_f.update(); return
        if not aid: assignee_id_f.border_color = theme.error; assignee_id_f.hint_text = "请输入员工 ID"; assignee_id_f.update(); return
        if not aname: assignee_name_f.border_color = theme.error; assignee_name_f.hint_text = "请输入姓名"; assignee_name_f.update(); return
        # 校验员工存在且可用
        if aid:
            from app.core.services.employee_service import employee_service
            from app.core.validators import TaskValidators, BusinessRuleError
            try:
                TaskValidators.validate_employee(aid)
            except BusinessRuleError as e:
                assignee_id_f.border_color = theme.error; assignee_id_f.update()
                Toast.show(page, str(e), "warning"); return
        try:
            if move_to and col:
                task_service.move_task(tid, col, index=index)
            updates: dict = {
                "assignee": f"{aid} {aname}",
                "due_date": due_dt,
                "planned_start": start_dt,
                "planned_end": due_dt,
            }
            try: updates["estimated_hours"] = float(hs)
            except ValueError: pass
            task_service.update_task(tid, **updates)
            if move_to and col:
                Toast.show(page, "已排程", "success")
            else:
                Toast.show(page, "排程已更新", "success")
        except Exception as ex: Toast.show(page, str(ex), "warning")
        dlg.close()

    header = dlg_header(ft.Icons.CALENDAR_MONTH_OUTLINED, "排程信息", lambda e: dlg.close())
    sep = ft.Divider(height=s(12), color=ft.Colors.TRANSPARENT)

    def _date_row(label_text, date_ctrl, h_f, m_f):
        return ft.Column([
            _label(label_text, required=True),
            ft.Row([
                ft.Container(content=date_ctrl, expand=True),
                ft.Container(width=s(4)),
                h_f, ft.Text("时", size=s(11), color=theme.text_secondary, font_family=ff),
                m_f, ft.Text("分", size=s(11), color=theme.text_secondary, font_family=ff),
            ], spacing=s(4), vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ], spacing=s(4), tight=True)

    form = ft.Container(
        ft.Column([
            _date_row("计划开始日期", start_date_ctrl, start_hour_f, start_min_f), sep,
            _date_row("计划完成日期", due_date_ctrl, due_hour_f, due_min_f), sep,
            ft.Row([_col(_label("计划工时", required=True), hours_f), ft.Container(expand=True)], spacing=s(12)), sep,
            ft.Row([_col(_label("员工 ID", required=True), assignee_id_f), _col(_label("姓名", required=True), assignee_name_f)], spacing=s(12)),
        ], spacing=s(4), tight=True),
        padding=ft.padding.all(s(14)))
    footer = dlg_footer("取消", "确认排程", _confirm, on_cancel=lambda e: dlg.close())
    content = ft.Column([header, form, footer], spacing=0, tight=True)
    dlg = ModalDialog(page, content, width=520)
    dlg.open()
