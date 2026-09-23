#!/usr/bin/env python3
"""Iteration ledger and CANNJudge submission budget guard.

Every optimisation round produces exactly one row. The row is the durable asset:
a later session (or a subagent) reads the ledger instead of re-deriving what was
already tried, which is what keeps an iterative loop from going in circles.

Two separate budgets are tracked, because CANNJudge enforces both:
  * at most 50 submissions per day,
  * at least 2 minutes between two submissions.

The guard refuses a submission that would violate either, rather than letting the
platform reject it.

Ranking caveat that the ledger exists to protect against
--------------------------------------------------------
The problem is ranked with ranking_submission_mode = "latest" and the rules say
"取比赛期间最后一次提交的成绩作为最终成绩". The LAST submission is the score, so a
careless final submission can destroy a good one. `guard.py` therefore also warns
when the most recent submission is worse than the best on record.

Usage
-----
    python guard.py status
    python guard.py can-submit
    python guard.py record --case-scores '{"case01": 91.2}' --mean 88.0 --note "tile 128x256"
    python guard.py best
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
LEDGER = HERE / "ledger.jsonl"

MAX_PER_DAY = 50
MIN_INTERVAL_SECONDS = 180


def load() -> list:
    if not LEDGER.exists():
        return []
    rows = []
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def parse_ts(value: str) -> dt.datetime:
    ts = dt.datetime.fromisoformat(value)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=dt.timezone.utc)
    return ts


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def submissions_today(rows: list) -> list:
    today = now().date()
    return [r for r in rows if parse_ts(r["ts"]).date() == today]


def check_budget(rows: list) -> dict:
    today = submissions_today(rows)
    remaining = MAX_PER_DAY - len(today)
    result = {"submitted_today": len(today), "remaining_today": remaining, "allowed": remaining > 0}

    if rows:
        last = max(parse_ts(r["ts"]) for r in rows)
        elapsed = (now() - last).total_seconds()
        result["seconds_since_last"] = round(elapsed, 1)
        if elapsed < MIN_INTERVAL_SECONDS:
            result["allowed"] = False
            result["wait_seconds"] = round(MIN_INTERVAL_SECONDS - elapsed, 1)
    else:
        result["seconds_since_last"] = None
    return result


def cmd_status(rows: list) -> int:
    budget = check_budget(rows)
    print(f"ledger rows      : {len(rows)}")
    print(f"submitted today  : {budget['submitted_today']} / {MAX_PER_DAY}")
    print(f"remaining today  : {budget['remaining_today']}")
    if budget["seconds_since_last"] is not None:
        print(f"since last submit: {budget['seconds_since_last']:.0f}s (min {MIN_INTERVAL_SECONDS}s)")
    scored = [r for r in rows if r.get("mean_score") is not None]
    if scored:
        best = max(scored, key=lambda r: r["mean_score"])
        print(f"best mean score  : {best['mean_score']:.4f}  ({best.get('note', '')})")
        last_scored = next((r for r in reversed(rows) if r.get("mean_score") is not None), None)
        if last_scored and last_scored["mean_score"] < best["mean_score"]:
            print(f"WARNING: the most recent scored submission ({last_scored['mean_score']:.4f}) "
                  f"is WORSE than the best ({best['mean_score']:.4f}).")
            print("         ranking uses the LATEST submission — do not end the contest here.")
    return 0


def cmd_can_submit(rows: list) -> int:
    budget = check_budget(rows)
    if budget["allowed"]:
        print("ALLOWED")
        return 0
    if budget["remaining_today"] <= 0:
        print("DENIED: daily submission budget exhausted (50/day)")
    else:
        print(f"DENIED: must wait {budget.get('wait_seconds', 0):.0f}s more (minimum 2 minutes between submissions)")
    return 1


def cmd_record(rows: list, args) -> int:
    row = {
        "ts": now().isoformat(),
        "round": len(rows) + 1,
        "kernel_sha256": args.kernel_sha256,
        "note": args.note,
        "case_scores": json.loads(args.case_scores) if args.case_scores else None,
        "mean_score": args.mean,
        "accepted_cases": args.accepted,
        "total_cases": args.total,
        "official_submission_id": args.submission_id,
    }
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"recorded round {row['round']}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("can-submit")
    sub.add_parser("best")
    rec = sub.add_parser("record")
    rec.add_argument("--case-scores", help="JSON object of per-case scores")
    rec.add_argument("--mean", type=float, help="mean score reported by CANNJudge")
    rec.add_argument("--accepted", type=int, help="number of cases that passed precision")
    rec.add_argument("--total", type=int, help="number of cases")
    rec.add_argument("--kernel-sha256", help="sha256 of the submitted kernel.asc")
    rec.add_argument("--submission-id", help="CANNJudge submission id")
    rec.add_argument("--note", default="")
    args = ap.parse_args()

    rows = load()

    if args.cmd == "status":
        return cmd_status(rows)
    if args.cmd == "can-submit":
        return cmd_can_submit(rows)
    if args.cmd == "best":
        scored = [r for r in rows if r.get("mean_score") is not None]
        if not scored:
            print("no scored submissions recorded")
            return 1
        best = max(scored, key=lambda r: r["mean_score"])
        print(json.dumps(best, ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "record":
        return cmd_record(rows, args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
