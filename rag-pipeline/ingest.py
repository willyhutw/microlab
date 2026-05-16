#!/usr/bin/env python3
# /// script
# dependencies = ["qdrant-client", "requests", "rank-bm25"]
# ///

import hashlib
import os
import re
from pathlib import Path

import requests
from rank_bm25 import BM25Okapi
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, PointStruct, SparseVector, SparseVectorParams, VectorParams,
)

WIKI_DIR    = Path.home() / "sync-obsidian/wiki"
EXCLUDE     = {"hot.md", "index.md", "log.md", "overview.md"}
SKIP_DIRS   = {"meta"}
COLLECTION  = "obsidian-wiki"
VECTOR_DIM  = 1024
SPARSE_DIM  = 2**18        # 262144 buckets, collision rate negligible for small corpora
OLLAMA_URL  = os.getenv("OLLAMA_URL", "http://localhost:11434")
QDRANT_URL  = os.getenv("QDRANT_URL", "http://localhost:6333")
EMBED_MODEL = "qwen3-embedding:0.6b"


# ── Text processing ────────────────────────────────────────────────────────────

def find_files() -> list[Path]:
    return sorted(
        f for f in WIKI_DIR.rglob("*.md")
        if f.name not in EXCLUDE
        and not any(p in SKIP_DIRS for p in f.parts)
    )

def strip_frontmatter(text: str) -> str:
    return re.sub(r"^---\n.*?\n---\n", "", text, flags=re.DOTALL)

def clean_wikilinks(text: str) -> str:
    return re.sub(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", r"\1", text)

def chunk_by_headers(text: str, source: str) -> list[dict]:
    title_m = re.search(r"^# (.+)$", text, re.MULTILINE)
    doc_title = title_m.group(1).strip() if title_m else source
    has_sections = bool(re.search(r"\n## ", text))

    chunks = []
    for section in re.split(r"\n(?=## )", text):
        section = section.strip()
        if not section:
            continue
        lines  = section.split("\n")
        header = lines[0].lstrip("#").strip()
        body   = "\n".join(lines[1:]).strip()
        if len(body) < 30:
            continue
        # Skip the pre-section preamble (header == doc_title) when ## sections exist.
        # This chunk scores artificially high in RRF because it semantically covers
        # the whole document, overshadowing more specific section chunks.
        if has_sections and header == doc_title:
            continue
        chunks.append({
            "source":    source,
            "doc_title": doc_title,
            "title":     header,
            "content":   body,
            "text":      f"{doc_title} > {header}\n{body}",
        })

    if not chunks and len(text.strip()) > 30:
        chunks.append({
            "source":    source,
            "doc_title": doc_title,
            "title":     doc_title,
            "content":   text.strip(),
            "text":      f"{doc_title}\n{text.strip()}",
        })
    return chunks

def process_file(path: Path) -> list[dict]:
    text = path.read_text()
    text = strip_frontmatter(text)
    text = clean_wikilinks(text)
    source = str(path.relative_to(Path.home() / "sync-obsidian"))
    return chunk_by_headers(text, source)


# ── Sparse (BM25) ──────────────────────────────────────────────────────────────

def tokenize(text: str) -> list[str]:
    # char-level Chinese + word-level English/numbers
    return re.findall(r'[一-鿿]|[a-zA-Z0-9]+', text.lower())

def term_hash(term: str) -> int:
    return int(hashlib.md5(term.encode()).hexdigest()[:8], 16) % SPARSE_DIM

def make_doc_sparse(bm25: BM25Okapi, doc_idx: int) -> SparseVector:
    tf_dict = bm25.doc_freqs[doc_idx]
    dl, avgdl = bm25.doc_len[doc_idx], bm25.avgdl
    k1, b = bm25.k1, bm25.b
    acc: dict[int, float] = {}
    for term, tf in tf_dict.items():
        idf = bm25.idf.get(term, 0.0)
        tf_norm = tf * (k1 + 1) / (tf + k1 * (1 - b + b * dl / avgdl))
        weight = idf * tf_norm
        if weight > 0:
            idx = term_hash(term)
            acc[idx] = acc.get(idx, 0.0) + weight
    pairs = sorted(acc.items())
    return SparseVector(indices=[i for i, _ in pairs], values=[v for _, v in pairs])


# ── Dense embedding & Qdrant ──────────────────────────────────────────────────

def embed(text: str) -> list[float]:
    resp = requests.post(
        f"{OLLAMA_URL}/api/embed",
        json={"model": EMBED_MODEL, "input": text},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["embeddings"][0]

def make_id(source: str, title: str) -> int:
    key = f"{source}::{title}"
    return int(hashlib.md5(key.encode()).hexdigest()[:8], 16)

def setup_collection(client: QdrantClient):
    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION in existing:
        client.delete_collection(COLLECTION)
        print(f"  ↺ Dropped collection: {COLLECTION}")
    client.create_collection(
        COLLECTION,
        vectors_config={"dense": VectorParams(size=VECTOR_DIM, distance=Distance.COSINE)},
        sparse_vectors_config={"sparse": SparseVectorParams()},
    )
    print(f"  ✓ Created collection: {COLLECTION}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'═'*60}")
    print("  Obsidian Wiki — RAG Ingestion Pipeline (Hybrid)")
    print(f"{'═'*60}\n")

    client = QdrantClient(url=QDRANT_URL, timeout=30, prefer_grpc=False)
    setup_collection(client)

    # Pass 1: collect all chunks + fit BM25
    print("  Pass 1: collecting chunks & fitting BM25...")
    all_chunks = []
    for f in find_files():
        all_chunks.extend(process_file(f))
    corpus_tokens = [tokenize(c["text"]) for c in all_chunks]
    bm25 = BM25Okapi(corpus_tokens)
    print(f"  BM25 fitted on {len(all_chunks)} chunks, vocab={len(bm25.idf)} terms\n")

    # Pass 2: embed (dense) + sparse + upsert, grouped by source file for display
    print("  Pass 2: embedding & upserting...")
    from itertools import groupby
    total = 0
    chunk_idx = 0
    for source, group in groupby(all_chunks, key=lambda c: c["source"]):
        group = list(group)
        points = []
        for c in group:
            dense_vec  = embed(c["text"])
            sparse_vec = make_doc_sparse(bm25, chunk_idx)
            points.append(PointStruct(
                id     = make_id(c["source"], c["title"]),
                vector = {"dense": dense_vec, "sparse": sparse_vec},
                payload = {
                    "source":    c["source"],
                    "doc_title": c["doc_title"],
                    "title":     c["title"],
                    "content":   c["content"],
                },
            ))
            chunk_idx += 1
        client.upsert(collection_name=COLLECTION, points=points)
        print(f"  {source:<60} {len(group)} chunks")
        total += len(group)

    info = client.get_collection(COLLECTION)
    print(f"\n{'═'*60}")
    print(f"  Done! {total} chunks → Qdrant ({info.points_count} vectors stored)")
    print(f"{'═'*60}\n")


if __name__ == "__main__":
    main()
