"""新建任务弹窗 — overlay 居中面板 + 全屏变暗遮罩."""

import flet as ft
from app.config.theme import theme
from app.core.services.task_service import task_service
from app.ui.widgets.overlay_dimmer import OverlayDimmer


class CreateTaskDialog:
    """新建任务弹窗（单例，OverlayDimmer 包裹）。"""

    _dimmer: OverlayDimmer | None = None
    _page: ft.Page | None = None
    _open = False

    @classmethod
    def open(cls, page: ft.Page):
        if cls._open:
            return
        cls._page = page
        cls._open = True
        cls._dimmer = OverlayDimmer.open(
            page, cls._build(), dim_opacity=0.55, close_on_dimmer_click=True)

    @classmethod
    def close(cls):
        if not cls._open:
            return
        cls._open = False
        if cls._dimmer:
            cls._dimmer.close()
            cls._dimmer = None

    @classmethod
    def _build(cls) -> ft.Container:
        ff = theme.font_family
        page = cls._page

        title_f = ft.TextField(
            hint_text="描述故障或维护需求...",
            border_color=theme.border, focused_border_color=theme.info,
            text_style=ft.TextStyle(color=theme.text_primary, size=theme.font_md, font_family=ff),
            bgcolor=theme.card, dense=True,
        )
        reg_f = ft.TextField(
            hint_text="飞机注册号，如 B-5823", width=200,
            border_color=theme.border, focused_border_color=theme.info,
            text_style=ft.TextStyle(color=theme.text_primary, size=theme.font_md, font_family=ff),
            bgcolor=theme.card, dense=True,
        )
        ata_f = ft.TextField(
            hint_text="ATA 章节，如 32-41-03", width=200,
            border_color=theme.border, focused_border_color=theme.info,
            text_style=ft.TextStyle(color=theme.text_primary, size=theme.font_md, font_family=ff),
            bgcolor=theme.card, dense=True,
        )
        ghost_hint = ft.Text("", size=theme.font_xs, color=theme.type_removal_install,
                             font_family=ff, italic=True)

        def on_title_change(e):
            val = (e.control.value or "").strip()
            if len(val) >= 3:
                try:
                    from app.ui.services.agent_service import AgentService
                    sug = AgentService.get_suggestions(val)
                    ata = sug.get("ata_chapter", "")
                    if ata and not ata_f.value:
                        ata_f.value = ata; ata_f.update()
                    ghost_hint.value = f"AI: ATA {ata}" if ata else ""
                    ghost_hint.update()
                except Exception:
                    ghost_hint.value = ""
        title_f.on_change = on_title_change

        pri_dd = ft.Dropdown(
            value="cat_c", dense=True,
            options=[ft.dropdown.Option(k, v) for k, v in [
                ("aog", "AOG — 立即"), ("cat_a", "Cat A — 当日"),
                ("cat_b", "Cat B — 72h"), ("cat_c", "Cat C — 10 天"),
                ("cat_d", "Cat D — 120 天")]],
            border_color=theme.border, focused_border_color=theme.info,
            bgcolor=theme.card, width=200,
        )
        type_dd = ft.Dropdown(
            value="troubleshoot", dense=True,
            options=[ft.dropdown.Option(k, v) for k, v in [
                ("troubleshoot", "排故"), ("inspection", "检查"),
                ("servicing", "勤务"), ("removal_install", "拆装"),
                ("test", "测试"), ("repair", "修复")]],
            border_color=theme.border, focused_border_color=theme.info,
            bgcolor=theme.card, width=200,
        )
        assignee_f = ft.TextField(
            hint_text="负责人，如 张工", width=200,
            border_color=theme.border, focused_border_color=theme.info,
            text_style=ft.TextStyle(color=theme.text_primary, size=theme.font_md, font_family=ff),
            bgcolor=theme.card, dense=True,
        )
        zone_f = ft.TextField(
            hint_text="区域 (Zone)，如 710", width=200,
            border_color=theme.border, focused_border_color=theme.info,
            text_style=ft.TextStyle(color=theme.text_primary, size=theme.font_md, font_family=ff),
            bgcolor=theme.card, dense=True,
        )

        def _create(_):
            t = (title_f.value or "").strip()
            if not t:
                from app.ui.widgets.toast import Toast
                Toast.show(cls._page, "请输入标题", "warning")
                return
            task_service.create_task(
                title=t,
                aircraft_reg=(reg_f.value or "").strip(),
                ata_chapter=(ata_f.value or "").strip(),
                priority=pri_dd.value or "cat_c",
                task_type=type_dd.value or "troubleshoot",
                assignee=(assignee_f.value or "").strip() or None,
                zone=(zone_f.value or "").strip() or None,
            )
            cls.close()
            from app.ui.widgets.toast import Toast
            Toast.show(cls._page, f"已创建: {t}", "success")

        # 标题栏
        title_bar = ft.Container(
            content=ft.Row([
                ft.Text("新建维护任务", size=theme.font_lg, weight=ft.FontWeight.W_600,
                        color=theme.text_primary, font_family=ff),
                ft.Container(expand=True),
                ft.IconButton(ft.Icons.CLOSE, icon_size=16, icon_color=ft.Colors.GREY_400,
                              on_click=lambda e: cls.close()),
            ]),
            padding=ft.padding.only(left=20, top=14, right=8, bottom=8),
        )

        # 表单
        form = ft.Container(
            content=ft.Column([
                ft.Text("任务标题", size=12, color=theme.text_secondary, font_family=ff),
                title_f, ghost_hint,
                ft.Container(height=8),
                ft.Row([reg_f, ata_f], spacing=12),
                ft.Row([pri_dd, type_dd], spacing=12),
                ft.Row([assignee_f, zone_f], spacing=12),
            ], spacing=4, tight=True),
            padding=ft.padding.only(left=20, right=20, bottom=16),
        )

        # 底部按钮
        btn_base = ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=6),
            padding=ft.padding.only(left=20, top=8, right=20, bottom=8),
            text_style=ft.TextStyle(size=13, font_family=ff),
        )
        footer = ft.Container(
            content=ft.Row([
                ft.Container(expand=True),
                ft.OutlinedButton("取消", on_click=lambda e: cls.close(),
                    style=ft.ButtonStyle(
                        shape=btn_base.shape,
                        padding=btn_base.padding,
                        text_style=btn_base.text_style,
                        side=ft.BorderSide(1, theme.border),
                        color=theme.text_primary,
                    )),
                ft.OutlinedButton("创建", on_click=_create,
                    style=ft.ButtonStyle(
                        shape=btn_base.shape,
                        padding=btn_base.padding,
                        text_style=btn_base.text_style,
                        side=ft.BorderSide(1, theme.info),
                        color=theme.info,
                    )),
            ], spacing=8),
            padding=ft.padding.only(left=16, top=8, right=16, bottom=10),
            border=ft.border.only(top=ft.BorderSide(1, theme.border)),
        )

        # 面板
        P_W, P_H = 460, 420
        cx = (page.width - P_W) // 2
        cy = (page.height - P_H) // 2
        return ft.Container(
            content=ft.Column([title_bar, form, footer], spacing=0, tight=True),
            width=P_W, bgcolor=theme.surface,
            border_radius=theme.radius_md,
            border=ft.border.all(1, theme.border),
            shadow=ft.BoxShadow(spread_radius=1, blur_radius=16, color="#000000aa"),
            left=cx, top=cy,
        )
