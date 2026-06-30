# -*- coding: utf-8 -*-
"""Build knowledge base from PDFs — two-phase: text extraction then embedding.

Usage:
    python scripts/build_kb.py extract         # Phase 1: PDF -> text files
    python scripts/build_kb.py embed           # Phase 2: text -> chunks -> embeddings -> store
    python scripts/build_kb.py build           # Both phases
    python scripts/build_kb.py build --force   # Force rebuild
"""

import sys
import os
import json
import time
import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
os.chdir(PROJECT_ROOT)
sys.path.insert(0, str(PROJECT_ROOT))

from app.knowledge.loader import PDFLoader
from app.knowledge.chunker import TextChunker
from app.knowledge.embedder import Embedder
from app.knowledge.store import VectorStore


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


# ── Phase 1: Extract ──

def phase_extract():
    header("PHASE 1: PDF -> Text Files")

    src_dir = PROJECT_ROOT / "data" / "knowledge_base"
    out_dir = PROJECT_ROOT / "data" / "knowledge_base" / "processed"
    out_dir.mkdir(parents=True, exist_ok=True)

    loader = PDFLoader(str(src_dir))
    pdf_files = loader.list_files()

    if not pdf_files:
        secho("  [ERROR] No PDF files found.")
        return False

    secho(f"  Source: {src_dir}")
    secho(f"  Output: {out_dir}")
    secho(f"  Files:  {len(pdf_files)}\n")

    processed = 0
    skipped = 0
    total_chars = 0
    manifest = []

    for i, fp in enumerate(pdf_files, 1):
        size_mb = fp.stat().st_size / (1024 * 1024)
        txt_path = out_dir / f"{fp.stem}.txt"
        meta_path = out_dir / f"{fp.stem}.json"

        # 检查是否已有
        if txt_path.exists() and meta_path.exists():
            existing_text = txt_path.read_text(encoding="utf-8")
            if len(existing_text) > 100:
                secho(f"  {bar(i, len(pdf_files))} [{i}/{len(pdf_files)}] SKIP {fp.name} (already extracted)")
                skipped += 1
                total_chars += len(existing_text)
                manifest.append({"file": fp.name, "chars": len(existing_text), "reused": True})
                continue

        secho(f"  {bar(i, len(pdf_files))} [{i}/{len(pdf_files)}] {fp.name} ({fmt_size(size_mb)})",
              end="", flush=True)

        t0 = time.time()
        doc = loader.load_file(fp)

        if doc and doc.get("text") and len(doc["text"]) > 50:
            # 保存文本
            txt_path.write_text(doc["text"], encoding="utf-8")
            meta_path.write_text(json.dumps({
                "filename": doc["filename"],
                "title": doc["title"],
                "pages": doc["pages"],
                "chars": len(doc["text"]),
                "size_bytes": doc.get("size_bytes", 0),
            }, ensure_ascii=False, indent=2), encoding="utf-8")

            secho(f" -> {doc['pages']}pg, {len(doc['text']):,} chars, {fmt_time(time.time() - t0)}")
            processed += 1
            total_chars += len(doc["text"])
            manifest.append({"file": fp.name, "chars": len(doc["text"]), "pages": doc["pages"]})
        else:
            secho(" -> EMPTY (no extractable text)")
            skipped += 1

    # 保存 manifest
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps({
        "total_files": len(pdf_files),
        "extracted": processed,
        "skipped": skipped,
        "total_chars": total_chars,
        "files": manifest,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    secho(f"\n  [DONE] Extracted: {processed}  |  Skipped: {skipped}  |  Chars: {total_chars:,}")
    secho(f"  Manifest: {manifest_path}")
    return True


# ── Phase 2: Embed ──

def phase_embed(force=False, incremental=False):
    header("PHASE 2: Text -> Chunks -> Embeddings -> Store")

    store_path = PROJECT_ROOT / "data" / "vector_store"
    store = VectorStore(str(store_path))
    state_file = store_path / "embedded.json"

    # Force rebuild
    if force and store.count() > 0:
        secho(f"  [CLEAR] Removing {store.count()} chunks...")
        store.clear()
        if state_file.exists():
            state_file.unlink()

    # Load processed text files
    txt_dir = PROJECT_ROOT / "data" / "knowledge_base" / "processed"
    txt_files = sorted(txt_dir.glob("*.txt"))

    if not txt_files:
        secho(f"  [ERROR] No processed text files in {txt_dir}")
        return False

    # Incremental: check which files already embedded
    embedded_state = {}
    if state_file.exists():
        embedded_state = json.loads(state_file.read_text(encoding="utf-8"))

    to_process = []
    skipped = 0
    for tf in txt_files:
        key = tf.name
        mtime = tf.stat().st_mtime
        if incremental and key in embedded_state:
            prev_mtime = embedded_state[key].get("mtime", 0)
            if mtime <= prev_mtime:
                skipped += 1
                continue
        to_process.append(tf)

    if incremental and skipped > 0:
        secho(f"  Incremental: {skipped} unchanged files skipped, {len(to_process)} to process")
    else:
        secho(f"  Text files: {len(txt_files)} (processing all)")

    if incremental and not to_process:
        secho(f"  [OK] All files up to date. Nothing to do.")
        return True

    # ── Chunk ──
    secho(f"\n  --- Chunking ---")
    chunker = TextChunker(chunk_size=800, chunk_overlap=120)
    all_chunks = []

    for i, tf in enumerate(to_process or txt_files, 1):
        meta_path = tf.with_suffix(".json")
        meta = {}
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))

        text = tf.read_text(encoding="utf-8")
        doc = {"text": text, "filename": meta.get("filename", tf.name),
               "title": meta.get("title", tf.stem)}

        secho(f"  {bar(i, len(to_process or txt_files))} [{i}/{len(to_process or txt_files)}] {tf.name} ({len(text):,} chars)",
              end="")

        chunks = chunker.chunk_document(doc)
        all_chunks.extend(chunks)
        ata = sum(1 for c in chunks if c["metadata"].get("ata_chapter"))
        secho(f" -> {len(chunks)} chunks (ATA: {ata})")

    secho(f"\n  Total chunks to add: {len(all_chunks)}")
    if not all_chunks:
        secho("  [OK] No new chunks to embed.")
        return True

    # ── Embed ──
    secho(f"\n  --- Embedding ---")
    secho(f"  Loading model (first run downloads ~80MB)...")

    embedder = Embedder()
    secho(f"  Model: {embedder.model_name}  |  Dims: {embedder.dimension}")

    texts = [c["text"] for c in all_chunks]
    batch_size = 64
    embeddings = []
    total = len(texts)
    t0 = time.time()

    for start in range(0, total, batch_size):
        end = min(start + batch_size, total)
        batch = texts[start:end]
        elapsed = time.time() - t0
        rate = (start + len(batch)) / max(elapsed, 0.1)
        secho(f"  {bar(end, total)} {end}/{total} | {fmt_time(elapsed)} | {rate:.0f} ch/s",
              end="", flush=True)

        emb = embedder.embed_documents(batch)
        embeddings.extend(emb)
        secho("")

    embed_time = time.time() - t0
    secho(f"\n  Done: {total} chunks in {fmt_time(embed_time)} ({total / embed_time:.0f} ch/s)")

    # ── Store ──
    secho(f"\n  --- Storing ---")
    t0 = time.time()
    added = store.add_chunks(all_chunks, embeddings)
    secho(f"  Stored {added} chunks in {fmt_time(time.time() - t0)}")
    secho(f"  Path: {store_path}")

    # Save incremental state
    for tf in (to_process if incremental else txt_files):
        embedded_state[tf.name] = {
            "mtime": tf.stat().st_mtime,
            "size": tf.stat().st_size,
            "embedded_at": time.time(),
        }
    state_file.write_text(json.dumps(embedded_state, indent=2), encoding="utf-8")

    return True


# ── Main ──

def main():
    parser = argparse.ArgumentParser(description="Build aviation knowledge base")
    parser.add_argument("command", nargs="?", default="build",
                        choices=["extract", "embed", "build"],
                        help="extract: PDF->text | embed: text->vectordb | build: both")
    parser.add_argument("--force", action="store_true",
                        help="Force rebuild (clear existing vector data)")
    parser.add_argument("--incremental", action="store_true",
                        help="Only embed new or changed text files")
    args = parser.parse_args()

    t_total = time.time()

    print("=" * 60)
    print("  TaskSense — Knowledge Base Builder")
    print("=" * 60)

    ok = True
    if args.command in ("extract", "build"):
        ok = phase_extract() and ok

    if args.command in ("embed", "build"):
        ok = phase_embed(force=args.force, incremental=args.incremental) and ok

    if ok:
        print(f"\n{'=' * 60}")
        print(f"  ALL DONE — {fmt_time(time.time() - t_total)}")
        print(f"{'=' * 60}\n")
    else:
        print(f"\n  [FAILED] See errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
