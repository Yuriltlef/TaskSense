"""员工数据服务。

管理虚拟员工数据的加载、查询和校验。
"""

import json
import os
from typing import Optional


class EmployeeService:
    """员工数据服务（单例）。"""

    _instance: Optional["EmployeeService"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._employees: list[dict] = []
        self._by_id: dict[str, dict] = {}
        self._loaded = False

    # ── 加载 ──

    def load(self, path: str = "data/employees.json") -> list[dict]:
        """加载员工 JSON 文件。返回员工列表。"""
        if not os.path.isabs(path):
            # 相对项目根目录
            project_root = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "..", "..")
            )
            path = os.path.join(project_root, path)

        if not os.path.exists(path):
            self._loaded = True
            return []

        try:
            with open(path, "r", encoding="utf-8") as f:
                self._employees = json.load(f)
            self._by_id = {e["employee_id"]: e for e in self._employees}
            self._loaded = True
            return self._employees
        except (json.JSONDecodeError, IOError) as e:
            print(f"[EmployeeService] 加载失败: {e}")
            self._loaded = True
            return []

    # ── 查询 ──

    def get_employee(self, employee_id: str) -> Optional[dict]:
        """按 ID 获取员工。"""
        self._ensure_loaded()
        return self._by_id.get(employee_id)

    def get_all(self) -> list[dict]:
        """获取全部员工。"""
        self._ensure_loaded()
        return list(self._employees)

    def search_employees(self, query: str) -> list[dict]:
        """模糊搜索员工（按 ID、姓名、工种）。"""
        self._ensure_loaded()
        if not query:
            return []
        q = query.lower()
        results = []
        for e in self._employees:
            if (q in e["employee_id"].lower()
                    or q in e["name"]
                    or q in e["trade"]):
                results.append(e)
        return results

    def get_available_employees(self) -> list[dict]:
        """获取当前可用的员工（available=True）。"""
        self._ensure_loaded()
        return [e for e in self._employees if e.get("available", True)]

    def get_by_trade(self, trade: str) -> list[dict]:
        """按工种筛选。"""
        self._ensure_loaded()
        return [e for e in self._employees if e.get("trade") == trade]

    # ── 校验 ──

    def validate(self, employee_id: str) -> bool:
        """校验员工 ID 是否存在且可用。"""
        emp = self.get_employee(employee_id)
        return emp is not None and emp.get("available", True)

    def exists(self, employee_id: str) -> bool:
        """检查员工 ID 是否存在（不管是否可用）。"""
        return self.get_employee(employee_id) is not None

    def employee_count(self) -> int:
        """员工总数。"""
        self._ensure_loaded()
        return len(self._employees)

    # ── 内部 ──

    def _ensure_loaded(self):
        """确保已加载数据。"""
        if not self._loaded:
            self.load()

    @classmethod
    def reset(cls):
        """重置单例（测试用）。"""
        cls._instance = None


# 全局单例
employee_service = EmployeeService()
