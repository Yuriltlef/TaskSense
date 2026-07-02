# -*- coding: utf-8 -*-
"""新建任务弹窗 — GhostTextField 内联幽灵 + 跨字段 AI 补全."""

import flet as ft
from app.config.theme import theme, s
from app.core.services.task_service import task_service
from app.core.services.employee_service import employee_service
from app.core.validators import TaskValidators, BusinessRuleError
from app.ui.widgets.overlay_dimmer import OverlayDimmer
from app.ui.widgets.ghost_text import GhostTextField, handle_ghost_keyboard


class CreateTaskDialog:
    _dimmer = None
    _page = None
    _open = False
    _fields: dict = {}  # field_name → control reference

    @classmethod
    def open(cls, page):
        if cls._open: return
        cls._page = page; cls._open = True; cls._fields = {}
        cls._dimmer = OverlayDimmer.open(page, cls._build(), dim_opacity=0.55,
                                         on_dimmer_click=lambda: cls.close())

    @classmethod
    def close(cls):
        if not cls._open: return
        cls._open = False
        if cls._dimmer: cls._dimmer.close(); cls._dimmer = None

    @classmethod
    def _build(cls):
        ff = theme.font_family; page = cls._page

        # 键盘：幽灵文本 Tab/Esc
        _orig_kb = page.on_keyboard_event
        page.on_keyboard_event = lambda e: handle_ghost_keyboard(e) or (_orig_kb(e) if _orig_kb else None)

        # ── helpers ──
        def _norm_tf(hint="", **kw):
            return ft.TextField(
                hint_text=hint, border_color=theme.border,
                focused_border_color=theme.info, cursor_color=theme.info,
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

        # ── 上下文：收集所有已填字段 ──
        def _get_ctx():
            return {fn: (cls._fields[fn].value if fn in cls._fields else "")
                     for fn in ["title", "description", "ata_chapter", "aircraft_reg",
                                "employee_id", "employee_name", "zone"]}

        # ── 幽灵建议填充回调 ──
        def _on_filled(target_field: str, value: str):
            """AI 建议接受后，填入对应字段。"""
            ctrl = cls._fields.get(target_field)
            if ctrl is None:
                return
            if hasattr(ctrl, 'text_field'):
                ctrl = ctrl.text_field
            ctrl.value = value
            try: ctrl.update()
            except Exception: pass

        # ── 字段 ──
        _ERR_HINTS = {}

        # title (GhostTextField — AI 增强)
        title_gf = GhostTextField(
            hint_text="描述故障或维护需求...", field_name="title",
            get_context=_get_ctx, on_field_filled=_on_filled,
        )
        cls._fields["title"] = title_gf
        _ERR_HINTS[title_gf] = "描述故障或维护需求..."

        # description (GhostTextField — AI 增强)
        desc_gf = GhostTextField(
            hint_text="详细任务描述、步骤说明...", field_name="description",
            get_context=_get_ctx, on_field_filled=_on_filled,
            multiline=True, min_lines=3,
        )
        cls._fields["description"] = desc_gf
        _ERR_HINTS[desc_gf] = "详细任务描述、步骤说明..."

        # aircraft_reg
        reg_f = _norm_tf("飞机注册号，如 B-5823")
        cls._fields["aircraft_reg"] = reg_f
        _ERR_HINTS[reg_f] = "飞机注册号，如 B-5823"

        # ata_chapter (GhostTextField — AI 增强)
        ata_gf = GhostTextField(
            hint_text="ATA 章节，如 32-41-03", field_name="ata_chapter",
            get_context=_get_ctx, on_field_filled=_on_filled,
        )
        cls._fields["ata_chapter"] = ata_gf
        _ERR_HINTS[ata_gf] = "ATA 章节，如 32-41-03"

        # employee_id
        emp_id_f = _norm_tf("员工 ID，如 ZH001")
        cls._fields["employee_id"] = emp_id_f
        def _on_emp_id(e):
            val = (e.control.value or "").strip()
            if not val:
                cls._fields["employee_name"].value = ""
                try: cls._fields["employee_name"].update()
                except Exception: pass
                return
            # 强匹配：必须精确匹配员工 ID
            emp = employee_service.get_employee(val)
            if emp:
                if emp.get("available", True):
                    cls._fields["employee_name"].value = emp["name"]
                else:
                    cls._fields["employee_name"].value = f"{emp['name']}(不可用)"
            else:
                cls._fields["employee_name"].value = "未知员工"
            try: cls._fields["employee_name"].update()
            except Exception: pass
        emp_id_f.on_change = _on_emp_id

        # employee_name
        emp_name_f = _norm_tf("员工姓名，如 张工")
        cls._fields["employee_name"] = emp_name_f

        # ── priority ──
        _PRI_OPTS = [("aog","AOG",theme.priority_color("aog")),("cat_a","Cat A",theme.priority_color("cat_a")),
                     ("cat_b","Cat B",theme.priority_color("cat_b")),("cat_c","Cat C",theme.priority_color("cat_c")),
                     ("cat_d","Cat D",theme.priority_color("cat_d"))]
        _sel_pri = ["cat_c"]; _pri_btns = []
        def _mk_pb(v,l,c):
            sel = (v==_sel_pri[0])
            b = ft.Container(ft.Text(l,size=s(10),color=c if not sel else ft.Colors.WHITE,font_family=ff,weight=ft.FontWeight.W_600),
                padding=ft.padding.symmetric(horizontal=s(10),vertical=s(5)),border_radius=s(4),
                bgcolor=c if sel else ft.Colors.TRANSPARENT,border=ft.border.all(1,c),
                on_click=lambda e,x=v: _on_pri(x))
            _pri_btns.append((v,b)); return b
        def _on_pri(v):
            _sel_pri[0]=v
            for pv,b in _pri_btns:
                c=theme.priority_color(pv);b.bgcolor=c if pv==v else ft.Colors.TRANSPARENT
                b.content.color=ft.Colors.WHITE if pv==v else c;b.update()
        pri_row = ft.Row([_mk_pb(v,l,c) for v,l,c in _PRI_OPTS],spacing=s(6),tight=True)

        # ── time ──
        sd=_norm_tf("2026-07-02",width=120);sh=_norm_tf("08",width=58);sm=_norm_tf("00",width=58)
        ed=_norm_tf("2026-07-02",width=120);eh=_norm_tf("12",width=58);em=_norm_tf("00",width=58)
        def _dp(tf):
            def o(e_): dp_=ft.DatePicker(on_change=lambda e,t=tf: _on_dp(t,e));page.overlay.append(dp_);dp_.pick_date()
            return o
        def _on_dp(tf,e):
            if e.control.value: tf.value=e.control.value.strftime("%Y-%m-%d");tf.update()
        sd.read_only=True;sd.on_click=_dp(sd);ed.read_only=True;ed.on_click=_dp(ed)
        hours_f = _norm_tf("（可选）", width=120)
        zone_f = _norm_tf("区域 (Zone)，如 710")
        cls._fields["zone"] = zone_f

        type_dd = ft.Dropdown(value="troubleshoot",dense=True,
            options=[ft.dropdown.Option(k,v) for k,v in [("troubleshoot","排故"),("inspection","检查"),
                ("servicing","勤务"),("removal_install","拆装"),("test","测试"),("repair","修复")]],
            border_color=theme.border,focused_border_color=theme.info,bgcolor=theme.card,
            text_style=ft.TextStyle(color="#e0e0e0",size=s(12),font_family=ff),border_radius=s(6))

        # ── validation ──
        def _create(_):
            from app.ui.widgets.toast import Toast
            for c,h in _ERR_HINTS.items():
                if hasattr(c,'border_color'): c.border_color=theme.border;c.hint_text=h

            t=title_gf.value;d=(desc_gf.value or "").strip();reg=(reg_f.value or "").strip().upper()
            ata=(ata_gf.value or "").strip();eid=(emp_id_f.value or "").strip();ename=(emp_name_f.value or "").strip()

            if not t:_err(title_gf,"请输入标题");return
            if not d:_err(desc_gf,"请输入描述");return
            if not reg:_err(reg_f,"请输入飞机注册号");return
            if not ata:_err(ata_gf,"请输入ATA章节");return
            try:TaskValidators.validate_aircraft_reg(reg)
            except BusinessRuleError as e:_err(reg_f,e.message);return
            try:TaskValidators.validate_ata_chapter(ata)
            except BusinessRuleError as e:_err(ata_gf,e.message);return
            if eid:
                try:TaskValidators.validate_employee(eid)
                except BusinessRuleError as e:_err(emp_id_f,e.message);return

            from datetime import datetime;ps=pe=None
            try:
                sd_=(sd.value or "").strip()
                if sd_:
                    sh_=(sh.value or "0").strip();sm_=(sm.value or "0").strip()
                    ps=datetime.strptime(f"{sd_} {int(sh_):02d}:{int(sm_):02d}","%Y-%m-%d %H:%M")
            except (ValueError,OverflowError):_err(sd,"日期无效");return
            try:
                ed_=(ed.value or "").strip()
                if ed_:
                    eh_=(eh.value or "0").strip();em_=(em.value or "0").strip()
                    pe=datetime.strptime(f"{ed_} {int(eh_):02d}:{int(em_):02d}","%Y-%m-%d %H:%M")
            except (ValueError,OverflowError):_err(ed,"日期无效");return
            if ps and pe:
                try:TaskValidators.validate_planned_time(ps,pe)
                except BusinessRuleError as e:_err(sd,e.message);return

            h=0.0;hv=(hours_f.value or "").strip()
            if hv:
                try:h=float(hv);TaskValidators.validate_hours(h)
                except ValueError:_err(hours_f,"请输入数字");return
                except BusinessRuleError as e:_err(hours_f,e.message);return

            task_service.create_task(title=t,description=d,aircraft_reg=reg,ata_chapter=ata,
                priority=_sel_pri[0],task_type=type_dd.value or "troubleshoot",
                assignee=ename or None,employee_id=eid or "",employee_name=ename or "",
                planned_start=ps,planned_end=pe,estimated_hours=h,
                zone=(zone_f.value or "").strip() or "")
            cls.close();Toast.show(page,f"已创建: {t}","success")

        def _err(ctrl,msg):
            if isinstance(ctrl, GhostTextField): ctrl.border_color=theme.error;ctrl.update()
            else: ctrl.border_color=theme.error;ctrl.hint_text=msg;ctrl.update()

        # ── assembly ──
        sep=ft.Divider(height=s(10),color=ft.Colors.TRANSPARENT)
        header=ft.Container(ft.Row([
            ft.Icon(ft.Icons.BUILD_OUTLINED,size=s(15),color="#5294e2"),
            ft.Text("新建维护任务",size=s(14),weight=ft.FontWeight.W_600,color=theme.text_primary,font_family=ff),
            ft.Container(expand=True),
            ft.IconButton(ft.Icons.CLOSE,icon_size=s(16),icon_color=theme.text_secondary,
                style=ft.ButtonStyle(bgcolor=ft.Colors.TRANSPARENT,overlay_color=ft.Colors.RED_900,
                shape=ft.RoundedRectangleBorder(radius=s(4))),on_click=lambda e:cls.close()),
        ],spacing=s(8)),padding=ft.padding.only(left=s(14),top=s(8),right=s(6),bottom=s(8)),
            border=ft.border.only(bottom=ft.BorderSide(1,theme.border)))

        form=ft.Container(ft.Column([
            _label("任务标题",required=True),title_gf,sep,
            _label("任务描述",required=True),desc_gf,sep,
            ft.Row([_col(_label("飞机注册号",required=True),reg_f),
                    _col(_label("ATA 章节",required=True),ata_gf)],spacing=s(12)),sep,
            ft.Row([_col(_label("员工 ID"),emp_id_f),
                    _col(_label("员工姓名"),emp_name_f)],spacing=s(12)),sep,
            _label("优先级"),pri_row,sep,
            ft.Row([_col(_label("任务类型"),type_dd),ft.Container(width=s(12)),
                    _col(_label("计划工时"),hours_f)],spacing=s(0)),sep,
            _label("计划时间"),
            ft.Row([ft.Text("开始",size=s(11),color=theme.text_secondary,font_family=ff),
                sd,sh,ft.Text("时",size=s(11),color=theme.text_secondary,font_family=ff),
                sm,ft.Text("分",size=s(11),color=theme.text_secondary,font_family=ff),
                ft.Container(width=s(16)),
                ft.Text("完成",size=s(11),color=theme.text_secondary,font_family=ff),
                ed,eh,ft.Text("时",size=s(11),color=theme.text_secondary,font_family=ff),
                em,ft.Text("分",size=s(11),color=theme.text_secondary,font_family=ff),
            ],spacing=s(6),wrap=True),sep,
            ft.Row([_col(_label("区域"),zone_f)],spacing=s(12)),
        ],spacing=s(4),tight=True),padding=ft.padding.only(left=s(14),top=s(14),right=s(14),bottom=s(14)))

        btn_st=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=s(6)),
            padding=ft.padding.only(left=s(18),top=s(7),right=s(18),bottom=s(7)),
            text_style=ft.TextStyle(size=s(12),font_family=ff))
        footer=ft.Container(ft.Row([
            ft.Container(expand=True),
            ft.OutlinedButton("取消",on_click=lambda e:cls.close(),
                style=ft.ButtonStyle(shape=btn_st.shape,padding=btn_st.padding,
                text_style=btn_st.text_style,side=ft.BorderSide(1,theme.border),color=theme.text_secondary)),
            ft.ElevatedButton("创建任务",on_click=_create,
                style=ft.ButtonStyle(shape=btn_st.shape,padding=btn_st.padding,
                text_style=btn_st.text_style,bgcolor="#5294e2",color=ft.Colors.WHITE,elevation=0)),
        ],spacing=s(8)),padding=ft.padding.only(left=s(14),top=s(8),right=s(14),bottom=s(10)),
            border=ft.border.only(top=ft.BorderSide(1,theme.border)))

        PW,PH=720,780;cx=max(0,(page.width-PW)//2);cy=max(20,(page.height-PH)//2)
        return ft.Container(
            content=ft.Column([
                header,
                ft.ListView([form], spacing=0, expand=True, padding=0),
                footer,
            ], spacing=0, tight=True),
            width=PW,height=PH,bgcolor=theme.surface,border_radius=s(10),
            border=ft.border.all(1,theme.border),
            shadow=ft.BoxShadow(spread_radius=1,blur_radius=20,color="#000000aa"),left=cx,top=cy)
