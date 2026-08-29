from ctxloom.artifacts import Artifact
from pydantic import BaseModel


class Person(BaseModel):
    name: str
    age: int
    address: dict = {}


def test_create_artifact():
    person = Person(name="Alice", age=30)
    artifact = Artifact(data=person)
    assert artifact.data.name == "Alice"
    assert artifact.data.age == 30
    assert artifact.version == 0
    assert artifact.history == []


def test_update_artifact():
    person_v1 = Person(name="Alice", age=30)
    artifact = Artifact(data=person_v1)

    person_v2 = Person(name="Alice", age=31)
    artifact.update(person_v2)

    assert artifact.data.age == 31
    assert artifact.version == 1
    assert len(artifact.history) == 1
    # Verify that the old version is preserved in history
    assert artifact.history[0].age == 30
    # And that it hasn't changed after the update
    assert artifact.history[0].name == "Alice"


def test_history_is_immutable():
    person = Person(name="Bob", age=25)
    artifact = Artifact(data=person)
    artifact.update(Person(name="Bob", age=26))

    # Attempting to mutate history through the returned list must not affect the artifact
    history = artifact.history
    history.clear()
    assert len(artifact.history) == 1  # history unchanged


def test_artifact_diff():
    person_v1 = Person(name="Alice", age=30, address={"city": "NY"})
    artifact = Artifact(data=person_v1)

    person_v2 = Person(name="Alice", age=31, address={"city": "LA"})
    artifact.update(person_v2)

    # Between versions 0 and 1, age and address.city must have changed
    diff = artifact.diff(0, 1)
    assert "age" in diff["changed"]
    assert diff["changed"]["age"]["old"] == 30
    assert diff["changed"]["age"]["new"] == 31
    assert "address" in diff["changed"]
    # Inside address, city must have changed
    assert "city" in diff["changed"]["address"]["changed"]
    assert diff["changed"]["address"]["changed"]["city"]["old"] == "NY"
    assert diff["changed"]["address"]["changed"]["city"]["new"] == "LA"
