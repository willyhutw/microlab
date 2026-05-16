"""
title: Obsidian Wiki RAG
author: willyhu
description: RAG pipeline for personal Obsidian wiki (obsidian-wiki collection in Qdrant)
requirements: qdrant-client, requests, langfuse
"""

import json
import os
from typing import Generator, Iterator, List, Union

import requests
from langfuse import Langfuse
from qdrant_client import QdrantClient


class Pipeline:
    def __init__(self):
        self.name = "Obsidian Wiki RAG"
        self.qdrant: QdrantClient = None
        self.ollama_url = os.getenv("OLLAMA_URL", "http://ollama.ai.svc.cluster.local:11434")
        self.qdrant_url = os.getenv("QDRANT_URL", "http://qdrant.ai.svc.cluster.local:6333")
        self.embed_model = "qwen3-embedding:0.6b"
        self.llm_model = os.getenv("LLM_MODEL", "gemma3:4b")
        self.collection = "obsidian-wiki"
        self.top_k = 5
        self.langfuse = Langfuse(
            public_key=os.getenv("LANGFUSE_PUBLIC_KEY", ""),
            secret_key=os.getenv("LANGFUSE_SECRET_KEY", ""),
            host=os.getenv("LANGFUSE_HOST", "http://langfuse-web.ai.svc.cluster.local:3000"),
        )

    async def on_startup(self):
        self.qdrant = QdrantClient(url=self.qdrant_url)

    async def on_shutdown(self):
        self.langfuse.flush()

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

        trace = self.langfuse.trace(
            name="rag-query",
            input=user_message,
            metadata={"collection": self.collection, "top_k": self.top_k},
        )

        # Embed + Retrieve
        retrieve_span = trace.span(name="retrieve", input=user_message)
        results = self._retrieve(user_message)
        retrieve_span.end(
            output=[
                {
                    "doc": r.payload["doc_title"],
                    "section": r.payload["title"],
                    "score": round(r.score, 4),
                }
                for r in results
            ]
        )

        if not results:
            trace.update(output="no results found")
            self.langfuse.flush()
            yield "（知識庫中找不到相關內容，請確認 obsidian-wiki collection 是否有資料）"
            return

        # Show retrieved sources
        sources = "\n".join(
            f"- **{r.payload['doc_title']} › {r.payload['title']}** `{r.score:.3f}`"
            for r in results
        )
        yield f"**Retrieved chunks:**\n{sources}\n\n---\n\n"

        # Build context + prompt
        context = "\n\n---\n\n".join(
            f"[{r.payload['doc_title']} › {r.payload['title']}]\n{r.payload['content']}"
            for r in results
        )
        prompt = f"""你是一個知識庫助手。根據以下知識庫內容回答問題，並標注資訊來源。若內容不足以回答，請直接說明。

=== 知識庫內容 ===
{context}

=== 問題 ===
{user_message}"""

        # Stream response from Ollama, tracked as a Langfuse generation
        generation = trace.generation(
            name="generate",
            model=self.llm_model,
            input=prompt,
        )

        resp = requests.post(
            f"{self.ollama_url}/api/generate",
            json={"model": self.llm_model, "prompt": prompt, "stream": True},
            stream=True,
            timeout=120,
        )
        resp.raise_for_status()

        output_tokens = []
        for line in resp.iter_lines():
            if line:
                data = json.loads(line)
                if token := data.get("response"):
                    output_tokens.append(token)
                    yield token
                if data.get("done"):
                    full_output = "".join(output_tokens)
                    generation.end(output=full_output)
                    trace.update(output=full_output)
                    self.langfuse.flush()
                    break
