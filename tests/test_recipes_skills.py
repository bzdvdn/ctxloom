"""recipes.skills: frontmatter parsing, directory loading, keyword matching."""

from ctxloom.recipes import Skill, load_skills, match_skills
from ctxloom.recipes.skills import parse_skill


def test_parse_skill_reads_frontmatter():
    content = (
        "---\n"
        "name: cost-reporting\n"
        "description: How to report a computed total. Use for cost calculations.\n"
        "---\n"
        "Always state the exact number and cite it as computed, not estimated.\n"
    )
    skill = parse_skill(content)
    assert skill.name == "cost-reporting"
    assert skill.description.startswith("How to report a computed total")
    assert skill.body == (
        "Always state the exact number and cite it as computed, not estimated."
    )


def test_parse_skill_without_frontmatter_is_all_body():
    skill = parse_skill("just some instructions", default_name="fallback")
    assert skill.name == "fallback"
    assert skill.description == ""
    assert skill.body == "just some instructions"


def test_load_skills_parses_every_file(tmp_path):
    (tmp_path / "a.md").write_text(
        "---\nname: a\ndescription: about a\n---\nbody a", encoding="utf-8"
    )
    (tmp_path / "b.md").write_text(
        "---\nname: b\ndescription: about b\n---\nbody b", encoding="utf-8"
    )
    (tmp_path / "ignored.txt").write_text("not a skill", encoding="utf-8")

    skills = load_skills(tmp_path)
    assert {s.name for s in skills} == {"a", "b"}


def test_load_skills_missing_directory_is_empty():
    assert load_skills("/no/such/directory") == []


def test_match_skills_ranks_by_keyword_overlap():
    skills = [
        Skill(
            name="cost-reporting",
            description="How to report a computed total for cost calculations",
            body="State the exact number.",
        ),
        Skill(
            name="greeting-tone",
            description="How to greet a new user warmly",
            body="Say hello.",
        ),
    ]
    matched = match_skills(
        skills, "assembling an answer backed by a computed cost total"
    )
    assert len(matched) == 1
    assert matched[0].name == "cost-reporting"


def test_match_skills_no_match_below_threshold():
    skills = [Skill(name="x", description="unrelated topic", body="body")]
    assert match_skills(skills, "completely different situation") == []
