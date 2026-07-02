"""新建任务弹窗 — overlay 居中面板 + 全屏变暗遮罩."""

import flet as ft
from app.config.theme import theme, s
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
    def _build(cls) -> ft.Container:
        ff = theme.font_family
        page = cls._page

        # ── 输入框工厂 ──
        def field(hint="", width=None):
            return ft.TextField(
                hint_text=hint,
                border_color=theme.border,
                focused_border_color=theme.info,
                cursor_color=theme.info,
                text_style=ft.TextStyle(
                    color="#e0e0e0", size=s(13), font_family=ff),
                hint_style=ft.TextStyle(
                    color=theme.text_secondary, size=s(12), font_family=ff),
                bgcolor=theme.card,
                dense=True,
                content_padding=ft.padding.only(
                    left=s(10), top=s(8), right=s(10), bottom=s(8)),
                border_radius=s(6),
                width=width,
            )

        # ── 下拉框工厂 ──
        def dropdown(value, options, width=None):
            return ft.Dropdown(
                value=value, dense=True,
                options=[ft.dropdown.Option(k, v) for k, v in options],
                border_color=theme.border,
                focused_border_color=theme.info,
                bgcolor=theme.card,
                text_style=ft.TextStyle(
                    color="#e0e0e0", size=s(12), font_family=ff),
                border_radius=s(6),
                width=width,
            )

        # ── 标签 ──
        def label(text, size=s(12)):
            return ft.Text(
                text, size=size, color=theme.text_primary,
                font_family=ff, weight=ft.FontWeight.W_500)

        # ── 表单控件 ──
        title_f = field("描述故障或维护需求...")
        reg_f = field("飞机注册号，如 B-5823", width=200)
        ata_f = field("ATA 章节，如 32-41-03", width=200)
        assignee_f = field("负责人，如 张工", width=200)
        zone_f = field("区域 (Zone)，如 710", width=200)

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
                        ata_f.value = ata; ata_f.update()
                    ghost_hint.value = f"AI: ATA {ata}" if ata else ""
                    ghost_hint.update()
                except Exception:
                    ghost_hint.value = ""
        title_f.on_change = on_title_change

        pri_dd = dropdown("cat_c", [
            ("aog", "AOG — 立即"), ("cat_a", "Cat A — 当日"),
            ("cat_b", "Cat B — 72h"), ("cat_c", "Cat C — 10 天"),
            ("cat_d", "Cat D — 120 天")], width=200)
        type_dd = dropdown("troubleshoot", [
            ("troubleshoot", "排故"), ("inspection", "检查"),
            ("servicing", "勤务"), ("removal_install", "拆装"),
            ("test", "测试"), ("repair", "修复")], width=200)

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

        # ── 标题栏 ──
        header = ft.Container(
            ft.Row([
                ft.Icon(ft.Icons.BUILD_OUTLINED, size=s(15), color="#5294e2"),
                ft.Text("新建维护任务", size=s(14),
                        weight=ft.FontWeight.W_600,
                        color=theme.text_primary, font_family=ff),
                ft.Container(expand=True),
                ft.IconButton(
                    ft.Icons.CLOSE, icon_size=s(16),
                    icon_color=theme.text_secondary,
                    on_click=lambda e: cls.close()),
            ], spacing=s(8)),
            padding=ft.padding.only(left=s(14), top=s(8), right=s(6), bottom=s(8)),
            border=ft.border.only(
                bottom=ft.BorderSide(1, theme.border)),
        )

        # ── 表单区 ──
        form = ft.Container(
            ft.Column([
                label("任务标题"),
                title_f,
                ghost_hint,
                ft.Divider(height=s(14), color=ft.Colors.TRANSPARENT),
                ft.Row([reg_f, ata_f], spacing=s(12)),
                ft.Divider(height=s(14), color=ft.Colors.TRANSPARENT),
                ft.Row([pri_dd, type_dd], spacing=s(12)),
                ft.Divider(height=s(14), color=ft.Colors.TRANSPARENT),
                ft.Row([assignee_f, zone_f], spacing=s(12)),
            ], spacing=s(4), tight=True),
            padding=ft.padding.only(
                left=s(14), top=s(14), right=s(14), bottom=s(14)),
        )

        # ── 底部 ──
        btn_style = ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=s(6)),
            padding=ft.padding.only(left=s(18), top=s(7), right=s(18), bottom=s(7)),
            text_style=ft.TextStyle(size=s(12), font_family=ff),
        )
        footer = ft.Container(
            ft.Row([
                ft.Container(expand=True),
                ft.OutlinedButton(
                    "取消", on_click=lambda e: cls.close(),
                    style=ft.ButtonStyle(
                        shape=btn_style.shape,
                        padding=btn_style.padding,
                        text_style=btn_style.text_style,
                        side=ft.BorderSide(1, theme.border),
                        color=theme.text_secondary,
                    )),
                ft.ElevatedButton(
                    "创建任务", on_click=_create,
                    style=ft.ButtonStyle(
                        shape=btn_style.shape,
                        padding=btn_style.padding,
                        text_style=btn_style.text_style,
                        bgcolor="#5294e2",
                        color=ft.Colors.WHITE,
                        elevation=0,
                    )),
            ], spacing=s(8)),
            padding=ft.padding.only(
                left=s(14), top=s(8), right=s(14), bottom=s(10)),
            border=ft.border.only(
                top=ft.BorderSide(1, theme.border)),
        )

        # ── 面板 ──
        P_W, P_H = 460, 440
        cx = (page.width - P_W) // 2
        cy = (page.height - P_H) // 2
        return ft.Container(
            content=ft.Column([header, form, footer], spacing=0, tight=True),
            width=P_W,             bgcolor="#1c1c1c",
            border_radius=s(10),
            border=ft.border.all(1, theme.border),
            shadow=ft.BoxShadow(
                spread_radius=1, blur_radius=20, color="#000000aa"),
            left=cx, top=cy,
        )
