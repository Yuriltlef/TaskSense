# -*- coding: utf-8 -*-
"""Build knowledge base from PDFs — two-phase: text extraction then embedding.

Usage:
    python scripts/build_kb.py extract         # Phase 1: PDF -> text (multi-process)
    python scripts/build_kb.py embed           # Phase 2: text -> chunks -> embed -> store
    python scripts/build_kb.py build           # Both phases
    python scripts/build_kb.py build --force   # Force rebuild
"""

import sys
import os
import json
import subprocess
import time
import argparse
from pathlib import Path

DEFAULT_WORKERS = max(4, os.cpu_count() or 8)

_SCRIPT_DIR = Path(__file__).parent
_PROJECT_DIR = _SCRIPT_DIR.parent

# 模型缓存到项目目录
_MODEL_CACHE = _PROJECT_DIR / ".model_cache"
os.environ.setdefault("HF_HOME", str(_MODEL_CACHE))
_MODEL_CACHE.mkdir(parents=True, exist_ok=True)

# 检查嵌入模型是否已缓存，决定离线/联网模式
_MODEL_NAME = "BAAI/bge-m3"
_MODEL_SLUG = "models--" + _MODEL_NAME.replace("/", "--")
_MODEL_SNAPSHOTS = _MODEL_CACHE / "hub" / _MODEL_SLUG / "snapshots"
_IS_MODEL_CACHED = _MODEL_SNAPSHOTS.exists() and any(_MODEL_SNAPSHOTS.iterdir())

if _IS_MODEL_CACHED:
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
else:
    print(f"Model '{_MODEL_NAME}' not found in cache. Downloading from HuggingFace...")
    print(f"Cache dir: {_MODEL_CACHE}")

if str(_PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(_PROJECT_DIR))
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

# ── Helpers ──

def fmt_size(mb):
    if mb < 1: return f"{mb * 1024:.0f}KB"
    return f"{mb:.1f}MB"

def fmt_time(s):
    if s < 60: return f"{s:.1f}s"
    m, sec = divmod(s, 60)
    return f"{int(m)}m{int(sec)}s"

def bar(current, total, w=25):
    pct = current / max(total, 1)
    filled = int(w * pct)
    return f"[{'#' * filled}{'-' * (w - filled)}] {pct:.0%}"

def header(title):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")

def secho(msg, end="\n", **kw):
    print(msg, end=end, flush=True)


# ═══════════════════════════════════════════
# Phase 1: Extract (multi-process)
# ═══════════════════════════════════════════

def phase_extract(workers: int = DEFAULT_WORKERS):
    header("PHASE 1: PDF -> Text Files (multi-process)")

    PROJECT = Path(__file__).parent.parent
    src_dir = PROJECT / "data" / "knowledge_base"
    out_dir = PROJECT / "data" / "knowledge_base" / "processed"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 避免在子进程中重复导入主模块的 setup
    sys.path.insert(0, str(PROJECT))
    from app.knowledge.loader import PDFLoader
    loader = PDFLoader(str(src_dir))
    pdf_files = loader.list_files()

    if not pdf_files:
        secho("  [ERROR] No PDF files found.")
        return False

    secho(f"  Source : {src_dir}")
    secho(f"  Files  : {len(pdf_files)}")
    secho(f"  Workers: {workers}\n")

    processed = 0; skipped = 0; empty = 0; total_chars = 0; done = 0

    # 将文件均匀分配给 workers
    chunks = [[] for _ in range(workers)]
    for i, fp in enumerate(pdf_files):
        chunks[i % workers].append(str(fp))

    worker_script = str(PROJECT / "scripts" / "extract_worker.py")
    # 使用项目 venv 的 Python
    venv_python = str(PROJECT / ".venv" / "Scripts" / "python.exe")
    if not Path(venv_python).exists():
        venv_python = sys.executable  # fallback

    procs = []
    for i, chunk in enumerate(chunks):
        if not chunk:
            continue
        cmd = [venv_python, worker_script, str(PROJECT), str(out_dir)] + chunk
        procs.append(subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8",
            cwd=str(PROJECT),
        ))

    secho(f"  Launched {len(procs)} worker processes\n")

    for i, proc in enumerate(procs):
        secho(f"  Worker {i+1}/{len(procs)} running...", end="", flush=True)
        try:
            out, err = proc.communicate(timeout=300)
        except subprocess.TimeoutExpired:
            proc.kill(); out, err = proc.communicate()
            secho(f" TIMEOUT")
            continue
        if proc.returncode != 0 or not out.strip():
            secho(f" FAILED (rc={proc.returncode}, err={err[:100]})")
            continue
        secho(" OK")

        try:
            results = json.loads(out)
            for r in results:
                done += 1
                name, chars, pages, elapsed = r.get("name","?"), r.get("chars",0), r.get("pages",0), r.get("elapsed",0)
                status = r.get("status","?")
                if status == "skip":
                    skipped += 1; total_chars += chars
                    secho(f"    {bar(done, len(pdf_files))} [{done}/{len(pdf_files)}] SKIP {name}")
                elif status == "ok":
                    processed += 1; total_chars += chars
                    secho(f"    {bar(done, len(pdf_files))} [{done}/{len(pdf_files)}] {name} -> {pages}pg, {chars:,} chars, {fmt_time(elapsed)}")
                elif status.startswith("error"):
                    empty += 1
                    secho(f"    {bar(done, len(pdf_files))} [{done}/{len(pdf_files)}] ERROR {name}: {status[7:50]}")
                else:
                    empty += 1
                    secho(f"    {bar(done, len(pdf_files))} [{done}/{len(pdf_files)}] EMPTY {name}")
        except json.JSONDecodeError:
            secho(f"  Worker {i+1} returned invalid JSON: {out[:200]}")
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps({
        "total_files": len(pdf_files), "extracted": processed,
        "skipped": skipped, "empty": empty, "total_chars": total_chars,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    secho(f"\n  [DONE] Extracted: {processed}  |  Skipped: {skipped}  |  Empty: {empty}  |  Chars: {total_chars:,}")
    return True


# ═══════════════════════════════════════════
# Phase 2: Embed
# ═══════════════════════════════════════════

def phase_embed(force=False, incremental=False, collection="kb_static"):
    header(f"PHASE 2: Embed -> [{collection}]")

    PROJECT = Path(__file__).parent.parent
    sys.path.insert(0, str(PROJECT))
    from app.knowledge.chunker import TextChunker
    from app.knowledge.embedder import Embedder
    from app.knowledge.store import VectorStore

    store_path = PROJECT / "data" / "vector_store"
    store = VectorStore(str(store_path), collection_name=collection)
    state_file = store_path / "embedded.json"

    if force and store.count() > 0:
        secho(f"  [CLEAR] Removing {store.count()} chunks...")
        store.clear()
        if state_file.exists(): state_file.unlink()

    txt_dir = PROJECT / "data" / "knowledge_base" / "processed"
    txt_files = sorted(txt_dir.glob("*.txt"))

    if not txt_files:
        secho("  [ERROR] No processed text files.")
        return False

    embedded_state = {}
    if state_file.exists():
        embedded_state = json.loads(state_file.read_text(encoding="utf-8"))

    to_process = []; skipped_count = 0
    for tf in txt_files:
        if incremental and tf.name in embedded_state:
            if tf.stat().st_mtime <= embedded_state[tf.name].get("mtime", 0):
                skipped_count += 1; continue
        to_process.append(tf)

    if incremental and skipped_count:
        secho(f"  Incremental: {skipped_count} skipped, {len(to_process)} to process")
    else:
        secho(f"  Text files: {len(txt_files)} (processing all)")

    if incremental and not to_process:
        secho("  [OK] All up to date.")
        return True

    secho(f"\n  --- Chunking ---")
    chunker = TextChunker(chunk_size=800, chunk_overlap=120)
    all_chunks = []
    for i, tf in enumerate(to_process, 1):
        meta = json.loads(tf.with_suffix(".json").read_text(encoding="utf-8")) if tf.with_suffix(".json").exists() else {}
        text = tf.read_text(encoding="utf-8")
        chunks = chunker.chunk_document({"text": text, "filename": meta.get("filename", tf.name), "title": meta.get("title", tf.stem)})
        all_chunks.extend(chunks)
        ata = sum(1 for c in chunks if c["metadata"].get("ata_chapter"))
        secho(f"  {bar(i, len(to_process))} [{i}/{len(to_process)}] {tf.name} -> {len(chunks)} chunks (ATA: {ata})")

    secho(f"\n  Total chunks: {len(all_chunks)}")
    if not all_chunks: secho("  [ERROR] No chunks."); return False

    secho(f"\n  --- Embedding ---")
    embedder = Embedder()
    dev, dev_name = embedder.device_info
    secho(f"  Model : {embedder.model_name}")
    secho(f"  Device: {dev_name} ({dev})")
    secho(f"  Dims  : {embedder.dimension}")

    if dev == "cuda":
        import torch; gb = torch.cuda.get_device_properties(0).total_memory / 1024**3
        secho(f"  VRAM  : {gb:.1f} GB")
    elif dev == "cpu":
        secho("  [WARN] No GPU. Install CUDA torch.")

    texts = [c["text"] for c in all_chunks]
    total = len(texts)
    secho(f"  Chunks: {total}")
    secho("  Encoding...")
    t0 = time.time()
    embeddings = embedder.embed_documents(texts)
    embed_time = time.time() - t0
    secho(f"  Done: {total} chunks in {fmt_time(embed_time)} ({total / embed_time:.0f} ch/s)")

    secho(f"\n  --- Storing ---"); t0 = time.time()
    added = store.add_chunks(all_chunks, embeddings)
    secho(f"  Stored {added} chunks in {fmt_time(time.time() - t0)}")

    for tf in to_process:
        embedded_state[tf.name] = {"mtime": tf.stat().st_mtime, "size": tf.stat().st_size, "embedded_at": time.time()}
    state_file.write_text(json.dumps(embedded_state, indent=2), encoding="utf-8")

    return True


# ═══════════════════════════════════════════
# Main
# ═══════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Build aviation knowledge base")
    parser.add_argument("command", nargs="?", default="build",
                        choices=["extract", "embed", "build"])
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                        help=f"Workers (default: cpu-2={DEFAULT_WORKERS})")
    parser.add_argument("--incremental", action="store_true")
    parser.add_argument("--collection", default="kb_static",
                        choices=["kb_static", "kb_live"],
                        help="Which collection to build (default: kb_static)")
    parser.add_argument("--cleanup", action="store_true",
                        help="Remove orphaned/duplicate collections before building")
    args = parser.parse_args()

    t0 = time.time()
    print("=" * 60)
    print("  TaskSense — Knowledge Base Builder")
    print("=" * 60)

    # ── Collection cleanup ──
    if args.cleanup:
        from app.knowledge.store import VectorStore
        store = VectorStore(str(_PROJECT_DIR / "data" / "vector_store"))
        known = {"kb_static", "kb_live"}
        all_colls = store.list_collections()
        orphaned = [c for c in all_colls if c not in known]
        if orphaned:
            header("Collection Cleanup")
            for c in orphaned:
                n = store.count(c)
                store.delete_collection(c)
                secho(f"  [DEL] {c} ({n} chunks)")
        else:
            secho("  [OK] No orphaned collections.")

    ok = True
    if args.command in ("extract", "build"):
        ok = phase_extract(workers=args.workers) and ok
    if args.command in ("embed", "build"):
        ok = phase_embed(force=args.force, incremental=args.incremental,
                         collection=args.collection) and ok

    if ok:
        print(f"\n{'=' * 60}")
        print(f"  ALL DONE — {fmt_time(time.time() - t0)}")
        print(f"{'=' * 60}\n")
    else:
        print("\n  [FAILED]"); sys.exit(1)


if __name__ == "__main__":
    main()
