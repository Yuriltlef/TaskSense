# -*- coding: utf-8 -*-
"""设置面板 — 页面内覆盖层，可拖拽 + 半屏变暗."""

import flet as ft
from app.config.theme import theme, SCALE, s
from app.config.settings_manager import SettingsManager
from app.ui.widgets.overlay_dimmer import OverlayDimmer

NAV_ITEMS = [
    ("llm",   "LLM / API",    ft.Icons.PSYCHOLOGY_OUTLINED),
    ("rag",   "RAG 知识库",   ft.Icons.SEARCH),
    ("ui",    "界面与主题",   ft.Icons.PALETTE_OUTLINED),
    ("agent", "Agent 行为",   ft.Icons.SMART_TOY_OUTLINED),
]

PANEL_W, PANEL_H = 720, 520


class SettingsOverlay:
    _panel: ft.Container | None = None
    _dimmer: OverlayDimmer | None = None
    _page: ft.Page | None = None
    _open = False
    _mgr = None
    _fields: dict = {}
    _active = ["llm"]
    _nav_ctrls: list = []
    _right: ft.Container | None = None
    _drag_start = (0, 0)

    # ── API ──

    @classmethod
    def open(cls, page: ft.Page):
        if cls._open:
            return
        cls._page = page
        cls._mgr = SettingsManager()
        cls._mgr.load()
        cls._fields = {}
        cls._active = ["llm"]
        cls._nav_ctrls = []
        cls._build()
        cls._open = True
        cls._dimmer = OverlayDimmer.open(
            page, cls._panel, dim_opacity=0.65,
            on_dimmer_click=lambda: cls.close())
        cls._switch("llm")
        page.update()

    @classmethod
    def close(cls):
        if not cls._open:
            return
        cls._open = False
        if cls._dimmer:
            cls._dimmer.close()
            cls._dimmer = None

    # ── Build ──

    @classmethod
    def _build(cls):
        ff = theme.font_family
        page = cls._page
        cx = (page.width - PANEL_W) // 2
        cy = (page.height - PANEL_H) // 2

        # ── 标题栏（可拖拽）──
        def on_bar_start(e: ft.DragStartEvent):
            cls._drag_start = (cls._panel.left or 0, cls._panel.top or 0)

        def on_bar_update(e: ft.DragUpdateEvent):
            cls._drag_start = (
                cls._drag_start[0] + int(e.delta_x),
                cls._drag_start[1] + int(e.delta_y),
            )
            nx = max(-PANEL_W // 3, min(
                cls._page.width - PANEL_W * 2 // 3, cls._drag_start[0]))
            ny = max(-40, min(cls._page.height - 40, cls._drag_start[1]))
            cls._panel.left = nx
            cls._panel.top = ny
            cls._panel.update()

        header_bg = theme.surface   # #0e0e0e
        header = ft.Container(
            content=ft.GestureDetector(
                content=ft.Row([
                    ft.Icon(ft.Icons.SETTINGS_OUTLINED, size=s(15), color="#5294e2"),
                    ft.Text("TaskSense", size=s(14),
                            weight=ft.FontWeight.W_600,
                            color=theme.text_primary, font_family=ff),
                    ft.Text("— 设置", size=s(12),
                            color=theme.text_secondary, font_family=ff),
                    ft.Container(expand=True),
                    ft.IconButton(
                        ft.Icons.CLOSE, icon_size=s(16),
                        icon_color=theme.text_secondary,
                        style=ft.ButtonStyle(
                            bgcolor=ft.Colors.TRANSPARENT,
                            overlay_color=ft.Colors.RED_900,
                            shape=ft.RoundedRectangleBorder(radius=s(4))),
                        on_click=lambda e: cls.close()),
                ], spacing=s(6)),
                mouse_cursor=ft.MouseCursor.MOVE,
                on_pan_start=on_bar_start,
                on_pan_update=on_bar_update,
            ),
            padding=ft.padding.only(
                left=s(14), top=s(8), right=s(6), bottom=s(8)),
            bgcolor=header_bg,
            border=ft.border.only(bottom=ft.BorderSide(1, theme.border)),
        )

        # ── 左侧导航 ──
        nav_bg = "#101010"   # 比 surface 稍亮，区分可交互区域
        for key, label, icon in NAV_ITEMS:
            sel = key == cls._active[0]
            c = ft.Container(
                content=ft.Row([
                    ft.Icon(icon, size=s(15),
                            color=theme.info if sel else theme.text_secondary),
                    ft.Text(label, size=s(12),
                            color=theme.text_primary if sel else theme.text_secondary,
                            font_family=ff,
                            weight=ft.FontWeight.W_500 if sel else ft.FontWeight.W_400),
                ], spacing=s(8)),
                padding=ft.padding.only(
                    left=s(10), top=s(8), right=s(12), bottom=s(8)),
                border_radius=s(6),
                bgcolor=ft.Colors.with_opacity(0.12, theme.info) if sel else None,
                margin=ft.margin.only(
                    left=s(6), right=s(6), top=s(2), bottom=s(2)),
                on_click=lambda e, k=key: cls._switch(k),
                data=key, ink=True,
            )
            cls._nav_ctrls.append(c)

        nav_panel = ft.Container(
            content=ft.Column(
                [ft.Container(height=s(6))] + cls._nav_ctrls,
                spacing=0),
            width=180, bgcolor=nav_bg,
            border=ft.border.only(
                right=ft.BorderSide(1, theme.border)),
        )

        # ── 右侧内容区 ──
        cls._right = ft.Container(
            bgcolor="#0c0c0c", expand=True,
            padding=ft.padding.all(s(18)))

        # ── 底部按钮 ──
        btn_style = ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=s(6)),
            padding=ft.padding.only(
                left=s(18), top=s(7), right=s(18), bottom=s(7)),
            text_style=ft.TextStyle(size=s(12), font_family=ff),
        )
        footer = ft.Container(
            content=ft.Row([
                ft.Container(expand=True),
                ft.OutlinedButton("取消", on_click=lambda e: cls.close(),
                    style=ft.ButtonStyle(
                        shape=btn_style.shape,
                        padding=btn_style.padding,
                        text_style=btn_style.text_style,
                        side=ft.BorderSide(1, theme.border),
                        color=theme.text_secondary,
                    )),
                ft.ElevatedButton("保存", on_click=cls._save,
                    style=ft.ButtonStyle(
                        shape=btn_style.shape,
                        padding=btn_style.padding,
                        text_style=btn_style.text_style,
                        bgcolor="#5294e2", color=ft.Colors.WHITE, elevation=0,
                    )),
            ], spacing=s(8)),
            padding=ft.padding.only(
                left=s(14), top=s(8), right=s(14), bottom=s(10)),
            bgcolor=header_bg,
            border=ft.border.only(top=ft.BorderSide(1, theme.border)),
        )

        # ── 面板内容 ──
        inner = ft.Container(
            content=ft.Column([
                header,
                ft.Row([nav_panel, cls._right], expand=True, spacing=0),
                footer,
            ], spacing=0, expand=True),
            border_radius=s(10),
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        )

        # ── 定位容器 ──
        cls._panel = ft.Container(
            content=ft.Container(
                content=inner,
                width=PANEL_W, height=PANEL_H,
                border_radius=s(10),
                border=ft.border.all(1, theme.border),
                shadow=ft.BoxShadow(
                    spread_radius=1, blur_radius=20, color="#000000aa"),
                bgcolor=ft.Colors.TRANSPARENT,
            ),
            left=cx, top=cy,
        )

    # ── Nav ──

    @classmethod
    def _switch(cls, key: str):
        cls._active[0] = key
        for ctrl in cls._nav_ctrls:
            is_sel = ctrl.data == key
            ctrl.bgcolor = (ft.Colors.with_opacity(0.12, theme.info)
                            if is_sel else None)
            iw = ctrl.content.controls[0]
            tw = ctrl.content.controls[1]
            iw.color = theme.info if is_sel else theme.text_secondary
            tw.color = theme.text_primary if is_sel else theme.text_secondary
            tw.weight = (ft.FontWeight.W_500 if is_sel
                         else ft.FontWeight.W_400)
        cls._right.content = cls._build_section(key)
        if cls._page:
            cls._page.update()

    # ── Form ──

    @classmethod
    def _label(cls, t):
        return ft.Text(
            t, size=s(11), color=theme.text_primary,
            font_family=theme.font_family, weight=ft.FontWeight.W_500)

    @classmethod
    def _tf(cls, sk, val, hint="", w=None, pw=False):
        ctrl = ft.TextField(
            value=str(val) if val is not None else "",
            hint_text=hint, width=w, password=pw, dense=True,
            border_color=theme.border,
            focused_border_color=theme.info,
            cursor_color=theme.info,
            text_style=ft.TextStyle(
                color="#e0e0e0", size=s(12), font_family=theme.font_family),
            hint_style=ft.TextStyle(
                color=theme.text_secondary, size=s(11),
                font_family=theme.font_family),
            bgcolor=theme.card,
            border_radius=s(6),
            content_padding=ft.padding.only(
                left=s(10), top=s(8), right=s(10), bottom=s(8)),
        )
        cls._fields[sk] = ctrl
        return ctrl

    @classmethod
    def _dd(cls, sk, val, opts, labels=None, w=None):
        ctrl = ft.Dropdown(
            value=str(val) if val is not None else "",
            options=[ft.dropdown.Option(
                o, labels.get(o, o) if labels else o) for o in opts],
            border_color=theme.border,
            focused_border_color=theme.info,
            bgcolor=theme.card, dense=True, width=w,
            text_style=ft.TextStyle(
                color="#e0e0e0", size=s(12), font_family=theme.font_family),
            border_radius=s(6),
            content_padding=ft.padding.only(
                left=s(10), top=s(8), right=s(10), bottom=s(8)),
        )
        cls._fields[sk] = ctrl
        return ctrl

    @classmethod
    def _section_title(cls, t):
        return ft.Text(
            t, size=s(14), weight=ft.FontWeight.W_600,
            color=theme.text_primary, font_family=theme.font_family)

    @classmethod
    def _spacer(cls):
        return ft.Divider(height=s(12), color=ft.Colors.TRANSPARENT)

    @classmethod
    def _build_section(cls, key):
        ff = theme.font_family
        data = cls._mgr.get_section(key)
        if key == "llm":
            return ft.Column([
                cls._section_title("LLM 模型配置"),
                cls._spacer(),
                cls._label("Provider"),
            cls._dd("llm.provider", data.get("provider"),
                    ["anthropic", "openai", "local"], w=220),
                cls._spacer(),
                cls._label("Model"),
                cls._tf("llm.model", data.get("model")),
                cls._spacer(),
                cls._label("API Key"),
                cls._tf("llm.api_key", data.get("api_key"), "sk-...", pw=True),
                cls._spacer(),
                cls._label("Base URL"),
                cls._tf("llm.base_url", data.get("base_url")),
                cls._spacer(),
                cls._label("Temperature / Max Tokens"),
                ft.Row([
                    cls._tf("llm.temperature", data.get("temperature"),
                            "0.0~1.0", 120),
                    cls._tf("llm.max_tokens", data.get("max_tokens"),
                            "tokens", 120),
                ], spacing=s(12)),
            ], spacing=0, scroll=ft.ScrollMode.AUTO, expand=True)
        elif key == "rag":
            return ft.Column([
                cls._section_title("RAG 知识库"),
                cls._spacer(),
                cls._label("Embedding Model"),
                cls._tf("rag.embedding_model", data.get("embedding_model")),
                cls._spacer(),
                cls._label("Vector Store"),
                cls._dd("rag.vector_store", data.get("vector_store"),
                        ["chroma", "qdrant"], w=220),
                cls._spacer(),
                cls._label("Chunk Size / Overlap"),
                ft.Row([
                    cls._tf("rag.chunk_size", data.get("chunk_size"),
                            "size", 120),
                    cls._tf("rag.chunk_overlap", data.get("chunk_overlap"),
                            "overlap", 120),
                ], spacing=s(12)),
                cls._spacer(),
                cls._label("Retrieval Top-K"),
                cls._tf("rag.retrieval_top_k", data.get("retrieval_top_k"),
                        "", 120),
            ], spacing=0, scroll=ft.ScrollMode.AUTO, expand=True)
        elif key == "ui":
            return ft.Column([
                cls._section_title("界面与主题"),
                cls._spacer(),
                cls._label("Theme"),
                cls._dd("ui.theme", data.get("theme"),
                        ["dark", "light"], w=220),
                cls._spacer(),
                cls._label("Language"),
                cls._dd("ui.language", data.get("language"),
                        ["zh", "en"], w=220),
                cls._spacer(),
                cls._label("Scale"),
                cls._tf("ui.scale", data.get("scale", SCALE), "", 120),
                cls._spacer(),
                cls._label("Card Preview Delay (ms)"),
                cls._tf("ui.card_preview_delay_ms",
                        data.get("card_preview_delay_ms"), "", 120),
            ], spacing=0, scroll=ft.ScrollMode.AUTO, expand=True)
        else:
            al = {"low": "Low", "medium": "Medium", "high": "High"}
            return ft.Column([
                cls._section_title("Agent 自主权"),
                cls._spacer(),
                cls._label("Triage"),
                cls._dd("agent.triage_autonomy",
                        data.get("triage_autonomy"),
                        ["low", "medium", "high"], al, w=220),
                cls._spacer(),
                cls._label("Suggest"),
                cls._dd("agent.suggest_autonomy",
                        data.get("suggest_autonomy"),
                        ["low", "medium", "high"], al, w=220),
                cls._spacer(),
                cls._label("Compliance"),
                cls._dd("agent.compliance_autonomy",
                        data.get("compliance_autonomy"),
                        ["low", "medium", "high"], al, w=220),
                cls._spacer(),
                cls._label("异常检测间隔 (分钟)"),
                cls._tf("agent.anomaly_check_interval_minutes",
                        data.get("anomaly_check_interval_minutes"), "", 120),
            ], spacing=0, scroll=ft.ScrollMode.AUTO, expand=True)

    @classmethod
    def _save(cls, e):
        for fqk, ctrl in cls._fields.items():
            val = ctrl.value if hasattr(ctrl, 'value') else ""
            if val is None: val = ""
            section, key = fqk.split(".", 1)
            defaults = cls._mgr.get_all()
            dv = defaults.get(section, {}).get(key)
            if isinstance(dv, bool):
                val = str(val).lower() in ("true", "1", "yes")
            elif isinstance(dv, int):
                try: val = int(val)
                except: pass
            elif isinstance(dv, float):
                try: val = float(val)
                except: pass
            cls._mgr.set(section, key, val)
        cls._mgr.save()
        cls.close()


# 兼容旧调用
open_settings_window = None
close_settings_window = SettingsOverlay.close
