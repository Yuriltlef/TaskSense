# -*- coding: utf-8 -*-
"""设置面板 — 页面内覆盖层，可拖拽 + 灰色描边."""

import flet as ft
from app.config.theme import theme, SCALE
from app.config.settings_manager import SettingsManager

NAV_ITEMS = [
    ("llm",   "LLM / API",    ft.Icons.PSYCHOLOGY_OUTLINED),
    ("rag",   "RAG 知识库",   ft.Icons.SEARCH),
    ("ui",    "界面与主题",   ft.Icons.PALETTE_OUTLINED),
    ("agent", "Agent 行为",   ft.Icons.SMART_TOY_OUTLINED),
]

PANEL_W, PANEL_H = 750, 550


class SettingsOverlay:
    _panel: ft.Container | None = None
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
        page.overlay.append(cls._panel)
        cls._switch("llm")
        page.update()

    @classmethod
    def close(cls):
        if not cls._open or not cls._page:
            return
        cls._open = False
        cls._page.overlay.remove(cls._panel)
        cls._page.update()

    # ── Build ──

    @classmethod
    def _build(cls):
        ff = theme.font_family
        page = cls._page
        cx = (page.width - PANEL_W) // 2
        cy = (page.height - PANEL_H) // 2

        # 标题栏（关闭按钮贴合右边，padding right=0）
        title_bar = ft.Container(
            content=ft.Row([
                ft.Text("TaskSense", size=13, weight=ft.FontWeight.W_600,
                        color=ft.Colors.WHITE, font_family=ff),
                ft.Text("— 设置", size=11, color=ft.Colors.GREY_500, font_family=ff),
                ft.Container(expand=True),
                ft.IconButton(ft.Icons.CLOSE, icon_size=16, icon_color=ft.Colors.GREY_400,
                              on_click=lambda e: cls.close(),
                              style=ft.ButtonStyle(bgcolor=ft.Colors.TRANSPARENT,
                                                   overlay_color=ft.Colors.RED_900,
                                                   shape=ft.RoundedRectangleBorder(radius=0))),
            ], spacing=0),
            height=37, bgcolor=theme.surface,
            padding=ft.padding.only(left=15, top=0, right=0, bottom=0),
            border=ft.border.only(bottom=ft.BorderSide(1, theme.border)),
        )

        # 左侧导航
        for key, label, icon in NAV_ITEMS:
            sel = key == cls._active[0]
            c = ft.Container(
                content=ft.Row([
                    ft.Icon(icon, size=16, color=theme.info if sel else theme.text_secondary),
                    ft.Text(label, size=theme.font_sm,
                            color=theme.text_primary if sel else theme.text_secondary,
                            font_family=ff,
                            weight=ft.FontWeight.W_600 if sel else ft.FontWeight.W_400),
                ], spacing=8),
                padding=ft.padding.only(left=12, top=10, right=12, bottom=10),
                border_radius=theme.radius_sm,
                bgcolor=theme.card if sel else None,
                margin=ft.margin.only(left=4, right=4, top=2, bottom=2),
                on_click=lambda e, k=key: cls._switch(k),
                data=key, ink=True,
            )
            cls._nav_ctrls.append(c)

        nav_panel = ft.Container(
            content=ft.Column([
                ft.Container(height=6),
                ft.Text("  设置", size=theme.font_xs, color=theme.text_disabled, font_family=ff),
                ft.Container(height=4),
                ft.Column(cls._nav_ctrls, spacing=0),
            ], spacing=0),
            width=190, bgcolor=theme.surface,
            border=ft.border.only(right=ft.BorderSide(1, theme.border)),
            padding=ft.padding.only(top=4),
        )

        # 右侧
        cls._right = ft.Container(bgcolor=theme.bg, expand=True, padding=ft.padding.all(24))

        # 底部
        footer = ft.Container(
            content=ft.Row([
                ft.Container(expand=True),
                ft.TextButton("取消", on_click=lambda e: cls.close()),
                ft.OutlinedButton("保存", on_click=cls._save,
                                  style=ft.ButtonStyle(
                                      side=ft.BorderSide(1, theme.info),
                                      shape=ft.RoundedRectangleBorder(radius=theme.radius_sm),
                                      color=theme.info,
                                      padding=ft.padding.only(left=16, top=6, right=16, bottom=6))),
            ], spacing=8),
            padding=ft.padding.only(left=16, top=8, right=16, bottom=10),
            border=ft.border.only(top=ft.BorderSide(1, theme.border)),
            bgcolor=theme.surface,
        )

        # 面板内容（外层负责圆角裁剪 + 阴影 + 描边）
        panel_content = ft.Container(
            content=ft.Container(
                content=ft.Column([
                    title_bar,
                    ft.Row([nav_panel, cls._right], expand=True, spacing=0),
                    footer,
                ], spacing=0, expand=True),
                bgcolor=theme.bg,
                border_radius=theme.radius_lg,
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            ),
            width=PANEL_W, height=PANEL_H,
            border_radius=theme.radius_lg,
            border=ft.border.all(2, theme.border),
            shadow=ft.BoxShadow(spread_radius=1, blur_radius=24, color="#000000aa"),
            bgcolor=ft.Colors.TRANSPARENT,
        )

        # 拖拽包裹层
        cls._panel = ft.Container(
            content=ft.GestureDetector(
                on_pan_start=cls._on_drag_start,
                on_pan_update=cls._on_drag_update,
                mouse_cursor=ft.MouseCursor.MOVE,
                content=panel_content,
            ),
            left=cx, top=cy,
        )

        # 遮罩已移除（page.overlay 不支持 bgcolor）

    # ── Drag ──

    @classmethod
    def _on_drag_start(cls, e: ft.DragStartEvent):
        cls._drag_start = (cls._panel.left or 0, cls._panel.top or 0)

    @classmethod
    def _on_drag_update(cls, e: ft.DragUpdateEvent):
        cls._drag_start = (
            cls._drag_start[0] + int(e.delta_x),
            cls._drag_start[1] + int(e.delta_y),
        )
        nx = max(-PANEL_W // 3, min(cls._page.width - PANEL_W * 2 // 3, cls._drag_start[0]))
        ny = max(-40, min(cls._page.height - 40, cls._drag_start[1]))
        cls._panel.left = nx
        cls._panel.top = ny
        cls._panel.update()

    # ── Nav ──

    @classmethod
    def _switch(cls, key: str):
        cls._active[0] = key
        for ctrl in cls._nav_ctrls:
            is_sel = ctrl.data == key
            ctrl.bgcolor = theme.card if is_sel else None
            iw = ctrl.content.controls[0]; tw = ctrl.content.controls[1]
            iw.color = theme.info if is_sel else theme.text_secondary
            tw.color = theme.text_primary if is_sel else theme.text_secondary
            tw.weight = ft.FontWeight.W_600 if is_sel else ft.FontWeight.W_400
        cls._right.content = cls._build_section(key)
        if cls._page:
            cls._page.update()

    # ── Form ──

    @classmethod
    def _label(cls, t):
        return ft.Container(
            content=ft.Text(t, size=theme.font_xs, color=theme.text_disabled,
                            font_family=theme.font_family),
            padding=ft.padding.only(top=10, bottom=2))

    @classmethod
    def _tf(cls, sk, val, hint="", w=None, pw=False):
        ctrl = ft.TextField(
            value=str(val) if val is not None else "",
            hint_text=hint, width=w, password=pw, dense=True,
            border_color=theme.border, focused_border_color=theme.info,
            text_style=ft.TextStyle(color=theme.text_primary, size=theme.font_sm,
                                    font_family=theme.font_family),
            bgcolor=theme.card,
        )
        cls._fields[sk] = ctrl
        return ctrl

    @classmethod
    def _dd(cls, sk, val, opts, labels=None):
        ctrl = ft.Dropdown(
            value=str(val) if val is not None else "",
            options=[ft.dropdown.Option(o, labels.get(o, o) if labels else o) for o in opts],
            border_color=theme.border, focused_border_color=theme.info,
            bgcolor=theme.card, dense=True,
        )
        cls._fields[sk] = ctrl
        return ctrl

    @classmethod
    def _build_section(cls, key):
        ff = theme.font_family
        data = cls._mgr.get_section(key)
        if key == "llm":
            return ft.Column([
                ft.Text("LLM 模型配置", size=theme.font_lg, weight=ft.FontWeight.W_700,
                        color=theme.text_primary, font_family=ff),
                cls._label("Provider"),
                cls._dd("llm.provider", data.get("provider"), ["anthropic", "openai", "local"]),
                cls._label("Model"),
                cls._tf("llm.model", data.get("model")),
                cls._label("API Key"),
                cls._tf("llm.api_key", data.get("api_key"), "sk-...", pw=True),
                cls._label("Base URL"),
                cls._tf("llm.base_url", data.get("base_url")),
                cls._label("Temperature / Max Tokens"),
                ft.Row([
                    cls._tf("llm.temperature", data.get("temperature"), "0.0~1.0", 120),
                    cls._tf("llm.max_tokens", data.get("max_tokens"), "tokens", 120),
                ], spacing=12),
            ], spacing=0, scroll=ft.ScrollMode.AUTO, expand=True)
        elif key == "rag":
            return ft.Column([
                ft.Text("RAG 知识库", size=theme.font_lg, weight=ft.FontWeight.W_700,
                        color=theme.text_primary, font_family=ff),
                cls._label("Embedding Model"),
                cls._tf("rag.embedding_model", data.get("embedding_model")),
                cls._label("Vector Store"),
                cls._dd("rag.vector_store", data.get("vector_store"), ["chroma", "qdrant"]),
                cls._label("Chunk Size / Overlap"),
                ft.Row([
                    cls._tf("rag.chunk_size", data.get("chunk_size"), "size", 100),
                    cls._tf("rag.chunk_overlap", data.get("chunk_overlap"), "overlap", 110),
                ], spacing=12),
                cls._label("Retrieval Top-K"),
                cls._tf("rag.retrieval_top_k", data.get("retrieval_top_k"), "", 100),
            ], spacing=0, scroll=ft.ScrollMode.AUTO, expand=True)
        elif key == "ui":
            return ft.Column([
                ft.Text("界面与主题", size=theme.font_lg, weight=ft.FontWeight.W_700,
                        color=theme.text_primary, font_family=ff),
                cls._label("Theme"),
                cls._dd("ui.theme", data.get("theme"), ["dark", "light"]),
                cls._label("Language"),
                cls._dd("ui.language", data.get("language"), ["zh", "en"]),
                cls._label("Scale"),
                cls._tf("ui.scale", data.get("scale", SCALE), "", 100),
                cls._label("Card Preview Delay (ms)"),
                cls._tf("ui.card_preview_delay_ms", data.get("card_preview_delay_ms"), "", 120),
            ], spacing=0, scroll=ft.ScrollMode.AUTO, expand=True)
        else:
            al = {"low": "Low", "medium": "Medium", "high": "High"}
            return ft.Column([
                ft.Text("Agent 自主权", size=theme.font_lg, weight=ft.FontWeight.W_700,
                        color=theme.text_primary, font_family=ff),
                cls._label("Triage"),
                cls._dd("agent.triage_autonomy", data.get("triage_autonomy"), ["low", "medium", "high"], al),
                cls._label("Suggest"),
                cls._dd("agent.suggest_autonomy", data.get("suggest_autonomy"), ["low", "medium", "high"], al),
                cls._label("Compliance"),
                cls._dd("agent.compliance_autonomy", data.get("compliance_autonomy"), ["low", "medium", "high"], al),
                cls._label("异常检测间隔 (分钟)"),
                cls._tf("agent.anomaly_check_interval_minutes", data.get("anomaly_check_interval_minutes"), "", 120),
            ], spacing=0, scroll=ft.ScrollMode.AUTO, expand=True)

    @classmethod
    def _save(cls, e):
        for fqk, ctrl in cls._fields.items():
            val = ctrl.value if hasattr(ctrl, 'value') else ""
            if val is None: val = ""
            section, key = fqk.split(".", 1)
            defaults = cls._mgr.get_all()
            dv = defaults.get(section, {}).get(key)
            if isinstance(dv, bool): val = str(val).lower() in ("true", "1", "yes")
            elif isinstance(dv, int):
                try: val = int(val)
                except: pass
            elif isinstance(dv, float):
                try: val = float(val)
                except: pass
            cls._mgr.set(section, key, val)
        cls._mgr.save()
        cls.close()


# 兼容旧调用（board_page 已改用 SettingsOverlay.open/close）
open_settings_window = None
close_settings_window = SettingsOverlay.close
