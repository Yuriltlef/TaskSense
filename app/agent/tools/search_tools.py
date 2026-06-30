"""Agent 工具 — RAG 知识库检索."""

from typing import Optional

from langchain.tools import tool

# 全局知识库流水线（延迟初始化）
_pipeline = None


def get_pipeline():
    global _pipeline
    if _pipeline is None:
        from app.knowledge.pipeline import KnowledgePipeline
        _pipeline = KnowledgePipeline()
    return _pipeline


@tool
def search_knowledge_base(query: str, top_k: int = 5) -> str:
    """搜索航空维护知识库。

    可查找:
    - ATA 章节对应的维护程序
    - 飞机型号的技术参数
    - 维护标准与实践

    Args:
        query: 搜索关键词或问题（中文或英文）
        top_k: 返回结果数（默认 5）
    """
    pipeline = get_pipeline()

    stats = pipeline.get_stats()
    if stats.get("chunks_stored", 0) == 0:
        # 尝试构建
        result = pipeline.build_knowledge_base()
        if result["status"] != "built":
            return f"知识库未就绪: {result.get('message', '未知错误')}"

    results = pipeline.search(query, top_k=top_k)
    if not results:
        return f"未找到与 '{query}' 相关的内容"

    lines = [f"搜索 '{query}' — 找到 {len(results)} 条结果:"]
    for i, r in enumerate(results, 1):
        meta = r.get("metadata", {})
        src = meta.get("filename", "未知")
        ata = meta.get("ata_chapter", "")
        score = r.get("score", 0)
        text = r.get("text", "")[:300]

        tag = f" [ATA {ata}]" if ata else ""
        lines.append(
            f"\n--- 结果 {i} (相关度: {score:.0%}, 来源: {src}{tag}) ---\n{text}..."
        )

    return "\n".join(lines)


@tool
def lookup_ata_chapter(ata_code: str) -> str:
    """查找 ATA 章节定义和维护信息。

    Args:
        ata_code: ATA 章节号（如 "32" 或 "32-41-03"）
    """
    pipeline = get_pipeline()

    stats = pipeline.get_stats()
    if stats.get("chunks_stored", 0) == 0:
        pipeline.build_knowledge_base()

    results = pipeline.search(
        f"ATA {ata_code} maintenance procedures",
        top_k=5,
        ata_filter=ata_code.split("-")[0],
    )

    if not results:
        return f"未找到 ATA {ata_code} 的详细信息"

    lines = [f"ATA {ata_code} — 找到 {len(results)} 条相关内容:"]
    for i, r in enumerate(results, 1):
        text = r.get("text", "")[:250]
        lines.append(f"\n--- {i} (相关度: {r.get('score', 0):.0%}) ---\n{text}...")

    return "\n".join(lines)
