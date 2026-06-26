"""配置层测试."""

import os
import pytest

from app.config.theme import theme, AppTheme
from app.config.constants import (
    ALLOWED_TRANSITIONS,
    ATA_CHAPTERS,
    DEFAULT_COLUMNS,
    PRIORITY_LABELS,
    PRIORITY_ORDER,
    TASK_TYPE_LABELS,
    STATUS_LABELS,
    ATACategory,
    ATATaskType,
    CHECK_TYPES,
    NOTIFICATION_TYPES,
)
from app.config.settings import AppSettings


class TestTheme:
    """AppTheme 测试。"""

    def test_theme_singleton(self):
        """theme 是 AppTheme 实例。"""
        assert isinstance(theme, AppTheme)
        assert theme.bg == "#0D1117"

    def test_priority_colors(self):
        """优先级颜色映射。"""
        assert theme.priority_color("aog") == "#FF4444"
        assert theme.priority_color("cat_a") == "#FF8C00"
        assert theme.priority_color("cat_b") == "#FFD700"
        assert theme.priority_color("cat_c") == "#58A6FF"
        assert theme.priority_color("cat_d") == "#8B949E"

    def test_priority_color_unknown(self):
        """未知优先级返回默认色。"""
        assert theme.priority_color("unknown") == theme.text_disabled

    def test_task_type_colors(self):
        """任务类型颜色。"""
        assert theme.task_type_color("troubleshoot") == "#F78166"
        assert theme.task_type_color("inspection") == "#7EE787"
        assert theme.task_type_color("servicing") == "#79C0FF"
        assert theme.task_type_color("removal_install") == "#D2A8FF"
        assert theme.task_type_color("test") == "#FFA657"
        assert theme.task_type_color("repair") == "#56D4DD"

    def test_task_type_color_unknown(self):
        assert theme.task_type_color("unknown") == theme.text_disabled

    def test_ata_category_color(self):
        """ATA 大类颜色。"""
        assert theme.ata_category_color("05") == "#00897B"    # General
        assert theme.ata_category_color("32") == "#1565C0"    # Systems
        assert theme.ata_category_color("53") == "#546E7A"    # Structure
        assert theme.ata_category_color("65") == "#3949AB"    # Propeller
        assert theme.ata_category_color("72") == "#D84315"    # Powerplant

    def test_ata_category_invalid(self):
        """无效 ATA 章号返回默认色。"""
        assert theme.ata_category_color("invalid") == theme.text_disabled
        assert theme.ata_category_color("") == theme.text_disabled

    def test_ata_category_with_subsection(self):
        """带子节的 ATA。"""
        assert theme.ata_category_color("32-41-03") == "#1565C0"

    def test_color_scheme_keys(self):
        """color_scheme 包含必要键。"""
        scheme = theme.color_scheme
        for key in ["primary", "surface", "background", "error"]:
            assert key in scheme

    def test_theme_is_frozen(self):
        """主题是不可变对象。"""
        with pytest.raises(Exception):
            theme.bg = "#FFFFFF"

    def test_dimension_values(self):
        """尺寸值为正数。"""
        assert theme.card_width == 280
        assert theme.column_width == 300
        assert theme.side_panel_width == 480
        assert theme.nav_width == 240

    def test_font_sizes(self):
        """字体大小合理。"""
        assert theme.font_xs == 11
        assert theme.font_lg == 16
        assert theme.font_xxl == 24

    def test_animation_durations_positive(self):
        """动画时长为正。"""
        assert theme.anim_fast > 0
        assert theme.anim_normal > 0
        assert theme.anim_slow > 0


class TestConstants:
    """常量定义测试。"""

    def test_priority_labels_complete(self):
        """所有优先级有标签。"""
        for pri in PRIORITY_ORDER:
            assert pri in PRIORITY_LABELS

    def test_priority_order_unique(self):
        """优先级排序无重复。"""
        assert len(PRIORITY_ORDER) == len(set(PRIORITY_ORDER))

    def test_task_type_labels_complete(self):
        """所有任务类型有标签。"""
        for tt in ["troubleshoot", "inspection", "servicing",
                    "removal_install", "test", "repair"]:
            assert tt in TASK_TYPE_LABELS

    def test_status_labels_complete(self):
        """所有状态有标签。"""
        expected = ["backlog", "triage", "scheduled", "ready",
                    "in_progress", "inspection", "parts_hold",
                    "completed", "archived"]
        for s in expected:
            assert s in STATUS_LABELS

    def test_default_columns_count(self):
        """默认列数。"""
        assert len(DEFAULT_COLUMNS) == 9

    def test_default_columns_order(self):
        """列按 order 排序。"""
        for i in range(len(DEFAULT_COLUMNS) - 1):
            assert DEFAULT_COLUMNS[i]["order"] <= DEFAULT_COLUMNS[i + 1]["order"]

    def test_default_columns_unique_ids(self):
        """列 ID 唯一。"""
        ids = [c["id"] for c in DEFAULT_COLUMNS]
        assert len(ids) == len(set(ids))

    def test_allowed_transitions_symmetric(self):
        """状态转换声明完整。"""
        all_statuses = set(ALLOWED_TRANSITIONS.keys())
        for allowed in ALLOWED_TRANSITIONS.values():
            for target in allowed:
                assert target in all_statuses

    def test_ata_chapters_not_empty(self):
        """ATA 章节列表非空。"""
        assert len(ATA_CHAPTERS) > 0

    def test_ata_chapters_structure(self):
        """每个 ATA 条目有 (章节号, 标题, 大类)。"""
        for entry in ATA_CHAPTERS:
            assert len(entry) == 3
            assert isinstance(entry[0], str)
            assert isinstance(entry[1], str)
            assert isinstance(entry[2], ATACategory)

    def test_ata_categories_are_valid(self):
        """ATA 大类正确。"""
        for _, _, cat in ATA_CHAPTERS:
            assert isinstance(cat, ATACategory)

    def test_check_types(self):
        """检查类型定义。"""
        for check in ["transit", "daily", "weekly", "a_check", "c_check", "d_check"]:
            assert check in CHECK_TYPES

    def test_notification_types(self):
        """通知类型定义。"""
        for ntype in ["critical", "warning", "info", "success"]:
            assert ntype in NOTIFICATION_TYPES
            assert "duration_ms" in NOTIFICATION_TYPES[ntype]
            assert "color" in NOTIFICATION_TYPES[ntype]

    def test_ata_task_types(self):
        """ATA 页面块类型枚举。"""
        types = [e for e in ATATaskType]
        assert len(types) == 9


class TestSettings:
    """AppSettings 测试。"""

    def test_default_settings(self):
        s = AppSettings()
        assert s.app_name == "TaskSense"
        assert s.app_version == "0.1.0"
        assert s.debug is False
        assert s.theme_mode == "dark"
        assert s.language == "zh"

    def test_default_rag_settings(self):
        s = AppSettings()
        assert s.chunk_size > 0
        assert s.chunk_overlap < s.chunk_size
        assert s.retrieval_top_k > 0

    def test_default_agent_settings(self):
        s = AppSettings()
        assert s.triage_autonomy == "low"
        assert s.suggest_autonomy == "medium"
        assert s.compliance_autonomy == "high"
        assert s.anomaly_check_interval_minutes > 0

    def test_from_env_override_string(self):
        """环境变量覆盖字符串配置。"""
        os.environ["TASKSENSE_APP_NAME"] = "TestApp"
        try:
            s = AppSettings.from_env()
            assert s.app_name == "TestApp"
        finally:
            del os.environ["TASKSENSE_APP_NAME"]

    def test_from_env_override_bool(self):
        """环境变量覆盖布尔配置。"""
        os.environ["TASKSENSE_DEBUG"] = "true"
        try:
            s = AppSettings.from_env()
            assert s.debug is True
        finally:
            del os.environ["TASKSENSE_DEBUG"]

    def test_from_env_override_int(self):
        """环境变量覆盖整数配置。"""
        os.environ["TASKSENSE_CHUNK_SIZE"] = "512"
        try:
            s = AppSettings.from_env()
            assert s.chunk_size == 512
        finally:
            del os.environ["TASKSENSE_CHUNK_SIZE"]

    def test_from_env_override_float(self):
        """环境变量覆盖浮点数配置。"""
        os.environ["TASKSENSE_LLM_TEMPERATURE"] = "0.5"
        try:
            s = AppSettings.from_env()
            assert s.llm_temperature == 0.5
        finally:
            del os.environ["TASKSENSE_LLM_TEMPERATURE"]

    def test_from_env_no_override(self):
        """无环境变量时返回默认值。"""
        # 清理可能存在的环境变量
        for key in list(os.environ.keys()):
            if key.startswith("TASKSENSE_"):
                del os.environ[key]
        s = AppSettings.from_env()
        assert s.app_name == "TaskSense"

    def test_llm_settings(self):
        s = AppSettings()
        assert s.llm_temperature == 0.0  # 维护领域用确定性输出
        assert s.llm_max_tokens > 0
