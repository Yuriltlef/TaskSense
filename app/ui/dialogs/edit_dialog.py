"""编辑任务弹窗."""
import flet as ft

from app.config.theme import theme, s
from app.core.services.task_service import task_service


def open(page: ft.Page, task):
    t = task
    """编辑任务弹窗 — 照搬创建任务弹窗风格，含 AI 补全、日期选择器、状态约束。"""
    ff = theme.font_family
    st = task.status.value

    # ── 状态约束规则 ──
    # backlog: 全部可编辑
    # triage: 锁定 reg/ata/type
    # scheduled: 锁定 reg/ata/priority/type/employee/times/zone
    # ready/in_progress/parts_hold: 锁定除 desc/log 外全部
    # inspection/completed/archived: 全部锁定（仅查看）
    _CORE_LOCKED = st not in ("backlog",)          # reg, ata
    _TYPE_LOCKED = st not in ("backlog",)           # task_type
    _PRI_LOCKED = st not in ("backlog", "triage")   # priority
    _EMP_LOCKED = st not in ("backlog", "triage")   # employee
    _TIME_LOCKED = st not in ("backlog", "triage")  # planned times, hours
    _ZONE_LOCKED = st not in ("backlog", "triage")  # zone
    _TITLE_LOCKED = st in ("ready", "in_progress", "parts_hold",
                           "inspection", "completed", "archived")
    _DESC_LOCKED = st in ("ready", "in_progress", "parts_hold",
                           "inspection", "completed", "archived")
    _LOG_LOCKED = st in ("inspection", "completed", "archived")
    _ALL_LOCKED = st in ("completed", "archived")

    # ── helpers（照搬 create_task_dialog 风格）──
    def _norm_tf(hint="", value="", readonly=False, **kw):
        if readonly:
            return ft.Text(str(value or "—"), size=s(13),
                           color=theme.text_disabled, font_family=ff)
        return ft.TextField(
            hint_text=hint, value=str(value or ""),
            border_color=theme.border, focused_border_color=theme.info,
            cursor_color=theme.info,
            text_style=ft.TextStyle(color="#e0e0e0", size=s(13), font_family=ff),
            hint_style=ft.TextStyle(color=theme.text_secondary, size=s(12), font_family=ff),
            bgcolor=theme.card, dense=True,
            content_padding=ft.padding.only(left=s(10), top=s(8), right=s(10), bottom=s(8)),
            border_radius=s(6), **kw)

    def _label(text, required=False):
        if required:
            return ft.Text(spans=[
                ft.TextSpan(text, ft.TextStyle(color=theme.text_primary, size=s(12), font_family=ff, weight=ft.FontWeight.W_500)),
                ft.TextSpan(" *", ft.TextStyle(color=theme.error, size=s(12), font_family=ff, weight=ft.FontWeight.W_500))])
        return ft.Text(text, size=s(12), color=theme.text_primary, font_family=ff, weight=ft.FontWeight.W_500)

    def _col(lbl, ctrl):
        return ft.Column([lbl, ctrl], spacing=s(4), tight=True, expand=True)

    # ── 上下文收集（供 AI 补全，仅未锁定字段）──
    _fields = {}
    # 字段 → 锁定标志映射
    _FIELD_LOCKS = {
        "title": lambda: _TITLE_LOCKED, "description": lambda: _DESC_LOCKED,
        "ata_chapter": lambda: _CORE_LOCKED, "aircraft_reg": lambda: _CORE_LOCKED,
        "employee_id": lambda: _EMP_LOCKED, "employee_name": lambda: _EMP_LOCKED,
        "zone": lambda: _ZONE_LOCKED, "task_type": lambda: _TYPE_LOCKED,
    }

    def _get_ctx():
        result = {}
        for fn, is_locked in _FIELD_LOCKS.items():
            if is_locked():
                continue  # 跳过已锁定字段
            ctrl = _fields.get(fn)
            if ctrl is None or not hasattr(ctrl, 'value'):
                result[fn] = ""
            else:
                result[fn] = ctrl.value or ""
        return result

    def _on_filled(target_field: str, value: str):
        # 拒绝填充已锁定字段
        lock_fn = _FIELD_LOCKS.get(target_field)
        if lock_fn and lock_fn():
            return
        ctrl = _fields.get(target_field)
        if ctrl is None: return
        if hasattr(ctrl, 'text_field'):
            ctrl = ctrl.text_field
        if not isinstance(ctrl, ft.TextField) or not ctrl.read_only:
            ctrl.value = value
            try: ctrl.update()
            except Exception: pass

    # ── 标题 ──
    from app.ui.widgets.ghost_text import GhostTextField
    if _TITLE_LOCKED:
        title_gf = _norm_tf("任务标题", str(task.title), readonly=True)
        _fields["title"] = title_gf
    else:
        title_gf = GhostTextField(
            hint_text="任务标题", field_name="title",
            get_context=_get_ctx, on_field_filled=_on_filled,
        )
        title_gf.value = task.title
        _fields["title"] = title_gf

    # ── 描述 ──
    if _DESC_LOCKED:
        desc_gf = ft.Text(task.description or "—", size=s(13),
                           color=theme.text_disabled, font_family=ff)
        _fields["description"] = desc_gf
    else:
        desc_gf = GhostTextField(
            hint_text="任务描述", field_name="description",
            get_context=_get_ctx, on_field_filled=_on_filled,
            multiline=True, min_lines=3,
        )
        desc_gf.value = task.description or ""
        _fields["description"] = desc_gf

    # ── 飞机注册号 ──
    reg_f = _norm_tf("飞机注册号，如 B-5823", str(task.aircraft_reg or ""), readonly=_CORE_LOCKED)
    _fields["aircraft_reg"] = reg_f

    # ── ATA 章节 ──
    if _CORE_LOCKED:
        ata_gf = _norm_tf("ATA 章节，如 32-41-03", str(task.ata_chapter or ""), readonly=True)
        _fields["ata_chapter"] = ata_gf
    else:
        ata_gf = GhostTextField(
            hint_text="ATA 章节，如 32-41-03", field_name="ata_chapter",
            get_context=_get_ctx, on_field_filled=_on_filled,
        )
        ata_gf.value = task.ata_chapter or ""
        _fields["ata_chapter"] = ata_gf

    # ── 优先级 ──
    _PRI_OPTS = [("aog","AOG",theme.priority_color("aog")),("cat_a","Cat A",theme.priority_color("cat_a")),
                 ("cat_b","Cat B",theme.priority_color("cat_b")),("cat_c","Cat C",theme.priority_color("cat_c")),
                 ("cat_d","Cat D",theme.priority_color("cat_d"))]
    cur_pri = task.priority.value if hasattr(task.priority, 'value') else str(task.priority)
    _sel_pri = [cur_pri]
    _pri_btns = []

    if _PRI_LOCKED:
        # 锁定态：只显示当前优先级彩色标签
        _pri_label = {v: l for v, l, _ in _PRI_OPTS}.get(cur_pri, cur_pri.upper())
        _pri_color = theme.priority_color(cur_pri)
        pri_row = ft.Container(
            ft.Text(_pri_label, size=s(11), color=ft.Colors.WHITE, font_family=ff,
                    weight=ft.FontWeight.W_600),
            padding=ft.padding.symmetric(horizontal=s(12), vertical=s(5)),
            border_radius=s(4), bgcolor=_pri_color,
        )
    else:
        def _mk_pb(v, l, c):
            sel = (v == _sel_pri[0])
            b = ft.Container(
                ft.Text(l, size=s(10),
                        color=c if not sel else ft.Colors.WHITE,
                        font_family=ff, weight=ft.FontWeight.W_600),
                padding=ft.padding.symmetric(horizontal=s(10), vertical=s(5)),
                border_radius=s(4),
                bgcolor=c if sel else ft.Colors.TRANSPARENT,
                border=ft.border.all(1, c),
                on_click=lambda e, x=v: _on_pri(x))
            _pri_btns.append((v, b))
            return b

        def _on_pri(v):
            _sel_pri[0] = v
            for pv, b in _pri_btns:
                c = theme.priority_color(pv); b.bgcolor = c if pv == v else ft.Colors.TRANSPARENT
                b.content.color = ft.Colors.WHITE if pv == v else c; b.update()

        pri_row = ft.Row([_mk_pb(v, l, c) for v, l, c in _PRI_OPTS], spacing=s(6), tight=True)

    # ── 任务类型 ──
    cur_tt = task.task_type.value if hasattr(task.task_type, 'value') else str(task.task_type)
    type_dd = ft.Dropdown(value=cur_tt, dense=True, disabled=_TYPE_LOCKED,
        options=[ft.dropdown.Option(k, v) for k, v in [
            ("troubleshoot","排故"),("inspection","检查"),("servicing","勤务"),
            ("removal_install","拆装"),("test","测试"),("repair","修复")]],
        border_color=theme.border,
        focused_border_color=theme.info, bgcolor=theme.card,
        text_style=ft.TextStyle(color="#e0e0e0", size=s(12), font_family=ff),
        border_radius=s(6))
    _fields["task_type"] = type_dd

    # ── 员工 ──
    emp_id_f = _norm_tf("员工 ID，如 ZH001", str(task.employee_id or ""), readonly=_EMP_LOCKED)
    emp_name_f = _norm_tf("员工姓名，如 张工", str(task.employee_name or ""), readonly=_EMP_LOCKED)
    print(f"[EDIT] emp_id='{task.employee_id}' name='{task.employee_name}' locked={_EMP_LOCKED}")
    _fields["employee_id"] = emp_id_f
    _fields["employee_name"] = emp_name_f
    if not _EMP_LOCKED:
        def _on_emp_id(e):
            val = (e.control.value or "").strip()
            if not val:
                emp_name_f.value = ""
                try: emp_name_f.update()
                except Exception: pass
                return
            from app.core.services.employee_service import employee_service
            emp = employee_service.get_employee(val)
            if emp:
                emp_name_f.value = emp["name"] if emp.get("available", True) else f"{emp['name']}(不可用)"
            else:
                emp_name_f.value = "未知员工"
            try: emp_name_f.update()
            except Exception: pass
        emp_id_f.on_change = _on_emp_id

    # ── 时间（照搬 create_task_dialog 的日期选择器）──
    from datetime import datetime as dt
    sh = _norm_tf("08", value=(task.planned_start.strftime("%H") if task.planned_start else "08"),
                   width=s(56), readonly=_TIME_LOCKED)
    sm = _norm_tf("00", value=(task.planned_start.strftime("%M") if task.planned_start else "00"),
                   width=s(56), readonly=_TIME_LOCKED)
    eh = _norm_tf("12", value=(task.planned_end.strftime("%H") if task.planned_end else "12"),
                   width=s(56), readonly=_TIME_LOCKED)
    em = _norm_tf("00", value=(task.planned_end.strftime("%M") if task.planned_end else "00"),
                   width=s(56), readonly=_TIME_LOCKED)
    hrs_str = f"{task.estimated_hours:.1f}" if task.estimated_hours else ""
    hours_f = _norm_tf("（可选）", value=hrs_str, width=120, readonly=_TIME_LOCKED)
    print(f"[EDIT] planned_start={task.planned_start} planned_end={task.planned_end} hrs={task.estimated_hours} locked={_TIME_LOCKED}")

    # 仅 backlog/triage 有时分校验
    if not _TIME_LOCKED:
        def _clamp_tf(tf, hi):
            val = (tf.value or "").strip()
            if val:
                if not val.isdigit(): tf.value = ""; tf.update(); return
                n = int(val)
                if n > hi: tf.value = str(hi); tf.update()
        for _tf, _hi in [(sh, 23), (sm, 59), (eh, 23), (em, 59)]:
            _tf.on_blur = lambda e, t=_tf, h=_hi: _clamp_tf(t, h)

    def _make_date_picker(initial_date=None):
        state = {"date": initial_date}
        dp = ft.DatePicker(first_date=dt(2024, 1, 1), last_date=dt(2030, 12, 31),
                           on_change=lambda e: _on_pick(e))
        if initial_date:
            display = ft.Text(initial_date.strftime("%Y-%m-%d"), size=s(12), color="#e0e0e0", font_family=ff)
        elif _TIME_LOCKED:
            display = ft.Text("—", size=s(12), color=theme.text_secondary, font_family=ff)
        else:
            display = ft.Text("点击选择日期", size=s(12), color=theme.text_secondary, font_family=ff)
        ctrl = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.CALENDAR_TODAY_OUTLINED, size=s(14),
                        color=theme.text_secondary),
                display,
            ], spacing=s(6)),
            bgcolor=theme.card,
            border_radius=s(6),
            border=ft.border.all(1, theme.border),
            padding=ft.padding.only(left=s(10), top=s(8), right=s(10), bottom=s(8)),
            on_click=None if _TIME_LOCKED else (lambda e: page.open(dp)),
            ink=not _TIME_LOCKED)
        def _on_pick(e):
            if e.control.value:
                state["date"] = e.control.value
                display.value = state["date"].strftime("%Y-%m-%d")
                display.color = "#e0e0e0"
                ctrl.update(); _recalc_hours()
        def _set_err(msg):
            display.value = msg; display.color = theme.error
            ctrl.border = ft.border.all(1, theme.error); ctrl.update()
        def _clear_err():
            if state["date"]:
                display.value = state["date"].strftime("%Y-%m-%d"); display.color = "#e0e0e0"
            else:
                display.value = "点击选择日期"; display.color = theme.text_secondary
            ctrl.border = ft.border.all(1, theme.border); ctrl.update()
        return ctrl, state, _set_err, _clear_err

    if _TIME_LOCKED:
        start_date_ctrl = ft.Text(
            task.planned_start.strftime("%Y-%m-%d %H:%M") if task.planned_start else "—",
            size=s(13), color=theme.text_disabled, font_family=ff)
        due_date_ctrl = ft.Text(
            task.planned_end.strftime("%Y-%m-%d %H:%M") if task.planned_end else "—",
            size=s(13), color=theme.text_disabled, font_family=ff)
        start_date_state = due_date_state = {"date": None}
        start_date_err = due_date_err = lambda m: None
        start_date_clr = due_date_clr = lambda: None
    else:
        start_date_ctrl, start_date_state, start_date_err, start_date_clr = _make_date_picker(
            initial_date=task.planned_start)
        due_date_ctrl, due_date_state, due_date_err, due_date_clr = _make_date_picker(
            initial_date=task.planned_end)

    def _get_dt(date_state, h_f, m_f):
        d = date_state["date"]
        if not d: return None
        h = (h_f.value or "").strip()
        m = (m_f.value or "").strip()
        if h and m:
            try: return dt(d.year, d.month, d.day, int(h), int(m))
            except: pass
        return d

    def _recalc_hours():
        if _TIME_LOCKED: return
        sd_dt = _get_dt(start_date_state, sh, sm)
        ed_dt = _get_dt(due_date_state, eh, em)
        if sd_dt and ed_dt:
            diff = (ed_dt - sd_dt).total_seconds() / 3600
            if diff > 0:
                hours_f.value = f"{diff:.1f}"
                try: hours_f.update()
                except Exception: pass
            else:
                due_date_state["date"] = None; eh.value = ""; em.value = ""
                try: eh.update(); em.update()
                except Exception: pass
                due_date_clr()
                hours_f.value = ""
                try: hours_f.update()
                except Exception: pass
                from app.ui.widgets.toast import Toast
                Toast.show(page, "完成时间必须晚于开始时间", "warning")

    def _date_row(label_text, date_ctrl, h_f, m_f):
        return ft.Row([
            ft.Text(label_text, size=s(11), color=theme.text_secondary, font_family=ff, width=s(36)),
            ft.Container(content=date_ctrl, expand=True),
            h_f,
            ft.Text("时", size=s(11), color=theme.text_secondary, font_family=ff),
            m_f,
            ft.Text("分", size=s(11), color=theme.text_secondary, font_family=ff),
        ], spacing=s(4), vertical_alignment=ft.CrossAxisAlignment.CENTER)

    # ── 区域 ──
    zone_f = _norm_tf("区域 (Zone)，如 710", str(task.zone or ""), readonly=_ZONE_LOCKED)
    print(f"[EDIT] zone='{task.zone}' locked={_ZONE_LOCKED}")
    _fields["zone"] = zone_f

    # ── 交接班日志 ──
    if _LOG_LOCKED:
        log_f = ft.Text(task.shift_handover_log or "—", size=s(13),
                        color=theme.text_disabled, font_family=ff)
    else:
        log_f = ft.TextField(
            label="交接班日志", value=task.shift_handover_log or "",
            border_color=theme.border, focused_border_color=theme.info,
            text_style=ft.TextStyle(color="#e0e0e0", size=s(13), font_family=ff),
            bgcolor=theme.card, multiline=True, min_lines=2, max_lines=5,
            border_radius=s(6), dense=True,
        )

    # ── 保存 ──
    def save(_):
        from app.ui.widgets.toast import Toast
        if not _TITLE_LOCKED:
            ttl = (title_gf.value or "").strip()
            if not ttl:
                Toast.show(page, "请输入标题", "warning"); return
        else:
            ttl = task.title

        changes = {}
        if not _TITLE_LOCKED:
            changes["title"] = ttl
        if not _DESC_LOCKED:
            changes["description"] = (desc_gf.value or "").strip()
        if not _CORE_LOCKED:
            changes["aircraft_reg"] = (reg_f.value or "").strip().upper()
            changes["ata_chapter"] = (ata_gf.value or "").strip()
        if not _PRI_LOCKED:
            changes["priority"] = _sel_pri[0]
        if not _TYPE_LOCKED:
            changes["task_type"] = type_dd.value or "troubleshoot"
        if not _EMP_LOCKED:
            eid = (emp_id_f.value or "").strip()
            ename = (emp_name_f.value or "").strip()
            changes["employee_id"] = eid
            changes["employee_name"] = ename
            if ename:
                changes["assignee"] = ename
        if not _TIME_LOCKED:
            ps = _get_dt(start_date_state, sh, sm)
            pe = _get_dt(due_date_state, eh, em)
            changes["planned_start"] = ps
            changes["planned_end"] = pe
            try:
                hv = (hours_f.value or "").strip()
                changes["estimated_hours"] = float(hv) if hv else 0.0
            except ValueError:
                pass
        if not _ZONE_LOCKED:
            changes["zone"] = (zone_f.value or "").strip()
        if not _LOG_LOCKED:
            changes["shift_handover_log"] = (log_f.value or "").strip()

        task_service.update_task(task.id, **changes)
        _close_dlg()
        Toast.show(page, "任务已更新", "success")

    # ── 组装 ──
    sep = ft.Divider(height=s(10), color=ft.Colors.TRANSPARENT)
    header = ft.Container(
        ft.Row([
            ft.Icon(ft.Icons.EDIT_OUTLINED, size=s(15), color="#5294e2"),
            ft.Text("编辑任务", size=s(14), weight=ft.FontWeight.W_600,
                    color=theme.text_primary, font_family=ff),
            ft.Container(expand=True),
            ft.Text(f"{task.status.value} | {task.work_order_id or task.id}",
                    size=s(10), color=theme.text_secondary, font_family=ff),
            ft.Container(width=s(8)),
            ft.IconButton(ft.Icons.CLOSE, icon_size=s(16), icon_color=theme.text_secondary,
                style=ft.ButtonStyle(bgcolor=ft.Colors.TRANSPARENT, overlay_color=ft.Colors.RED_900,
                    shape=ft.RoundedRectangleBorder(radius=s(4))),
                on_click=lambda e: _close_dlg()),
        ], spacing=s(8)),
        padding=ft.padding.only(left=s(14), top=s(8), right=s(6), bottom=s(8)),
        border=ft.border.only(bottom=ft.BorderSide(1, theme.border)),
    )

    form = ft.Container(
        ft.Column([
            _label("任务标题", required=not _TITLE_LOCKED), title_gf, sep,
            _label("任务描述"), desc_gf, sep,
            ft.Row([_col(_label("飞机注册号", required=not _CORE_LOCKED), reg_f),
                    _col(_label("ATA 章节", required=not _CORE_LOCKED), ata_gf)], spacing=s(12)), sep,
            ft.Row([_col(_label("员工 ID"), emp_id_f),
                    _col(_label("员工姓名"), emp_name_f)], spacing=s(12)), sep,
            _label("优先级"), pri_row, sep,
            ft.Row([_col(_label("任务类型"), type_dd),
                    ft.Container(width=s(12)),
                    _col(_label("计划工时"), hours_f)], spacing=s(0)), sep,
            _label("计划时间"),
            _date_row("开始", start_date_ctrl, sh, sm),
            ft.Container(height=s(4)),
            _date_row("完成", due_date_ctrl, eh, em), sep,
            ft.Row([_col(_label("区域"), zone_f)], spacing=s(12)), sep,
            _label("交接班日志"), log_f,
        ], spacing=s(4), tight=True),
        padding=ft.padding.only(left=s(14), top=s(14), right=s(14), bottom=s(14)),
    )

    # parts_hold 取消阻塞按钮
    extra_btns = []
    if st == "parts_hold" and task.is_blocked:
        def _unblock(e):
            try:
                task_service.unblock_task(task.id, user="user")
                _close_dlg()
                from app.ui.widgets.toast import Toast
                Toast.show(page, "已取消阻塞", "success")
            except Exception as ex:
                from app.ui.widgets.toast import Toast
                Toast.show(page, f"取消失败: {ex}", "error")
        extra_btns.append(
            ft.OutlinedButton("取消阻塞", icon=ft.Icons.LOCK_OPEN_OUTLINED,
                on_click=_unblock,
                style=ft.ButtonStyle(
                    color=theme.error, side=ft.BorderSide(1, theme.error),
                    shape=ft.RoundedRectangleBorder(radius=s(6)),
                    padding=ft.padding.symmetric(horizontal=s(12), vertical=s(6)),
                    text_style=ft.TextStyle(size=s(11), font_family=ff))))

    btn_st = ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=s(6)),
        padding=ft.padding.only(left=s(18), top=s(7), right=s(18), bottom=s(7)),
        text_style=ft.TextStyle(size=s(12), font_family=ff))
    footer = ft.Container(
        ft.Row(extra_btns + [
            ft.Container(expand=True),
            ft.TextButton("取消", on_click=lambda e: _close_dlg(),
                style=ft.ButtonStyle(shape=btn_st.shape, padding=btn_st.padding,
                    text_style=btn_st.text_style, side=ft.BorderSide(1, theme.border),
                    color=theme.text_secondary)),
            ft.ElevatedButton("保存", on_click=save,
                style=ft.ButtonStyle(shape=btn_st.shape, padding=btn_st.padding,
                    text_style=btn_st.text_style, bgcolor="#5294e2",
                    color=ft.Colors.WHITE, elevation=0)),
        ], spacing=s(8)),
        padding=ft.padding.only(left=s(14), top=s(8), right=s(14), bottom=s(10)),
        border=ft.border.only(top=ft.BorderSide(1, theme.border)),
    )

    print(f"[EDIT] opening dialog: st={st} locked={{core:{_CORE_LOCKED} pri:{_PRI_LOCKED} type:{_TYPE_LOCKED} emp:{_EMP_LOCKED} time:{_TIME_LOCKED} zone:{_ZONE_LOCKED} title:{_TITLE_LOCKED} desc:{_DESC_LOCKED} log:{_LOG_LOCKED}}}")

    # 照搬 CreateTaskDialog 的定位逻辑：OverlayDimmer + Stack 绝对定位
    PW, PH = 700, 750
    cx = max(0, (page.width - PW) // 2)
    cy = max(10, (page.height - PH) // 2)

    from app.ui.widgets.overlay_dimmer import OverlayDimmer
    panel = ft.Container(
        content=ft.Column([header,
            ft.ListView([form], spacing=0, expand=True, padding=0),
            footer], spacing=0, tight=True),
        width=PW, height=PH,
        bgcolor=theme.surface, border_radius=s(10),
        border=ft.border.all(1, theme.border),
        shadow=ft.BoxShadow(spread_radius=1, blur_radius=20, color="#000000aa"),
        left=cx, top=cy,
    )

    _dimmer_ref: list = [None]
    def _close_dlg():
        if _dimmer_ref[0] is not None:
            _dimmer_ref[0].close()
    _dimmer_ref[0] = OverlayDimmer.open(page, panel, dim_opacity=0.55,
                                         on_dimmer_click=_close_dlg)

