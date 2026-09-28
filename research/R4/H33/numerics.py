"""Diagnostic-only H33 numerical primitives; no estimator state is changed.

The C shape assumes independent equal-variance endpoint errors, not two
independent wheels. NumPy is intentionally unnecessary for these primitives.
"""
from collections import deque
import math

FLOOR = 1e-6  # C = sigma**2 * (D D' + FLOOR I); never fit this value.


def solve_tridiagonal(rhs):
    """Solve (tridiag(-1, 2, -1) + FLOOR I)x=rhs, n<=6."""
    n = len(rhs)
    if not 1 <= n <= 6 or not all(math.isfinite(x) for x in rhs):
        raise ValueError('Invalid bounded system')
    pivots = [2.0 + FLOOR]
    work = [float(rhs[0])]
    for i in range(1, n):
        if pivots[-1] <= 1e-12:
            raise ValueError('Nonpositive/ill-conditioned pivot')
        factor = -1.0 / pivots[-1]
        pivots.append(2.0 + FLOOR + factor)
        work.append(rhs[i] - factor * work[-1])
    # Analytic eigenvalues bound condition for this fixed Toeplitz matrix.
    condition = (2 + FLOOR + 2*math.cos(math.pi/(n+1))) / (2 + FLOOR - 2*math.cos(math.pi/(n+1)))
    if pivots[-1] <= 1e-12 or condition > 1e6:
        raise ValueError('Condition failure')
    result = [0.0] * n
    result[-1] = work[-1] / pivots[-1]
    for i in range(n-2, -1, -1):
        result[i] = (work[i] + result[i+1]) / pivots[i]
    if not all(math.isfinite(x) for x in result):
        raise ValueError('Nonfinite solution')
    return result


def targets(times, increments, sigma=0.1):
    """GLS/OLS point targets and model variance for RAW increments, in SI."""
    h = [b-a for a, b in zip(times, times[1:])]
    if len(h) != len(increments) or not h or not all(0.05-1e-9 <= x <= .25+1e-9 for x in h):
        raise ValueError('Invalid native intervals')
    if not math.isfinite(sigma) or sigma <= 0 or not all(math.isfinite(y) for y in increments):
        raise ValueError('Invalid data or sigma')
    x = solve_tridiagonal(h)
    denom = sum(a*b for a,b in zip(h,x))
    weights = [v/denom for v in x]
    gls = sum(w*y for w,y in zip(weights,increments))
    ols = sum(a*y for a,y in zip(h,increments)) / sum(a*a for a in h)
    var = sigma*sigma / denom
    return gls, ols, var


class GHistory:
    """Causal piecewise-linear pre-correction g, bounded by count AND age."""
    def __init__(self):
        self.points = deque(maxlen=32)

    def add(self, t, g, valid):
        if self.points and t <= self.points[-1][0]:
            raise ValueError('Nonincreasing snapshot')
        self.points.append((t, g, bool(valid) and math.isfinite(g)))
        while self.points and t-self.points[0][0] > .75+1e-9:
            self.points.popleft()

    def integral(self, left, right):
        if not (math.isfinite(left) and math.isfinite(right)) or right <= left:
            raise ValueError('Invalid integral interval')
        p = self.points
        if len(p)<2 or left < p[0][0]-1e-9 or right > p[-1][0]+1e-9:
            raise ValueError('Insufficient causal history')
        total=covered=0.0
        for (a,ga,va),(b,gb,vb) in zip(p,list(p)[1:]):
            lo,hi=max(a,left),min(b,right)
            if hi<=lo:continue
            if not va or not vb or b-a > .2+1e-9:
                raise ValueError('Stale/clipped/gap segment')
            flo=ga+(gb-ga)*(lo-a)/(b-a)
            fhi=ga+(gb-ga)*(hi-a)/(b-a)
            total+=(flo+fhi)*.5*(hi-lo);covered+=hi-lo
        if abs(covered-(right-left))>1e-8:
            raise ValueError('Incomplete interval')
        return total
