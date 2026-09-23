#!/usr/bin/env python3
"""Explode the official CANNJudge problem template into problem/template/.

The template is the组委会-issued project skeleton. Files marked editable=false are
locked: they define the harness contract (how the judge builds, runs and verifies
the operator). Do not modify them; kernel.asc is the only file a contestant edits.

Usage:  python explode_template.py
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "problem" / "template.json"
DST = ROOT / "problem" / "template"


def main() -> int:
    if not SRC.exists():
        print(f"ERROR: {SRC} not found. Download it first:", file=sys.stderr)
        print(
            '  curl.exe -sS -o problem/template.json '
            '"https://cannjudge.cn/api/problems/6a9aa054bf41025d6014f3ef/template"',
            file=sys.stderr,
        )
        return 2

    payload = json.loads(SRC.read_text(encoding="utf-8"))
    files = payload.get("data", {}).get("files", [])
    if not files:
        print("ERROR: no files in template payload", file=sys.stderr)
        return 3

    DST.mkdir(parents=True, exist_ok=True)
    rows = []
    for f in files:
        rel = f["path"]
        target = DST / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        content = f.get("content", "") or ""
        target.write_text(content, encoding="utf-8", newline="")
        blob = content.encode("utf-8")
        digest = hashlib.sha256(blob).hexdigest()[:16]
        rows.append((rel, "EDIT" if f.get("editable") else "locked", len(blob), digest))

    width = max(len(r[0]) for r in rows)
    print(f"exploded {len(rows)} files into {DST}")
    print(f"{'path'.ljust(width)}  edit    bytes  sha256[:16]")
    for rel, ed, n, digest in rows:
        print(f"{rel.ljust(width)}  {ed:<6}  {n:>5}  {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
