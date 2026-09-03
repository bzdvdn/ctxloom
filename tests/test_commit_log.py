"""CommitLog (§12) in isolation — Context's own commit/version/checkout
behavior is covered by tests/test_backbone.py and tests/test_relations.py
through the public Context API; these lock in the extracted unit directly."""

from ctxloom.commit import Commit, Write
from ctxloom.commit_log import CommitLog
from ctxloom.patches import Create, Delete, Link, Unlink, Update
from pydantic import BaseModel


class Note(BaseModel):
    text: str


def test_append_fills_parent_and_moves_head():
    log = CommitLog()
    assert log.version == 0
    assert log.head_id is None

    c1 = Commit(author="a", message="m1", operations=[Create(Note(text="1"), id="n1")])
    log.append(c1)
    assert log.version == 1
    assert log.head_id == c1.id
    assert c1.parent_id is None
    assert c1.context_version == 1

    c2 = Commit(author="a", message="m2", operations=[Update("n1", Note(text="2"))])
    log.append(c2)
    assert log.version == 2
    assert log.head_id == c2.id
    assert c2.parent_id == c1.id
    assert c2.context_version == 2


def test_history_and_len():
    log = CommitLog()
    c1 = Commit(author="a", message="m1", operations=[])
    log.append(c1)
    assert log.history() == [c1]
    assert len(log) == 1
    # history() returns a copy — mutating it must not affect the log
    log.history().append(Commit(author="x", message="y", operations=[]))
    assert len(log) == 1


def test_commits_from_and_upto():
    log = CommitLog()
    ops = [
        Commit(author="a", message=str(i), operations=[]) for i in range(3)
    ]
    for c in ops:
        log.append(c)
    assert log.commits_upto(2) == ops[:2]
    assert log.commits_from(1) == ops[1:]


def test_replay_state_applies_create_update_delete():
    log = CommitLog()
    log.append(
        Commit(author="a", message="c1", operations=[Create(Note(text="1"), id="n1")])
    )
    log.append(
        Commit(author="a", message="c2", operations=[Update("n1", Note(text="2"))])
    )
    state = log.replay_state(2)
    assert state["n1"].text == "2"

    log.append(Commit(author="a", message="c3", operations=[Delete("n1")]))
    state = log.replay_state(3)
    assert "n1" not in state
    # replay_state(2) is unaffected — it only looks at the first two commits
    assert "n1" in log.replay_state(2)


def test_replay_relations_applies_link_and_unlink():
    log = CommitLog()
    log.append(
        Commit(
            author="a",
            message="c1",
            operations=[Link(artifact_id="a", relation="rel", target_id="b")],
        )
    )
    rels = log.replay_relations(1)
    assert ("a", "rel", "b") in rels

    log.append(
        Commit(
            author="a",
            message="c2",
            operations=[Unlink(artifact_id="a", relation="rel")],
        )
    )
    rels = log.replay_relations(2)
    assert ("a", "rel", "b") not in rels
    # replay_relations(1) is unaffected
    assert ("a", "rel", "b") in log.replay_relations(1)


def test_producing_commit_returns_last_writer():
    log = CommitLog()
    c1 = Commit(author="a", message="c1", operations=[])
    c1.writes = [Write("n1", 0, "create")]
    log.append(c1)
    c2 = Commit(author="a", message="c2", operations=[])
    log.append(c2)  # does not write n1
    assert log.producing_commit("n1") is c1
    assert log.producing_commit("missing") is None


def test_truncate_rolls_back_head_and_version():
    log = CommitLog()
    c1 = Commit(author="a", message="c1", operations=[])
    c2 = Commit(author="a", message="c2", operations=[])
    log.append(c1)
    log.append(c2)
    log.truncate(1)
    assert log.version == 1
    assert log.head_id == c1.id
    assert log.history() == [c1]

    log.truncate(0)
    assert log.version == 0
    assert log.head_id is None
    assert log.history() == []


def test_copy_is_independent():
    log = CommitLog()
    log.append(Commit(author="a", message="c1", operations=[]))
    clone = log.copy()
    clone.append(Commit(author="a", message="c2", operations=[]))
    assert log.version == 1
    assert clone.version == 2


def test_to_dict_from_dict_roundtrip():
    log = CommitLog()
    log.append(Commit(author="a", message="c1", operations=[Create(Note(text="1"), id="n1")]))
    log.append(Commit(author="a", message="c2", operations=[Update("n1", Note(text="2"))]))
    restored = CommitLog.from_dict(log.to_dict(), version=log.version, head_id=log.head_id)
    assert restored.version == log.version
    assert restored.head_id == log.head_id
    assert len(restored.history()) == 2


def test_from_dict_infers_version_and_head_when_omitted():
    log = CommitLog()
    log.append(Commit(author="a", message="c1", operations=[]))
    log.append(Commit(author="a", message="c2", operations=[]))
    restored = CommitLog.from_dict(log.to_dict(), version=None, head_id=None)
    assert restored.version == 2
    assert restored.head_id == log.history()[-1].id
