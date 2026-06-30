# -*- coding: utf-8 -*-
"""独立设置窗口 — 与主窗口样式一致的无边框 Flet 窗口."""

import os
import sys
import flet as ft

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from app.config.theme import theme, SCALE
from app.config.settings_manager import SettingsManager

NAV_ITEMS = [
    ("llm",   "LLM / API",    ft.Icons.PSYCHOLOGY_OUTLINED),
    ("rag",   "RAG 知识库",   ft.Icons.SEARCH),
    ("ui",    "界面与主题",   ft.Icons.PALETTE_OUTLINED),
    ("agent", "Agent 行为",   ft.Icons.SMART_TOY_OUTLINED),
]


def main(page: ft.Page):
    page.title = "TaskSense — 设置"
    page.theme_mode = ft.ThemeMode.DARK
    page.window.frameless = False
    page.window.title_bar_hidden = True
    page.window.title_bar_buttons_hidden = True
    page.window.bgcolor = ft.Colors.TRANSPARENT
    page.window.width = 750
    page.window.height = 550
    page.window.shadow = True
    page.window.resizable = False
    page.window.maximizable = False
    page.padding = 0; page.spacing = 0; page.margin = 0
    page.bgcolor = ft.Colors.TRANSPARENT

    ff = theme.font_family
    mgr = SettingsManager()
    mgr.load()
    _fields = {}
    _active = ["llm"]          # mutable for closure capture
    _nav_ctrls: list[ft.Container] = []

    # ── 标题栏 ──
    def _bar_buttons():
        def _tb(icon, oc, tip, hov=ft.Colors.GREY_800):
            return ft.IconButton(icon=icon, icon_size=14, width=42, height=37, on_click=oc,
                                 icon_color=ft.Colors.GREY_400,
                                 style=ft.ButtonStyle(bgcolor=ft.Colors.TRANSPARENT,
                                                      overlay_color=hov,
                                                      shape=ft.RoundedRectangleBorder(radius=0)),
                                 mouse_cursor=ft.MouseCursor.BASIC,
                                 tooltip=ft.Tooltip(message=tip, bgcolor="#202020",
                                                    text_style=ft.TextStyle(color=ft.Colors.WHITE)))
        return ft.Container(content=ft.Row([
            _tb(ft.Icons.REMOVE,
                lambda e: setattr(page.window, 'minimized', True), "最小化"),
            _tb(ft.Icons.CLOSE, lambda e: page.window.close(), "关闭", ft.Colors.RED_900),
        ], spacing=0))

    btns = _bar_buttons()
    title_bar = ft.Container(
        content=ft.Row([
            ft.WindowDragArea(
                ft.Container(
                    content=ft.Row([
                        ft.Text("TaskSense", size=13, weight=ft.FontWeight.W_600,
                                color=ft.Colors.WHITE, font_family=ff),
                        ft.Text("— 设置", size=11, color=ft.Colors.GREY_500, font_family=ff),
                        ft.Container(expand=True),
                    ], spacing=6),
                    expand=True, height=50, padding=ft.padding.only(left=15),
                    bgcolor=theme.surface,
                ), expand=True,
            ), btns,
        ], spacing=0),
        height=37, bgcolor=theme.surface,
        border=ft.border.only(bottom=ft.BorderSide(1, theme.border)),
    )

    # ── 左侧导航 ──
    def _switch(k: str):
        _active[0] = k
        # 更新所有导航项高亮
        for ctrl in _nav_ctrls:
            is_sel = ctrl.data == k
            ctrl.bgcolor = theme.card if is_sel else None
            icon_widget = ctrl.content.controls[0]
            text_widget = ctrl.content.controls[1]
            icon_widget.color = theme.info if is_sel else theme.text_secondary
            text_widget.color = theme.text_primary if is_sel else theme.text_secondary
            text_widget.weight = ft.FontWeight.W_600 if is_sel else ft.FontWeight.W_400
        right.content = _build_section(k)
        page.update()

    for key, label, icon in NAV_ITEMS:
        sel = key == _active[0]
        c = ft.Container(
            content=ft.Row([
                ft.Icon(icon, size=16,
                        color=theme.info if sel else theme.text_secondary),
                ft.Text(label, size=theme.font_sm,
                        color=theme.text_primary if sel else theme.text_secondary,
                        font_family=ff,
                        weight=ft.FontWeight.W_600 if sel else ft.FontWeight.W_400),
            ], spacing=8),
            padding=ft.padding.only(left=12, top=10, right=12, bottom=10),
            border_radius=theme.radius_sm,
            bgcolor=theme.card if sel else None,
            margin=ft.margin.only(left=4, right=4, top=2, bottom=2),
            on_click=lambda e, k=key: _switch(k),
            data=key,
            ink=True,
        )
        _nav_ctrls.append(c)

    nav_panel = ft.Container(
        content=ft.Column([
            ft.Container(height=6),
            ft.Text("  设置", size=theme.font_xs, color=theme.text_disabled, font_family=ff),
            ft.Container(height=4),
            ft.Column(_nav_ctrls, spacing=0),
        ], spacing=0),
        width=190, bgcolor=theme.surface,
        border=ft.border.only(right=ft.BorderSide(1, theme.border)),
        padding=ft.padding.only(top=4),
    )

    # ── 右侧表单 builders ──
    def _label(t):
        return ft.Container(
            content=ft.Text(t, size=theme.font_xs, color=theme.text_disabled, font_family=ff),
            padding=ft.padding.only(top=10, bottom=2))

    def _tf(sk, val, hint="", w=None, pw=False):
        ctrl = ft.TextField(
            value=str(val) if val is not None else "",
            hint_text=hint, width=w, password=pw, dense=True,
            border_color=theme.border, focused_border_color=theme.info,
            text_style=ft.TextStyle(color=theme.text_primary, size=theme.font_sm, font_family=ff),
            bgcolor=theme.card,
        )
        _fields[sk] = ctrl
        return ctrl

    def _dd(sk, val, opts, labels=None):
        ctrl = ft.Dropdown(
            value=str(val) if val is not None else "",
            options=[ft.dropdown.Option(o, labels.get(o, o) if labels else o) for o in opts],
            border_color=theme.border, focused_border_color=theme.info,
            bgcolor=theme.card, dense=True,
        )
        _fields[sk] = ctrl
        return ctrl

    def _build_section(key):
        data = mgr.get_section(key)
        if key == "llm":
            return ft.Column([
                ft.Text("LLM 模型配置", size=theme.font_lg, weight=ft.FontWeight.W_700,
                        color=theme.text_primary, font_family=ff),
                _label("Provider"),
                _dd("llm.provider", data.get("provider"), ["anthropic", "openai", "local"]),
                _label("Model"),
                _tf("llm.model", data.get("model")),
                _label("API Key"),
                _tf("llm.api_key", data.get("api_key"), "sk-...", pw=True),
                _label("Base URL"),
                _tf("llm.base_url", data.get("base_url")),
                _label("Temperature / Max Tokens"),
                ft.Row([
                    _tf("llm.temperature", data.get("temperature"), "0.0~1.0", 120),
                    _tf("llm.max_tokens", data.get("max_tokens"), "tokens", 120),
                ], spacing=12),
            ], spacing=0, scroll=ft.ScrollMode.AUTO, expand=True)
        elif key == "rag":
            return ft.Column([
                ft.Text("RAG 知识库", size=theme.font_lg, weight=ft.FontWeight.W_700,
                        color=theme.text_primary, font_family=ff),
                _label("Embedding Model"),
                _tf("rag.embedding_model", data.get("embedding_model")),
                _label("Vector Store"),
                _dd("rag.vector_store", data.get("vector_store"), ["chroma", "qdrant"]),
                _label("Chunk Size / Overlap"),
                ft.Row([
                    _tf("rag.chunk_size", data.get("chunk_size"), "size", 100),
                    _tf("rag.chunk_overlap", data.get("chunk_overlap"), "overlap", 110),
                ], spacing=12),
                _label("Retrieval Top-K"),
                _tf("rag.retrieval_top_k", data.get("retrieval_top_k"), "", 100),
            ], spacing=0, scroll=ft.ScrollMode.AUTO, expand=True)
        elif key == "ui":
            return ft.Column([
                ft.Text("界面与主题", size=theme.font_lg, weight=ft.FontWeight.W_700,
                        color=theme.text_primary, font_family=ff),
                _label("Theme"),
                _dd("ui.theme", data.get("theme"), ["dark", "light"]),
                _label("Language"),
                _dd("ui.language", data.get("language"), ["zh", "en"]),
                _label("Scale"),
                _tf("ui.scale", data.get("scale", SCALE), "", 100),
                _label("Card Preview Delay (ms)"),
                _tf("ui.card_preview_delay_ms", data.get("card_preview_delay_ms"), "", 120),
            ], spacing=0, scroll=ft.ScrollMode.AUTO, expand=True)
        else:
            al = {"low": "Low — 全自动", "medium": "Medium — 建议+确认", "high": "High — 仅草稿+审批"}
            return ft.Column([
                ft.Text("Agent 自主权", size=theme.font_lg, weight=ft.FontWeight.W_700,
                        color=theme.text_primary, font_family=ff),
                _label("Triage (自动分类)"),
                _dd("agent.triage_autonomy", data.get("triage_autonomy"), ["low", "medium", "high"], al),
                _label("Suggest (操作建议)"),
                _dd("agent.suggest_autonomy", data.get("suggest_autonomy"), ["low", "medium", "high"], al),
                _label("Compliance (合规检查)"),
                _dd("agent.compliance_autonomy", data.get("compliance_autonomy"), ["low", "medium", "high"], al),
                _label("异常检测间隔 (分钟)"),
                _tf("agent.anomaly_check_interval_minutes", data.get("anomaly_check_interval_minutes"), "", 120),
            ], spacing=0, scroll=ft.ScrollMode.AUTO, expand=True)

    right = ft.Container(content=_build_section("llm"), bgcolor=theme.bg,
                         expand=True, padding=ft.padding.all(24))

    # ── 底部按钮 (描边+小圆角) ──
    def _save(e):
        for fqk, ctrl in _fields.items():
            val = ctrl.value if hasattr(ctrl, 'value') else ""
            if val is None: val = ""
            section, key = fqk.split(".", 1)
            defaults = mgr.get_all()
            dv = defaults.get(section, {}).get(key)
            if isinstance(dv, bool): val = str(val).lower() in ("true", "1", "yes")
            elif isinstance(dv, int):
                try: val = int(val)
                except: pass
            elif isinstance(dv, float):
                try: val = float(val)
                except: pass
            mgr.set(section, key, val)
        mgr.save()
        page.window.close()

    footer = ft.Container(
        content=ft.Row([
            ft.Container(expand=True),
            ft.TextButton("取消", on_click=lambda e: page.window.close()),
            ft.OutlinedButton("保存", on_click=_save,
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

    page.add(ft.Container(
        content=ft.Column([
            title_bar,
            ft.Row([nav_panel, right], expand=True, spacing=0),
            footer,
        ], spacing=0, expand=True),
        expand=True, bgcolor=theme.bg,
    ))


def open_settings_window():
    import subprocess, sys
    subprocess.Popen([sys.executable, __file__],
                     creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)


if __name__ == "__main__":
    ft.app(target=main)
