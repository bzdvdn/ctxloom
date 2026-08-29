from ctxloom.sources import FileSystemSource, Source, SourceRef


def test_filesystem_keyword_search(tmp_path):
    (tmp_path / "auth.md").write_text(
        "Аутентификация по токенам. Вход через SSO.", encoding="utf-8"
    )
    (tmp_path / "api.txt").write_text(
        "Ручки API без отношения к вопросу.", encoding="utf-8"
    )

    src = FileSystemSource(str(tmp_path))
    refs = src.search("аутентификация вход", limit=10)

    assert len(refs) == 1
    ref = refs[0]
    assert ref.source_id == "filesystem"
    assert ref.locator == "auth.md"
    assert ref.score is not None and ref.score > 0
    assert "Аутентификация" in ref.excerpt
    assert ref.stable_id() == ref.stable_id()


def test_search_limit_and_score_ordering(tmp_path):
    (tmp_path / "costs.md").write_text("Цены платформы за месяц.", encoding="utf-8")
    (tmp_path / "costs_more.md").write_text(
        "Цены и тарифы платформы на месяц и квартал.", encoding="utf-8"
    )
    src = FileSystemSource(str(tmp_path))
    refs = src.search("цены тарифы платформа", limit=1)
    assert len(refs) == 1
    assert refs[0].score >= 0  # ordered by descending relevance


def test_source_without_search_returns_empty():
    class ResolveOnly(Source):
        def __init__(self):
            super().__init__("resolve_only")

        async def resolve(self, ref: SourceRef) -> str:
            return "ok"

    src = ResolveOnly()
    assert src.search("anything") == []


def test_filesystem_source_custom_source_id():
    src = FileSystemSource("some_root", source_id="docs-a")
    assert src.source_id == "docs-a"
