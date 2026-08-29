import asyncio
import hashlib
import re

from ctxloom.providers import EmbeddingProvider
from ctxloom.sources import EmbeddingSource


class WordEmbedder(EmbeddingProvider):
    """Bag-of-words embedder: word → stable index. Similarity by shared words."""

    async def embed(self, texts):
        vectors = []
        for text in texts:
            vec = {}
            for word in re.findall(r"\w+", text.casefold()):
                idx = int(hashlib.md5(word.encode()).hexdigest()[:8], 16) % 1024
                vec[idx] = 1.0
            v = [0.0] * 1024
            for idx, val in vec.items():
                v[idx] = val
            vectors.append(v)
        return vectors


def test_embedding_source_finds_exact_match(tmp_path):
    (tmp_path / "auth.md").write_text(
        "Аутентификация по токенам. Вход через SSO.", encoding="utf-8"
    )
    (tmp_path / "api.md").write_text(
        "Ручки API без отношения к вопросу.", encoding="utf-8"
    )
    src = EmbeddingSource(str(tmp_path), source_id="rag", embedder=WordEmbedder())

    refs = asyncio.run(src.asearch("Аутентификация по токенам вход через SSO"))
    assert len(refs) == 1
    assert refs[0].locator == "auth.md"
    assert refs[0].score > 0.9  # full word overlap


def test_embedding_source_semantic_match_beats_unrelated(tmp_path):
    (tmp_path / "auth.md").write_text(
        "Аутентификация по токенам. Вход через SSO.", encoding="utf-8"
    )
    (tmp_path / "api.md").write_text(
        "Ручки API без отношения к вопросу.", encoding="utf-8"
    )
    src = EmbeddingSource(str(tmp_path), embedder=WordEmbedder())

    refs = asyncio.run(src.asearch("как войти через SSO"))
    assert len(refs) == 1
    assert refs[0].locator == "auth.md"  # semantic match, not an exact copy


def test_embedding_source_threshold_filters_noise(tmp_path):
    (tmp_path / "a.md").write_text("какой-то текст про документы", encoding="utf-8")
    src = EmbeddingSource(str(tmp_path), source_id="rag", embedder=WordEmbedder())
    refs = asyncio.run(src.asearch("совершенно не связанный запрос"))
    assert refs == []


def test_embedding_source_preferred_and_resolve(tmp_path):
    (tmp_path / "doc.md").write_text("Содержимое документа.", encoding="utf-8")
    src = EmbeddingSource(str(tmp_path), embedder=WordEmbedder())
    assert src.preferred is True  # RAG is queried first (RAG-first)
    refs = asyncio.run(src.asearch("Содержимое документа"))
    content = asyncio.run(src.resolve(refs[0]))
    assert "Содержимое документа" in content


def test_embedding_source_requires_embedder():
    try:
        EmbeddingSource("some_root")
    except ValueError as exc:
        assert "embedder" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_embedding_source_sync_search_unsupported():
    src = EmbeddingSource("some_root", embedder=WordEmbedder())
    try:
        src.search("anything")
    except NotImplementedError:
        pass
    else:
        raise AssertionError("expected NotImplementedError")
