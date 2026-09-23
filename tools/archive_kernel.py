#!/usr/bin/env python3
"""Archive every version of kernel.asc together with why it existed and what it scored.

A pile of kernel snapshots is not an archive. What makes this useful is the join
between four things that otherwise drift apart:

    version  <->  hypothesis (why this change)  <->  on-device outcome  <->  official score

So each archived version gets a .asc byte-copy plus a .json sidecar carrying the
hypothesis, the local verification state, and (after a CANNJudge submission) the
submission id and score. versions/INDEX.md is the human-readable roll-up.

Rules this tool enforces
------------------------
* kernel.asc is archived verbatim by bytes; the sha256 is the identity.
* A version is only "verified" if something actually verified it. Local verification
  can never be anything stronger than spec-level checks, because this machine has no
  NPU and no CANN toolkit. Do not record "verified: works" from a local run.
* Scores attach to a version, not to the repo, so a later round can tell which
  change actually moved the number.

Usage
-----
    python tools/archive_kernel.py --hypothesis "baseline:组委会 skeleton, no compute"
    python tools/archive_kernel.py --hypothesis "DataCopyPad for unaligned tails" \
        --expected "+ precision on tail cases" --local-verification spec
    python tools/archive_kernel.py --list
    python tools/archive_kernel.py --annotate v001 --submission-id 123456 --mean 0.0
    python tools/archive_kernel.py --commit          # git add + commit the archive
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
KERNEL = ROOT / "work" / "kernel.asc"
VERSIONS = ROOT / "versions"
INDEX = VERSIONS / "INDEX.md"

VERIFICATION_LEVELS = (
    "none",                 # not checked at all
    "spec",                 # arithmetic / spec-conformance checked locally against the golden
    "compiled-on-device",   # CANN compiler accepted it on a real CANN machine
    "precision-on-device",  # ran and passed the precision gate on device / CANNJudge
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def existing_versions() -> list:
    out = []
    for p in sorted(VERSIONS.glob("kernel.v*.json")):
        m = re.search(r"kernel\.v(\d+)\.json$", p.name)
        if m:
            out.append((int(m.group(1)), p))
    return out


def next_version() -> int:
    vs = existing_versions()
    return (max(v for v, _ in vs) + 1) if vs else 1


def sidecars() -> list:
    return [json.loads(p.read_text(encoding="utf-8")) for _, p in existing_versions()]


def write_index() -> None:
    rows = sidecars()
    lines = [
        "# kernel.asc 版本留档",
        "",
        "每一版 kernel.asc 的字节副本 + 假设 + 验证状态 + 官方得分。",
        "得分只在真机/CANNJudge 上产生；本机**不可能**产生 `precision-on-device`。",
        "",
        "| 版本 | sha256[:12] | 本地验证 | 官方均分 | submission | 假设 |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        score = r.get("official_mean_score")
        score_s = f"{score:.4f}" if isinstance(score, (int, float)) else "—"
        hyp = (r.get("hypothesis") or "").replace("|", "\\|")
        if len(hyp) > 70:
            hyp = hyp[:67] + "..."
        lines.append(
            f"| {r['version']} | `{r['sha256'][:12]}` | {r.get('local_verification', 'none')} "
            f"| {score_s} | {r.get('official_submission_id') or '—'} | {hyp} |"
        )
    lines.append("")
    INDEX.write_text("\n".join(lines), encoding="utf-8")


def cmd_archive(args) -> int:
    if not KERNEL.exists():
        print(f"ERROR: kernel not found: {KERNEL}", file=sys.stderr)
        return 2
    if args.local_verification not in VERIFICATION_LEVELS:
        print(f"ERROR: --local-verification must be one of {VERIFICATION_LEVELS}", file=sys.stderr)
        return 2
    # Device-level verification must come with its evidence. This machine cannot
    # compile or run Ascend C, so such a claim can only be earned on the CANNLab
    # instance (same CANN/bisheng version as the judge) — and that is exactly why
    # the detail is mandatory rather than the claim being refused outright.
    if args.local_verification in ("compiled-on-device", "precision-on-device"):
        if not args.verification_detail:
            print("ERROR: device-level verification requires --verification-detail naming "
                  "where and with which toolchain it was obtained (e.g. CANNLab instance, "
                  "CANN 9.0.0, bisheng clang 15.0.5, cmake/make exit codes).", file=sys.stderr)
            return 2
        if "cann" not in args.verification_detail.lower():
            print("ERROR: --verification-detail must name the CANN environment used.", file=sys.stderr)
            return 2

    data = KERNEL.read_bytes()
    digest = sha256_bytes(data)

    for r in sidecars():
        if r["sha256"] == digest:
            print(f"NOTE: byte-identical to existing {r['version']} — nothing new to archive.")
            print(f"      (kernel.asc sha256 {digest[:16]})")
            return 0

    v = next_version()
    tag = f"v{v:03d}"
    VERSIONS.mkdir(parents=True, exist_ok=True)
    (VERSIONS / f"kernel.{tag}.asc").write_bytes(data)

    meta = {
        "version": tag,
        "file": f"versions/kernel.{tag}.asc",
        "sha256": digest,
        "bytes": len(data),
        "archived_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "hypothesis": args.hypothesis,
        "expected_effect": args.expected or "",
        "local_verification": args.local_verification,
        "local_verification_detail": args.verification_detail or "",
        "official_submission_id": None,
        "official_mean_score": None,
        "ledger_round": None,
        "notes": args.notes or "",
    }
    (VERSIONS / f"kernel.{tag}.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    write_index()
    print(f"archived {tag}  sha256={digest[:16]}  bytes={len(data)}")
    print(f"  {VERSIONS / f'kernel.{tag}.asc'}")

    if args.commit:
        return git_commit(f"kernel {tag}: {args.hypothesis or 'archive'}")
    return 0


def cmd_list(args) -> int:
    rows = sidecars()
    if not rows:
        print("no archived versions yet")
        return 0
    for r in rows:
        score = r.get("official_mean_score")
        print(f"{r['version']}  {r['sha256'][:12]}  local={r.get('local_verification', 'none'):<20} "
              f"score={score if score is not None else '—'}  {(r.get('hypothesis') or '')[:60]}")
    return 0


def cmd_annotate(args) -> int:
    matches = [p for p, _ in [(p, None) for p in VERSIONS.glob(f"kernel.{args.annotate}.json")]]
    if not matches:
        print(f"ERROR: no such version: {args.annotate}", file=sys.stderr)
        return 2
    path = matches[0]
    meta = json.loads(path.read_text(encoding="utf-8"))
    if args.submission_id:
        meta["official_submission_id"] = args.submission_id
    if args.mean is not None:
        meta["official_mean_score"] = args.mean
    if args.ledger_round is not None:
        meta["ledger_round"] = args.ledger_round
    if args.notes:
        meta["notes"] = (meta.get("notes", "") + "\n" + args.notes).strip()
    if args.submission_id or args.mean is not None:
        # a device/CANNJudge outcome is the only thing that can raise this
        meta["local_verification"] = "precision-on-device" if args.mean is not None and args.mean > 0 \
            else "compiled-on-device"
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    write_index()
    print(f"annotated {args.annotate}: submission={meta.get('official_submission_id')} "
          f"mean={meta.get('official_mean_score')} verification={meta.get('local_verification')}")
    if args.commit:
        return git_commit(f"kernel {args.annotate}: record CANNJudge outcome")
    return 0


def git_commit(message: str) -> int:
    try:
        subprocess.run(["git", "-C", str(ROOT), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(ROOT), "commit", "-q", "-m", message], check=True)
        head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
        print(f"  committed {head}: {message}")
        return 0
    except subprocess.CalledProcessError as exc:
        print(f"  git commit failed: {exc}", file=sys.stderr)
        return 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hypothesis", help="why this version exists")
    ap.add_argument("--expected", help="expected effect on correctness/performance")
    ap.add_argument("--local-verification", default="none", choices=VERIFICATION_LEVELS)
    ap.add_argument("--verification-detail", help="what exactly was checked locally")
    ap.add_argument("--notes", default="")
    ap.add_argument("--commit", action="store_true", help="git add + commit after archiving")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--annotate", metavar="vNNN", help="attach device/CANNJudge results to a version")
    ap.add_argument("--submission-id")
    ap.add_argument("--mean", type=float)
    ap.add_argument("--ledger-round", type=int)
    args = ap.parse_args()

    if args.list:
        return cmd_list(args)
    if args.annotate:
        return cmd_annotate(args)
    if not args.hypothesis:
        ap.error("--hypothesis is required when archiving a new version")
    return cmd_archive(args)


if __name__ == "__main__":
    raise SystemExit(main())
