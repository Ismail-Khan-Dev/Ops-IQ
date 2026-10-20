"""
Semantic LLM Response Cache
Redis-backed cache that reuses previous LLM responses for identical or
semantically similar prompts, cutting token spend and latency.

Design:
- Exact-match fast path: SHA-256 of the normalized prompt.
- Semantic path: embed the prompt and return the highest-similarity cached
  response when cosine similarity >= threshold.
- Graceful degradation: if Redis or the embedding provider is unavailable,
  get() returns None and set() is a no-op, so callers fall through to the LLM.
"""

import hashlib
import logging
from typing import Any, Dict, List, Optional

import numpy as np

from ecommerce_ops.api.metrics import METRIC_LLM_CACHE_HITS, METRIC_LLM_CACHE_MISSES
from ecommerce_ops.memory.cache import cache
from ecommerce_ops.memory.vector.embeddings import embedding_service

logger = logging.getLogger("ecommerce_ops.memory.llm_cache")


LLM_CACHE_TTL = 86400  # 24h
LLM_CACHE_MAX_ENTRIES = 200
LLM_SEMANTIC_THRESHOLD = 0.92

_KEY_PREFIX = "llm_semantic"
_INDEX_KEY = f"{_KEY_PREFIX}:index"


def _prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def _entry_key(namespace: str, prompt_hash: str) -> str:
    return f"{_KEY_PREFIX}:{namespace}:{prompt_hash}"


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Cosine similarity between two vectors. Returns 0.0 on degenerate input."""
    if not a or not b or len(a) != len(b):
        return 0.0
    va = np.asarray(a, dtype=np.float64)
    vb = np.asarray(b, dtype=np.float64)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    if denom == 0:
        return 0.0
    return float(np.dot(va, vb) / denom)


class SemanticLLMCache:
    """Bounded Redis semantic cache for LLM responses."""

    def __init__(
        self,
        backend: Any = None,
        embedder: Any = None,
        threshold: float = LLM_SEMANTIC_THRESHOLD,
        max_entries: int = LLM_CACHE_MAX_ENTRIES,
        ttl: int = LLM_CACHE_TTL,
    ):
        self.backend = backend or cache
        self.embedder = embedder or embedding_service
        self.threshold = threshold
        self.max_entries = max_entries
        self.ttl = ttl

    def _track(self, hit: bool) -> None:
        try:
            if hit:
                METRIC_LLM_CACHE_HITS.inc()
            else:
                METRIC_LLM_CACHE_MISSES.inc()
        except Exception:
            pass

    async def get(self, prompt: str, namespace: str = "default") -> Optional[Dict[str, Any]]:
        """Return a cached response for the prompt, or None on miss/error."""
        prompt = self._normalize(prompt)
        key = _entry_key(namespace, _prompt_hash(prompt))

        # 1. Exact match fast path
        try:
            exact = await self.backend.get(key)
            if exact is not None:
                self._track(True)
                return exact.get("response")
        except Exception as e:
            logger.warning("LLM cache exact lookup failed: %s", e)

        # 2. Semantic similarity scan over bounded recent entries
        try:
            query_embedding = await self.embedder.embed(prompt)
        except Exception as e:
            logger.debug("Embedding unavailable for semantic cache: %s", e)
            self._track(False)
            return None

        best = None
        best_score = self.threshold
        try:
            index: List[str] = await self.backend.get(_INDEX_KEY) or []
            for entry_hash in index[-self.max_entries :]:
                entry = await self.backend.get(f"{_KEY_PREFIX}:{namespace}:{entry_hash}")
                if not entry:
                    continue
                score = cosine_similarity(query_embedding, entry.get("embedding") or [])
                if score >= best_score:
                    best = entry.get("response")
                    best_score = score
        except Exception as e:
            logger.warning("LLM cache semantic lookup failed: %s", e)
            self._track(False)
            return None

        if best is not None:
            self._track(True)
            logger.info("LLM semantic cache hit (sim=%.3f) namespace=%s", best_score, namespace)
        else:
            self._track(False)
        return best

    async def set(
        self,
        prompt: str,
        response: Dict[str, Any],
        namespace: str = "default",
        ttl: Optional[int] = None,
    ) -> None:
        """Store a response keyed by exact prompt and (bounded) semantic index."""
        prompt = self._normalize(prompt)
        ttl = ttl or self.ttl
        try:
            embedding = await self.embedder.embed(prompt)
        except Exception as e:
            logger.debug("Embedding unavailable, skipping LLM cache write: %s", e)
            return

        entry_hash = _prompt_hash(prompt)
        entry = {
            "prompt": prompt,
            "embedding": embedding,
            "response": response,
        }

        try:
            # 1. Exact entry
            await self.backend.set(_entry_key(namespace, entry_hash), entry, ttl=ttl)

            # 2. Maintain bounded index
            index: List[str] = await self.backend.get(_INDEX_KEY) or []
            if entry_hash not in index:
                index.append(entry_hash)
            index = index[-self.max_entries :]
            await self.backend.set(_INDEX_KEY, index, ttl=ttl)
        except Exception as e:
            logger.warning("LLM cache write failed: %s", e)

    @staticmethod
    def _normalize(prompt: str) -> str:
        """Normalize whitespace so formatting differences don't bust the cache."""
        return " ".join(str(prompt).split())


llm_response_cache = SemanticLLMCache()
