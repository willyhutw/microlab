#!/usr/bin/env python3
# /// script
# dependencies = ["qdrant-client", "requests"]
# ///

import hashlib
import os
import re
import sys

import requests
from qdrant_client import QdrantClient
from qdrant_client.models import Fusion, FusionQuery, Prefetch, SparseVector

COLLECTION  = "obsidian-wiki"
SPARSE_DIM  = 2**18
OLLAMA_URL  = os.getenv("OLLAMA_URL", "http://localhost:11434")
QDRANT_URL  = os.getenv("QDRANT_URL", "http://localhost:6333")
EMBED_MODEL = "qwen3-embedding:0.6b"
LLM_MODEL   = os.getenv("LLM_MODEL", "gemma3:4b")
TOP_K       = 5


def tokenize(text: str) -> list[str]:
    return re.findall(r'[一-鿿]|[a-zA-Z0-9]+', text.lower())

def term_hash(term: str) -> int:
    return int(hashlib.md5(term.encode()).hexdigest()[:8], 16) % SPARSE_DIM

def query_sparse(text: str) -> SparseVector:
    acc: dict[int, float] = {}
    for term in set(tokenize(text)):
        idx = term_hash(term)
        acc[idx] = acc.get(idx, 0.0) + 1.0
    pairs = sorted(acc.items())
    return SparseVector(indices=[i for i, _ in pairs], values=[v for _, v in pairs])

def embed(text: str) -> list[float]:
    resp = requests.post(
        f"{OLLAMA_URL}/api/embed",
        json={"model": EMBED_MODEL, "input": text},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["embeddings"][0]

def search(question: str) -> list:
    client = QdrantClient(url=QDRANT_URL, timeout=30, prefer_grpc=False)
    return client.query_points(
        COLLECTION,
        prefetch=[
            Prefetch(query=embed(question), using="dense", limit=20),
            Prefetch(query=query_sparse(question), using="sparse", limit=20),
        ],
        query=FusionQuery(fusion=Fusion.RRF),
        limit=TOP_K,
        with_payload=True,
    ).points

def ask(question: str):
    print(f"\n{'─'*60}")
    print(f"  Query: {question}")
    print(f"{'─'*60}\n")

    results = search(question)

    print("  Retrieved chunks:")
    context_parts = []
    for r in results:
        print(f"    [{r.score:.4f}] {r.payload['doc_title']} › {r.payload['title']}")
        context_parts.append(
            f"[來源: {r.payload['doc_title']} › {r.payload['title']}]\n{r.payload['content']}"
        )

    context = "\n\n---\n\n".join(context_parts)
    prompt = f"""你是一個知識庫助手。根據以下內容回答問題，並標注資訊來源。若內容不足以回答，請直接說明。

=== 知識庫內容 ===
{context}

=== 問題 ===
{question}"""

    print("\n  Generating answer...\n")
    resp = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={"model": LLM_MODEL, "prompt": prompt, "stream": False},
        timeout=120,
    )
    resp.raise_for_status()
    print(resp.json()["response"])
    print()


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "我的 AI 工程師轉職計畫分哪幾個 Phase？目前進度到哪裡？"
    ask(question)
