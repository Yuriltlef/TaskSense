"""TaskSense 任务看板 — 独立子进程入口.

用法:
    python taskboard_app.py

每次启动打开一个独立的任务看板窗口，只读展示所有列的任务卡片。
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
    from app.taskboard.app import TaskBoardWindowApp

    ft.app(target=TaskBoardWindowApp().main)
