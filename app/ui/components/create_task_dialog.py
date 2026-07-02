# -*- coding: utf-8 -*-
"""新建任务弹窗."""

import flet as ft
from app.config.theme import theme, s
from app.core.services.task_service import task_service
from app.ui.widgets.overlay_dimmer import OverlayDimmer


class CreateTaskDialog:
    _dimmer = None
    _page = None
    _open = False

    @classmethod
    def open(cls, page):
        if cls._open:
            return
        cls._page = page
        cls._open = True
        cls._dimmer = OverlayDimmer.open(
            page, cls._build(), dim_opacity=0.55,
            on_dimmer_click=lambda: cls.close())

    @classmethod
    def close(cls):
        if not cls._open:
            return
        cls._open = False
        if cls._dimmer:
            cls._dimmer.close()
            cls._dimmer = None

    @classmethod
    def _build(cls):
        ff = theme.font_family
        page = cls._page

        def _field(hint="", width=None, multiline=False, min_lines=1):
            return ft.TextField(
                hint_text=hint, border_color=theme.border,
                focused_border_color=theme.info, cursor_color=theme.info,
                text_style=ft.TextStyle(
                    color="#e0e0e0", size=s(13), font_family=ff),
                hint_style=ft.TextStyle(
                    color=theme.text_secondary, size=s(12), font_family=ff),
                bgcolor=theme.card, dense=True, multiline=multiline,
                min_lines=min_lines, max_lines=min_lines + 2,
                content_padding=ft.padding.only(
                    left=s(10), top=s(8), right=s(10), bottom=s(8)),
                border_radius=s(6), width=width)

        def _dropdown(value, options, width=None):
            return ft.Dropdown(
                value=value, dense=True,
                options=[ft.dropdown.Option(k, v) for k, v in options],
                border_color=theme.border,
                focused_border_color=theme.info, bgcolor=theme.card,
                text_style=ft.TextStyle(
                    color="#e0e0e0", size=s(12), font_family=ff),
                border_radius=s(6),
                content_padding=ft.padding.only(
                    left=s(10), top=s(8), right=s(10), bottom=s(8)),
                width=width)

        def _label(text, required=False):
            if required:
                return ft.Text(spans=[
                    ft.TextSpan(text, ft.TextStyle(
                        color=theme.text_primary, size=s(12),
                        font_family=ff, weight=ft.FontWeight.W_500)),
                    ft.TextSpan(" *", ft.TextStyle(
                        color=theme.error, size=s(12),
                        font_family=ff, weight=ft.FontWeight.W_500))])
            return ft.Text(
                text, size=s(12), color=theme.text_primary,
                font_family=ff, weight=ft.FontWeight.W_500)

        def _col(lbl, ctrl):
            return ft.Column(
                [lbl, ctrl], spacing=s(4), tight=True, expand=True)

        title_f = _field("描述故障或维护需求...")
        desc_f = _field("详细任务描述、步骤说明...",
                        multiline=True, min_lines=2)
        reg_f = _field("飞机注册号，如 B-5823")
        ata_f = _field("ATA 章节，如 32-41-03")
        assignee_f = _field("负责人，如 张工")
        zone_f = _field("区域 (Zone)，如 710")

        ghost_hint = ft.Text(
            "", size=s(11), color=theme.type_removal_install,
            font_family=ff, italic=True)

        def on_title_change(e):
            val = (e.control.value or "").strip()
            if len(val) >= 3:
                try:
                    from app.ui.services.agent_service import AgentService
                    sug = AgentService.get_suggestions(val)
                    ata = sug.get("ata_chapter", "")
                    if ata and not ata_f.value:
                        ata_f.value = ata
                        ata_f.update()
                    ghost_hint.value = f"AI: ATA {ata}" if ata else ""
                    ghost_hint.update()
                except Exception:
                    ghost_hint.value = ""
        title_f.on_change = on_title_change

        type_dd = _dropdown("troubleshoot", [
            ("troubleshoot", "排故"), ("inspection", "检查"),
            ("servicing", "勤务"), ("removal_install", "拆装"),
            ("test", "测试"), ("repair", "修复")], width=200)

        def _set_error(ctrl, msg):
            ctrl.border_color = theme.error
            ctrl.hint_text = msg
            ctrl.update()

        def _clear_error(ctrl, hint):
            ctrl.border_color = theme.border
            ctrl.hint_text = hint

        def _create(_):
            from app.ui.widgets.toast import Toast
            t = (title_f.value or "").strip()
            d = (desc_f.value or "").strip()
            reg = (reg_f.value or "").strip().upper()
            ata = (ata_f.value or "").strip()

            hints = {
                title_f: "描述故障或维护需求...",
                desc_f: "详细任务描述、步骤说明...",
                reg_f: "飞机注册号，如 B-5823",
                ata_f: "ATA 章节，如 32-41-03"}
            for c, h in hints.items():
                _clear_error(c, h)

            if not t:
                _set_error(title_f, "请输入任务标题")
                return
            if not d:
                _set_error(desc_f, "请输入任务描述")
                return
            if not reg:
                _set_error(reg_f, "请输入飞机注册号")
                return
            if not ata:
                _set_error(ata_f, "请输入 ATA 章节")
                return

            task_service.create_task(
                title=t, description=d,
                aircraft_reg=reg, ata_chapter=ata,
                priority="cat_c",
                task_type=type_dd.value or "troubleshoot",
                assignee=(assignee_f.value or "").strip() or None,
                zone=(zone_f.value or "").strip() or None)
            cls.close()
            Toast.show(cls._page, f"已创建: {t}", "success")

        header = ft.Container(
            ft.Row([
                ft.Icon(ft.Icons.BUILD_OUTLINED,
                        size=s(15), color="#5294e2"),
                ft.Text("新建维护任务", size=s(14),
                        weight=ft.FontWeight.W_600,
                        color=theme.text_primary, font_family=ff),
                ft.Container(expand=True),
                ft.IconButton(
                    ft.Icons.CLOSE, icon_size=s(16),
                    icon_color=theme.text_secondary,
                    on_click=lambda e: cls.close())], spacing=s(8)),
            padding=ft.padding.only(
                left=s(14), top=s(8), right=s(6), bottom=s(8)),
            border=ft.border.only(
                bottom=ft.BorderSide(1, theme.border)))

        sep = ft.Divider(height=s(12), color=ft.Colors.TRANSPARENT)
        form = ft.Container(
            ft.Column([
                _label("任务标题", required=True), title_f, ghost_hint, sep,
                _label("任务描述", required=True), desc_f, sep,
                ft.Row([
                    _col(_label("飞机注册号", required=True), reg_f),
                    _col(_label("ATA 章节", required=True), ata_f),
                ], spacing=s(12)), sep,
                ft.Row([
                    _col(_label("负责人"), assignee_f),
                    _col(_label("区域"), zone_f),
                ], spacing=s(12)), sep,
                ft.Row([
                    _col(_label("任务类型"), type_dd),
                ], spacing=s(12)),
            ], spacing=s(4), tight=True),
            padding=ft.padding.only(
                left=s(14), top=s(14), right=s(14), bottom=s(14)))

        btn_style = ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=s(6)),
            padding=ft.padding.only(
                left=s(18), top=s(7), right=s(18), bottom=s(7)),
            text_style=ft.TextStyle(size=s(12), font_family=ff))
        footer = ft.Container(
            ft.Row([
                ft.Container(expand=True),
                ft.OutlinedButton("取消", on_click=lambda e: cls.close(),
                    style=ft.ButtonStyle(
                        shape=btn_style.shape, padding=btn_style.padding,
                        text_style=btn_style.text_style,
                        side=ft.BorderSide(1, theme.border),
                        color=theme.text_secondary)),
                ft.ElevatedButton("创建任务", on_click=_create,
                    style=ft.ButtonStyle(
                        shape=btn_style.shape, padding=btn_style.padding,
                        text_style=btn_style.text_style,
                        bgcolor="#5294e2", color=ft.Colors.WHITE,
                        elevation=0))], spacing=s(8)),
            padding=ft.padding.only(
                left=s(14), top=s(8), right=s(14), bottom=s(10)),
            border=ft.border.only(
                top=ft.BorderSide(1, theme.border)))

        P_W, P_H = 600, 620
        cx = (page.width - P_W) // 2
        cy = (page.height - P_H) // 2
        return ft.Container(
            content=ft.Column(
                [header, form, footer], spacing=0, tight=True,
                scroll=ft.ScrollMode.AUTO),
            width=P_W, height=P_H, bgcolor="#1c1c1c",
            border_radius=s(10),
            border=ft.border.all(1, theme.border),
            shadow=ft.BoxShadow(
                spread_radius=1, blur_radius=20, color="#000000aa"),
            left=cx, top=cy)
