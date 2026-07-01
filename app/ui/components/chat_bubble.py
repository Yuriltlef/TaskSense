"""对话气泡组件 — 单 Text(spans) 选区不可断裂。

四个公开控件：
- timestamp_label(text)    独立的日期时间行（居中、灰色）
- user_bubble(text, max_w, on_copy, on_refresh)   用户气泡（蓝色、靠右）
- ai_bubble(markdown, max_w, on_copy, on_refresh)  AI 气泡（卡片、靠左）
- error_bubble(error_text, max_w, on_copy, on_refresh)  错误气泡（红色调、左侧红色边框）

max_w 应由父容器传入（如 panel.width），保证响应式跟随父容器而非 page。
"""
from __future__ import annotations

import unicodedata
import flet as ft
from app.config.theme import theme
from app.ui.components.md_renderer import parse_markdown_to_spans

# ═══════════════════════════════════════════════
# 主题常量（从 AppTheme 派生）
# ═══════════════════════════════════════════════

_ff = theme.font_family
_fm = theme.font_mono

USER_BG = "#1565c0"
USER_TEXT_COLOR = "#ffffff"
AI_BG = theme.card
AI_BORDER = theme.border
ERROR_BG = "#1a0d0d"
ERROR_BORDER_LEFT = theme.error           # "#c62828" 红色左边框
ERROR_BORDER_OTHER = "#3a1a1a"            # 暗红其余三边
ERROR_HEADER_COLOR = theme.error          # 错误标题色
ERROR_TEXT_COLOR = "#c89090"              # 错误正文色（柔红，暗底可读）
ACCENT = theme.info
DISABLED = theme.text_disabled
RADIUS = theme.radius_md
PAD = theme.pad_md               # 气泡内边距

# 文本样式
USER_STYLE = ft.TextStyle(
    color=USER_TEXT_COLOR, size=theme.font_md, font_family=_ff, height=1.6,
)

# ═══════════════════════════════════════════════
# 宽度估算（仅用于短文本收缩，长文本由 max_w 约束）
# ═══════════════════════════════════════════════

def _char_w(ch: str, fs: int = theme.font_md) -> float:
    if ch in ('\n', '\r'):
        return 0
    return fs * 1.02 if unicodedata.east_asian_width(ch) in ('W', 'F') else fs * 0.58


def _line_max_width(text: str, fs: int = theme.font_md) -> float:
    mw = cur = 0.0
    for ch in text:
        if ch == '\n':
            mw, cur = max(mw, cur), 0.0
        else:
            cur += _char_w(ch, fs)
    return max(mw, cur)


def _spans_to_plain(spans: list[ft.TextSpan]) -> str:
    return "".join(s.text or "" for s in spans)


# ═══════════════════════════════════════════════
# 内部工具
# ═══════════════════════════════════════════════

def _tooltip(msg: str) -> ft.Tooltip:
    return ft.Tooltip(
        message=msg,
        bgcolor=theme.card,
        border=ft.border.all(1, theme.border),
        border_radius=6,
        text_style=ft.TextStyle(
            color=theme.text_primary, size=theme.font_xs, font_family=_ff,
        ),
        padding=ft.padding.only(left=10, top=6, right=10, bottom=6),
        wait_duration=500,
    )


def _btn_row(copy_text: str, on_copy, on_refresh) -> ft.Row:
    return ft.Row(
        [
            ft.IconButton(
                ft.Icons.CONTENT_COPY, icon_size=13, icon_color=DISABLED,
                tooltip=_tooltip("复制全文"),
                on_click=lambda e: on_copy(copy_text),
                splash_radius=14,
            ),
            ft.IconButton(
                ft.Icons.REFRESH, icon_size=13, icon_color=DISABLED,
                tooltip=_tooltip("重新生成"),
                on_click=on_refresh,
                splash_radius=14,
            ),
        ],
        spacing=2,
    )


def _noop_copy(_t: str) -> None:
    pass


def _noop_refresh(_e) -> None:
    pass


# ═══════════════════════════════════════════════
# 公开控件
# ═══════════════════════════════════════════════

def timestamp_label(text: str) -> ft.Control:
    """居中、灰色、斜体的日期时间行。"""
    return ft.Row(
        [
            ft.Container(expand=True),
            ft.Text(text, size=theme.font_xs, color=DISABLED, font_family=_ff, italic=True),
            ft.Container(expand=True),
        ],
    )


def user_bubble(
    text: str,
    max_w: float,
    on_copy=None,
    on_refresh=None,
) -> ft.Control:
    """用户气泡 — 纯文本、蓝色底、靠右。

    max_w: 父容器可用宽度（如 panel.width）。
    """
    _copy = on_copy or _noop_copy
    _reflash = on_refresh or _noop_refresh
    bw = min(_line_max_width(text) + PAD * 2 + 4, max_w)

    return ft.Column(
        [
            ft.Row(
                [
                    ft.Container(expand=True),
                    ft.Container(
                        ft.Text(text, style=USER_STYLE, selectable=True),
                        width=bw,
                        bgcolor=USER_BG, border_radius=RADIUS,
                        padding=ft.padding.only(left=PAD, top=PAD - 2, right=PAD, bottom=PAD - 2),
                    ),
                ],
            ),
            ft.Row([ft.Container(expand=True), _btn_row(text, _copy, _reflash)]),
        ],
        spacing=2, tight=True,
    )


def ai_bubble(
    markdown: str,
    max_w: float,
    on_copy=None,
    on_refresh=None,
) -> ft.Control:
    """AI 气泡 — Markdown 渲染、卡片底、靠左。选区物理不可断。

    max_w: 父容器可用宽度（如 panel.width）。
    """
    spans = parse_markdown_to_spans(markdown)
    plain = _spans_to_plain(spans)
    bw = min(_line_max_width(plain) + PAD * 2 + 4, max_w)
    _copy = on_copy or _noop_copy
    _reflash = on_refresh or _noop_refresh

    return ft.Column(
        [
            ft.Row(
                [
                    ft.Container(
                        ft.Text(spans=spans, selectable=True),
                        width=bw,
                        bgcolor=AI_BG, border_radius=RADIUS,
                        border=ft.border.all(1, AI_BORDER),
                        padding=ft.padding.only(left=PAD, top=PAD, right=PAD, bottom=PAD),
                    ),
                    ft.Container(expand=True, width=40),
                ],
            ),
            ft.Row([_btn_row(plain, _copy, _reflash), ft.Container(expand=True)]),
        ],
        spacing=2, tight=True,
    )


def error_bubble(
    error_text: str,
    max_w: float,
    on_copy=None,
    on_refresh=None,
) -> ft.Control:
    """错误气泡 — 深红底色 + 左侧红色粗边框 + ⚠️ 图标，靠左。

    样式明确区分于正常 AI 回复：
    - 背景色   : 深红黑 (#1a0d0d)
    - 左边框   : 3px 实色错误红 (#c62828)
    - 其余边框 : 1px 暗红 (#3a1a1a)
    - 错误标题 : ⚠️ 图标 + 红色标题文字
    - 正文     : 柔红色 (#c89090)，暗底可读

    max_w: 父容器可用宽度（如 panel.width）。
    """
    spans = parse_markdown_to_spans(error_text)
    plain = _spans_to_plain(spans)
    # 确保最小宽度（极短文本不会导致换行异常）
    text_w = max(_line_max_width(plain) + 20, 120)
    bw = min(text_w + PAD * 2 + 4, max_w)
    _copy = on_copy or _noop_copy
    _reflash = on_refresh or _noop_refresh

    _error_text_style = ft.TextStyle(
        color=ERROR_TEXT_COLOR, size=theme.font_md, font_family=_ff, height=1.6,
    )

    return ft.Column(
        [
            ft.Row(
                [
                    ft.Container(
                        ft.Column([
                            ft.Row([
                                ft.Icon(ft.Icons.ERROR_OUTLINE, size=15, color=ERROR_HEADER_COLOR),
                                ft.Text("AI 响应出错", size=12, weight=ft.FontWeight.W_600,
                                        color=ERROR_HEADER_COLOR, font_family=_ff),
                            ], spacing=6),
                            ft.Container(height=6),
                            ft.Text(spans=spans, selectable=True, style=_error_text_style),
                        ], spacing=0, tight=True),
                        width=bw,
                        bgcolor=ERROR_BG, border_radius=RADIUS,
                        border=ft.border.only(
                            left=ft.BorderSide(3, ERROR_BORDER_LEFT),
                            top=ft.BorderSide(1, ERROR_BORDER_OTHER),
                            right=ft.BorderSide(1, ERROR_BORDER_OTHER),
                            bottom=ft.BorderSide(1, ERROR_BORDER_OTHER),
                        ),
                        padding=ft.padding.only(left=PAD, top=PAD, right=PAD, bottom=PAD),
                    ),
                    ft.Container(expand=True, width=40),
                ],
            ),
            ft.Row([_btn_row(plain, _copy, _reflash), ft.Container(expand=True)]),
        ],
        spacing=2, tight=True,
    )
