# -*- coding: utf-8 -*-
"""模型缓存工具 — 设置 HuggingFace 离线/联网模式。"""

import os
from pathlib import Path


def setup_model_cache(project_dir: Path | str, model_name: str = "BAAI/bge-m3") -> bool:
    """配置模型缓存目录，检测是否已缓存并设置离线/联网模式。

    返回 True 表示模型已缓存（离线模式），False 需联网下载。
    """
    cache_dir = Path(project_dir) / ".model_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(cache_dir))

    model_slug = "models--" + model_name.replace("/", "--")
    snapshots = cache_dir / "hub" / model_slug / "snapshots"
    is_cached = snapshots.exists() and any(snapshots.iterdir())

    if is_cached:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"

    return is_cached
