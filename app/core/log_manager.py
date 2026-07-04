# -*- coding: utf-8 -*-
"""日志文件自动管理 — 启动时清理过期日志，保留最近 N 个文件。"""

import os
import re
import threading
from datetime import datetime, timedelta
from pathlib import Path

_LOG_DIR = os.environ.get("TASKSENSE_LOG_DIR", "data/logs")
_KEEP_FILES = 20       # 保留最近 N 个日志文件
_KEEP_DAYS = 7         # 保留近 N 天的日志


def cleanup_logs(log_dir: str = _LOG_DIR, keep_files: int = _KEEP_FILES,
                 keep_days: int = _KEEP_DAYS):
    """清理过期日志文件。

    规则:
    1. 保留最近 keep_files 个文件（按修改时间）
    2. 删除超过 keep_days 天的文件
    """
    import glob as _glob

    path = Path(log_dir)
    if not path.exists():
        return

    # 收集所有 .log 文件（含轮转后缀 .log.1 .log.2 .log.3）
    all_logs = []
    for f in path.iterdir():
        if f.suffix in (".log",) or re.match(r"\.log\.\d+$", f.suffix + "".join(f.suffixes[1:] if len(f.suffixes) > 1 else [""])):
            all_logs.append(f)
    # 更简单的匹配
    all_logs = list(path.glob("*.log*"))

    if not all_logs:
        return

    now = datetime.now()
    cutoff_date = now - timedelta(days=keep_days)

    deleted = 0
    kept = 0

    for f in sorted(all_logs, key=lambda x: x.stat().st_mtime):
        mtime = datetime.fromtimestamp(f.stat().st_mtime)

        # 规则1: 超过 keep_days → 删除
        if mtime < cutoff_date:
            try:
                f.unlink()
                deleted += 1
            except OSError:
                pass
            continue

        # 规则2: 保留最近 keep_files 个
        kept += 1

    # 如果还超过 keep_files，删除最旧的
    if kept > keep_files:
        sorted_logs = sorted(all_logs, key=lambda x: x.stat().st_mtime)
        for f in sorted_logs[:kept - keep_files]:
            try:
                f.unlink()
                deleted += 1
            except OSError:
                pass

    if deleted:
        print(f"[LOG_MGR] Cleaned {deleted} old log files, {min(kept, keep_files)} retained")


def start_cleanup():
    """在后台线程启动日志清理（避免阻塞启动）。"""
    t = threading.Thread(target=cleanup_logs, daemon=True)
    t.start()
