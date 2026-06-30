"""Pytest 全局配置 — 跳过慢测试的条件标记。"""

import pytest
from pathlib import Path


def _kb_has_data() -> bool:
    """检测知识库是否有数据。"""
    try:
        import chromadb
        from chromadb.config import Settings
        db_dir = Path("data/vector_store")
        if not db_dir.exists():
            return False
        client = chromadb.PersistentClient(
            path=str(db_dir),
            settings=Settings(anonymized_telemetry=False),
        )
        colls = client.list_collections()
        for c in colls:
            if c.count() > 0:
                return True
        return False
    except Exception:
        return False


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "needs_kb: 标记需要已构建知识库的测试（CI 中默认跳过）"
    )
    config.addinivalue_line(
        "markers",
        "slow: 标记慢测试（默认跳过，用 --run-slow 启用）"
    )


def pytest_addoption(parser):
    parser.addoption("--run-slow", action="store_true", default=False,
                     help="运行慢测试（含 PDF 提取和嵌入模型加载）")


def pytest_collection_modifyitems(config, items):
    run_slow = config.getoption("--run-slow")

    for item in items:
        # needs_kb: 没有知识库数据时自动跳过
        if "needs_kb" in item.keywords:
            if not _kb_has_data():
                item.add_marker(
                    pytest.mark.skip("知识库为空，请先运行: python scripts/build_kb.py embed"))

    if not run_slow:
        skip_slow = pytest.mark.skip(reason="需要 --run-slow 选项运行慢测试")
        for item in items:
            if "slow" in item.keywords:
                item.add_marker(skip_slow)
