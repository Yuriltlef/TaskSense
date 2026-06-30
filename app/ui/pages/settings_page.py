# -*- coding: utf-8 -*-
"""设置页面 — Cursor/Trae 风格：左侧等宽导航 + 右侧表单."""

import flet as ft
from app.config.theme import theme, SCALE
from app.config.settings_manager import SettingsManager


class SettingsPage:
    """Cursor 风格设置页。

    - 左侧：等宽导航项，圆角小，高亮选中
    - 右侧：表单区域，根据选中 section 渲染
    - 作为新 View 打开，与主看板风格一致
    """

    NAV_WIDTH = 200
    NAV_ITEMS = [
        ("llm",    "LLM / API",      ft.Icons.PSYCHOLOGY_OUTLINED),
        ("rag",    "RAG 知识库",      ft.Icons.SEARCH),
        ("ui",     "界面与主题",      ft.Icons.PALETTE_OUTLINED),
        ("agent",  "Agent 行为",      ft.Icons.SMART_TOY_OUTLINED),
    ]

    def __init__(self, on_back=None):
        self._mgr = SettingsManager
        self._mgr.load()
        self._active = "llm"
        self._on_back = on_back
        # 存储所有输入控件，key = "section.key"
        self._fields: dict[str, ft.Control] = {}

    def build(self, page: ft.Page) -> ft.Container:
        ff = theme.font_family

        # ── 左侧导航 ──
        nav = ft.Column(spacing=0)
        for key, label, icon in self.NAV_ITEMS:
            active = key == self._active
            nav.controls.append(
                ft.Container(
                    content=ft.Row([
                        ft.Icon(icon, size=18,
                                color=theme.info if active else theme.text_secondary),
                        ft.Text(label, size=theme.font_sm,
                                color=theme.text_primary if active else theme.text_secondary,
                                font_family=ff,
                                weight=ft.FontWeight.W_600 if active else ft.FontWeight.W_400),
                    ], spacing=10),
                    padding=ft.padding.only(left=14, top=10, right=14, bottom=10),
                    border_radius=theme.radius_sm,
                    bgcolor=theme.card if active else None,
                    margin=ft.margin.only(left=6, right=6, top=1, bottom=1),
                    on_click=lambda e, k=key: self._switch(k, page),
                )
            )

        nav_panel = ft.Container(
            content=ft.Column([
                ft.Container(height=8),
                ft.Text("  TaskSense", size=theme.font_lg,
                        weight=ft.FontWeight.W_700,
                        color=theme.text_primary, font_family=ff),
                ft.Divider(height=16, color=ft.Colors.TRANSPARENT),
                ft.Text("  设置", size=theme.font_xs,
                        color=theme.text_disabled, font_family=ff),
                ft.Container(height=4),
                nav,
            ], spacing=0),
            width=self.NAV_WIDTH,
            bgcolor=theme.surface,
            border=ft.border.only(right=ft.BorderSide(1, theme.border)),
            padding=ft.padding.only(top=8),
        )

        # ── 右侧内容 ──
        self._right = ft.Container(
            content=self._build_section("llm"),
            expand=True, padding=ft.padding.all(24),
        )

        # 顶栏
        top = ft.Container(
            content=ft.Row([
                ft.IconButton(
                    icon=ft.Icons.ARROW_BACK, icon_size=20,
                    icon_color=theme.text_secondary,
                    on_click=lambda e: self._go_back(page),
                    hover_color=ft.Colors.GREY_800,
                ),
                ft.Text("设置", size=theme.font_lg, weight=ft.FontWeight.W_700,
                        color=theme.text_primary, font_family=ff),
                ft.Container(expand=True),
                ft.ElevatedButton("保存并应用", on_click=lambda e: self._save(page),
                                  style=ft.ButtonStyle(bgcolor=theme.info,
                                                       color=theme.text_primary)),
            ], spacing=8),
            padding=ft.padding.only(left=12, top=6, right=12, bottom=6),
            bgcolor=theme.surface,
            border=ft.border.only(bottom=ft.BorderSide(1, theme.border)),
        )

        return ft.Container(
            content=ft.Column([
                top,
                ft.Row([nav_panel, self._right], expand=True, spacing=0),
            ], spacing=0, expand=True),
            expand=True, bgcolor=theme.bg,
        )

    def _switch(self, key: str, page: ft.Page):
        self._active = key
        self._right.content = self._build_section(key)
        self._right.update()

    def _go_back(self, page: ft.Page):
        if self._on_back:
            self._on_back()
        else:
            page.go("/")

    def _save(self, page: ft.Page):
        """收集所有字段值并保存。"""
        for fqk, ctrl in self._fields.items():
            section, key = fqk.split(".", 1)
            val = ctrl.value if hasattr(ctrl, 'value') else ""
            if val is None:
                val = ""
            # 类型转换
            defaults = self._mgr.get_all()
            default_val = defaults.get(section, {}).get(key)
            if isinstance(default_val, bool):
                val = str(val).lower() in ("true", "1", "yes")
            elif isinstance(default_val, int):
                try: val = int(val)
                except: pass
            elif isinstance(default_val, float):
                try: val = float(val)
                except: pass
            self._mgr.set(section, key, val)

        path = self._mgr.save()
        from app.ui.widgets.toast import Toast
        Toast.show(page, f"设置已保存到 {path}", "success")

    # ═══════════════════════ 各 Section ═══════════════════════

    def _build_section(self, key: str) -> ft.Column:
        data = self._mgr.get_section(key)
        ff = theme.font_family

        def _title(t):
            return ft.Text(t, size=theme.font_lg, weight=ft.FontWeight.W_700,
                           color=theme.text_primary, font_family=ff)

        def _label(t):
            return ft.Text(t, size=theme.font_xs, color=theme.text_disabled, font_family=ff)

        def _tf(sk, val, hint="", w=None, pw=False):
            fqk = f"{key}.{sk}"
            tf = ft.TextField(
                value=str(val) if val is not None else "",
                hint_text=hint, width=w, password=pw, dense=True,
                border_color=theme.border, focused_border_color=theme.info,
                text_style=ft.TextStyle(color=theme.text_primary, size=theme.font_sm, font_family=ff),
                bgcolor=theme.card,
            )
            self._fields[fqk] = tf
            return tf

        def _dd(sk, val, opts, labels=None):
            fqk = f"{key}.{sk}"
            dd = ft.Dropdown(
                value=str(val) if val is not None else "",
                options=[ft.dropdown.Option(o, labels.get(o, o) if labels else o) for o in opts],
                border_color=theme.border, focused_border_color=theme.info,
                bgcolor=theme.card, dense=True,
            )
            self._fields[fqk] = dd
            return dd

        def _row(*children):
            return ft.Row(list(children), spacing=12)

        if key == "llm":
            return ft.Column([
                _title("LLM 模型配置"),
                ft.Divider(height=12, color=ft.Colors.TRANSPARENT),
                _label("Provider"),
                _dd("provider", data.get("provider"), ["anthropic", "openai", "local"]),
                _label("Model"),
                _tf("model", data.get("model")),
                _label("API Key"),
                _tf("api_key", data.get("api_key"), "sk-...", pw=True),
                _label("Base URL"),
                _tf("base_url", data.get("base_url")),
                _label("Temperature"),
                _tf("temperature", data.get("temperature"), "0.0 ~ 1.0", 120),
                _label("Max Tokens"),
                _tf("max_tokens", data.get("max_tokens"), "", 120),
            ], spacing=4)

        elif key == "rag":
            return ft.Column([
                _title("RAG 知识库"),
                ft.Divider(height=12, color=ft.Colors.TRANSPARENT),
                _label("Embedding Model"),
                _tf("embedding_model", data.get("embedding_model")),
                _label("Vector Store"),
                _dd("vector_store", data.get("vector_store"), ["chroma", "qdrant"]),
                _label("Chunk Size"),
                _tf("chunk_size", data.get("chunk_size"), "", 100),
                _label("Chunk Overlap"),
                _tf("chunk_overlap", data.get("chunk_overlap"), "", 100),
                _label("Retrieval Top-K"),
                _tf("retrieval_top_k", data.get("retrieval_top_k"), "", 100),
            ], spacing=4)

        elif key == "ui":
            return ft.Column([
                _title("界面与主题"),
                ft.Divider(height=12, color=ft.Colors.TRANSPARENT),
                _label("Theme"),
                _dd("theme", data.get("theme"), ["dark", "light"]),
                _label("Language"),
                _dd("language", data.get("language"), ["zh", "en"]),
                _label("Scale"),
                _tf("scale", data.get("scale", SCALE), "", 100),
                _label("Card Preview Delay (ms)"),
                _tf("card_preview_delay_ms", data.get("card_preview_delay_ms"), "", 120),
            ], spacing=4)

        else:  # agent
            return ft.Column([
                _title("Agent 自主权"),
                ft.Divider(height=12, color=ft.Colors.TRANSPARENT),
                _label("Triage (自动分类)"),
                _dd("triage_autonomy", data.get("triage_autonomy"),
                    ["low", "medium", "high"],
                    {"low": "Low — 全自动", "medium": "Medium — 建议+确认", "high": "High — 仅草稿+审批"}),
                _label("Suggest (操作建议)"),
                _dd("suggest_autonomy", data.get("suggest_autonomy"),
                    ["low", "medium", "high"],
                    {"low": "Low — 全自动", "medium": "Medium — 建议+确认", "high": "High — 仅草稿+审批"}),
                _label("Compliance (合规检查)"),
                _dd("compliance_autonomy", data.get("compliance_autonomy"),
                    ["low", "medium", "high"],
                    {"low": "Low — 全自动", "medium": "Medium — 建议+确认", "high": "High — 仅草稿+审批"}),
                _label("异常检测间隔 (分钟)"),
                _tf("anomaly_check_interval_minutes", data.get("anomaly_check_interval_minutes"), "", 120),
            ], spacing=4)
