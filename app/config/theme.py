"""暗色航空仪表盘主题 — 深黑灰 + HarmonyOS Sans SC."""

from dataclasses import dataclass, field

# ── 全局缩放（适配高 PPI 屏幕） ──
SCALE = 1.2


def s(value: int | float) -> int:
    """将尺寸按缩放因子放大。"""
    return round(value * SCALE)


@dataclass(frozen=True)
class AppTheme:
    """航空维护看板 — 极暗灰主题。

    背景仅比纯黑亮一点，减少眩光，适配暗室/机库环境。
    """

    # ── 字体 ──
    font_family: str = "HarmonyOS Sans SC"
    font_family_bold: str = "HarmonyOS Sans SC Bold"
    font_mono: str = "Consolas, 'Courier New', monospace"

    # ── 背景层级（极暗灰，仅微亮于纯黑） ──
    bg: str = "#080808"
    surface: str = "#0e0e0e"
    card: str = "#141414"
    card_hover: str = "#1a1a1a"
    border: str = "#1e1e1e"
    divider: str = "#161616"

    # ── 文字 ──
    text_primary: str = "#c8c8c8"
    text_secondary: str = "#6a6a6a"
    text_disabled: str = "#404040"
    text_link: str = "#5294e2"
    text_content: str = "#c0c0c0"     # 侧栏/报告等次级内容文字
    form_text: str = "#e0e0e0"        # 表单输入框文字
    accent: str = "#5294e2"           # 主色调蓝（图标/按钮/高亮）
    dialog_shadow: str = "#000000aa"  # 弹窗阴影
    panel_dark: str = "#111111"       # 深色面板背景
    border_active: str = "#2a2a2a"    # 输入框激活态边框
    nav_bg: str = "#101010"           # 设置左侧导航背景
    tooltip_bg: str = "#202020"       # 工具提示背景
    ai_icon: str = "#c498e8"          # AI 助手图标紫色
    notification_shadow: str = "#00000066"
    section_bg: str = "#0a0a0a"        # 侧栏深色区块背景

    # ── 优先级 ──
    priority_aog: str = "#f44747"
    priority_cat_a: str = "#e88400"
    priority_cat_b: str = "#e0b800"
    priority_cat_c: str = "#5294e2"
    priority_cat_d: str = "#808080"

    # ── 任务类型 ──
    type_troubleshoot: str = "#e87b62"
    type_inspection: str = "#73c990"
    type_servicing: str = "#6db8e8"
    type_removal_install: str = "#c498e8"
    type_test: str = "#e8a050"
    type_repair: str = "#4ec9d4"

    # ── ATA 大类 ──
    ata_general: str = "#00897B"
    ata_systems: str = "#3b7fd4"
    ata_structure: str = "#607d8b"
    ata_propeller: str = "#5c6bc0"
    ata_powerplant: str = "#d45a1a"

    # ── 状态色 ──
    success: str = "#388e3c"
    warning: str = "#e6a000"
    error: str = "#c62828"
    info: str = "#1976d2"

    # ── 高亮 / 交互 ──
    highlight_border_width: int = 2
    card_shadow_color: str = "#00000030"
    card_hover_shadow_color: str = "#00000050"
    menu_shadow_color: str = "#00000080"

    # ── 列头色 ──
    column_header: str = "#808080"

    # ── 尺寸（已缩放） ──
    card_width: int = field(default_factory=lambda: s(280))
    card_min_height: int = field(default_factory=lambda: s(120))
    column_width: int = field(default_factory=lambda: s(300))
    column_gap: int = field(default_factory=lambda: s(12))
    side_panel_width: int = field(default_factory=lambda: s(480))
    nav_width: int = field(default_factory=lambda: s(240))
    nav_collapsed_width: int = field(default_factory=lambda: s(48))
    header_height: int = field(default_factory=lambda: s(48))

    # ── 间距（已缩放） ──
    spacing_xs: int = field(default_factory=lambda: s(4))
    spacing_sm: int = field(default_factory=lambda: s(6))
    spacing_md: int = field(default_factory=lambda: s(10))
    spacing_lg: int = field(default_factory=lambda: s(16))
    spacing_xl: int = field(default_factory=lambda: s(24))

    # ── 内边距（已缩放） ──
    pad_xs: int = field(default_factory=lambda: s(4))
    pad_sm: int = field(default_factory=lambda: s(8))
    pad_md: int = field(default_factory=lambda: s(12))
    pad_lg: int = field(default_factory=lambda: s(16))
    pad_xl: int = field(default_factory=lambda: s(24))

    # ── 圆角（已缩放） ──
    radius_sm: int = field(default_factory=lambda: s(4))
    radius_md: int = field(default_factory=lambda: s(8))
    radius_lg: int = field(default_factory=lambda: s(12))

    # ── 字体大小（已缩放） ──
    font_xs: int = field(default_factory=lambda: s(11))
    font_sm: int = field(default_factory=lambda: s(12))
    font_md: int = field(default_factory=lambda: s(14))
    font_lg: int = field(default_factory=lambda: s(16))
    font_xl: int = field(default_factory=lambda: s(20))
    font_xxl: int = field(default_factory=lambda: s(24))
    font_title: int = field(default_factory=lambda: s(30))

    # ── 动画时长 (ms) ──
    anim_fast: int = 150
    anim_normal: int = 200
    anim_slow: int = 300

    @property
    def color_scheme(self) -> dict:
        return {
            "primary": self.info,
            "on_primary": self.text_primary,
            "surface": self.surface,
            "on_surface": self.text_primary,
            "background": self.bg,
            "on_background": self.text_primary,
            "error": self.error,
            "on_error": "#FFFFFF",
            "outline": self.border,
        }

    def priority_color(self, priority: str) -> str:
        return {
            "aog": self.priority_aog,
            "cat_a": self.priority_cat_a,
            "cat_b": self.priority_cat_b,
            "cat_c": self.priority_cat_c,
            "cat_d": self.priority_cat_d,
        }.get(priority, self.text_disabled)

    def task_type_color(self, task_type: str) -> str:
        return {
            "troubleshoot": self.type_troubleshoot,
            "inspection": self.type_inspection,
            "servicing": self.type_servicing,
            "removal_install": self.type_removal_install,
            "test": self.type_test,
            "repair": self.type_repair,
        }.get(task_type, self.text_disabled)

    def ata_category_color(self, chapter: str) -> str:
        try:
            ch = int(chapter.split("-")[0])
        except (ValueError, IndexError):
            return self.text_disabled
        if ch <= 19:
            return self.ata_general
        elif ch <= 50:
            return self.ata_systems
        elif ch <= 57:
            return self.ata_structure
        elif ch <= 67:
            return self.ata_propeller
        else:
            return self.ata_powerplant


# 全局单例
theme = AppTheme()
