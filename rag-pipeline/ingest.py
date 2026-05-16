#!/usr/bin/env python3
# /// script
# dependencies = ["qdrant-client", "requests"]
# ///

import hashlib
import os
import re
from pathlib import Path

import requests
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

WIKI_DIR    = Path.home() / "sync-obsidian/wiki"
EXCLUDE     = {"hot.md", "index.md", "log.md", "overview.md"}
SKIP_DIRS   = {"meta"}
COLLECTION  = "obsidian-wiki"
VECTOR_DIM  = 768
OLLAMA_URL  = os.getenv("OLLAMA_URL", "http://localhost:11434")
QDRANT_URL  = os.getenv("QDRANT_URL", "http://localhost:6333")
EMBED_MODEL = "nomic-embed-text"


# ── Processing ─────────────────────────────────────────────────────────────────

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


# ── Embedding & Qdrant ─────────────────────────────────────────────────────────

def embed(text: str) -> list[float]:
    # mxbai-embed-large max context is 512 tokens (~1800 chars); truncate to be safe
    resp = requests.post(
        f"{OLLAMA_URL}/api/embed",
        json={"model": EMBED_MODEL, "input": text[:1800]},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["embeddings"][0]

def make_id(source: str, title: str) -> int:
    key = f"{source}::{title}"
    return int(hashlib.md5(key.encode()).hexdigest()[:8], 16)

def setup_collection(client: QdrantClient):
    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION not in existing:
        client.create_collection(
            COLLECTION,
            vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
        )
        print(f"  ✓ Created collection: {COLLECTION}")
    else:
        print(f"  ✓ Collection ready:   {COLLECTION}")

def upsert_chunks(client: QdrantClient, chunks: list[dict]):
    points = []
    for c in chunks:
        vec = embed(c["text"])
        points.append(PointStruct(
            id      = make_id(c["source"], c["title"]),
            vector  = vec,
            payload = {
                "source":    c["source"],
                "doc_title": c["doc_title"],
                "title":     c["title"],
                "content":   c["content"],
            },
        ))
    client.upsert(collection_name=COLLECTION, points=points)


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'═'*60}")
    print("  Obsidian Wiki — RAG Ingestion Pipeline")
    print(f"{'═'*60}\n")

    client = QdrantClient(url=QDRANT_URL)
    setup_collection(client)

    files = find_files()
    print(f"  Found {len(files)} wiki files\n")

    total = 0
    for i, f in enumerate(files, 1):
        chunks = process_file(f)
        if not chunks:
            continue
        rel = f.relative_to(Path.home() / "sync-obsidian")
        print(f"  [{i:2}/{len(files)}] {str(rel):<55} {len(chunks)} chunks")
        upsert_chunks(client, chunks)
        total += len(chunks)

    info = client.get_collection(COLLECTION)
    print(f"\n{'═'*60}")
    print(f"  Done! {total} chunks → Qdrant ({info.points_count} vectors stored)")
    print(f"{'═'*60}\n")


if __name__ == "__main__":
    main()
