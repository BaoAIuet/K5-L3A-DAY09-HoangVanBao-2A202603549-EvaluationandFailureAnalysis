"""Statistics students implement (M2 judge calibration, M4 paired bootstrap).

Rules: a judge is a classifier -- measure it like one. A higher mean is not
"better" until the paired CI of the difference excludes 0.
Reference values to self-check are in tests/test_lab9_stats.py.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from scipy.stats import bootstrap

POS = "FAIL"   # the judge's job is to FIND failures, so FAIL is the positive class


def _norm(seq: Sequence[str]) -> list[str]:
    normalized = [str(x).strip().upper() for x in seq]
    if any(value not in {"PASS", POS} for value in normalized):
        raise ValueError("labels must be PASS or FAIL")
    return normalized


def confusion(human: Sequence[str], judge: Sequence[str]) -> dict[str, int]:
    """tp/fp/fn/tn with FAIL as positive."""
    h = _norm(human)
    j = _norm(judge)
    if len(h) != len(j):
        raise ValueError("human and judge sequence lengths must match")
    tp = fp = fn = tn = 0
    for hv, jv in zip(h, j):
        if hv == POS and jv == POS:
            tp += 1
        elif hv != POS and jv == POS:
            fp += 1
        elif hv == POS and jv != POS:
            fn += 1
        else:
            tn += 1
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn}


def precision_recall(human: Sequence[str], judge: Sequence[str]) -> tuple[float, float]:
    c = confusion(human, judge)
    tp = c["tp"]
    fp = c["fp"]
    fn = c["fn"]
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    return precision, recall


def cohen_kappa(human: Sequence[str], judge: Sequence[str]) -> float:
    """kappa = (p_o - p_e) / (1 - p_e). Raise ValueError when undefined (p_e == 1):
    a constant judge has no signal and must FAIL calibration, not pass on a technicality."""
    h = _norm(human)
    j = _norm(judge)
    if len(h) != len(j):
        raise ValueError("human and judge sequence lengths must match")
    n = len(h)
    if n == 0:
        return 0.0
    h_fail = sum(1 for x in h if x == POS)
    j_fail = sum(1 for x in j if x == POS)
    p_e = (h_fail / n) * (j_fail / n) + ((n - h_fail) / n) * ((n - j_fail) / n)
    if math.isclose(p_e, 1.0, abs_tol=1e-12):
        raise ValueError("Cohen's kappa undefined: p_e == 1")
    p_o = sum(1 for hv, jv in zip(h, j) if hv == jv) / n
    return (p_o - p_e) / (1 - p_e)


def rogan_gladen(observed_rate: float, sensitivity: float, specificity: float) -> float:
    """Correct an observed failure rate for judge error; clip to [0, 1]."""
    if any(not 0.0 <= value <= 1.0 for value in (observed_rate, sensitivity, specificity)):
        raise ValueError("observed rate, sensitivity, and specificity must be in [0, 1]")
    denom = sensitivity + specificity - 1
    if math.isclose(denom, 0.0, abs_tol=1e-12):
        raise ValueError("Rogan-Gladen correction undefined when sensitivity + specificity == 1")
    corrected = (observed_rate + specificity - 1.0) / denom
    return min(1.0, max(0.0, corrected))


def paired_bootstrap(a: Sequence[float], b: Sequence[float], *, n_resamples: int = 1000,
                     rng: int = 2027, confidence: float = 0.95) -> tuple[float, float, float]:
    """a[i], b[i] = per-item mean over seeds, SAME items, SAME order.
    Return (mean(a)-mean(b), lo, hi) with scipy.stats.bootstrap(paired=True, method="percentile",
    rng=numpy.random.default_rng(rng)). If a == b everywhere return (0.0, 0.0, 0.0)."""
    aa = np.asarray(a, dtype=float)
    bb = np.asarray(b, dtype=float)
    if aa.shape != bb.shape:
        raise ValueError("a and b must have the same shape")
    if n_resamples < 1:
        raise ValueError("n_resamples must be positive")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be between 0 and 1")
    if aa.size == 0:
        return (0.0, 0.0, 0.0)
    if np.array_equal(aa, bb):
        return (0.0, 0.0, 0.0)
    diff = lambda x, y: np.mean(x) - np.mean(y)
    res = bootstrap((aa, bb), statistic=diff, paired=True, method="percentile",
                    n_resamples=n_resamples, rng=np.random.default_rng(rng),
                    confidence_level=confidence)
    lo = float(res.confidence_interval.low)
    hi = float(res.confidence_interval.high)
    return float(np.mean(aa) - np.mean(bb)), lo, hi


def _comb(n: int, k: int) -> int:
    if k < 0 or n < 0 or k > n:
        raise ValueError("invalid combination")
    return math.comb(n, k)


def pass_at_k(n: int, c: int, k: int) -> float:
    """Probability that AT LEAST ONE of k trials drawn from n (c of them passing) passes.
    Unbiased estimator (Chen et al. 2021): 1 - C(n-c, k) / C(n, k). Raise ValueError if k > n."""
    if k <= 0 or k > n or c < 0 or c > n:
        raise ValueError("require 0 < k <= n and 0 <= c <= n")
    if k > n - c:
        return 1.0
    return 1.0 - (_comb(n - c, k) / _comb(n, k))


def pass_hat_k(n: int, c: int, k: int) -> float:
    """pass^k (tau-bench, Yao et al. 2024): probability that ALL k trials drawn from n pass.
    Unbiased estimator: C(c, k) / C(n, k). Raise ValueError if k > n.
    pass^k <= pass@1 <= pass@k; a reliable agent keeps pass^k close to pass@1."""
    if k <= 0 or k > n or c < 0 or c > n:
        raise ValueError("require 0 < k <= n and 0 <= c <= n")
    if k > c:
        return 0.0
    return _comb(c, k) / _comb(n, k)
