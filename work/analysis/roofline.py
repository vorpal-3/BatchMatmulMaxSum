#!/usr/bin/env python3
"""Hardware-independent design analysis for BatchMatmulMaxSum.

NO dav-2201 constants are used, because none are grounded in kb/corpus.
Every number below is a ratio or a count that follows from the problem
statement alone (offline/spec.py) plus the dataflow the kernel implements.
That is deliberate: design *ordering* must not depend on unverified card
constants, only on traffic and MAC counts.

Quantities
----------
input_elems   : B*K*(M+N)            -- the only bytes the op MAY read
input_bytes   : input_elems * 2      -- fp16/bf16
macs          : B*M*N*K
ai            : macs / input_bytes   -- arithmetic intensity (MAC/byte)

Design A "materialize" (what work/kernel.asc v005 does today):
    AIC computes the full (M,N) product for a batch block into a GM scratch
    buffer, AIV reads it back to ReduceMax over N then ReduceSum over M.
    scratch traffic = B*M*N*4 written + B*M*N*4 read

Design B "fused" (reduce on-chip, never materialize A in GM):
    traffic = input_bytes (each input element read once)

The point of the table: `scratch/input` needs no card to compute, and it is
the dominant term whenever M,N >> K.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "offline"))
import spec  # noqa: E402

# Representative feasible shapes: the spec envelope corners that matter.
PROBES = [
    # (B,   M,    N,    K,    dtype,     tx1,   tx2,   why)
    (64,   8192, 8192, 32,   "float16", False, False, "max M,N with min K -> worst scratch ratio"),
    (64,   4096, 4096, 64,   "float16", False, False, "large square, K=64"),
    (64,   1024, 1024, 1024, "float16", False, False, "cubic, AI balanced"),
    (64,   256,  256,  4096, "bfloat16", False, False, "long-K, small MN"),
    (1,    8192, 8192, 1024, "float16", False, False, "B=1 max square (no batch parallelism)"),
    (64,   32,   32,   8192, "float16", False, False, "max K, tiny MN"),
    (64,   8192, 32,   256,  "float16", True,  True,  "transposed storage, asymmetric"),
]


def analyze(B, M, N, K, dtype, tx1, tx2, why):
    case = spec.Case(cid=0, B=B, M=M, N=N, K=K, dtype=dtype,
                     transposeX1=tx1, transposeX2=tx2)
    bad = spec.validate(case)
    input_elems = case.input_elements
    input_bytes = input_elems * 2          # fp16 / bf16 both 2 bytes
    macs = case.macs
    ai = macs / input_bytes

    scratch_bytes = B * M * N * 4 * 2      # write A + read A, fp32
    ratio = scratch_bytes / input_bytes

    # Design B: read once. Design A: read once + round-trip the product.
    traffic_a = input_bytes + scratch_bytes
    traffic_b = input_bytes
    return dict(why=why, bad=bad, input_MiB=input_bytes / 2**20,
                macs_g=macs / 1e9, ai=ai, scratch_GiB=scratch_bytes / 2**30,
                ratio=ratio, speedup=traffic_a / traffic_b)


def main():
    print("BatchMatmulMaxSum — dataflow analysis (no card constants used)\n")
    hdr = (f"{'M':>6} {'N':>6} {'K':>6} {'B':>3} {'dtype':>9} "
           f"{'in MiB':>9} {'G-MAC':>9} {'MAC/B':>9} {'scr GiB':>9} "
           f"{'scr/in':>8} {'A/B':>8}")
    print(hdr)
    print("-" * len(hdr))
    rows = []
    for (B, M, N, K, dt, tx1, tx2, why) in PROBES:
        r = analyze(B, M, N, K, dt, tx1, tx2, why)
        if r["bad"]:
            print(f"SKIP infeasible {why}: {r['bad']}")
            continue
        rows.append(r)
        print(f"{M:>6} {N:>6} {K:>6} {B:>3} {dt:>9} "
              f"{r['input_MiB']:>9.1f} {r['macs_g']:>9.2f} {r['ai']:>9.1f} "
              f"{r['scratch_GiB']:>9.2f} {r['ratio']:>7.1f}x {r['speedup']:>7.1f}x")

    print("\nA/B = memory traffic of the current 'materialize A in GM' design vs")
    print("      a fused design that reduces on-chip without ever writing A out.")
    print("      A ratio of 100x+ means the current design's cost is")
    print("      ~entirely self-inflicted and provable without a device.\n")

    print("Derived identities (hardware-independent):")
    print("  scratch/input = 4*M*N / (K*(M+N))")
    print("  ai            = M*N*K / (2*K*(M+N)) = M*N / (2*(M+N))")
    print("  -> ai does NOT depend on B or K. It only depends on M,N.\n")
    for (M, N) in [(8192, 8192), (1024, 1024), (256, 256), (32, 32)]:
        ai = M * N / (2 * (M + N))
        print(f"  M=N={M:<5} ai = {ai:>8.1f} MAC/byte  -> "
              f"{'compute-bound' if ai > 50 else 'memory-bound'}")

    print("\nWorst-case scratch ratio:  M=N=8192, K=32 -> "
          f"{4*8192*8192/(32*(8192+8192)):.0f}x the input traffic")


if __name__ == "__main__":
    main()
