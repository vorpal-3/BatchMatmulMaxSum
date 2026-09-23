#!/usr/bin/env python3
"""Dev-visible correctness tests for the shared spec module.

These use only material that is public to contestants:
  * the three worked examples printed in the problem statement,
  * an invariant implied by the storage-layout rule.

The组委会 golden script (problem/template/scripts/BatchMatmulMaxSum.py) checks
examples 1 and 3 only. Example 2 — the transpose storage layout — is NOT covered
there, and it is the one most likely to be implemented wrongly, so it is checked
here.

The invariant test is stronger than all three examples: for any logical X1, X2,
feeding them in transposed physical layout with transposeX1/transposeX2 = true
must produce exactly the same y as feeding them in normal layout with the flags
false. A symmetric identity matrix (as used by example 2) hides transpose bugs;
random asymmetric matrices do not.

Usage:  python spec_examples.py
"""
from __future__ import annotations

import pathlib
import sys

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import spec  # noqa: E402


def example_1() -> None:
    """Basic computation -> y = [2.0]."""
    x1 = np.array([[[1.0, 0.0], [0.0, 1.0]]], dtype=np.float16)
    x2 = np.array([[[1.0, 0.0, -1.0], [0.0, 1.0, 0.0]]], dtype=np.float16)
    y = spec.golden(x1, x2, False, False)
    np.testing.assert_array_equal(y, np.array([2.0], dtype=np.float32))


def example_2() -> None:
    """Transposed storage layout -> y = [2.0], and no explicit transpose is performed.

    Logical x1 (B,M,K) = (1,2,2); stored as (B,K,M).
    Logical x2 (B,K,N) = (1,2,3); stored as (B,N,K).
    """
    x1_logical = np.array([[[1.0, 0.0], [0.0, 1.0]]], dtype=np.float16)
    x2_logical = np.array([[[1.0, 0.0, -1.0], [0.0, 1.0, 0.0]]], dtype=np.float16)

    x1_stored = np.swapaxes(x1_logical, -1, -2)   # (1,2,2)
    x2_stored = np.swapaxes(x2_logical, -1, -2)   # (1,3,2)
    assert x2_stored.shape == (1, 3, 2), x2_stored.shape

    y = spec.golden(x1_stored, x2_stored, True, True)
    np.testing.assert_array_equal(y, np.array([2.0], dtype=np.float32))


def example_3() -> None:
    """All-negative scores -> y = [-1.0]; MaxSim must NOT start at 0."""
    x1 = np.array([[[1.0, 0.0]]], dtype=np.float16)
    x2 = np.array([[[-1.0, -2.0], [0.0, 0.0]]], dtype=np.float16)
    y = spec.golden(x1, x2, False, False)
    np.testing.assert_array_equal(y, np.array([-1.0], dtype=np.float32))


def layout_invariant(trials: int = 40, seed: int = 20260923) -> None:
    """Storage-layout equivalence on asymmetric random data.

    This is the property the four (transposeX1, transposeX2) combinations must
    all satisfy, and the one a kernel is most likely to get wrong.
    """
    rng = np.random.default_rng(seed)
    for t in range(trials):
        B = int(rng.integers(1, 5))
        M = int(rng.integers(1, 33))
        N = int(rng.integers(1, 33))
        K = int(rng.integers(4, 17)) * 8

        logical_x1 = rng.uniform(-1, 1, (B, M, K)).astype(np.float32).astype(np.float16)
        logical_x2 = rng.uniform(-1, 1, (B, K, N)).astype(np.float32).astype(np.float16)

        baseline = spec.golden(logical_x1, logical_x2, False, False)

        for tx1 in (False, True):
            for tx2 in (False, True):
                s1 = np.swapaxes(logical_x1, -1, -2) if tx1 else logical_x1
                s2 = np.swapaxes(logical_x2, -1, -2) if tx2 else logical_x2
                got = spec.golden(s1, s2, tx1, tx2)
                if not np.array_equal(got, baseline):
                    raise AssertionError(
                        f"trial {t}: layout (tx1={tx1}, tx2={tx2}) diverged "
                        f"(B={B} M={M} N={N} K={K})\n baseline={baseline}\n got={got}"
                    )


def case_validation() -> None:
    """The declared envelope in section 3.4 must be enforced by spec.validate."""
    ok = spec.Case(1, 2, 64, 64, 64, "float16")
    assert spec.validate(ok) == [], spec.validate(ok)

    bad_k = spec.Case(1, 1, 8, 8, 33, "float16")            # K not a multiple of 8
    assert any("multiple" in p for p in spec.validate(bad_k))

    # B*M*K = 64 * 8192 * 8192 = 2**32, well past the 2**26 element budget
    over = spec.Case(1, 64, 8192, 8, 8192, "float16")
    assert over.B * over.M * over.K > spec.ELEMENT_BUDGET
    assert any("2**26" in p for p in spec.validate(over))

    bad_dtype = spec.Case(1, 1, 8, 8, 32, "float32")
    assert any("dtype" in p for p in spec.validate(bad_dtype))


def main() -> int:
    checks = [
        ("problem statement example 1 (basic)", example_1),
        ("problem statement example 2 (transposed storage)", example_2),
        ("problem statement example 3 (all-negative)", example_3),
        ("storage-layout invariant, 40 random asymmetric trials", layout_invariant),
        ("spec envelope validation", case_validation),
    ]
    failed = 0
    for name, fn in checks:
        try:
            fn()
            print(f"OK   {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {name}\n     {type(exc).__name__}: {exc}")

    print()
    if failed:
        print(f"{failed} check(s) failed")
        return 1
    print("all spec checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
