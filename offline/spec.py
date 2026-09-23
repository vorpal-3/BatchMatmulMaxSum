#!/usr/bin/env python3
"""Shared specification module for the BatchMatmulMaxSum problem.

This module encodes ONLY publicly available facts:
  * the problem statement's constraints (dims, dtypes, layouts),
  * the组委会 golden semantics (shipped to contestants in
    problem/template/scripts/BatchMatmulMaxSum.py),
  * the组委会 precision gate (shipped in
    problem/template/scripts/verify_result.py),
  * the published scoring formula.

It deliberately contains NO evaluation cases. The hidden evaluation case set
lives outside the development workspace and imports this module.

Semantics (verbatim from the problem statement):
    A[b,m,n] = sum_k X1[b,m,k] * X2[b,k,n]
    R[b,m]   = max_n A[b,m,n]
    y[b]     = sum_m R[b,m]
  * X1/X2 are rank-3. transposeX1/transposeX2 declare the *storage* shape only;
    they do not mean the operator performs a transpose.
  * Golden uses the actual stored values in FP64, then casts to FP32.
  * Max and Sum are NOT interchangeable.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np

try:
    from ml_dtypes import bfloat16 as _bfloat16
except ImportError:  # pragma: no cover - ml_dtypes is required by the组委会 harness
    _bfloat16 = None

# --------------------------------------------------------------------------
# dtypes
# --------------------------------------------------------------------------

# Matches TensorInfo.dtype in main.asc and the组委会 template comments.
DTYPE_ENUM = {
    "float32": 0,
    "float16": 1,
    "bfloat16": 2,
    "int8": 3,
    "int16": 4,
    "int32": 5,
    "int64": 6,
    "uint8": 7,
    "uint16": 8,
    "uint32": 9,
    "uint64": 10,
    "bool": 11,
}

# The problem supports only these two input dtypes for x1/x2.
SUPPORTED_INPUT_DTYPES = ("float16", "bfloat16")

OUTPUT_DTYPE = "float32"

_NUMPY_DTYPE = {
    "float32": np.float32,
    "float16": np.float16,
    "bfloat16": _bfloat16,
}


def numpy_dtype(name: str):
    if name not in _NUMPY_DTYPE or _NUMPY_DTYPE[name] is None:
        raise ValueError(f"unsupported or unavailable dtype: {name!r}")
    return _NUMPY_DTYPE[name]


# --------------------------------------------------------------------------
# Problem constraints (problem statement section 3.4)
# --------------------------------------------------------------------------

MAX_B = 64
MAX_M = 8192
MAX_N = 8192
MIN_K = 32
MAX_K = 8192
K_MULTIPLE = 8
ELEMENT_BUDGET = 1 << 26  # B*M*K <= 2**26 and B*N*K <= 2**26

# Precision gate, verbatim from the shipped verify_result.py:
#   ("y", np.float32, rtol=1e-4, atol=1e-4, tol=1e-4)
PRECISION_RTOL = 1e-4
PRECISION_ATOL = 1e-4
PRECISION_MAX_ERROR_RATE = 1e-4


# --------------------------------------------------------------------------
# Cases
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Case:
    """One evaluation case, in the组委会 generator's own tuple order."""

    cid: int
    B: int
    M: int
    N: int
    K: int
    dtype: str
    transposeX1: bool = False
    transposeX2: bool = False
    x1_range: tuple = (-1.0, 1.0)
    x2_range: tuple = (-1.0, 1.0)

    @property
    def x1_storage_shape(self) -> tuple:
        return (self.B, self.K, self.M) if self.transposeX1 else (self.B, self.M, self.K)

    @property
    def x2_storage_shape(self) -> tuple:
        return (self.B, self.N, self.K) if self.transposeX2 else (self.B, self.K, self.N)

    @property
    def y_shape(self) -> tuple:
        return (self.B,)

    @property
    def macs(self) -> int:
        return self.B * self.M * self.N * self.K

    @property
    def input_elements(self) -> int:
        return self.B * self.K * (self.M + self.N)

    def label(self) -> str:
        tx = f"tx1={int(self.transposeX1)},tx2={int(self.transposeX2)}"
        return (
            f"case{self.cid:02d} B={self.B} M={self.M} N={self.N} K={self.K} "
            f"{self.dtype} {tx}"
        )


def validate(case: Case) -> list:
    """Return a list of spec violations (empty means conformant)."""
    problems = []
    if not (1 <= case.B <= MAX_B):
        problems.append(f"B={case.B} outside 1..{MAX_B}")
    if not (1 <= case.M <= MAX_M):
        problems.append(f"M={case.M} outside 1..{MAX_M}")
    if not (1 <= case.N <= MAX_N):
        problems.append(f"N={case.N} outside 1..{MAX_N}")
    if not (MIN_K <= case.K <= MAX_K):
        problems.append(f"K={case.K} outside {MIN_K}..{MAX_K}")
    if case.K % K_MULTIPLE != 0:
        problems.append(f"K={case.K} is not a multiple of {K_MULTIPLE}")
    if case.B * case.M * case.K > ELEMENT_BUDGET:
        problems.append(f"B*M*K={case.B * case.M * case.K} exceeds 2**26")
    if case.B * case.N * case.K > ELEMENT_BUDGET:
        problems.append(f"B*N*K={case.B * case.N * case.K} exceeds 2**26")
    if case.dtype not in SUPPORTED_INPUT_DTYPES:
        problems.append(f"dtype={case.dtype!r} not in {SUPPORTED_INPUT_DTYPES}")
    return problems


def _make_input(shape: Sequence[int], dtype: str, value_range: Sequence[float], rng) -> np.ndarray:
    """Exactly the组委会 generator's value model: uniform, cast down to the input dtype."""
    low, high = value_range
    value = rng.uniform(low, high, tuple(shape)).astype(np.float32)
    if dtype == "float16":
        return value.astype(np.float16)
    if dtype == "bfloat16":
        if _bfloat16 is None:
            raise RuntimeError("ml_dtypes is required for bfloat16 cases")
        return value.astype(_bfloat16)
    raise ValueError(f"unsupported dtype: {dtype}")


def build_inputs(case: Case, rng) -> tuple:
    """Return (x1_storage, x2_storage) for a case, using the组委会 value model."""
    x1 = _make_input(case.x1_storage_shape, case.dtype, case.x1_range, rng)
    x2 = _make_input(case.x2_storage_shape, case.dtype, case.x2_range, rng)
    return x1, x2


# --------------------------------------------------------------------------
# Golden
# --------------------------------------------------------------------------

def golden(x1, x2, transposeX1: bool = False, transposeX2: bool = False) -> np.ndarray:
    """The组委会 golden implementation, reproduced exactly.

    Actual stored values are computed in FP64 and cast to FP32 at the end.
    """
    x1_np = np.asarray(x1)
    x2_np = np.asarray(x2)
    if x1_np.ndim != 3 or x2_np.ndim != 3:
        raise ValueError("x1 and x2 must both be rank-3 tensors")

    x1_f = x1_np.astype(np.float64)
    x2_f = x2_np.astype(np.float64)

    x1_logical = np.swapaxes(x1_f, -1, -2) if transposeX1 else x1_f
    x2_logical = np.swapaxes(x2_f, -1, -2) if transposeX2 else x2_f

    if x1_logical.shape[0] != x2_logical.shape[0]:
        raise ValueError("x1 and x2 must have the same batch dimension; no broadcast")
    if x1_logical.shape[2] != x2_logical.shape[1]:
        raise ValueError("the logical K dimensions of x1 and x2 must match")

    similarity = np.matmul(x1_logical, x2_logical)
    max_sim = np.max(similarity, axis=-1)
    y = np.sum(max_sim, axis=-1)
    return y.astype(np.float32)


def golden_for_case(case: Case, rng) -> tuple:
    """Convenience: build inputs for a case and return (x1, x2, y_golden)."""
    x1, x2 = build_inputs(case, rng)
    return x1, x2, golden(x1, x2, case.transposeX1, case.transposeX2)


# --------------------------------------------------------------------------
# Precision gate (verbatim port of the组委会 verify_result.py float branch)
# --------------------------------------------------------------------------

def precision_check(output: np.ndarray, reference: np.ndarray) -> dict:
    """Return a dict describing whether `output` passes the per-case gate."""
    out = np.asarray(output, dtype=np.float32).reshape(-1)
    ref = np.asarray(reference, dtype=np.float32).reshape(-1)
    total = ref.size

    result = {
        "total": int(total),
        "output_size": int(out.size),
        "errors": None,
        "error_rate": None,
        "max_diff": None,
        "passed": False,
    }

    if out.size != ref.size:
        if out.size < ref.size:
            ref = ref[: out.size]
            result["truncated_reference"] = True
        else:
            result["reason"] = "size mismatch (output larger than reference)"
            return result
    missing = total - out.size

    isclose = np.isclose(out, ref, rtol=PRECISION_RTOL, atol=PRECISION_ATOL, equal_nan=True)
    errors = int(np.sum(~isclose)) + missing
    error_rate = errors / total if total else 0.0
    diff = np.abs(out - ref)

    result.update(
        errors=errors,
        error_rate=error_rate,
        max_diff=float(np.max(diff)) if diff.size else 0.0,
        passed=bool(error_rate <= PRECISION_MAX_ERROR_RATE),
        missing=int(missing),
    )
    if not np.all(np.isfinite(out)):
        result["has_non_finite"] = True
    return result


# --------------------------------------------------------------------------
# Scoring (problem statement section 6)
# --------------------------------------------------------------------------

def case_score(t: float, best: float) -> float:
    """Per-case score 100 / (1 + log_1.5(t / T)).

    `t` is this submission's time for the case, `T` the best known time.
    Only valid once the case's precision gate has passed.
    """
    if t <= 0 or best <= 0:
        raise ValueError("times must be positive")
    return 100.0 / (1.0 + math.log(t / best, 1.5))


def mean_score(scores: Iterable[float]) -> float:
    values = [s for s in scores if s is not None]
    if not values:
        raise ValueError("no scored cases")
    return sum(values) / len(values)
