import os
import tempfile

from ctxloom import Context
from ctxloom.checkpoints import SQLiteBackend
from pydantic import BaseModel


class Doc(BaseModel):
    title: str
    content: str


def test_sqlite_checkpoint_roundtrip():
    ws = Context()
    doc = ws.create(Doc(title="Test", content="Hello"))
    ws.update(doc.id, Doc(title="Test", content="Updated"))

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "state.db")
        backend = SQLiteBackend(db_path)

        ws.save_checkpoint(backend)

        # Load into a new Workspace
        ws2 = Context.load_checkpoint(backend)

    # Verify that the artifact was restored
    assert len(ws2.list_artifacts(Doc)) == 1
    restored_doc = ws2.list_artifacts(Doc)[0]
    assert restored_doc.id == doc.id
    assert restored_doc.data.content == "Updated"
    assert len(restored_doc.history) == 1
    assert restored_doc.history[0].content == "Hello"
