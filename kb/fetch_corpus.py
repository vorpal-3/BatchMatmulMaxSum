#!/usr/bin/env python3
"""Mirror the official Ascend C corpus that matters for operator development.

Why this exists
---------------
The hard part of this problem is not the fused-operator arithmetic; it is
expressing it inside Ascend C on Ascend NPU under the platform's real
constraints. Generic knowledge does not cover that, and a model's parametric
memory of CANN is typically stale (much of it predates CANN 9.0.0 and the
2026 Gitee -> GitCode repository migration). So the knowledge base is built from
primary sources: real, compiling source that ships with the toolkit.

Sources (both reachable from this machine, verified):
  * cann/asc-devkit    - the Ascend C language + API repo (docs/ and examples/)
  * cann/cann-samples  - performance-oriented samples, incl. Samples/2_Performance

GitCode is Gitee-API compatible, so the tree walk uses the public v5 contents API
and file bodies come from raw.gitcode.com. No credentials required.

Usage
-----
    python fetch_corpus.py --list                 # enumerate trees only
    python fetch_corpus.py --fetch                # download matching files
    python fetch_corpus.py --fetch --keyword matmul
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
CORPUS = HERE / "corpus"
INDEX = HERE / "index.jsonl"

API = "https://gitcode.com/api/v5/repos/{repo}/contents/{path}?ref=master"
RAW = "https://raw.gitcode.com/{repo}/raw/master/{path}"

REPOS = {
    "asc-devkit": {"repo": "cann/asc-devkit", "roots": ["examples", "docs"]},
    "cann-samples": {"repo": "cann/cann-samples", "roots": ["Samples"]},
}

TEXT_EXT = {
    ".asc", ".cpp", ".cc", ".cxx", ".c", ".h", ".hpp", ".md", ".txt",
    ".cmake", ".py", ".json", ".sh", ".inc", ".yaml", ".yml",
}

# Keywords that select material relevant to this problem: Cube/matmul execution,
# the two-stage reduction, and the pipeline/tiling machinery.
DEFAULT_KEYWORDS = [
    "matmul", "mmad", "cube", "fixpipe", "l0a", "l0b", "l0c",
    "reduce", "reducemax", "reducesum", "max", "sum",
    "tiling", "doublebuffer", "double_buffer", "pipe", "que",
    "performance", "perf",
]

MAX_FILE_BYTES = 2_000_000


def get(url: str, retries: int = 5) -> bytes:
    """GET with polite backoff. GitCode throttles aggressively (HTTP 429)."""
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "dsh-cann-kb/1.0"})
            with urllib.request.urlopen(req, timeout=45) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code == 429:
                # hard throttle: wait progressively longer and retry
                time.sleep(6.0 * (attempt + 1))
                continue
            if exc.code == 404:
                raise
            time.sleep(1.5 * (attempt + 1))
        except (urllib.error.URLError, TimeoutError) as exc:
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"GET failed: {url}: {last}")


def list_dir(repo: str, path: str) -> list:
    url = API.format(repo=repo, path=urllib.parse.quote(path))
    try:
        data = json.loads(get(url).decode("utf-8", "replace"))
    except Exception as exc:  # noqa: BLE001
        print(f"  ! cannot list {repo}:{path} ({exc})", file=sys.stderr)
        return []
    if isinstance(data, dict):
        return []
    return data


def walk(repo: str, root: str, max_depth: int, max_dirs: int, delay: float, verbose: bool):
    """Yield (path, size) for every file under root, breadth-first and bounded."""
    queue = [(root, 0)]
    seen_dirs = 0
    while queue:
        path, depth = queue.pop(0)
        if depth > max_depth or seen_dirs >= max_dirs:
            continue
        seen_dirs += 1
        entries = list_dir(repo, path)
        time.sleep(delay)
        for e in entries:
            if e.get("type") == "dir":
                queue.append((e["path"], depth + 1))
            else:
                yield e.get("path", ""), int(e.get("size") or 0)
        if verbose:
            print(f"  walked {path} (depth {depth}, {len(entries)} entries)", file=sys.stderr)


def download(repo: str, path: str) -> bytes:
    return get(RAW.format(repo=repo, path=urllib.parse.quote(path)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="enumerate trees only")
    ap.add_argument("--fetch", action="store_true", help="download matching files")
    ap.add_argument("--keyword", action="append", help="extra keyword filter (repeatable)")
    ap.add_argument("--max-depth", type=int, default=4)
    ap.add_argument("--max-dirs", type=int, default=260)
    ap.add_argument("--delay", type=float, default=0.6, help="seconds between API calls")
    ap.add_argument("--root", action="append",
                    help="targeted walk root as name:path (repeatable); overrides the repo defaults")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--all-files", action="store_true",
                    help="do not keyword-filter paths (useful for exploring a tree)")
    args = ap.parse_args()

    if not (args.list or args.fetch):
        ap.print_help()
        return 2

    keywords = [k.lower() for k in (args.keyword or [])] or DEFAULT_KEYWORDS
    CORPUS.mkdir(parents=True, exist_ok=True)

    summary = {}
    records = []

    targets = []
    if args.root:
        for spec_str in args.root:
            if ":" not in spec_str:
                raise SystemExit(f"--root must be name:path, got {spec_str!r}")
            name, root = spec_str.split(":", 1)
            if name not in REPOS:
                raise SystemExit(f"unknown repo name {name!r}; known: {sorted(REPOS)}")
            targets.append((name, REPOS[name]["repo"], root))
    else:
        for name, cfg in REPOS.items():
            for root in cfg["roots"]:
                targets.append((name, cfg["repo"], root))

    for name, repo, root in targets:
        if True:
            print(f"== {name}:{root}")
            count = 0
            for path, size in walk(repo, root, args.max_depth, args.max_dirs, args.delay, args.verbose):
                if not path:
                    continue
                ext = pathlib.PurePosixPath(path).suffix.lower()
                if ext not in TEXT_EXT:
                    continue
                low = path.lower()
                if not args.all_files and not any(k in low for k in keywords):
                    continue
                count += 1
                if args.list:
                    print(f"   {size:>9}  {path}")
                    continue
                if size > MAX_FILE_BYTES:
                    print(f"   skip (too large {size}): {path}")
                    continue
                try:
                    body = download(repo, path)
                    time.sleep(args.delay)
                except Exception as exc:  # noqa: BLE001
                    print(f"   ! download failed {path}: {exc}", file=sys.stderr)
                    continue
                target = CORPUS / name / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(body)
                records.append({
                    "repo": repo,
                    "path": path,
                    "bytes": len(body),
                    "sha256": hashlib.sha256(body).hexdigest(),
                    "local": str(target),
                })
                print(f"   {len(body):>9}  {path}")
            summary[f"{name}:{root}"] = count

    print("\n== summary ==")
    for k, v in summary.items():
        print(f"  {k}: {v} matching files")
    if records:
        with INDEX.open("w", encoding="utf-8") as fh:
            for r in records:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        total = sum(r["bytes"] for r in records)
        print(f"  downloaded {len(records)} files, {total / 1e6:.2f} MB -> {CORPUS}")
        print(f"  index -> {INDEX}")
    elif args.list:
        print("  (listing only; nothing downloaded)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
