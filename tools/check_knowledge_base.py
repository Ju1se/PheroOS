#!/usr/bin/env python3
"""Knowledge-base gate. Fails the build when the documentation stops matching the repository.

Every rule below was forced by a specific failure, not designed in advance. The comment on each
names the failure, because a rule whose reason is lost is the next rule to be relaxed away.

    (a) Resolution is evaluated against `git archive HEAD`. A reference that resolves only in a
        working tree is a failure, not a pass.
        WHY: AGENTS.md cited 13 enforcement nodes; all 13 lived in untracked files. In the working
        tree every one resolved. From a clean clone, none did.

    (b) Before checking a file, assert it exists in HEAD and matches the working tree.
        WHY: `git archive HEAD` once yielded the 99-line pre-rewrite AGENTS.md while the 168-line
        rewrite sat uncommitted. A clean-tree run would have validated the wrong file and passed.

    (c) A FAIL is reproduced before it is acted on.
        WHY: two false FAILs, both the auditor's own — a path-prefix mismatch, and a diff taken
        against the wrong baseline. A false FAIL sends someone to fix a non-problem, and here
        fixing often means deleting something correct.

    (d) Archival trees are exempt from currency checks and subject to integrity checks.
        WHY: audit/FINDINGS.md legitimately names paths that no longer exist; it is a dated report
        and amending it would falsify the record it exists to preserve.

    (e) Any claim about what changed states its baseline and its definition of "touched".
        WHY: `git diff 4111b67` vs `e664d2e` gave 20 changed test files against a claim of 3. The
        difference was a semantic choice about what "changed" means, made silently.

    (f) Checks over prose operate on semantic units, not lines.
        WHY: a line-based grep for the superseded one-agent premise found 2 sites; a
        whitespace-normalised search found 4. The two it missed wrapped mid-phrase.

    (g) Any weakening of a check requires a recorded boundary, and the weakened check must still
        catch the failure it was built for.
        WHY: without it, "this check is too strict" becomes "this check does nothing".

Usage:  python tools/check_knowledge_base.py [--working-tree]
"""
from __future__ import annotations

import argparse
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent

# --- rule (d): trees exempt from currency checks, subject to integrity checks -------------------
ARCHIVAL_TREES = ("docs/history/", "audit/")
# Not part of the repository: gitignored local data, absent from `git archive HEAD`.
NOT_SCANNED = ("research-data/", ".venv/", "node_modules/")

# --- rule (g): every relaxation is recorded here, with its boundary and the doc that states it --
# Currently EMPTY, and that is the intended state. An earlier draft added a relaxation here letting
# an ADR gap be filled by a row marked `released`. That was rejected: with `released` legal, "this
# number was never used" and "this record was written and lost" both pass, and the check stops
# distinguishing them — which is the only thing it was built to do. A gap is legal only with a
# `planned` row naming the topic that will fill it.
RELAXATIONS: list[dict] = []

# --- rule (e): any check that makes a claim about what CHANGED declares its baseline and its
# definition of "touched". Empty today: no check diffs anything. The registry exists so that the
# first one to do so cannot omit them — `git diff 4111b67` vs `e664d2e` gave 20 changed test files
# against a claim of 3, and the difference was a silent semantic choice.
DIFF_CHECKS: list[dict] = []


class Problem(str):
    pass


def sh(*args: str, cwd: pathlib.Path | None = None) -> str:
    return subprocess.run(args, cwd=cwd or REPO, capture_output=True, text=True).stdout


def is_archival(path: str) -> bool:
    return any(path.startswith(t) or ("/" + t) in path for t in ARCHIVAL_TREES)


def normalise(text: str) -> str:
    """Rule (f): collapse every run of whitespace so a wrapped phrase is one semantic unit."""
    return re.sub(r"\s+", " ", text)


# ---------------------------------------------------------------- the checks

def check_head_matches_worktree(tree: pathlib.Path) -> list[Problem]:
    """Rule (b) — the artefacts being checked must be in HEAD and identical to the working tree."""
    out = []
    dirty = [l[3:] for l in sh("git", "status", "--porcelain").splitlines()
             if l[:2].strip() and not l.startswith("??")]
    for f in ("AGENTS.md", "ARCHITECTURE.md", "docs/invariants.md", "docs/findings.md"):
        if not (tree / f).exists():
            out.append(Problem("(b) %s is not in HEAD; a clean-tree check would validate nothing" % f))
        elif f in dirty:
            out.append(Problem("(b) %s differs between HEAD and the working tree" % f))
    return out


def check_references_resolve(tree: pathlib.Path) -> list[Problem]:
    """Check 1 + 7 — every path, file:line, invariant id and finding id named in a live doc exists."""
    out = []
    ids = set(re.findall(r"^### ((?:L|R)-\d+) · ", (tree / "docs/invariants.md").read_text(), re.M))
    fids = set(re.findall(r"^### (F-\d+)", (tree / "docs/findings.md").read_text(), re.M))
    fids |= set(re.findall(r"^### (F-\d+)", (tree / "audit/FINDINGS.md").read_text(), re.M))
    for doc in sorted(tree.rglob("*.md")):
        rel = str(doc.relative_to(tree))
        if is_archival(rel) or any(rel.startswith(x) for x in NOT_SCANNED):
            continue                                   # rule (d)
        text = doc.read_text()
        for m in re.finditer(r"`([A-Za-z0-9_./-]+\.(?:py|md|toml|json|yml)):(\d+)(?:-(\d+))?`", text):
            target, lo, hi = m.group(1), int(m.group(2)), m.group(3)
            p = tree / target
            if not p.exists():
                out.append(Problem("%s: names %s, which is not in HEAD" % (rel, target)))
            elif (n := len(p.read_text().splitlines())) < (int(hi) if hi else lo):
                out.append(Problem("%s: %s is past end of file (%d lines)" % (rel, m.group(0), n)))
        for x in sorted(set(re.findall(r"\b((?:L|R)-\d+)\b", text))):
            if x not in ids:
                out.append(Problem("%s: cites %s, absent from docs/invariants.md" % (rel, x)))
        for x in sorted(set(re.findall(r"\b(F-\d+)\b", text))):
            if x not in fids:
                out.append(Problem("%s: cites %s, absent from both finding registers" % (rel, x)))
    return out


def check_planned_markers(tree: pathlib.Path) -> list[Problem]:
    """Check 2 — a (PLANNED) marker on something that now exists is a lie the reader inherits."""
    out = []
    text = (tree / "AGENTS.md").read_text()
    for m in re.finditer(r"`([A-Za-z0-9_./-]+)`[^|\n]{0,40}\(PLANNED", text):
        target = m.group(1)
        if (tree / target).exists():
            out.append(Problem("AGENTS.md: %s is marked (PLANNED) but exists in HEAD" % target))
    return out


def check_invariant_ids(tree: pathlib.Path) -> list[Problem]:
    """Check 3 — ids are append-only protocol vocabulary; one disappearing breaks every citation."""
    out = []
    baseline = [l.strip() for l in (tree / "tools/baseline/invariant-ids.txt").read_text().splitlines()
                if l.strip() and not l.startswith("#")]
    present = re.findall(r"^### ((?:L|R)-\d+) · ", (tree / "docs/invariants.md").read_text(), re.M)
    if len(present) != len(set(present)):
        out.append(Problem("(3) duplicate invariant id in docs/invariants.md"))
    for i in baseline:
        if i not in present:
            out.append(Problem("(3) %s is in the baseline but gone from the register — ids are append-only" % i))
    for ns in ("L", "R"):
        nums = sorted(int(i.split("-")[1]) for i in present if i.startswith(ns + "-"))
        if nums and nums != list(range(1, len(nums) + 1)):
            out.append(Problem("(3) %s-namespace is not contiguous from 1: %s" % (ns, nums)))
    return out


def check_enforcement(tree: pathlib.Path) -> list[Problem]:
    """Check 4 — every enforcement reference resolves, or is UNENFORCED with a named closing gate."""
    out = []
    reg = (tree / "docs/invariants.md").read_text()
    marks = list(re.finditer(r"^### ((?:L|R)-\d+(?:\.\w+)?) · ", reg, re.M))
    known = {m.group(1) for m in marks}
    nodes = set()
    for line in sh(sys.executable, "-m", "pytest", "--collect-only", "-q", cwd=tree).splitlines():
        if "::" in line:
            nodes.add(line.strip().split("[")[0].removeprefix("tests/interaction/"))
    for i, m in enumerate(marks):
        body = reg[m.end(): marks[i + 1].start() if i + 1 < len(marks) else len(reg)]
        refs = re.findall(r"`kind: (test|fixture|lint|schema|delegated)\s+([^`]+)`", body)
        unenf = re.findall(r"`UNENFORCED \(([^)]*)\)`", body)
        if not refs and not unenf:
            out.append(Problem("(4) %s has no enforcement entry at all" % m.group(1)))
        for kind, ref in refs:
            ref = ref.strip()
            if kind == "test" and ref not in nodes:
                out.append(Problem("(4) %s cites test node %s, which does not resolve" % (m.group(1), ref)))
            if kind == "fixture":
                path, _, name = ref.partition("::")
                src = tree / "tests/interaction" / path
                if not src.exists() or not re.search(r"^def %s\(" % re.escape(name), src.read_text(), re.M):
                    out.append(Problem("(4) %s cites fixture %s, which does not resolve" % (m.group(1), ref)))
            if kind == "delegated":
                if ref not in known:
                    out.append(Problem("(4) %s delegates to %s, which does not exist" % (m.group(1), ref)))
                elif ref == m.group(1):
                    out.append(Problem("(4) %s delegates to itself" % m.group(1)))
        for u in unenf:
            if not re.search(r"gate\s+G[\d.]+", u):
                out.append(Problem("(4) %s is UNENFORCED with no named closing gate: %r" % (m.group(1), u)))
    return out


def check_unenforced_ceiling(tree: pathlib.Path) -> list[Problem]:
    """Check 5 — the ceiling is a debt register, not an escape hatch. Raising it fails outright."""
    out = []
    baseline = [l for l in (tree / "tools/baseline/unenforced.txt").read_text().splitlines()
                if l.strip() and not l.startswith("#")]
    reg = (tree / "docs/invariants.md").read_text()
    marks = list(re.finditer(r"^### ((?:L|R)-\d+(?:\.\w+)?) · ", reg, re.M))
    actual = []
    for i, m in enumerate(marks):
        body = reg[m.end(): marks[i + 1].start() if i + 1 < len(marks) else len(reg)]
        actual += ["%-8s %s" % (m.group(1), u.strip())
                   for u in re.findall(r"`UNENFORCED \(([^)]*)\)`", body)]
    if len(actual) > len(baseline):
        out.append(Problem("(5) unenforced count rose from %d to %d — raising the ceiling fails outright"
                           % (len(baseline), len(actual))))
    for extra in sorted(set(actual) - set(baseline)):
        out.append(Problem("(5) unenforced entry not in the baseline: %s" % extra.strip()))
    return out


def check_adr_numbering(tree: pathlib.Path) -> list[Problem]:
    """Check 6 — ids unique and zero-padded; a gap is legal only with a row in README (rule (g))."""
    out = []
    files = sorted((tree / "docs/decisions").glob("[0-9]*.md"))
    nums = []
    for f in files:
        m = re.match(r"^(\d{4})-", f.name)
        if not m:
            out.append(Problem("(6) %s is not zero-padded NNNN-title" % f.name))
            continue
        nums.append(int(m.group(1)))
    if len(nums) != len(set(nums)):
        out.append(Problem("(6) duplicate ADR number"))
    readme = (tree / "docs/decisions/README.md").read_text()
    # A gap is legal IFF README has a matching row whose status is `planned`. `released` is not a
    # legal state: it would make "never used" and "written and lost" indistinguishable.
    planned = {int(m.group(1)) for m in
               re.finditer(r"^\| `(\d{4})` \| [^|]* \| planned \|", readme, re.M)}
    for n in range(1, max(nums, default=0) + 1):
        if n not in nums and n not in planned:
            out.append(Problem("(6) ADR %04d is missing with no `planned` row in README.md "
                               "— a record was written and lost" % n))
    for adr in files:
        for target in re.findall(r"^supersedes:\s*\[([^\]]*)\]", adr.read_text(), re.M):
            for t in [x.strip().strip("'\"") for x in target.split(",") if x.strip()]:
                if not list((tree / "docs/decisions").glob("%s*.md" % t)):
                    out.append(Problem("(6) %s supersedes %s, which does not exist" % (adr.name, t)))
    return out


def check_no_restated_invariants(tree: pathlib.Path) -> list[Problem]:
    """Check 8 — two copies of a rule is one copy that goes stale. Rule (f): normalised matching."""
    out = []
    reg = (tree / "docs/invariants.md").read_text()
    statements = []
    marks = list(re.finditer(r"^### ((?:L|R)-\d+(?:\.\w+)?) · (.+)$", reg, re.M))
    for i, m in enumerate(marks):
        body = reg[m.end(): marks[i + 1].start() if i + 1 < len(marks) else len(reg)]
        first = next((normalise(p).strip() for p in body.split("\n\n")
                      if p.strip() and not p.strip().startswith(("`", "*", "-"))), "")
        if len(first) > 90:
            statements.append((m.group(1), first[:90]))
    for doc in sorted(tree.rglob("*.md")):
        rel = str(doc.relative_to(tree))
        if is_archival(rel) or rel == "docs/invariants.md" \
                or any(rel.startswith(x) for x in NOT_SCANNED):
            continue                                   # rule (d)
        flat = normalise(doc.read_text())              # rule (f)
        for inv_id, stmt in statements:
            if stmt in flat:
                out.append(Problem("%s: restates %s's statement verbatim; cite the id instead" % (rel, inv_id)))
    return out


def check_research_contract(tree: pathlib.Path) -> list[Problem]:
    """R-1 and R-2 — the two research constraints most likely to be 'cleaned up'."""
    out = []
    # R-1: colony.py must stay unreachable from every CLI entry point.
    mods = {p.stem: p for p in (tree / "runner").glob("*.py") if p.name != "__init__.py"}
    edges: dict[str, set[str]] = {}
    for stem, p in mods.items():
        found = set(re.findall(r"^from \.(\w+) import|^from \. import ([\w, ]+)|^import (\w+)",
                               p.read_text(), re.M))
        names = set()
        for a, b, c in found:
            names |= {a} if a else set()
            names |= {x.strip() for x in b.split(",")} if b else set()
            names |= {c} if c else set()
        edges[stem] = {n for n in names if n in mods}
    seen, stack = set(), ["cli"]
    while stack:
        m = stack.pop()
        if m in seen or m not in mods:
            continue
        seen.add(m)
        stack += list(edges[m])
    if "colony" in seen:
        out.append(Problem("R-1: runner/colony.py became reachable from the CLI import closure"))
    # R-2: the two call-identity schemes must stay distinct.
    orch = normalise((tree / "runner/orchestration.py").read_text())   # rule (f)
    col = normalise((tree / "runner/colony.py").read_text())
    if '"orch:"' not in orch and "'orch:'" not in orch:
        out.append(Problem("R-2: the orch: call-identity prefix is gone from runner/orchestration.py"))
    if '"colony:"' not in col and "'colony:'" not in col:
        out.append(Problem("R-2: the colony: call-identity prefix is gone from runner/colony.py"))
    return out


def check_diff_claims_declare_baseline(tree: pathlib.Path) -> list[Problem]:
    """Rule (e) — a diff without a declared baseline and a definition of "touched" is not evidence."""
    out = []
    for d in DIFF_CHECKS:
        for field in ("check", "baseline", "touched_means"):
            if not d.get(field):
                out.append(Problem("(e) diff-claim %r is missing %s" % (d.get("check"), field)))
    return out


def check_relaxations_recorded(tree: pathlib.Path) -> list[Problem]:
    """Rule (g) — every relaxation states its boundary, cites a doc, and names what it still catches."""
    out = []
    for r in RELAXATIONS:
        for field in ("check", "relaxation", "boundary", "recorded_in", "still_catches"):
            if not r.get(field):
                out.append(Problem("(g) relaxation of %r is missing %s" % (r.get("check"), field)))
        doc = tree / r["recorded_in"]
        if not doc.exists():
            out.append(Problem("(g) relaxation of %r cites %s, which does not exist"
                               % (r["check"], r["recorded_in"])))
    return out


def check_generated_is_current(tree: pathlib.Path) -> list[Problem]:
    """Check 9 — a hand-EDITED generated file is F-24's defect in its next form."""
    out = []
    target = tree / "docs/generated/verification-status.md"
    if not target.exists():
        return [Problem("(9) docs/generated/verification-status.md is missing; run the generator")]
    head = target.read_text().splitlines()[:8]
    if not any(l.startswith("generated-by:") for l in head):
        out.append(Problem("(9) generated file has no machine-readable `generated-by:` header"))
    if not any(l.startswith("generated-from-commit:") for l in head):
        out.append(Problem("(9) generated file does not declare the commit it was generated from"))
    rc = subprocess.run([sys.executable, "tools/generate_verification_status.py", "--check"],
                        cwd=tree, capture_output=True, text=True)
    if rc.returncode != 0:
        out.append(Problem("(9) generated file does not match a fresh run: %s"
                           % (rc.stderr.strip() or rc.stdout.strip())[:120]))
    return out


CHECKS = [
    ("head_matches_worktree", check_head_matches_worktree),
    ("references_resolve", check_references_resolve),
    ("planned_markers", check_planned_markers),
    ("invariant_ids", check_invariant_ids),
    ("enforcement", check_enforcement),
    ("unenforced_ceiling", check_unenforced_ceiling),
    ("adr_numbering", check_adr_numbering),
    ("no_restated_invariants", check_no_restated_invariants),
    ("research_contract", check_research_contract),
    ("diff_claims_declare_baseline", check_diff_claims_declare_baseline),
    ("relaxations_recorded", check_relaxations_recorded),
    ("generated_is_current", check_generated_is_current),
]


def run_all(tree: pathlib.Path) -> tuple[int, list[str]]:
    """Rule (c): a failing check is re-run, and both runs must agree before it is reported."""
    failures, notes = [], []
    for name, fn in CHECKS:
        first = fn(tree)
        if not first:
            notes.append("  ok    %s" % name)
            continue
        second = fn(tree)                              # rule (c)
        if sorted(first) != sorted(second):
            notes.append("  FLAKY %s — two runs disagreed; not reported as a failure" % name)
            failures.append("%s: NONDETERMINISTIC, investigate before acting" % name)
            continue
        notes.append("  FAIL  %s (%d, reproduced)" % (name, len(first)))
        failures += ["%s: %s" % (name, p) for p in first]
    return len(failures), notes + ([""] + failures if failures else [])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--working-tree", action="store_true",
                    help="check the working tree instead of a clean archive (diagnostic only)")
    args = ap.parse_args()

    if args.working_tree:
        print("knowledge-base gate — WORKING TREE (rule (a) suspended; diagnostic only)")
        n, notes = run_all(REPO)
    else:
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="kb-gate-"))
        try:
            subprocess.run("git archive HEAD | tar -x -C %s" % tmp, shell=True, cwd=REPO, check=True)
            print("knowledge-base gate — clean archive of HEAD %s"
                  % sh("git", "rev-parse", "--short", "HEAD").strip())
            n, notes = run_all(tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    print("\n".join(notes))
    print("\n%s — %d problem(s)" % ("FAIL" if n else "PASS", n))
    return 1 if n else 0


if __name__ == "__main__":
    raise SystemExit(main())
