from types import SimpleNamespace as NS
from typing import Any

import pytest

from ezo_api.knowledge.embeddings.service import EmbeddingError, EmbeddingService
from ezo_api.providers.gemini_provider import GeminiProvider
from ezo_api.providers.openai_provider import OpenAIProvider
from ezo_api.providers.router import CandidateConfig
from tests.fakes import FakeProvider

CANDIDATES = (
    CandidateConfig("openai", "text-embedding-3-small"),
    CandidateConfig("gemini", "gemini-embedding-001"),
)


def test_first_provider_with_embeddings_is_used() -> None:
    service = EmbeddingService(
        CANDIDATES,
        {
            "anthropic": FakeProvider(name="anthropic"),
            "gemini": FakeProvider(name="gemini", supports_embeddings=True),
        },
    )
    assert service.model_key == "gemini:gemini-embedding-001"
    assert not EmbeddingService(CANDIDATES, {"anthropic": FakeProvider(name="anthropic")}).available


async def test_batching_and_errors() -> None:
    provider = FakeProvider(name="openai", supports_embeddings=True)
    service = EmbeddingService(CANDIDATES, {"openai": provider})
    vectors = await service.embed_documents([f"matn {i}" for i in range(130)])
    assert len(vectors) == 130 and provider.embed_calls == 3  # batches of 64

    provider.embed_fail = True
    with pytest.raises(EmbeddingError) as info:
        await service.embed_query("x")
    assert "rate_limit" in info.value.message

    with pytest.raises(EmbeddingError, match="No embedding provider"):
        await EmbeddingService(CANDIDATES, {}).embed_query("x")


async def test_openai_adapter_embeddings_keep_order() -> None:
    seen: dict[str, Any] = {}

    async def create(**params: Any) -> Any:
        seen.update(params)
        return NS(data=[NS(index=1, embedding=[0.0, 1.0]), NS(index=0, embedding=[1.0, 0.0])])

    client = NS(embeddings=NS(create=create))
    vectors = await OpenAIProvider("k", 10, client=client).embed(
        ["a", "b"], "text-embedding-3-small"
    )
    assert vectors == [[1.0, 0.0], [0.0, 1.0]]
    assert seen == {"model": "text-embedding-3-small", "input": ["a", "b"]}


async def test_gemini_adapter_embeddings_use_task_type() -> None:
    seen: dict[str, Any] = {}

    async def embed_content(**kwargs: Any) -> Any:
        seen.update(kwargs)
        return NS(embeddings=[NS(values=[0.5, 0.5])])

    client = NS(aio=NS(models=NS(embed_content=embed_content)))
    vectors = await GeminiProvider("k", 10, client=client).embed(
        ["q"], "gemini-embedding-001", "query"
    )
    assert vectors == [[0.5, 0.5]]
    assert seen["config"].task_type == "RETRIEVAL_QUERY"
