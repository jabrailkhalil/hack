"""Preregistered scalar rule. No fitted parameters; no observation history."""
import math


def student_variance(prior, floor, residual, nu):
    """Return (effective variance, K, posterior variance, iterations).

    R0 is a VARIANCE. The t SCALE is R0*(nu-2)/nu. The posterior here is
    an approximate Gaussian/Joseph covariance, not exact Student-t covariance.
    A failed numeric update is reported as None; the caller retains baseline.
    """
    if not all(math.isfinite(x) for x in (prior, floor, residual, nu)):
        return None
    if prior <= 0 or floor <= 0 or nu <= 2:
        return None
    error, covariance = residual, prior
    for _ in range(3):
        raw = ((nu - 2.0) * floor + error * error + covariance) / (nu + 1.0)
        if not math.isfinite(raw) or raw <= 0:
            return None
        effective = max(floor, min(100.0 * floor, raw))
        gain = prior / (prior + effective)
        error = (1.0 - gain) * residual
        covariance = (1.0 - gain) ** 2 * prior + gain * gain * effective
        if not all(math.isfinite(x) for x in (effective, gain, error, covariance)):
            return None
        if not 0 <= gain <= 1 or covariance <= 0:
            return None
    return effective, gain, covariance, 3
