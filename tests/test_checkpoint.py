import os
import tempfile

from ctxloom.commit import Commit
from ctxloom.context import Context
from ctxloom.patches import Update
from pydantic import BaseModel


class Doc(BaseModel):
    title: str
    content: str


def test_checkpoint_roundtrip():
    ws = Context()
    doc = ws.create(Doc(title="Test", content="Hello"))
    # update the artifact
    ws.update(doc.id, Doc(title="Test", content="Updated"))
    ws.log_commit(
        Commit(
            author="test",
            message="test commit",
            operations=[Update(doc.id, Doc(title="Test", content="Updated"))],
        )
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "checkpoint.json")
        ws.save_checkpoint(path)

        # load into a new Context
        ws2 = Context.load_checkpoint(path)

    # verify that the artifact was restored
    assert len(ws2.list_artifacts(Doc)) == 1
    restored_doc = ws2.list_artifacts(Doc)[0]
    assert restored_doc.id == doc.id
    assert restored_doc.data.content == "Updated"
    # check the history
    assert len(restored_doc.history) == 1
    assert restored_doc.history[0].content == "Hello"
    # check the commits
    commits = ws2.commit_log()
    assert len(commits) == 1
    assert commits[0].author == "test"
    assert len(commits[0].operations) == 1
    op = commits[0].operations[0]
    assert isinstance(op, Update)
    assert op.artifact_id == doc.id
    assert op.new_data.content == "Updated"
