"""TaskSense 甘特图 — 独立子进程入口.

用法:
    python gantt_app.py

每次启动打开一个独立的甘特图窗口，只读展示已排程任务的时间线。
"""

import asyncio.streams
_original_del = asyncio.streams.StreamWriter.__del__


def _safe_del(self):
    try:
        _original_del(self)
    except RuntimeError:
        pass


asyncio.streams.StreamWriter.__del__ = _safe_del


if __name__ == "__main__":
    import flet as ft
    from app.gantt.app import GanttWindowApp

    ft.app(target=GanttWindowApp().main)
