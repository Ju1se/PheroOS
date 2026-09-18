"""The knowledge-base gate's own tests — 3a: one failing case per check.

Every check here is given a tree in which exactly one thing is wrong, and must report it. A check
with no failing case is a comment: it can be satisfied by doing nothing, and nobody notices when it
silently stops working.

Each test builds a minimal synthetic tree rather than copying the repository, so a test failure
points at the check rather than at unrelated repository drift.
"""

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))
import check_knowledge_base as kb  # noqa: E402


REGISTER = """# Invariants

### L-1 · First invariant
A statement long enough to be treated as a restatable one for the purposes of check 8, padded out.
`kind: test  test_example.py::test_one`

### L-2 · Second invariant
Another statement.
`UNENFORCED (F-03, gate G2)`

### R-1 · A research constraint
Something that must not be tidied away.
`kind: fixture  conftest.py::forbid_network`
"""

FINDINGS = "# Findings\n\n### F-03 · A finding\nBody.\n"
AUDIT = "# Audit\n\n### F-01 · Another finding\nBody.\n"
IDS = "# comment\nL-1\nL-2\nR-1\n"
UNENF = "# comment\nL-2       F-03, gate G2\n"
ADR_README = """# Decision records

| Number | Title | Status | Written by | Subject |
|---|---|---|---|---|
| `0001` | `first` | **written** | G0.5 | one |
"""


def tree(tmp_path, **override):
    """A minimal knowledge base. Pass keyword overrides to break exactly one thing."""
    files = {
        "AGENTS.md": "# Map\n\nSee `docs/invariants.md`.\n",
        "ARCHITECTURE.md": "# Architecture\n\nCites L-1 and F-03.\n",
        "docs/invariants.md": REGISTER,
        "docs/findings.md": FINDINGS,
        "audit/FINDINGS.md": AUDIT,
        "tools/baseline/invariant-ids.txt": IDS,
        "tools/baseline/unenforced.txt": UNENF,
        "docs/decisions/README.md": ADR_README,
        "docs/decisions/0001-first.md": "---\nid: 0001\nsupersedes: []\n---\n# First\n",
        "tests/interaction/conftest.py": "import pytest\n\n\n@pytest.fixture(autouse=True)\ndef forbid_network():\n    pass\n",
        "runner/cli.py": "from . import runtime\n",
        "runner/runtime.py": "X = 1\n",
        "runner/orchestration.py": 'PREFIX = "orch:"\n',
        "runner/colony.py": 'PREFIX = "colony:"\n',
    }
    files.update(override)
    for rel, body in files.items():
        if body is None:
            continue
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    return tmp_path


# ---------------------------------------------------------------- one failing case per check

def test_references_resolve_catches_a_path_not_in_the_tree(tmp_path):
    t = tree(tmp_path, **{"ARCHITECTURE.md": "# A\n\nSee `runner/does_not_exist.py:12`.\n"})
    problems = kb.check_references_resolve(t)
    assert any("does_not_exist.py" in p for p in problems), problems


def test_references_resolve_catches_a_line_past_end_of_file(tmp_path):
    t = tree(tmp_path, **{"ARCHITECTURE.md": "# A\n\nSee `runner/runtime.py:9999`.\n"})
    problems = kb.check_references_resolve(t)
    assert any("past end of file" in p for p in problems), problems


def test_references_resolve_catches_an_invariant_id_not_in_the_register(tmp_path):
    t = tree(tmp_path, **{"ARCHITECTURE.md": "# A\n\nCites L-99.\n"})
    problems = kb.check_references_resolve(t)
    assert any("L-99" in p for p in problems), problems


def test_planned_markers_catches_a_marker_on_a_file_that_exists(tmp_path):
    t = tree(tmp_path, **{"AGENTS.md": "# Map\n\n`docs/invariants.md` **(PLANNED — not yet created)**\n"})
    problems = kb.check_planned_markers(t)
    assert any("PLANNED" in p and "invariants" in p for p in problems), problems


def test_invariant_ids_catches_a_disappeared_id(tmp_path):
    shrunk = REGISTER[:REGISTER.index("### R-1")]
    t = tree(tmp_path, **{"docs/invariants.md": shrunk})
    problems = kb.check_invariant_ids(t)
    assert any("R-1" in p and "append-only" in p for p in problems), problems


def test_invariant_ids_catches_a_non_contiguous_namespace(tmp_path):
    gapped = REGISTER.replace("### L-2 ·", "### L-7 ·")
    t = tree(tmp_path,
             **{"docs/invariants.md": gapped, "tools/baseline/invariant-ids.txt": "# c\nL-1\nR-1\n"})
    problems = kb.check_invariant_ids(t)
    assert any("not contiguous" in p for p in problems), problems


def test_enforcement_catches_an_unenforced_entry_with_no_gate(tmp_path):
    bad = REGISTER.replace("`UNENFORCED (F-03, gate G2)`", "`UNENFORCED (F-03)`")
    t = tree(tmp_path, **{"docs/invariants.md": bad})
    problems = kb.check_enforcement(t)
    assert any("no named closing gate" in p for p in problems), problems


def test_enforcement_catches_a_dangling_delegation(tmp_path):
    bad = REGISTER.replace("`kind: fixture  conftest.py::forbid_network`", "`kind: delegated  L-404`")
    t = tree(tmp_path, **{"docs/invariants.md": bad})
    problems = kb.check_enforcement(t)
    assert any("L-404" in p for p in problems), problems


def test_enforcement_catches_an_invariant_with_no_entry_at_all(tmp_path):
    bare = REGISTER.replace("`kind: fixture  conftest.py::forbid_network`", "")
    t = tree(tmp_path, **{"docs/invariants.md": bare})
    problems = kb.check_enforcement(t)
    assert any("no enforcement entry" in p for p in problems), problems


def test_unenforced_ceiling_catches_a_raised_ceiling(tmp_path):
    raised = REGISTER.replace("`kind: fixture  conftest.py::forbid_network`",
                              "`UNENFORCED (F-01, gate G9)`")
    t = tree(tmp_path, **{"docs/invariants.md": raised})
    problems = kb.check_unenforced_ceiling(t)
    assert any("raising the ceiling fails outright" in p for p in problems), problems
    assert any("not in the baseline" in p for p in problems), problems


def test_adr_numbering_catches_a_gap_with_no_planned_row(tmp_path):
    t = tree(tmp_path, **{"docs/decisions/0003-third.md": "---\nid: 0003\nsupersedes: []\n---\n# Third\n"})
    problems = kb.check_adr_numbering(t)
    assert any("0002" in p and "written and lost" in p for p in problems), problems


def test_adr_numbering_accepts_a_gap_that_has_a_planned_row(tmp_path):
    readme = ADR_README + "| `0002` | `second` | planned | *unassigned* | two |\n"
    t = tree(tmp_path, **{"docs/decisions/README.md": readme,
                          "docs/decisions/0003-third.md": "---\nid: 0003\nsupersedes: []\n---\n# Third\n"})
    assert not [p for p in kb.check_adr_numbering(t) if "0002" in p]


def test_adr_numbering_rejects_released_as_a_gap_filler(tmp_path):
    """`released` must not satisfy a gap: it makes 'never used' and 'lost' indistinguishable."""
    readme = ADR_README + "| `0002` | — | *released* | — | freed |\n"
    t = tree(tmp_path, **{"docs/decisions/README.md": readme,
                          "docs/decisions/0003-third.md": "---\nid: 0003\nsupersedes: []\n---\n# Third\n"})
    problems = kb.check_adr_numbering(t)
    assert any("0002" in p for p in problems), problems


def test_adr_numbering_catches_a_dangling_supersedes(tmp_path):
    t = tree(tmp_path, **{"docs/decisions/0001-first.md":
                          "---\nid: 0001\nsupersedes: [0099]\n---\n# First\n"})
    problems = kb.check_adr_numbering(t)
    assert any("0099" in p for p in problems), problems


def test_no_restated_invariants_catches_a_verbatim_copy(tmp_path):
    stmt = "A statement long enough to be treated as a restatable one for the purposes of check 8"
    t = tree(tmp_path, **{"ARCHITECTURE.md": "# A\n\n%s, padded out.\n" % stmt})
    problems = kb.check_no_restated_invariants(t)
    assert any("restates L-1" in p for p in problems), problems


def test_research_contract_catches_colony_becoming_reachable(tmp_path):
    t = tree(tmp_path, **{"runner/cli.py": "from . import runtime\nfrom . import colony\n"})
    problems = kb.check_research_contract(t)
    assert any("R-1" in p and "reachable" in p for p in problems), problems


def test_research_contract_catches_a_lost_call_identity_prefix(tmp_path):
    t = tree(tmp_path, **{"runner/colony.py": "PREFIX = 'orch:'\n"})
    problems = kb.check_research_contract(t)
    assert any("R-2" in p for p in problems), problems


def test_relaxations_recorded_catches_one_missing_its_boundary(tmp_path, monkeypatch):
    monkeypatch.setattr(kb, "RELAXATIONS",
                        [{"check": "x", "relaxation": "y", "boundary": "",
                          "recorded_in": "docs/invariants.md", "still_catches": "z"}])
    problems = kb.check_relaxations_recorded(tree(tmp_path))
    assert any("missing boundary" in p for p in problems), problems


def test_relaxations_recorded_catches_one_citing_a_missing_doc(tmp_path, monkeypatch):
    monkeypatch.setattr(kb, "RELAXATIONS",
                        [{"check": "x", "relaxation": "y", "boundary": "b",
                          "recorded_in": "docs/nope.md", "still_catches": "z"}])
    problems = kb.check_relaxations_recorded(tree(tmp_path))
    assert any("does not exist" in p for p in problems), problems


def test_generated_is_current_catches_a_missing_generated_file(tmp_path):
    problems = kb.check_generated_is_current(tree(tmp_path))
    assert any("missing" in p for p in problems), problems


def test_the_live_repository_currently_has_zero_recorded_relaxations():
    """Rule (g) holds vacuously today, and that is worth asserting: a relaxation must be added
    deliberately, as a recorded decision, not acquired as an implementation detail."""
    assert kb.RELAXATIONS == []
