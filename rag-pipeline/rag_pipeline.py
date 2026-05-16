"""
title: Obsidian Wiki RAG
author: willyhu
description: RAG pipeline for personal Obsidian wiki (obsidian-wiki collection in Qdrant)
requirements: qdrant-client, requests
"""

import json
import os
from typing import Generator, Iterator, List, Union

import requests
from qdrant_client import QdrantClient


class Pipeline:
    def __init__(self):
        self.name = "Obsidian Wiki RAG"
        self.qdrant: QdrantClient = None
        self.ollama_url = os.getenv("OLLAMA_URL", "http://ollama.ai.svc.cluster.local:11434")
        self.qdrant_url = os.getenv("QDRANT_URL", "http://qdrant.ai.svc.cluster.local:6333")
        self.embed_model = "nomic-embed-text"
        self.llm_model = os.getenv("LLM_MODEL", "gemma3:4b")
        self.collection = "obsidian-wiki"
        self.top_k = 3

    async def on_startup(self):
        self.qdrant = QdrantClient(url=self.qdrant_url)

    async def on_shutdown(self):
        pass

    def _embed(self, text: str) -> list[float]:
        resp = requests.post(
            f"{self.ollama_url}/api/embed",
            json={"model": self.embed_model, "input": text},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["embeddings"][0]

    def _retrieve(self, query: str) -> list:
        vec = self._embed(query)
        return self.qdrant.query_points(
            self.collection,
            query=vec,
            limit=self.top_k,
            with_payload=True,
        ).points

    def pipe(
        self,
        user_message: str,
        model_id: str,
        messages: List[dict],
        body: dict,
    ) -> Union[str, Generator, Iterator]:

        results = self._retrieve(user_message)

        if not results:
            yield "（知識庫中找不到相關內容，請確認 obsidian-wiki collection 是否有資料）"
            return

        # Show retrieved sources
        sources = "\n".join(
            f"- **{r.payload['doc_title']} › {r.payload['title']}** `{r.score:.3f}`"
            for r in results
        )
        yield f"**Retrieved chunks:**\n{sources}\n\n---\n\n"

        # Build context
        context = "\n\n---\n\n".join(
            f"[{r.payload['doc_title']} › {r.payload['title']}]\n{r.payload['content']}"
            for r in results
        )

        prompt = f"""你是一個知識庫助手。根據以下知識庫內容回答問題，並標注資訊來源。若內容不足以回答，請直接說明。

=== 知識庫內容 ===
{context}

=== 問題 ===
{user_message}"""

        # Stream response from Ollama
        resp = requests.post(
            f"{self.ollama_url}/api/generate",
            json={"model": self.llm_model, "prompt": prompt, "stream": True},
            stream=True,
            timeout=120,
        )
        resp.raise_for_status()

        for line in resp.iter_lines():
            if line:
                data = json.loads(line)
                if token := data.get("response"):
                    yield token
                if data.get("done"):
                    break
