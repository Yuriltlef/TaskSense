# -*- coding: utf-8 -*-
"""
Agent 功能演示 — RAG + LLM 真实对话.

用法: python scripts/agent_demo.py
"""

import sys, os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
os.chdir(PROJECT_ROOT)
sys.path.insert(0, str(PROJECT_ROOT))

from app.config.settings_manager import SettingsManager
from app.knowledge.pipeline import KnowledgePipeline
from app.agent.llm_client import llm
from app.agent.orchestrator import agent as agent_svc
from app.core.state import state
from app.core.services.task_service import task_service


def sep(title=""):
    print(f"\n{'='*60}")
    if title:
        print(f"  {title}")
        print(f"{'='*60}")


def main():
    mgr = SettingsManager(); mgr.load()
    c = mgr.get_section("llm")
    r = mgr.get_section("rag")

    sep("TaskSense Agent Demo")
    print(f"  LLM  : {c['provider']} / {c['model']}")
    print(f"  URL  : {c['base_url']}")
    print(f"  Key  : {'***'+c['api_key'][-4:] if c['api_key'] else 'MISSING'}")
    print(f"  RAG  : {r['embedding_model']}")

    pipeline = KnowledgePipeline()
    chunks = pipeline.get_stats().get("chunks_stored", 0)
    print(f"  KB   : {chunks:,} chunks")

    # ── LLM 连接测试 ──
    sep("LLM Test")
    if not llm.is_available:
        print("  [FAIL] No API key. Set api_key in settings.json.")
    else:
        print(f"  Calling {c['model']}...", end=" ", flush=True)
        resp = llm.chat("用中文回复，尽量简短。", "请回复三个字：已连接")
        ok = not resp.startswith("[Error]")
        print("OK" if ok else f"FAIL")
        if not ok:
            print(f"  {resp}")
            print(f"\n  For DeepSeek: provider=openai, base_url=https://api.deepseek.com")
            print(f"  For Anthropic: provider=anthropic, base_url=https://api.anthropic.com")

    # ── 演示数据 ──
    from datetime import datetime, timedelta
    from app.core.models.aircraft import Aircraft, AircraftStatus
    for rn, m in [("B-5823", "737-800"), ("B-2518", "A320neo")]:
        if not state.get_aircraft(rn):
            state.add_aircraft(Aircraft(registration=rn, model=m,
                               status=AircraftStatus.OPERATIONAL, total_hours=25000))
    if not state.get_all_tasks():
        n = datetime.now()
        for t, reg, ata, pri in [
            ("前起落架转向异响排查", "B-5823", "32-41-03", "cat_a"),
            ("右发滑油耗率偏高", "B-5823", "79-21-01", "cat_b"),
            ("A检-飞行控制面检查", "B-2518", "27-10-00", "cat_c"),
        ]:
            task_service.create_task(title=t, aircraft_reg=reg, ata_chapter=ata,
                                     priority=pri, assignee="张工", estimated_hours=4.0,
                                     due_date=n + timedelta(hours=24))

    # ── REPL ──
    sep("REPL (/help /quit)")
    while True:
        try:
            cmd = input("\n>> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye."); break
        if not cmd: continue
        if cmd == "/quit": print("Bye."); break

        if cmd == "/help":
            print("""
  <问题>         AI 回答 (RAG + LLM)
  /kb <查询>     纯知识库检索
  /report        每日报告
  /suggest <描述> 任务建议
  /summary       看板摘要
  /list          任务列表
  /stats         知识库统计
  /help /quit
            """)
        elif cmd == "/report":
            sep("Report"); print(agent_svc.generate_daily_report())
        elif cmd.startswith("/kb "):
            sep(f"KB: {cmd[4:]}")
            for i, r in enumerate(pipeline.search(cmd[4:], top_k=5), 1):
                m = r.get("metadata", {})
                print(f"\n  [{i}] {r['score']:.0%} | {m.get('filename','?')} | ATA {m.get('ata_chapter','-')}")
                print(f"  {r['text'][:200]}...")
        elif cmd.startswith("/suggest "):
            sep(f"Suggest: {cmd[9:]}")
            r = agent_svc.suggest_task_template(cmd[9:])
            print(f"  ATA: {r.get('ata_chapter','?')}  Type: {r.get('task_type','?')}")
            for t in r.get("similar_tasks", [])[:3]:
                print(f"  Similar: {t['title']}")
        elif cmd == "/summary":
            from app.agent.tools.board_tools import get_board_summary
            print(get_board_summary.invoke({}))
        elif cmd == "/list":
            for t in state.get_all_tasks():
                print(f"  [{t.id}] {t.title} | {t.priority.value} | {t.status.value}")
        elif cmd == "/stats":
            s = pipeline.get_stats()
            print(f"  Files: {s['total_files']} | {s['total_size_mb']}MB | Chunks: {s['chunks_stored']:,}")
        else:
            sep(f"Q: {cmd[:60]}")
            # RAG
            kb = pipeline.search(cmd, top_k=3)
            print(f"  [RAG] {len(kb)} hits")
            for i, r in enumerate(kb, 1):
                print(f"    {i}. {r['score']:.0%} | {r['metadata'].get('filename','?')[:40]}")

            if llm.is_available and kb:
                ctx = "\n".join(f"[{i+1}] {r['text'][:500]}" for i, r in enumerate(kb[:3]))
                system = (
                    "You are an aviation maintenance expert. Answer in Chinese based on the "
                    "retrieved knowledge below. Be concise, professional. Never fabricate."
                )
                prompt = f"Context:\n{ctx}\n\nQuestion: {cmd}"
                print(f"\n  [LLM] ...", end=" ", flush=True)
                ans = llm.chat(system, prompt)
                if ans.startswith("[Error]"):
                    print(f"FAIL\n  {ans}")
                else:
                    print("OK")
                    print(f"{'─'*55}\n{ans}\n{'─'*55}")
            elif not llm.is_available:
                print("  [LLM unavailable, RAG only]")
                for i, r in enumerate(kb, 1):
                    print(f"\n  [{i}] {r['text'][:300]}...")
            else:
                print("  No relevant results.")


if __name__ == "__main__":
    main()
