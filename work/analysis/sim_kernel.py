#!/usr/bin/env python3
"""Simulator for the BatchMatmulMaxSum tiling / partition / reduction scheme.

WHY THIS EXISTS
---------------
Every kernel version so far died on *logic* errors (bad offsets, bad tails,
mismatched partition cover, wrong reduce order, wrong transpose mapping), not
on hardware. Those are all reproducible on the host in a few lines of numpy.

This file models EXACTLY the scheme `kernel.asc` implements:

  partition : tiles over (batch, m-block), tile index t = b*nMBlocks + mb
              core c owns tiles with (t % nCores) == c
  compute   : for each owned tile, for each n-block:
                 S = X1[mBlock, K] @ X2[K, nBlock]      (fp32 accumulate)
                 rowmax[mBlock] = max over n of S
              running per-(core,batch) partial = sum over m of rowmax
  combine   : partials[core][b] summed into y[b]

The simulator asserts:
  * the partition covers every (b, m) exactly once
  * the (possibly partial) m-blocks and n-blocks and k-blocks are handled
  * storage transposes map to the logical matrices correctly
  * the final y matches the组委会 golden within the judge's gate

Run:  .venv/Scripts/python.exe work/analysis/sim_kernel.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "offline"))
import spec  # noqa: E402

NEG_INF = float("-inf")


# --------------------------------------------------------------------------
# the scheme, exactly as the kernel will implement it
# --------------------------------------------------------------------------

def logical_views(x1, x2, tx1, tx2):
    """Map stored tensors to the logical (B,M,K) and (B,K,N)."""
    # x1 storage: (B,M,K) or (B,K,M)
    x1l = np.swapaxes(x1, -1, -2) if tx1 else x1
    # x2 storage: (B,K,N) or (B,N,K)
    x2l = np.swapaxes(x2, -1, -2) if tx2 else x2
    return x1l, x2l


def simulate(x1, x2, B, M, N, K, tx1, tx2, ncores, tile_m, tile_n, tile_k,
             acc_dtype=np.float32):
    """Return (y, partitions_seen) using the kernel's partition + reduction."""
    x1l, x2l = logical_views(x1, x2, tx1, tx2)
    x1l = x1l.astype(acc_dtype)
    x2l = x2l.astype(acc_dtype)

    nMBlocks = (M + tile_m - 1) // tile_m
    nTiles = B * nMBlocks

    partials = np.zeros((ncores, B), dtype=np.float32)
    cover = np.zeros((B, M), dtype=np.int32)   # how many times each (b,m) is hit

    for t in range(nTiles):
        core = t % ncores
        b = t // nMBlocks
        mb = t % nMBlocks
        m0 = mb * tile_m
        m1 = min(m0 + tile_m, M)
        rows = m1 - m0
        cover[b, m0:m1] += 1

        # running per-row max over the full N, accumulated across n-blocks with -inf init
        rowmax = np.full(rows, NEG_INF, dtype=np.float32)

        for n0 in range(0, N, tile_n):
            n1 = min(n0 + tile_n, N)
            cols = n1 - n0

            # S = X1[m0:m1, :] @ X2[:, n0:n1], accumulated over k-blocks
            S = np.zeros((rows, cols), dtype=acc_dtype)
            for k0 in range(0, K, tile_k):
                k1 = min(k0 + tile_k, K)
                a = x1l[b, m0:m1, k0:k1]          # (rows, kk)
                bb = x2l[b, k0:k1, n0:n1]         # (kk, cols)
                S += (a @ bb).astype(acc_dtype) if a.dtype != np.float32 else a @ bb

            rowmax = np.maximum(rowmax, S.max(axis=1).astype(np.float32))

        partials[core, b] += np.float32(rowmax.sum())

    # combine phase: sum the per-core partials for each batch
    y = partials.sum(axis=0).astype(np.float32)
    return y, cover, partials


# --------------------------------------------------------------------------
# checks
# --------------------------------------------------------------------------

def check_case(case, ncores, tile_m, tile_n, tile_k, acc_dtype=np.float32):
    rng = np.random.default_rng(1234 + case.cid)
    x1, x2 = spec.build_inputs(case, rng)
    y, cover, partials = simulate(
        x1, x2, case.B, case.M, case.N, case.K,
        case.transposeX1, case.transposeX2,
        ncores, tile_m, tile_n, tile_k, acc_dtype,
    )
    golden = spec.golden(x1, x2, case.transposeX1, case.transposeX2)
    gate = spec.precision_check(y, golden)

    problems = []
    if not np.all(cover == 1):
        problems.append(f"partition cover != 1 everywhere (min={cover.min()}, max={cover.max()})")
    if y.shape != (case.B,):
        problems.append(f"y shape {y.shape} != ({case.B},)")
    if not np.all(np.isfinite(y)):
        problems.append("y has non-finite values")
    if not gate["passed"]:
        problems.append(f"precision gate failed: err={gate['errors']}/{gate['total']} "
                        f"max_diff={gate['max_diff']:.3e}")
    return problems, gate


def main():
    print("BatchMatmulMaxSum — tiling/partition/reduction simulator\n")

    # (B, M, N, K, dtype, tx1, tx2, label)
    cases = [
        (1,    1,    1,    32,   "float16",  False, False, "local harness case0"),
        (1,    1,    1,    32,   "float16",  True,  True,  "case0, both transposed"),
        (2,    64,   64,   32,   "float16",  False, False, "small square"),
        (4,    33,   17,   40,   "float16",  False, False, "ragged tails"),
        (3,    17,   33,   40,   "float16",  True,  False, "ragged + tx1"),
        (3,    17,   33,   40,   "float16",  False, True,  "ragged + tx2"),
        (5,    128,  96,   64,   "bfloat16", False, False, "bf16"),
        (2,    256,  256,  128,  "float16",  True,  True,  "bigger, both transposed"),
        (64,   8,    8,    32,   "float16",  False, False, "max batch"),
        (1,    512,  512,  32,   "float16",  False, False, "B=1 wide, few cores busy"),
    ]

    ncores = 20
    print(f"cores={ncores}  tile_m=32 tile_n=64 tile_k=64  acc=float32\n")
    hdr = f"{'case':<28} {'B':>3} {'M':>5} {'N':>5} {'K':>5} {'dtype':>9}  result"
    print(hdr)
    print("-" * len(hdr))

    bad = 0
    for (B, M, N, K, dt, tx1, tx2, label) in cases:
        case = spec.Case(cid=B * 1000 + M, B=B, M=M, N=N, K=K, dtype=dt,
                         transposeX1=tx1, transposeX2=tx2)
        viol = spec.validate(case)
        if viol:
            print(f"{label:<28} INFEASIBLE: {viol}")
            continue
        problems, gate = check_case(case, ncores, 32, 64, 64)
        if problems:
            bad += 1
            print(f"{label:<28} {B:>3} {M:>5} {N:>5} {K:>5} {dt:>9}  FAIL")
            for p in problems:
                print(f"{'':<28}   - {p}")
        else:
            print(f"{label:<28} {B:>3} {M:>5} {N:>5} {K:>5} {dt:>9}  OK "
                  f"(max_diff={gate['max_diff']:.2e})")

    print()
    # Does fp16 accumulation survive the 1e-4 gate as K grows? This decides
    # whether the kernel may accumulate in the input dtype or must use fp32.
    print("fp16 input, fp16 accumulation vs fp32 accumulation (gate rtol=atol=1e-4):")
    print(f"{'K':>6} {'fp32 max_diff':>16} {'fp16 max_diff':>16} {'fp16 passes?':>14}")
    for K in (32, 256, 1024, 4096, 8192):
        case = spec.Case(cid=0, B=1, M=16, N=16, K=K, dtype="float16")
        if spec.validate(case):
            print(f"{K:>6}  INFEASIBLE")
            continue
        rng = np.random.default_rng(7)
        x1, x2 = spec.build_inputs(case, rng)
        golden = spec.golden(x1, x2, False, False)
        y32, _, _ = simulate(x1, x2, 1, 16, 16, K, False, False, ncores, 8, 16, 64, np.float32)
        y16, _, _ = simulate(x1, x2, 1, 16, 16, K, False, False, ncores, 8, 16, 64, np.float16)
        g32 = spec.precision_check(y32, golden)
        g16 = spec.precision_check(y16, golden)
        print(f"{K:>6} {g32['max_diff']:>16.3e} {g16['max_diff']:>16.3e} "
              f"{str(g16['passed']):>14}")

    print()
    print(f"cases failing: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
