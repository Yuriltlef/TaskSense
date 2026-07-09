"""数据迁移脚本 — JSON → SQLite。

用法:
    python scripts/migrate_to_sql.py

从 data/board_state.json 读取旧数据，写入 data/board_state.db。
如果 SQLite 已有数据，跳过（除非 --force）。
"""

import argparse
import os
import sys

# 确保项目根在 path 中
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.services.persistence_service import persistence_service


def main():
    parser = argparse.ArgumentParser(description="TaskSense JSON → SQLite 数据迁移")
    parser.add_argument("--force", action="store_true", help="强制覆盖已有 SQLite 数据")
    parser.add_argument("--json", default="data/board_state.json", help="源 JSON 路径")
    parser.add_argument("--db", default="data/board_state.db", help="目标 SQLite 路径")
    args = parser.parse_args()

    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    json_path = os.path.join(project_root, args.json)
    db_path = os.path.join(project_root, args.db)

    if not os.path.exists(json_path):
        print(f"错误: 源文件不存在 — {json_path}")
        sys.exit(1)

    if os.path.exists(db_path) and not args.force:
        print(f"SQLite 已有数据 ({db_path})，使用 --force 强制覆盖")
        sys.exit(0)

    persistence_service.set_path(db_path)
    success = persistence_service.migrate_from_json(json_path)

    if success:
        print("迁移成功！")
        print(f"  源: {json_path}")
        print(f"  目标: {db_path}")

        # 验证
        from app.core.state import state
        persistence_service.load()
        tasks = state.get_all_tasks()
        aircraft = state.get_all_aircraft()
        print(f"  验证: {len(tasks)} 任务, {len(aircraft)} 飞机")
    else:
        print("迁移失败！")
        sys.exit(1)


if __name__ == "__main__":
    main()
