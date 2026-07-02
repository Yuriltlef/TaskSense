# -*- coding: utf-8 -*-
"""结构化日志 — 基于 Python logging 模块，双通道输出（控制台 + 文件）。

用法不变:
    from app.core.logging import log
    log.info("task.create", title="发动机检查", ata="72-00-00")
    log.begin("agent.ask", question="...") / log.end("agent.ask")
    log.section("Phase 启动")

环境变量:
    TASKSENSE_LOG_LEVEL = DEBUG | INFO | WARN | ERROR (默认 INFO)
    TASKSENSE_LOG_DIR   = 日志目录 (默认 data/logs)
"""

import logging
import logging.handlers
import os
import sys
import threading
from datetime import datetime
from functools import wraps

# ── 日志器配置 ──

_LOG_LEVEL_NAME = os.environ.get("TASKSENSE_LOG_LEVEL", "INFO").upper()
_LOG_LEVEL = getattr(logging, _LOG_LEVEL_NAME, logging.INFO)
_LOG_DIR = os.environ.get("TASKSENSE_LOG_DIR", "data/logs")

_logger = logging.getLogger("tasksense")
_logger.setLevel(_LOG_LEVEL)
_logger.propagate = False

# 控制台 handler（彩色级别标签）
_console_fmt = logging.Formatter(
    "%(asctime)s.%(msecs)03d [%(levelname)-5s] %(message)s",
    datefmt="%H:%M:%S",
)
_console = logging.StreamHandler(sys.stdout)
_console.setLevel(_LOG_LEVEL)
_console.setFormatter(_console_fmt)
_logger.addHandler(_console)

# 文件 handler（按时间戳命名）
_file_path = None
_file_handler = None
_lock = threading.Lock()
_indent = 0


def _ensure_file_handler():
    global _file_handler, _file_path
    if _file_handler is not None:
        return
    try:
        os.makedirs(_LOG_DIR, exist_ok=True)
        _file_path = os.path.join(
            _LOG_DIR, f"tasksense_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
        _file_handler = logging.handlers.RotatingFileHandler(
            _file_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
        _file_handler.setLevel(logging.DEBUG)  # 文件始终记录 DEBUG
        _file_fmt = logging.Formatter(
            "%(asctime)s [%(levelname)-5s] %(name)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        _file_handler.setFormatter(_file_fmt)
        _logger.addHandler(_file_handler)
    except Exception:
        pass


# ── 公开 API（与旧接口完全兼容）──

class _Log:
    """结构化日志门面。"""

    @staticmethod
    def _msg(category: str, msg: str, **kwargs) -> str:
        indent = "  " * _indent
        extra = ""
        if kwargs:
            parts = []
            for k, v in kwargs.items():
                if isinstance(v, str) and len(v) > 100:
                    v = v[:97] + "..."
                elif not isinstance(v, (str, int, float, bool)):
                    v = str(v)[:60]
                parts.append(f"{k}={v}")
            extra = " | " + " ".join(parts)
        return f"{indent}{category:30s} {msg}{extra}"

    @classmethod
    def debug(cls, category: str, msg: str = "", **kwargs):
        _ensure_file_handler()
        _logger.debug(cls._msg(category, msg, **kwargs))

    @classmethod
    def info(cls, category: str, msg: str = "", **kwargs):
        _ensure_file_handler()
        _logger.info(cls._msg(category, msg, **kwargs))

    @classmethod
    def warn(cls, category: str, msg: str = "", **kwargs):
        _ensure_file_handler()
        _logger.warning(cls._msg(category, msg, **kwargs))

    @classmethod
    def error(cls, category: str, msg: str = "", **kwargs):
        _ensure_file_handler()
        _logger.error(cls._msg(category, msg, **kwargs))

    @classmethod
    def trace(cls, category: str, msg: str = "", **kwargs):
        cls.debug(category, msg, **kwargs)

    @classmethod
    def begin(cls, category: str, msg: str = "", **kwargs):
        global _indent
        cls.info(category, "BEGIN " + msg, **kwargs)
        _indent += 1

    @classmethod
    def end(cls, category: str, msg: str = "", **kwargs):
        global _indent
        _indent = max(0, _indent - 1)
        cls.info(category, "END " + msg, **kwargs)

    @classmethod
    def result(cls, category: str, msg: str = "", **kwargs):
        cls.info(category, "=> " + msg, **kwargs)

    @classmethod
    def section(cls, title: str):
        _ensure_file_handler()
        line = "=" * 60
        with _lock:
            print(f"\n{line}")
            print(f"  {title}")
            print(f"{line}")
        _logger.info(f"{line}")
        _logger.info(f"  {title}")
        _logger.info(f"{line}")

    @classmethod
    def get_log_path(cls) -> str:
        """返回当前日志文件路径。"""
        return _file_path or ""

    @classmethod
    def trace_call(cls, category: str = ""):
        """函数调用追踪装饰器。"""
        def decorator(fn):
            cat = category or fn.__qualname__
            @wraps(fn)
            def wrapper(*a, **kw):
                a_short = [str(x)[:40] for x in a[:3]]
                kw_short = {k: str(v)[:40] for k, v in list(kw.items())[:3]}
                cls.begin(cat, f"{fn.__name__}({', '.join(a_short)})", **kw_short)
                try:
                    result = fn(*a, **kw)
                    cls.end(cat, "ok")
                    return result
                except Exception as e:
                    cls.error(cat, f"FAILED: {e}")
                    raise
            return wrapper
        return decorator


log = _Log()
