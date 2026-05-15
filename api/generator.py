"""
LLM generator — calls OpenRouter (OpenAI-compatible API) with retrieved context.
"""

import logging
import os
import time
from openai import OpenAI

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a DevOps documentation assistant. Answer questions using ONLY the provided context.
If the context doesn't contain enough information, say "I don't have enough documentation to answer that."
Always cite the source URLs when you use information from them.
Be concise and technical — this is for engineers."""


class Generator:
    """Calls OpenRouter LLM with retrieved context."""

    def __init__(
        self,
        model: str = "openai/gpt-4o-mini",
        api_key: str | None = None,
        base_url: str = "https://openrouter.ai/api/v1",
    ):
        self.model = model
        api_key = api_key or os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY") or "sk-placeholder"
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        logger.info(f"Generator initialized: model={model}")

    def generate(self, question: str, chunks: list[dict]) -> dict:
        """
        Generate an answer from retrieved chunks.
        Returns {"answer": str, "tokens_used": int, "model": str}
        """
        if not chunks:
            return {
                "answer": "I don't have enough documentation to answer that question.",
                "tokens_used": 0,
                "model": self.model,
            }

        # Build context from chunks
        context_parts = []
        for i, chunk in enumerate(chunks):
            source_line = f"[{i+1}] {chunk.get('title', 'Unknown')} — {chunk.get('url', '')}"
            context_parts.append(f"{source_line}\n{chunk['text']}")

        context = "\n\n---\n\n".join(context_parts)

        user_message = f"""Context from documentation:

{context}

Question: {question}

Answer (cite sources with [N] notation):"""

        start = time.monotonic()
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.3,
                max_tokens=1024,
            )
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return {
                "answer": f"Error calling LLM: {e}",
                "tokens_used": 0,
                "model": self.model,
            }

        elapsed = time.monotonic() - start
        choice = response.choices[0]
        usage = response.usage

        tokens = usage.total_tokens if usage else 0
        logger.info(f"LLM response: {tokens} tokens in {elapsed:.2f}s")

        return {
            "answer": choice.message.content or "",
            "tokens_used": tokens,
            "model": response.model or self.model,
            "llm_latency_s": elapsed,
        }
