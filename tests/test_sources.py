import asyncio

from ctxloom.sources import FileSystemSource, SourceRef


def test_filesystem_source_resolve(tmp_path):
    file = tmp_path / "test.md"
    file.write_text("Hello")
    src = FileSystemSource(str(tmp_path))
    ref = SourceRef(source_id="filesystem", locator="test.md")
    content = asyncio.run(src.resolve(ref))
    assert content == "Hello"


def test_source_ref_stable_id():
    ref1 = SourceRef(source_id="gitlab", locator="repo/file.md")
    ref2 = SourceRef(source_id="gitlab", locator="repo/file.md")
    assert ref1.stable_id() == ref2.stable_id()
