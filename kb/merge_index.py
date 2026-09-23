#!/usr/bin/env python3
"""Merge kb/index.jsonl.bak (pre-refetch) with the post-refetch index.

fetch_corpus.py rewrites INDEX with "w", so a targeted refetch silently drops
every previously indexed file. This restores the union, deduped by (repo, path).
"""
import json
import pathlib
import sys

KB = pathlib.Path(__file__).resolve().parent
old_p = KB / "index.jsonl.bak"
new_p = KB / "index.jsonl"

if not old_p.exists():
    print("no backup; nothing to merge")
    sys.exit(0)


def load(p):
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


old, new = load(old_p), load(new_p)
by_key = {}
for r in old + new:
    by_key[(r["repo"], r["path"])] = r
merged = sorted(by_key.values(), key=lambda r: (r["repo"], r["path"]))
with new_p.open("w", encoding="utf-8") as fh:
    for r in merged:
        fh.write(json.dumps(r, ensure_ascii=False) + "\n")
print(f"old={len(old)} new={len(new)} merged={len(merged)}")
print(f"only-in-backup={len({(r['repo'], r['path']) for r in old} - {(r['repo'], r['path']) for r in new})}")
