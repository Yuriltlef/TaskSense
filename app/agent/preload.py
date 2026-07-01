"""预加载模块 — 应用启动时预热嵌入模型和知识库."""

import threading
import time


_preload_done = False
_preload_status = "pending"
_preload_message = ""


def preload_async() -> threading.Thread:
    """异步预加载嵌入模型 + 知识库流水线。

    在后台线程执行，不阻塞 UI 启动。
    返回线程对象（可 join 等待完成）。
    """
    global _preload_done, _preload_status, _preload_message

    def _load():
        global _preload_done, _preload_status, _preload_message
        t0 = time.time()
        try:
            _preload_status = "loading_embedder"
            _preload_message = "Loading embedding model..."

            # 1. 预热嵌入模型（触发 SentenceTransformer 加载 + CUDA 初始化）
            from app.knowledge.embedder import Embedder
            embedder = Embedder()
            dev, dev_name = embedder.device_info
            _ = embedder.dimension  # 触发模型加载
            _preload_message = f"Embedder ready ({dev_name})"

            _preload_status = "loading_pipeline"
            # 2. 初始化知识库流水线（验证 ChromaDB 连接）
            from app.knowledge.pipeline import KnowledgePipeline
            pipeline = KnowledgePipeline()
            stats = pipeline.get_stats()
            total = stats.get("total", 0)
            _preload_message = f"KB ready ({total:,} chunks)"

            _preload_status = "done"
            _preload_done = True
            elapsed = time.time() - t0
            print(f"[Preload] All ready in {elapsed:.1f}s — "
                  f"{dev_name}, {total:,} chunks")

        except Exception as e:
            _preload_status = "error"
            _preload_message = f"Preload failed: {e}"
            _preload_done = True
            print(f"[Preload] Failed: {e}")

    thread = threading.Thread(target=_load, daemon=True, name="preload")
    thread.start()
    return thread


def is_preload_done() -> bool:
    return _preload_done


def get_preload_status() -> tuple[str, str]:
    """返回 (status, message)。status: pending/loading_embedder/loading_pipeline/done/error"""
    return _preload_status, _preload_message
