"""Agent 工具 — RAG 知识库检索."""

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
def search_knowledge_base(query: str, top_k: int = 5,
                          doc_type: str = "") -> str:
    """搜索航空维护知识库。

    可查找:
    - ATA 章节对应的维护程序
    - 飞机型号的技术参数
    - 维护标准与实践

    Args:
        query: 搜索关键词或问题（中文或英文）
        top_k: 返回结果数（默认 5）
        doc_type: 文档类型过滤（可选：amm/fim/ad/ac/amt_handbook/sb/regulation/textbook）
    """
    pipeline = get_pipeline()

    stats = pipeline.get_stats()
    total_chunks = stats.get("total", sum(
        v for k, v in stats.items() if isinstance(v, int)))
    if total_chunks == 0:
        return "知识库为空。请先运行: python scripts/build_kb.py embed --force"

    results = pipeline.search(
        query, top_k=top_k,
        doc_type=doc_type if doc_type else None,
    )
    if not results:
        return f"未找到与 '{query}' 相关的内容"

    lines = [f"搜索 '{query}' — 找到 {len(results)} 条结果:"]
    for i, r in enumerate(results, 1):
        meta = r.get("metadata", {})
        src = meta.get("filename", "未知")
        ata = meta.get("ata_chapter", "")
        dtype = meta.get("doc_type", "")
        pg = meta.get("page_start", "")
        chapter = meta.get("chapter")
        score = r.get("score", 0)
        text = r.get("text", "")[:300]

        tags = []
        if ata:
            tags.append(f"ATA {ata}")
        if dtype:
            tags.append(dtype)
        if chapter is not None:
            tags.append(f"第{chapter}章")
        if pg:
            pg_tag = f"第{pg}页" if pg == meta.get("page_end", "") else f"第{pg}-{meta.get('page_end','')}页"
            tags.append(pg_tag)
        tag = f" [{', '.join(tags)}]" if tags else ""
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
    total_chunks = stats.get("total", sum(
        v for k, v in stats.items() if isinstance(v, int)))
    if total_chunks == 0:
        return "知识库为空。请先运行: python scripts/build_kb.py embed --force"

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


@tool
def search_operation_log(query: str, limit: int = 20) -> str:
    """搜索最近的操作日志。

    查找历史上类似任务的处理方式和结果。
    用于了解过去类似故障的维修过程、排故方法等。

    Args:
        query: 搜索关键词（任务标题、ATA、机号等）
        limit: 返回结果数（默认 20）
    """
    from app.core.services.log_service import log_service

    logs = log_service.search_logs(query, limit=limit)
    if not logs:
        return f"未找到与 '{query}' 相关的操作记录。可以尝试更宽泛的关键词。"

    lines = [f"操作日志 — '{query}' 找到 {len(logs)} 条记录:"]
    for i, entry in enumerate(logs, 1):
        ts = entry.timestamp.strftime("%m-%d %H:%M") if entry.timestamp else ""
        title_hint = f" [{entry.task_title[:20]}]" if entry.task_title else ""
        lines.append(
            f"{i}. [{ts}] [{entry.log_type.value}]{title_hint} {entry.description}"
        )
        if entry.details:
            detail_str = ", ".join(
                f"{k}={v}" for k, v in entry.details.items()
                if v is not None
            )
            if detail_str:
                lines.append(f"   详情: {detail_str}")

    return "\n".join(lines)
