#!/usr/bin/env python3
"""Generate docs/generated/verification-status.md from the suite and the invariant register.

Verification status is GENERATED, never hand-written. A hand-maintained count drifts silently and
then lies: the retired verification document reported 964 passing tests against an actual 1016, and
two of its eight per-file counts were wrong (F-24). ARCHITECTURE.md's opening constraint evicts every
"was exercised" claim from prose; this is where they land instead.

Usage:  python tools/generate_verification_status.py [--check]

  (no flag)  rewrite docs/generated/verification-status.md
  --check    exit 1 if the committed file differs from what would be generated now
"""
from __future__ import annotations

import argparse
import datetime
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TESTS = "tests/interaction/"
OUT = ROOT / "docs" / "generated" / "verification-status.md"
REGISTER = ROOT / "docs" / "invariants.md"
GENERATOR = "tools/generate_verification_status.py"


def _python() -> str:
    venv = ROOT / ".venv" / "bin" / "python"
    return str(venv) if venv.exists() else sys.executable


def collect_node_ids() -> set[str]:
    """Every test node pytest can collect, as `file.py::name`."""
    out = subprocess.run([_python(), "-m", "pytest", "--collect-only", "-q"],
                         cwd=ROOT, capture_output=True, text=True).stdout
    ids = set()
    for line in out.splitlines():
        line = line.strip()
        if "::" not in line:
            continue
        ids.add(line.split("[")[0].removeprefix(TESTS))
    return ids


def run_suite() -> tuple[int, int, str]:
    """(passed, failed, raw summary line) for the whole suite."""
    out = subprocess.run([_python(), "-m", "pytest", "-q"],
                         cwd=ROOT, capture_output=True, text=True).stdout
    tail = [l for l in out.splitlines() if l.strip()][-1] if out.strip() else ""
    passed = int(m.group(1)) if (m := re.search(r"(\d+) passed", tail)) else 0
    failed = int(m.group(1)) if (m := re.search(r"(\d+) failed", tail)) else 0
    # Strip the wall-clock duration: it differs on every run, so leaving it in would make
    # --check report a freshly generated file as stale. Counts are the signal, timing is not.
    return passed, failed, re.sub(r"\s+in\s+[\d.]+s$", "", tail)


ENTRY = re.compile(r"^### ((?:L|R)-\d+(?:\.\w+)?) · (.+)$", re.M)
ENFORCE = re.compile(r"`kind: (test|fixture|lint|schema|delegated)\s+([^`]+)`")
UNENF = re.compile(r"`UNENFORCED \(([^)]*)\)`")


def parse_register() -> list[dict]:
    """Every invariant with its enforcement entries, in register order."""
    text = REGISTER.read_text()
    marks = list(ENTRY.finditer(text))
    entries = []
    for i, m in enumerate(marks):
        body = text[m.end(): marks[i + 1].start() if i + 1 < len(marks) else len(text)]
        refs = [{"kind": k, "ref": r.strip()} for k, r in ENFORCE.findall(body)]
        refs += [{"kind": "UNENFORCED", "ref": u.strip()} for u in UNENF.findall(body)]
        entries.append({"id": m.group(1), "title": m.group(2).strip(), "refs": refs})
    return entries


def resolve(entries: list[dict], ids: set[str]) -> None:
    """Annotate each enforcement reference with whether it resolves."""
    known = {e["id"] for e in entries}
    for e in entries:
        for r in e["refs"]:
            if r["kind"] == "test":
                r["ok"] = r["ref"] in ids
                r["note"] = "resolves" if r["ok"] else "DOES NOT RESOLVE"
            elif r["kind"] == "fixture":
                path, _, name = r["ref"].partition("::")
                src = ROOT / "tests" / "interaction" / path
                body = src.read_text() if src.exists() else ""
                r["ok"] = bool(re.search(r"^def %s\(" % re.escape(name), body, re.M))
                auto = "autouse=True" in body
                r["note"] = ("defined, autouse" if r["ok"] and auto
                             else "defined" if r["ok"] else "DOES NOT RESOLVE")
            elif r["kind"] == "delegated":
                target = r["ref"].strip()
                r["ok"] = target in known
                r["note"] = "delegated to %s" % target if r["ok"] else "DANGLING DELEGATION"
            elif r["kind"] == "UNENFORCED":
                r["ok"] = bool(re.search(r"gate\s+G[\d.]+", r["ref"]))
                r["note"] = r["ref"] if r["ok"] else "NO CLOSING GATE NAMED"
            else:
                r["ok"], r["note"] = True, r["kind"]


def render(entries: list[dict], passed: int, failed: int, tail: str, sha: str) -> str:
    unenf = [(e, r) for e in entries for r in e["refs"] if r["kind"] == "UNENFORCED"]
    broken = [(e, r) for e in entries for r in e["refs"] if not r.get("ok", True)]
    files: dict[str, int] = {}
    for e in entries:
        for r in e["refs"]:
            if r["kind"] == "test":
                files[r["ref"].split("::")[0]] = files.get(r["ref"].split("::")[0], 0) + 1

    L = ["---",
         "generated: true",
         "generated-by: %s" % GENERATOR,
         "generated-from-commit: %s" % sha,
         "generated-on: %s" % datetime.date.today().isoformat(),
         "edit: never — regenerate instead; a hand-edited generated file is F-24 in its next form",
         "---", "",
         "# Verification status", "",
         "Regenerate with `python tools/generate_verification_status.py`.",
         "Every number here is measured, never typed. Hand-maintained counts are F-24's root cause.", "",
         "| | |", "|---|---|",
         "| Suite result | `%s` |" % tail,
         "| Tests passed | **%d** |" % passed,
         "| Tests failed | **%d** |" % failed,
         "| Invariants in register | %d |" % len(entries),
         "| Enforcement references | %d |" % sum(len(e["refs"]) for e in entries),
         "| Unenforced entries | **%d** |" % len(unenf),
         "| References that do not resolve | **%d** |" % len(broken), "",
         "## Enforcement resolution", "",
         "| ID | Title | Kind | Reference | Result |", "|---|---|---|---|---|"]
    for e in entries:
        for r in e["refs"]:
            mark = "" if r.get("ok", True) else " ⚠"
            ref = r["ref"] if r["kind"] != "UNENFORCED" else "—"
            L.append("| `%s` | %s | %s | `%s` | %s%s |"
                     % (e["id"], e["title"][:58], r["kind"], ref[:76], r["note"][:44], mark))
    L += ["", "## Enforcement references per test file", "", "| File | References |", "|---|---|"]
    for f, n in sorted(files.items(), key=lambda kv: -kv[1]):
        L.append("| `%s%s` | %d |" % (TESTS, f, n))
    L += ["", "## Unenforced register", "",
          "The ceiling is the count above. Raising it fails the gate; lowering it is a normal commit.",
          "", "| ID | Title | Why / closing gate |", "|---|---|---|"]
    for e, r in unenf:
        L.append("| `%s` | %s | %s |" % (e["id"], e["title"][:56], r["ref"][:56]))
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if the committed file is stale")
    args = ap.parse_args()

    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                         capture_output=True, text=True).stdout.strip() or "unknown"
    entries = parse_register()
    ids = collect_node_ids()
    resolve(entries, ids)
    passed, failed, tail = run_suite()
    body = render(entries, passed, failed, tail, sha)

    if args.check:
        if not OUT.exists():
            print("verification-status.md is missing; run the generator", file=sys.stderr)
            return 1
        # the commit sha and date legitimately differ between runs; compare the rest
        # the commit and date legitimately differ between runs; everything else must match
        strip = lambda t: "\n".join(l for l in t.splitlines()
                                    if not l.startswith(("generated-from-commit:", "generated-on:")))
        if strip(OUT.read_text()) != strip(body):
            print("verification-status.md is stale; regenerate it", file=sys.stderr)
            return 1
        print("verification-status.md is current")
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(body)
    print("wrote %s — %d passed, %d unenforced, %d unresolved"
          % (OUT.relative_to(ROOT), passed,
             sum(1 for e in entries for r in e["refs"] if r["kind"] == "UNENFORCED"),
             sum(1 for e in entries for r in e["refs"] if not r.get("ok", True))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
