"""RelationGraph (§15) in isolation — Context's own behavior is covered by
tests/test_relations.py through the public Context API; these lock in the
extracted unit directly."""

from ctxloom.relations import RelationGraph


def test_link_returns_relation_and_is_queryable():
    graph = RelationGraph()
    rel = graph.link("a", "supports", "b")
    assert rel.source_id == "a"
    assert rel.relation == "supports"
    assert rel.target_id == "b"
    assert graph.relations("a") == [rel]


def test_link_is_idempotent():
    graph = RelationGraph()
    graph.link("a", "rel", "b")
    graph.link("a", "rel", "b")
    assert len(graph.values()) == 1


def test_unlink_variants():
    graph = RelationGraph()
    graph.link("a", "supports", "t1")
    graph.link("a", "supports", "t2")
    graph.link("a", "contradicts", "t3")

    assert graph.unlink("a", "supports", "t1") == 1
    assert len(graph.relations("a")) == 2
    assert graph.unlink("a", "supports") == 1
    assert len(graph.relations("a")) == 1
    assert graph.unlink("a", target_id="t3") == 1
    assert graph.relations("a") == []


def test_contains_uses_the_edge_tuple():
    graph = RelationGraph()
    graph.link("a", "rel", "b")
    assert ("a", "rel", "b") in graph
    assert ("a", "rel", "c") not in graph


def test_copy_is_independent():
    graph = RelationGraph()
    graph.link("a", "rel", "b")
    clone = graph.copy()
    clone.link("a", "rel", "c")
    assert len(graph.values()) == 1
    assert len(clone.values()) == 2


def test_to_dict_from_dict_roundtrip():
    graph = RelationGraph()
    graph.link("a", "rel", "b")
    graph.link("c", "other", "d")
    restored = RelationGraph.from_dict(graph.to_dict())
    assert {(r.source_id, r.relation, r.target_id) for r in restored.values()} == {
        ("a", "rel", "b"),
        ("c", "other", "d"),
    }


def test_from_mapping_builds_a_graph():
    graph = RelationGraph()
    rel = graph.link("a", "rel", "b")
    mapping = dict(graph.items())
    rebuilt = RelationGraph.from_mapping(mapping)
    assert rebuilt.relations("a") == [rel]
