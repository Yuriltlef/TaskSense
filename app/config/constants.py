"""航空维护领域常量定义."""

from enum import Enum


# ── 优先级 ──

PRIORITY_LABELS = {
    "aog": "AOG",
    "cat_a": "Cat A",
    "cat_b": "Cat B",
    "cat_c": "Cat C",
    "cat_d": "Cat D",
}

PRIORITY_ORDER = ["aog", "cat_a", "cat_b", "cat_c", "cat_d"]

PRIORITY_DESCRIPTIONS = {
    "aog": "Aircraft on Ground — 立即修复，飞机不能放行",
    "cat_a": "Category A — 按MEL条目，当日或下一航班前修复",
    "cat_b": "Category B — 3个连续日历日（72小时）内修复",
    "cat_c": "Category C — 10个连续日历日（240小时）内修复",
    "cat_d": "Category D — 120个连续日历日（2880小时）内修复",
}


# ── 任务类型 ──

TASK_TYPE_LABELS = {
    "troubleshoot": "排故",
    "inspection": "检查",
    "servicing": "勤务",
    "removal_install": "拆卸安装",
    "test": "测试",
    "repair": "修复",
}

TASK_TYPE_ICONS = {
    "troubleshoot": "🔧",
    "inspection": "🔍",
    "servicing": "🛢️",
    "removal_install": "🔩",
    "test": "📏",
    "repair": "🔨",
}


# ── 任务状态与看板列 ──

STATUS_LABELS = {
    "backlog": "待处理",
    "triage": "分类中",
    "scheduled": "已排程",
    "ready": "就绪",
    "in_progress": "执行中",
    "inspection": "检查中",
    "parts_hold": "待零件",
    "completed": "已完成",
    "archived": "已归档",
}

DEFAULT_COLUMNS = [
    {"id": "backlog",       "title": "待处理",   "wip_limit": None, "order": 0, "visible": True},
    {"id": "triage",        "title": "分类中",   "wip_limit": 10,   "order": 1, "visible": True},
    {"id": "scheduled",     "title": "已排程",   "wip_limit": None, "order": 2, "visible": True},
    {"id": "ready",         "title": "就绪",     "wip_limit": 20,   "order": 3, "visible": True},
    {"id": "in_progress",   "title": "执行中",   "wip_limit": 15,   "order": 4, "visible": True},
    {"id": "inspection",    "title": "检查中",   "wip_limit": 15,   "order": 5, "visible": True},
    {"id": "parts_hold",    "title": "待零件",   "wip_limit": 10,   "order": 6, "visible": True},
    {"id": "completed",     "title": "已完成",   "wip_limit": None, "order": 7, "visible": True},
    {"id": "archived",      "title": "已归档",   "wip_limit": None, "order": 8, "visible": False},
]

# 允许的状态转换
ALLOWED_TRANSITIONS = {
    "backlog":      ["triage", "archived"],
    "triage":       ["scheduled", "backlog"],
    "scheduled":    ["ready", "backlog", "triage"],
    "ready":        ["in_progress", "scheduled"],
    "in_progress":  ["inspection", "parts_hold", "completed"],
    "inspection":   ["completed", "in_progress"],
    "parts_hold":   ["ready", "scheduled"],
    "completed":    ["archived"],
    "archived":     [],
}


# ── ATA 大分类 ──

class ATACategory(Enum):
    GENERAL = "general"         # 00-19 飞机通用
    SYSTEMS = "systems"         # 20-50 机体系统
    STRUCTURE = "structure"     # 51-57 结构
    PROPELLER = "propeller"    # 60-67 螺旋桨/旋翼
    POWERPLANT = "powerplant"  # 70-91 动力装置


# ── ATA 页面块类型 ──

class ATATaskType(Enum):
    DESCRIPTION = "001-099"      # 描述与操作
    FAULT_ISOLATION = "101-199"  # 故障隔离
    MAINTENANCE = "201-299"      # 维护实践
    SERVICING = "301-399"        # 勤务
    REMOVAL_INSTALL = "401-499"  # 拆卸/安装
    ADJUST_TEST = "501-599"      # 调整/测试
    INSPECTION = "601-699"       # 检查
    CLEANING = "701-799"         # 清洁/喷漆
    REPAIR = "801-899"           # 批准修理


ATA_PAGE_BLOCK_MAP = {
    "001-099": "troubleshoot",    # 描述 → 参考
    "101-199": "troubleshoot",    # 排故
    "201-299": "repair",          # 维护实践
    "301-399": "servicing",       # 勤务
    "401-499": "removal_install", # 拆卸安装
    "501-599": "test",            # 调整测试
    "601-699": "inspection",      # 检查
    "701-799": "servicing",       # 清洁
    "801-899": "repair",          # 批准修理
}


# ── ATA 章节列表（核心章节）─

ATA_CHAPTERS = [
    # (章节号, 标题, 大类)
    ("05", "时限/维修检查", ATACategory.GENERAL),
    ("12", "勤务", ATACategory.GENERAL),
    ("21", "空调与增压", ATACategory.SYSTEMS),
    ("22", "自动飞行", ATACategory.SYSTEMS),
    ("23", "通信", ATACategory.SYSTEMS),
    ("24", "电源", ATACategory.SYSTEMS),
    ("25", "设备/装饰", ATACategory.SYSTEMS),
    ("26", "防火", ATACategory.SYSTEMS),
    ("27", "飞行控制", ATACategory.SYSTEMS),
    ("28", "燃油", ATACategory.SYSTEMS),
    ("29", "液压", ATACategory.SYSTEMS),
    ("30", "防冰防雨", ATACategory.SYSTEMS),
    ("31", "指示/记录系统", ATACategory.SYSTEMS),
    ("32", "起落架", ATACategory.SYSTEMS),
    ("33", "灯光", ATACategory.SYSTEMS),
    ("34", "导航", ATACategory.SYSTEMS),
    ("35", "氧气", ATACategory.SYSTEMS),
    ("36", "气源", ATACategory.SYSTEMS),
    ("38", "水/废水", ATACategory.SYSTEMS),
    ("49", "APU辅助动力装置", ATACategory.SYSTEMS),
    ("52", "舱门", ATACategory.STRUCTURE),
    ("53", "机身", ATACategory.STRUCTURE),
    ("57", "机翼", ATACategory.STRUCTURE),
    ("71", "动力装置总成", ATACategory.POWERPLANT),
    ("72", "发动机", ATACategory.POWERPLANT),
    ("73", "发动机燃油与控制", ATACategory.POWERPLANT),
    ("74", "点火", ATACategory.POWERPLANT),
    ("79", "滑油", ATACategory.POWERPLANT),
    ("80", "起动", ATACategory.POWERPLANT),
]


# ── 维护检查级别 ──

CHECK_TYPES = {
    "transit": {"label": "过站检查", "hours": 0.5},
    "daily": {"label": "日检", "hours": 2},
    "weekly": {"label": "周检", "hours": 8},
    "a_check": {"label": "A检", "hours": 60, "interval": "400-600 FH"},
    "c_check": {"label": "C检", "hours": 6000, "interval": "20-24个月"},
    "d_check": {"label": "D检", "hours": 50000, "interval": "6-10年"},
}


# ── 通知/告警 ──

NOTIFICATION_TYPES = {
    "critical": {"duration_ms": 0, "color": "#C62828"},     # 持续显示直到确认
    "warning":  {"duration_ms": 5000, "color": "#FFA000"},   # 5秒自动消失
    "info":     {"duration_ms": 3000, "color": "#1976D2"},   # 3秒自动消失
    "success":  {"duration_ms": 3000, "color": "#2E7D32"},
}
