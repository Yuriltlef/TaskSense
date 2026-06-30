"""Markdown → ft.TextSpan 平坦渲染器。

核心思路：markdown_it token 遍历 → 单个 ft.Text(spans=[...], selectable=True)
这样所有内容在同一 Text 内，选区物理上不可切断。
"""
from __future__ import annotations

import re
import markdown_it
import flet as ft
from app.config.theme import theme


# ═══════════════════════════════════════════════
# 从 AppTheme 派生文本样式
# ═══════════════════════════════════════════════

_ff = theme.font_family
_fm = theme.font_mono

BASE = ft.TextStyle(color=theme.text_primary, size=theme.font_md, font_family=_ff, height=1.6)
BOLD = ft.TextStyle(color=theme.text_primary, size=theme.font_md, font_family=_ff,
                    weight=ft.FontWeight.W_700, height=1.6)
ITALIC = ft.TextStyle(color=theme.text_primary, size=theme.font_md, font_family=_ff,
                      italic=True, height=1.6)
CODE_INLINE = ft.TextStyle(color=theme.info, size=theme.font_sm, font_family=_fm,
                           bgcolor="#1a1a2e", height=1.5)
CODE_BLOCK = ft.TextStyle(color=theme.text_primary, size=theme.font_sm, font_family=_fm,
                          bgcolor="#121212", height=1.6)
HEADING = {
    1: ft.TextStyle(color=theme.text_primary, size=theme.font_xl, font_family=_ff,
                    weight=ft.FontWeight.W_700, height=1.4),
    2: ft.TextStyle(color=theme.text_primary, size=theme.font_lg, font_family=_ff,
                    weight=ft.FontWeight.W_700, height=1.4),
    3: ft.TextStyle(color=theme.text_primary, size=theme.font_md + 1, font_family=_ff,
                    weight=ft.FontWeight.W_600, height=1.4),
}
QUOTE = ft.TextStyle(color=theme.text_secondary, size=theme.font_md, font_family=_ff,
                     italic=True, height=1.6)
QUOTE_PREFIX = ft.TextStyle(color=theme.info, size=theme.font_md, font_family=_ff,
                             weight=ft.FontWeight.W_700, height=1.6)
TABLE = ft.TextStyle(color=theme.text_primary, size=theme.font_xs + 1, font_family=_fm, height=1.5)
MATH = ft.TextStyle(color=theme.info, size=theme.font_sm, font_family=_fm,
                    italic=True, bgcolor="#121212", height=1.5)
META = ft.TextStyle(color=theme.text_secondary, size=theme.font_xs, font_family=_ff)
CODE_LABEL = ft.TextStyle(color=theme.text_disabled, size=theme.font_xs, font_family=_fm)
STRIKE = ft.TextStyle(color=theme.text_disabled, size=theme.font_md, font_family=_ff,
                      decoration=ft.TextDecoration.LINE_THROUGH, height=1.6)

# ── LaTeX → Unicode ──

_LATEX_UNICODE = {
    r"\alpha": "α", r"\beta": "β", r"\gamma": "γ", r"\delta": "δ",
    r"\epsilon": "ε", r"\zeta": "ζ", r"\eta": "η", r"\theta": "θ",
    r"\iota": "ι", r"\kappa": "κ", r"\lambda": "λ", r"\mu": "μ",
    r"\nu": "ν", r"\xi": "ξ", r"\pi": "π", r"\rho": "ρ",
    r"\sigma": "σ", r"\tau": "τ", r"\upsilon": "υ", r"\phi": "φ",
    r"\chi": "χ", r"\psi": "ψ", r"\omega": "ω",
    r"\Gamma": "Γ", r"\Delta": "Δ", r"\Theta": "Θ", r"\Lambda": "Λ",
    r"\Xi": "Ξ", r"\Pi": "Π", r"\Sigma": "Σ", r"\Upsilon": "Υ",
    r"\Phi": "Φ", r"\Psi": "Ψ", r"\Omega": "Ω",
    r"\infty": "∞", r"\pm": "±", r"\times": "×", r"\div": "÷",
    r"\cdot": "·", r"\leq": "≤", r"\geq": "≥", r"\neq": "≠",
    r"\approx": "≈", r"\equiv": "≡", r"\propto": "∝",
    r"\sum": "Σ", r"\prod": "Π", r"\int": "∫",
    r"\sqrt": "√", r"\partial": "∂", r"\nabla": "∇",
    r"\to": "→", r"\mapsto": "↦", r"\implies": "⇒",
    r"\leftarrow": "←", r"\rightarrow": "→", r"\uparrow": "↑", r"\downarrow": "↓",
    r"\langle": "⟨", r"\rangle": "⟩", r"\lfloor": "⌊", r"\rfloor": "⌋",
    r"\ldots": "…", r"\cdots": "⋯", r"\vdots": "⋮", r"\ddots": "⋱",
}


def _translate_math(latex: str) -> str:
    result = latex.strip()
    for cmd, uni in _LATEX_UNICODE.items():
        result = result.replace(cmd, uni)
    result = re.sub(r'\^\{([^}]+)\}', r'^\1', result)
    result = re.sub(r'_\{([^}]+)\}', r'_\1', result)
    return result


# ═══════════════════════════════════════════════
# MarkdownIt token → TextSpan
# ═══════════════════════════════════════════════

_md = markdown_it.MarkdownIt()


def _inline_children(children: list, base_style: ft.TextStyle = BASE) -> list[ft.TextSpan]:
    result: list[ft.TextSpan] = []
    stack: list[ft.TextStyle] = [base_style]

    for tok in children:
        t = tok.type
        if t == "text":
            result.append(ft.TextSpan(text=tok.content, style=stack[-1]))
        elif t in ("softbreak", "hardbreak"):
            result.append(ft.TextSpan(text="\n", style=stack[-1]))
        elif t == "code_inline":
            result.append(ft.TextSpan(text=tok.content, style=CODE_INLINE))
        elif t == "strong_open":
            stack.append(BOLD)
        elif t == "strong_close":
            len(stack) > 1 and stack.pop()
        elif t == "em_open":
            stack.append(ITALIC)
        elif t == "em_close":
            len(stack) > 1 and stack.pop()
        elif t == "s_open":
            stack.append(STRIKE)
        elif t == "s_close":
            len(stack) > 1 and stack.pop()
        elif t in ("link_open", "link_close"):
            pass
        elif t == "image":
            alt = tok.attrGet("alt") or tok.attrGet("src") or "?"
            result.append(ft.TextSpan(text=f"[图片: {alt}]", style=META))
        elif t == "html_inline":
            result.append(ft.TextSpan(text=tok.content, style=CODE_INLINE))
    return result


def _merge(spans: list[ft.TextSpan]) -> list[ft.TextSpan]:
    if not spans:
        return []
    out, cur = [], spans[0]
    for nxt in spans[1:]:
        if type(cur.style) is type(nxt.style) and cur.style == nxt.style:
            cur = ft.TextSpan(text=(cur.text or "") + (nxt.text or ""), style=cur.style)
        else:
            cur.text and out.append(cur)
            cur = nxt
    cur.text and out.append(cur)
    return out


def _strip_trailing(spans: list[ft.TextSpan]) -> list[ft.TextSpan]:
    while spans and (spans[-1].text or "").strip() == "":
        spans.pop()
    if spans and spans[-1].text:
        spans[-1].text = (spans[-1].text or "").rstrip("\n")
        if not spans[-1].text:
            spans.pop()
    return spans


def parse_markdown_to_spans(source: str) -> list[ft.TextSpan]:
    """markdown 文本 → 平坦 ft.TextSpan 列表（单 Text 控件用）。"""
    spans: list[ft.TextSpan] = []

    # 预提取数学公式
    math_blocks: dict[str, str] = {}
    math_inlines: dict[str, str] = {}

    def _save_block(m: re.Match) -> str:
        k = f"\x00MB{len(math_blocks)}\x00"
        math_blocks[k] = m.group(1).strip()
        return k

    def _save_inline(m: re.Match) -> str:
        k = f"\x00MI{len(math_inlines)}\x00"
        math_inlines[k] = m.group(1).strip()
        return k

    processed = re.sub(r"\$\$\s*(.+?)\s*\$\$", _save_block, source, flags=re.DOTALL)
    processed = re.sub(r"\$(.+?)\$", _save_inline, processed)

    tokens = _md.parse(processed)

    _first_block = True

    def _add(text: str, style: ft.TextStyle = BASE):
        nonlocal _first_block
        if text:
            spans.append(ft.TextSpan(text=text, style=style))
        _first_block = False

    def _adds(new_spans: list[ft.TextSpan]):
        nonlocal _first_block
        spans.extend(new_spans)
        _first_block = False

    def _gap():
        nonlocal _first_block
        if not _first_block:
            spans.append(ft.TextSpan(text="\n", style=BASE))

    i = 0
    while i < len(tokens):
        tok = tokens[i]

        if tok.type == "heading_open":
            level = int(tok.tag[1])
            style = HEADING.get(level, BASE)
            i += 1
            if i < len(tokens) and tokens[i].type == "inline":
                _gap()
                _adds(_inline_children(tokens[i].children or [], style))
                i += 1
            if i < len(tokens) and tokens[i].type == "heading_close":
                i += 1

        elif tok.type == "paragraph_open":
            i += 1
            if i < len(tokens) and tokens[i].type == "inline":
                _gap()
                _adds(_inline_children(tokens[i].children or []))
                i += 1
            if i < len(tokens) and tokens[i].type == "paragraph_close":
                i += 1

        elif tok.type == "fence":
            lang = (tok.info or "").strip()
            code = (tok.content or "").rstrip()
            _gap()
            if lang:
                _add(f"┌── {lang} ──\n", CODE_LABEL)
            for line in code.split("\n"):
                _add(line + "\n", CODE_BLOCK)
            if lang:
                _add("└──\n", CODE_LABEL)
            i += 1

        elif tok.type == "bullet_list_open":
            i += 1
            while i < len(tokens) and tokens[i].type != "bullet_list_close":
                if tokens[i].type == "list_item_open":
                    i += 1
                    _gap()
                    _add("●  ", META)
                    while i < len(tokens) and tokens[i].type not in ("list_item_close", "bullet_list_close"):
                        if tokens[i].type == "paragraph_open":
                            i += 1
                            if i < len(tokens) and tokens[i].type == "inline":
                                _adds(_inline_children(tokens[i].children or []))
                                i += 1
                            if i < len(tokens) and tokens[i].type == "paragraph_close":
                                i += 1
                        else:
                            i += 1
                    if i < len(tokens) and tokens[i].type == "list_item_close":
                        i += 1
                else:
                    i += 1
            if i < len(tokens) and tokens[i].type == "bullet_list_close":
                i += 1

        elif tok.type == "ordered_list_open":
            i += 1
            num = 1
            while i < len(tokens) and tokens[i].type != "ordered_list_close":
                if tokens[i].type == "list_item_open":
                    i += 1
                    _gap()
                    _add(f"{num}.  ", META)
                    while i < len(tokens) and tokens[i].type not in ("list_item_close", "ordered_list_close"):
                        if tokens[i].type == "paragraph_open":
                            i += 1
                            if i < len(tokens) and tokens[i].type == "inline":
                                _adds(_inline_children(tokens[i].children or []))
                                i += 1
                            if i < len(tokens) and tokens[i].type == "paragraph_close":
                                i += 1
                        else:
                            i += 1
                    num += 1
                    if i < len(tokens) and tokens[i].type == "list_item_close":
                        i += 1
                else:
                    i += 1
            if i < len(tokens) and tokens[i].type == "ordered_list_close":
                i += 1

        elif tok.type == "blockquote_open":
            i += 1
            _gap()
            _add("▌ ", QUOTE_PREFIX)
            while i < len(tokens) and tokens[i].type != "blockquote_close":
                if tokens[i].type == "paragraph_open":
                    i += 1
                    if i < len(tokens) and tokens[i].type == "inline":
                        _adds(_inline_children(tokens[i].children or [], QUOTE))
                        i += 1
                    if i < len(tokens) and tokens[i].type == "paragraph_close":
                        i += 1
                else:
                    i += 1
            if i < len(tokens) and tokens[i].type == "blockquote_close":
                i += 1

        elif tok.type == "table_open":
            i += 1
            lines: list[str] = []
            while i < len(tokens) and tokens[i].type != "table_close":
                if tokens[i].type in ("thead_open", "tbody_open"):
                    i += 1
                    while i < len(tokens) and tokens[i].type not in ("thead_close", "tbody_close", "table_close"):
                        if tokens[i].type == "tr_open":
                            i += 1
                            cells: list[str] = []
                            while i < len(tokens) and tokens[i].type != "tr_close":
                                if tokens[i].type in ("th_open", "td_open"):
                                    i += 1
                                    ct = ""
                                    if i < len(tokens) and tokens[i].type == "inline":
                                        ct = "".join((c.content or "") for c in (tokens[i].children or []))
                                        i += 1
                                    cells.append(ct)
                                    if i < len(tokens) and tokens[i].type in ("th_close", "td_close"):
                                        i += 1
                                else:
                                    i += 1
                            lines.append("│ " + " │ ".join(cells) + " │")
                            if i < len(tokens) and tokens[i].type == "tr_close":
                                i += 1
                        else:
                            i += 1
                else:
                    i += 1
            if lines:
                _gap()
                _add("┌" + "─" * 4 + "┬" + "─" * 4 + "┐\n", TABLE)
                for j, line in enumerate(lines):
                    _add(line + "\n", TABLE)
                    if j == 0:
                        _add("├" + "─" * 4 + "┼" + "─" * 4 + "┤\n", TABLE)
                _add("└" + "─" * 4 + "┴" + "─" * 4 + "┘\n", TABLE)
            if i < len(tokens) and tokens[i].type == "table_close":
                i += 1

        elif tok.type == "hr":
            _gap()
            _add("─" * 20 + "\n", META)
            i += 1

        else:
            if tok.content:
                for key, latex in math_blocks.items():
                    if tok.content.strip() == key.strip():
                        _gap()
                        _add(f"📐 {_translate_math(latex)}\n", MATH)
                        break
            i += 1

    return _strip_trailing(_merge(spans))
