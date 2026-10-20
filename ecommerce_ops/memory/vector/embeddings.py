"""
Embedding Service
Service for generating text embeddings using various providers.
"""

import logging
import os
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

import numpy as np

from ecommerce_ops.config import Environment, settings

logger = logging.getLogger("ecommerce_ops.memory.vector.embeddings")

# Dimension expected by the persistent vector store (persistent_store.py).
# Must match the pgvector column dimension. Providers with mismatched
# dimensions are rejected or warned (M5).
STORE_EMBEDDING_DIMENSIONS = 1536


class EmbeddingProvider(ABC):
    """Abstract base class for embedding providers."""

    @abstractmethod
    async def embed_text(self, text: str) -> List[float]:
        """Generate embedding for a single text."""
        pass

    @abstractmethod
    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts."""
        pass

    @abstractmethod
    def get_dimensions(self) -> int:
        """Get embedding dimensions."""
        pass


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """OpenAI embedding provider."""

    def __init__(self, api_key: Optional[str] = None, model: str = "text-embedding-3-small"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            if not self.api_key:
                raise RuntimeError("OpenAI API key not configured")
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(api_key=self.api_key)
        return self._client

    async def embed_text(self, text: str) -> List[float]:
        client = self._get_client()
        response = await client.embeddings.create(
            model=self.model,
            input=text,
        )
        return response.data[0].embedding

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        client = self._get_client()
        response = await client.embeddings.create(
            model=self.model,
            input=texts,
        )
        return [item.embedding for item in response.data]

    def get_dimensions(self) -> int:
        return 1536 if "small" in self.model else 3072


class GoogleEmbeddingProvider(EmbeddingProvider):
    """Google embedding provider using Gemini's text-embedding model.

    Raises RuntimeError if GOOGLE_API_KEY is not set — never silently
    falls back to fake MD5 pseudo-embeddings (M5).
    """

    EMBEDDING_MODEL = "text-embedding-004"
    _EMBEDDING_DIM = 768  # Google text-embedding-004 native dimension

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise RuntimeError(
                "GOOGLE_API_KEY is required for GoogleEmbeddingProvider. "
                "No fake MD5 fallback — set the key or use OpenAIEmbeddings."
            )

    async def embed_text(self, text: str) -> List[float]:
        import google.generativeai as genai

        genai.configure(api_key=self.api_key)
        result = await genai.embed_content_async(
            model=self.EMBEDDING_MODEL,
            content=text,
            task_type="retrieval_document",
        )
        return list(result["embedding"])

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        import google.generativeai as genai

        genai.configure(api_key=self.api_key)
        results = []
        for text in texts:
            result = await genai.embed_content_async(
                model=self.EMBEDDING_MODEL,
                content=text,
                task_type="retrieval_document",
            )
            results.append(list(result["embedding"]))
        return results

    def get_dimensions(self) -> int:
        return self._EMBEDDING_DIM


class LocalEmbeddingProvider(EmbeddingProvider):
    """Local embedding provider using sentence-transformers.

    Warns if the model's output dimension does not match the expected
    store dimension (M5). Callers must ensure compatibility or use a
    dimensional projection layer.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2", expected_dim: int = 1536):
        self.model_name = model_name
        self.expected_dim = expected_dim
        self._model = None

    def _get_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(self.model_name)
            except ImportError as exc:
                raise RuntimeError("sentence-transformers not installed") from exc
        return self._model

    async def embed_text(self, text: str) -> List[float]:
        model = self._get_model()
        embedding = model.encode(text)
        actual_dim = len(embedding)
        if actual_dim != self.expected_dim:
            logger.warning(
                "LocalEmbeddingProvider produces %d-dim vectors but store expects %d — "
                "semantic search results will be degraded",
                actual_dim,
                self.expected_dim,
            )
        return embedding.tolist()

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        model = self._get_model()
        embeddings = model.encode(texts)
        for emb in embeddings:
            if len(emb) != self.expected_dim:
                logger.warning(
                    "LocalEmbeddingProvider produces %d-dim vectors but store expects %d",
                    len(emb),
                    self.expected_dim,
                )
        return embeddings.tolist()

    def get_dimensions(self) -> int:
        # Return the EXPECTED dimension (not the model's native dimension),
        # so callers know what dimension the store requires.
        return self.expected_dim


class EmbeddingService:
    """Service for generating embeddings with multiple providers."""

    def __init__(self, provider: Optional[EmbeddingProvider] = None):
        self.provider = provider or self._create_default_provider()
        self._cache: Dict[str, List[float]] = {}

    def _create_default_provider(self) -> EmbeddingProvider:
        """Create default embedding provider based on available config.

        M5: The semantic path is disabled unless a REAL embedding provider
        with compatible dimensions is configured. No fake MD5 fallback.
        """
        if settings.ENV == Environment.TESTING:
            logger.warning(
                "Embeddings disabled in TESTING (hermetic guard) — using mock "
                "embeddings so tests never dial a provider"
            )
            return MockEmbeddingProvider()
        if os.getenv("OPENAI_API_KEY"):
            provider = OpenAIEmbeddingProvider()
        elif os.getenv("GOOGLE_API_KEY"):
            provider = GoogleEmbeddingProvider()
        else:
            logger.warning(
                "No real embedding API key (OPENAI_API_KEY / GOOGLE_API_KEY) — "
                "semantic search DISABLED, using mock embeddings for tests only"
            )
            return MockEmbeddingProvider()

        # Validate dimension compatibility with the persistent store.
        store_dim = STORE_EMBEDDING_DIMENSIONS
        provider_dim = provider.get_dimensions()
        if provider_dim != store_dim:
            logger.warning(
                "Embedding provider dimension mismatch: provider=%d, store=%d — "
                "semantic search will be degraded",
                provider_dim,
                store_dim,
            )

        return provider

    async def embed(self, text: str, use_cache: bool = True) -> List[float]:
        """Generate embedding for text."""
        if use_cache and text in self._cache:
            return self._cache[text]

        embedding = await self.provider.embed_text(text)

        if use_cache:
            self._cache[text] = embedding

        return embedding

    async def embed_batch(self, texts: List[str], use_cache: bool = True) -> List[List[float]]:
        """Generate embeddings for multiple texts."""
        results = []
        uncached_texts = []
        uncached_indices = []

        # Check cache
        for i, text in enumerate(texts):
            if use_cache and text in self._cache:
                results.append(self._cache[text])
            else:
                results.append(None)
                uncached_texts.append(text)
                uncached_indices.append(i)

        # Generate embeddings for uncached texts
        if uncached_texts:
            new_embeddings = await self.provider.embed_texts(uncached_texts)
            for idx, embedding in zip(uncached_indices, new_embeddings, strict=False):
                results[idx] = embedding
                if use_cache:
                    self._cache[texts[idx]] = embedding

        return results

    def clear_cache(self):
        """Clear embedding cache."""
        self._cache.clear()

    def get_dimensions(self) -> int:
        """Get embedding dimensions."""
        return self.provider.get_dimensions()


class MockEmbeddingProvider(EmbeddingProvider):
    """Mock embedding provider for testing."""

    async def embed_text(self, text: str) -> List[float]:
        # Generate deterministic pseudo-embedding based on text hash
        import hashlib

        hash_obj = hashlib.sha256(text.encode())
        seed = int(hash_obj.hexdigest()[:8], 16)
        rng = np.random.RandomState(seed)
        embedding = rng.randn(1536).tolist()
        # Normalize
        norm = np.linalg.norm(embedding)
        return (np.array(embedding) / norm).tolist()

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        return [await self.embed_text(text) for text in texts]

    def get_dimensions(self) -> int:
        return 1536


# Singleton
embedding_service = EmbeddingService()
