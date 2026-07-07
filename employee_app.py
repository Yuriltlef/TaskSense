"""TaskSense 员工工作台 — 独立子进程入口（轻量，不加载 Agent/LLM）。

用法:
    python employee_app.py

每次启动打开一个独立的员工窗口，先显示登录页（员工选择），
登录后进入任务工作台。可同时启动多个窗口。
"""

# ── 修复 Windows 退出时 "Event loop is closed" 报错 ──
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
    from app.employee.app import EmployeeWindowApp

    ft.app(target=EmployeeWindowApp().main)
