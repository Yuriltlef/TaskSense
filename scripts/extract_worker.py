# -*- coding: utf-8 -*-
"""独立 worker 进程 — 通过命令行参数接收文件列表，输出 JSON 结果到 stdout。"""

import sys
import json
import time
from pathlib import Path


def main():
    """命令行: python extract_worker.py <project_root> <out_dir> <file1> <file2> ..."""
    project_root = sys.argv[1]
    out_dir = sys.argv[2]
    files = sys.argv[3:]

    sys.path.insert(0, project_root)
    from app.knowledge.loader import PDFLoader

    results = []
    for fp_str in files:
        fp = Path(fp_str)
        txt_path = Path(out_dir) / f"{fp.stem}.txt"
        meta_path = Path(out_dir) / f"{fp.stem}.json"

        if txt_path.exists() and meta_path.exists():
            existing = txt_path.read_text(encoding="utf-8")
            if len(existing) > 100:
                results.append({"name": fp.name, "chars": len(existing),
                                "pages": 0, "elapsed": 0, "status": "skip"})
                continue

        t0 = time.time()
        try:
            loader = PDFLoader(str(fp.parent))
            doc = loader.load_file(fp)
        except Exception as e:
            results.append({"name": fp.name, "chars": 0, "pages": 0,
                            "elapsed": time.time() - t0, "status": f"error: {e}"})
            continue

        elapsed = time.time() - t0
        if doc and doc.get("text") and len(doc["text"]) > 50:
            txt_path.write_text(doc["text"], encoding="utf-8")
            meta_path.write_text(json.dumps({
                "filename": doc["filename"], "title": doc["title"],
                "pages": doc["pages"], "chars": len(doc["text"]),
                "size_bytes": doc.get("size_bytes", 0),
            }, ensure_ascii=False, indent=2), encoding="utf-8")
            results.append({"name": fp.name, "chars": len(doc["text"]),
                            "pages": doc["pages"], "elapsed": elapsed, "status": "ok"})
        else:
            results.append({"name": fp.name, "chars": 0, "pages": 0,
                            "elapsed": elapsed, "status": "empty"})

    # 输出 JSON 到 stdout
    sys.stdout.write(json.dumps(results, ensure_ascii=False))
    sys.stdout.flush()


if __name__ == "__main__":
    main()
