"""Independent local symbolic/numeric H27 oracle: ideal model only."""
import json
import sympy as s
T,h,d=s.symbols('T h delta_d',positive=True,finite=True)
n=s.symbols('n',integer=True,positive=True)
v=d*T
x=s.integrate(d*s.Symbol('t'),(s.Symbol('t'),0,T))
trap=s.summation((d*h*(s.Symbol('k')-1)+d*h*s.Symbol('k'))*h/2,(s.Symbol('k'),1,n))
assert s.simplify(trap-d*(n*h)**2/2)==0
assert s.diff(v,T)==d and s.diff(x,T)==v
assert s.limit(v,T,0)==s.limit(x,T,0)==0
assert s.limit(v,d,0)==s.limit(x,d,0)==0
# Counterexample to importing the equality into a clipped acceleration model.
clip=lambda a:max(-3.,min(3.,a))
clipped=clip(2.9+.3)-clip(2.9)
assert abs(clipped-.1)<1e-12 and abs(clipped-.3)>.1
print(json.dumps(dict(assumptions='Equal initial v/s; constant additive acceleration error; no clipping, resistance difference, feedback, switching or measurements.',
 delta_v=str(v),delta_s=str(x),discrete_trapezoid=str(s.simplify(trap)),limits_zero=True,
 acceleration_clip_counterexample=dict(native=2.9,delta_d=.3,actual_delta_a=clipped),
 implications='Neither physical disturbance identification nor nonlinear observer stability follows.',warnings=[]),indent=2))
