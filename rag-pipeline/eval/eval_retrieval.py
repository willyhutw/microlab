#!/usr/bin/env python3
# /// script
# dependencies = ["qdrant-client", "requests"]
# ///
"""
RAG Retrieval Evaluation — measures Hit@K and MRR against dataset.json

Usage:
  python eval_retrieval.py                        # hybrid + score filter (default)
  python eval_retrieval.py --mode dense           # dense only
  python eval_retrieval.py --mode hybrid          # hybrid, no score filter
  python eval_retrieval.py --mode hybrid-filtered # hybrid + 0.5 score filter (default)
  python eval_retrieval.py --top-k 3              # override top-k
  python eval_retrieval.py --category work        # filter by category
  python eval_retrieval.py --verbose              # show all results per query
"""

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

import requests
from qdrant_client import QdrantClient
from qdrant_client.models import Fusion, FusionQuery, Prefetch, SparseVector

COLLECTION  = "obsidian-wiki"
SPARSE_DIM  = 2**18
OLLAMA_URL  = os.getenv("OLLAMA_URL", "http://localhost:11434")
QDRANT_URL  = os.getenv("QDRANT_URL", "http://localhost:6333")
EMBED_MODEL = "qwen3-embedding:0.6b"
DATASET     = Path(__file__).parent / "dataset.json"


def tokenize(text: str) -> list[str]:
    return re.findall(r'[一-鿿]|[a-zA-Z0-9]+', text.lower())

def query_sparse(text: str) -> SparseVector:
    acc: dict[int, float] = {}
    for term in set(tokenize(text)):
        idx = int(hashlib.md5(term.encode()).hexdigest()[:8], 16) % SPARSE_DIM
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


def retrieve(client: QdrantClient, query: str, mode: str, top_k: int, score_threshold: float) -> list:
    if mode == "dense":
        results = client.query_points(
            COLLECTION,
            query=embed(query),
            using="dense",
            limit=top_k,
            with_payload=True,
        ).points
    else:
        results = client.query_points(
            COLLECTION,
            prefetch=[
                Prefetch(query=embed(query), using="dense", limit=20),
                Prefetch(query=query_sparse(query), using="sparse", limit=20),
            ],
            query=FusionQuery(fusion=Fusion.RRF),
            limit=top_k,
            with_payload=True,
        ).points

    if score_threshold > 0 and results:
        max_score = results[0].score
        results = [r for r in results if r.score >= max_score * score_threshold]

    return results


def find_rank(results: list, expected_doc: str, expected_section: str) -> int:
    """Return 1-based rank of expected chunk, or 0 if not found."""
    for i, r in enumerate(results, 1):
        if r.payload["doc_title"] == expected_doc and r.payload["title"] == expected_section:
            return i
    return 0


def run_eval(args):
    with open(DATASET) as f:
        dataset = json.load(f)

    if args.category:
        dataset = [d for d in dataset if d.get("category") == args.category]
        if not dataset:
            print(f"No items found for category '{args.category}'")
            sys.exit(1)

    score_threshold = 0.5 if args.mode == "hybrid-filtered" else 0.0
    retrieval_mode  = "hybrid" if args.mode in ("hybrid", "hybrid-filtered") else "dense"

    print(f"\n{'═'*65}")
    print(f"  RAG Retrieval Evaluation")
    print(f"  mode={args.mode}  top_k={args.top_k}  score_threshold={score_threshold}")
    if args.category:
        print(f"  category={args.category}")
    print(f"{'═'*65}\n")

    client = QdrantClient(url=QDRANT_URL, timeout=30, prefer_grpc=False)

    ranks   = []
    hits    = []
    details = []

    for item in dataset:
        results = retrieve(client, item["query"], retrieval_mode, args.top_k, score_threshold)
        rank    = find_rank(results, item["expected_doc"], item["expected_section"])
        hit     = rank > 0

        ranks.append(rank)
        hits.append(hit)

        detail = {
            "id":       item["id"],
            "query":    item["query"],
            "expected": f"{item['expected_doc']} › {item['expected_section']}",
            "hit":      hit,
            "rank":     rank,
            "retrieved": [
                f"[{r.score:.4f}] {r.payload['doc_title']} › {r.payload['title']}"
                for r in results
            ],
        }
        details.append(detail)

        status = f"✓ rank {rank}" if hit else "✗ miss"
        print(f"  [{item['id']:02d}] {status:<10}  {item['query'][:50]}")
        if args.verbose or not hit:
            print(f"         expected: {detail['expected']}")
            for r in detail["retrieved"]:
                marker = " ←" if (item["expected_doc"] in r and item["expected_section"] in r) else ""
                print(f"           {r}{marker}")
            print()

    # Metrics
    n         = len(dataset)
    hit_rate  = sum(hits) / n
    mrr       = sum(1/r for r in ranks if r > 0) / n
    retrieved_counts = [len(retrieve(client, item["query"], retrieval_mode, args.top_k, score_threshold))
                        for item in dataset]
    avg_chunks = sum(retrieved_counts) / n

    print(f"\n{'─'*65}")
    print(f"  Results ({n} queries)")
    print(f"{'─'*65}")
    print(f"  Hit@{args.top_k}:      {hit_rate:.1%}  ({sum(hits)}/{n})")
    print(f"  MRR:         {mrr:.3f}")
    print(f"  Avg chunks:  {avg_chunks:.1f}  (after filter)")
    print(f"{'─'*65}")

    misses = [d for d in details if not d["hit"]]
    if misses:
        print(f"\n  Missed ({len(misses)}):")
        for m in misses:
            print(f"    [{m['id']:02d}] {m['query']}")
            print(f"         expected: {m['expected']}")

    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["dense", "hybrid", "hybrid-filtered"],
                        default="hybrid-filtered")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--category", choices=["career", "personal", "learning", "homelab", "work"])
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    run_eval(args)
