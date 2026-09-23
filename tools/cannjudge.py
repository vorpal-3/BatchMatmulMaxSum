#!/usr/bin/env python3
"""CANNJudge client: submit a kernel, read the per-case verdict, record the round.

The request contract was captured from a real submission (wire-level), not guessed:

    POST https://cannjudge.cn/api/submissions/submit
    Content-Type: application/json
    Cookie: cannjudge_auth=<JWT>
    {
      "problemId": "<problem object id>",
      "files": [{"path": "kernel.asc", "content": "<source>"}],
      "tiling_h": "", "tiling_key_h": "", "host_cpp": "", "kernel_cpp": "",
      "userId": "<numeric uid from the session>"
    }
    -> {"code":0,"msg":"success","data":{"submissionId":"<id>"}}

Only kernel.asc was sent by the real browser editor; the other four slots are
optional extra translation units and stay empty for this problem.

    GET https://cannjudge.cn/api/submissions/<id>?userId=<uid>
    -> {... "status": "...", "result": [ 15 x {
            "testcase_id", "time", "precision_ratio", "testcase_status",
            "msg", "score", "type", "best_time" } ] }

Why `best_time` matters
-----------------------
The per-case score is 100 / (1 + log_1.5(t/T)) where T is the best known time.
T is not published, but the judge returns `best_time` per testcase, so a real
submission reveals the T table. That is what lets a local evaluation set be
calibrated against official scores instead of merely guessed at.

Auth
----
The token is a live credential for the account. It is read from, in order:
  1. $CANNJUDGE_AUTH
  2. .secrets/cannjudge.json   (gitignored)
It is never printed by this tool.

Usage
-----
    python tools/cannjudge.py whoami
    python tools/cannjudge.py budget
    python tools/cannjudge.py submit --kernel work/kernel.asc --dry-run
    python tools/cannjudge.py submit --kernel work/kernel.asc
    python tools/cannjudge.py result <submissionId>
    python tools/cannjudge.py wait <submissionId> --timeout 900
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
SECRETS = ROOT / ".secrets" / "cannjudge.json"
BASE = "https://cannjudge.cn"

# The competition problem (2026 CANN Challenge, 上合赛区, 初赛).
SHANGHE_PROBLEM_ID = "6a9aa054bf41025d6014f3ef"
# Practice problem of the same kernel pattern (Cube), safe target for dry runs.
CUBE_PRACTICE_PROBLEM_ID = "6a96ae38bf41025d607d1950"

IN_PROGRESS = ("running", "pending", "queued", "judging", "waiting")


def load_guard():
    """Import ledger/guard.py by path so the budget rules stay in one place."""
    spec = importlib.util.spec_from_file_location("ledger_guard", ROOT / "ledger" / "guard.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_auth() -> tuple:
    import os
    token = os.environ.get("CANNJUDGE_AUTH")
    uid = os.environ.get("CANNJUDGE_USER_ID")
    if token and uid:
        return token, uid
    if SECRETS.exists():
        # utf-8-sig: tolerate a BOM, which Windows PowerShell's Set-Content -Encoding utf8 writes
        data = json.loads(SECRETS.read_text(encoding="utf-8-sig"))
        return token or data.get("auth"), uid or data.get("userId")
    raise SystemExit(
        "no credentials. Set $CANNJUDGE_AUTH and $CANNJUDGE_USER_ID, or create "
        f"{SECRETS} with {{\"auth\": \"...\", \"userId\": \"...\"}}"
    )


def request(method: str, path: str, token: str, body: dict | None = None) -> tuple:
    headers = {
        "Cookie": f"cannjudge_auth={token}",
        "Accept": "*/*",
        "Accept-Language": "zh-CN",
        "User-Agent": "dsh-cannjudge/1.0",
        "Origin": BASE,
        "Referer": f"{BASE}/",
    }
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read()
    try:
        return resp.status, json.loads(raw.decode("utf-8"))
    except Exception:  # noqa: BLE001
        return resp.status, {"_raw": raw[:500].decode("utf-8", "replace")}


def cmd_whoami(args) -> int:
    token, uid = load_auth()
    status, payload = request("GET", f"/api/submissions/user/{uid}/problem/{SHANGHE_PROBLEM_ID}", token)
    print(f"http {status}  uid={uid}  token={token[:12]}...({len(token)} chars)")
    subs = payload if isinstance(payload, list) else payload.get("data") or []
    print(f"submissions on the competition problem: {len(subs) if isinstance(subs, list) else '?'}")
    return 0


def cmd_budget(args) -> int:
    guard = load_guard()
    rows = guard.load()
    return guard.cmd_status(rows)


def cmd_submit(args) -> int:
    guard = load_guard()
    rows = guard.load()
    decision = guard.check_budget(rows)

    kernel = pathlib.Path(args.kernel)
    if not kernel.exists():
        print(f"ERROR: kernel not found: {kernel}", file=sys.stderr)
        return 2
    source = kernel.read_text(encoding="utf-8", errors="replace")
    import hashlib
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()

    print(f"kernel      : {kernel}  ({len(source)} chars, sha256 {digest[:16]})")
    print(f"problem     : {args.problem}")
    print(f"budget      : {decision['submitted_today']}/50 today, "
          f"{decision['remaining_today']} remaining")

    if not decision["allowed"]:
        if decision["remaining_today"] <= 0:
            print("DENIED: daily submission budget exhausted")
        else:
            print(f"DENIED: wait {decision.get('wait_seconds', 0):.0f}s "
                  f"(minimum 2 minutes between submissions)")
        return 1

    if args.dry_run:
        print("DRY RUN: request not sent.")
        return 0

    token, uid = load_auth()
    body = {
        "problemId": args.problem,
        "files": [{"path": "kernel.asc", "content": source}],
        "tiling_h": "",
        "tiling_key_h": "",
        "host_cpp": "",
        "kernel_cpp": "",
        "userId": uid,
    }
    status, payload = request("POST", "/api/submissions/submit", token, body)
    if payload.get("code") != 0:
        print(f"SUBMIT FAILED: http {status} payload={json.dumps(payload)[:300]}", file=sys.stderr)
        return 1

    sid = payload["data"]["submissionId"]
    print(f"submitted   : submissionId={sid}")

    row = {
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
        "round": len(rows) + 1,
        "kernel_sha256": digest,
        "note": args.note or "",
        "case_scores": None,
        "mean_score": None,
        "accepted_cases": None,
        "total_cases": None,
        "official_submission_id": sid,
    }
    with (ROOT / "ledger" / "ledger.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"ledger      : round {row['round']} recorded")
    return 0


def fetch_result(sid: str) -> dict:
    token, uid = load_auth()
    status, payload = request("GET", f"/api/submissions/{sid}?userId={uid}", token)
    if status != 200:
        raise SystemExit(f"result fetch failed: http {status}")
    return payload


def cmd_result(args) -> int:
    payload = fetch_result(args.submission_id)
    cases = payload.get("result") or []
    print(f"submission  : {args.submission_id}  (ID {payload.get('ID')})")
    print(f"status      : {payload.get('status')}   valid={payload.get('valid')}")
    print(f"created     : {payload.get('create_time')}")
    if not cases:
        print("no per-case results yet")
        return 0
    print()
    print(f"{'#':<3}{'status':<16}{'score':>8}{'prec_ratio':>12}{'time':>12}{'best_time':>12}  msg")
    print("-" * 100)
    total = 0.0
    scored = 0
    for i, c in enumerate(cases, 1):
        total += c.get("score") or 0
        if c.get("score"):
            scored += 1
        msg = (c.get("msg") or "").replace("\n", " ")[:52]
        print(f"{i:<3}{str(c.get('testcase_status'))[:15]:<16}{c.get('score', 0):>8}"
              f"{c.get('precision_ratio', 0):>12}{c.get('time', 0):>12}"
              f"{str(c.get('best_time')):>12}  {msg}")
    print("-" * 100)
    if cases:
        print(f"mean score over {len(cases)} cases: {total / len(cases):.4f}  "
              f"(cases with score>0: {scored})")

    # persist the T table we just learned: best_time per testcase is the official
    # best-known time and is the only source of T for local calibration.
    ttable = {
        f"case{i:02d}": {"testcase_id": c.get("testcase_id"), "best_time": c.get("best_time")}
        for i, c in enumerate(cases, 1)
    }
    out = ROOT / "ledger" / f"best_times.{args.submission_id}.json"
    out.write_text(json.dumps(
        {"submission_id": args.submission_id, "status": payload.get("status"),
         "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(), "cases": ttable},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"T table written: {out}")
    return 0


def cmd_wait(args) -> int:
    deadline = time.time() + args.timeout
    last = None
    while time.time() < deadline:
        payload = fetch_result(args.submission_id)
        status = str(payload.get("status") or "")
        if status != last:
            print(f"[{dt.datetime.now().strftime('%H:%M:%S')}] status={status}")
            last = status
        if status.strip().lower() not in IN_PROGRESS:
            print("terminal status reached")
            return cmd_result(args)
        time.sleep(args.interval)
    print(f"timed out after {args.timeout}s; last status={last}")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("whoami")
    sub.add_parser("budget")

    s = sub.add_parser("submit")
    s.add_argument("--kernel", default="work/kernel.asc")
    s.add_argument("--problem", default=SHANGHE_PROBLEM_ID)
    s.add_argument("--practice", action="store_true",
                   help=f"target the Cube practice problem ({CUBE_PRACTICE_PROBLEM_ID}) instead")
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--note", default="")

    r = sub.add_parser("result")
    r.add_argument("submission_id")

    w = sub.add_parser("wait")
    w.add_argument("submission_id")
    w.add_argument("--timeout", type=int, default=900)
    w.add_argument("--interval", type=float, default=10.0)

    args = ap.parse_args()
    if getattr(args, "practice", False):
        args.problem = CUBE_PRACTICE_PROBLEM_ID

    if args.cmd == "whoami":
        return cmd_whoami(args)
    if args.cmd == "budget":
        return cmd_budget(args)
    if args.cmd == "submit":
        return cmd_submit(args)
    if args.cmd == "result":
        return cmd_result(args)
    if args.cmd == "wait":
        return cmd_wait(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
