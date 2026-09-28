"""Independent symbolic/numeric checks; no claims about switched-filter stability."""
import json
import math
import sympy as s


def run():
    c, x, dt = s.symbols('c x dt', positive=True)
    v = s.symbols('v', real=True)
    beta, alpha, latent, k = s.symbols('beta alpha latent k', positive=True)
    sx2, sxy = s.symbols('sx2 sxy', positive=True)
    candidate = s.symbols('candidate', real=True)
    w0,w1,z0,z1,y0,y1=s.symbols('w0 w1 z0 z1 y0 y1', real=True)
    loss=w0*(candidate*z0-y0)**2+w1*(candidate*z1-y1)**2
    opt=(w0*z0*y0+w1*z1*y1)/(w0*z0**2+w1*z1**2)
    checks={
      'zero_invariant':s.simplify(c*0)==0,
      'positive_preserves_sign':s.simplify(s.sign(c*v)-s.sign(v))==0,
      'positive_motion':s.ask(s.Q.positive(c*x)),
      'trapezoid_input_displacement_scaling':s.expand((c*z0+c*z1)*dt/2-c*(z0+z1)*dt/2)==0,
      'weighted_scalar_least_squares_stationarity':s.simplify(s.diff(loss,candidate).subs(candidate,opt))==0,
      'common_bias_ratio':s.simplify((beta*latent)/(alpha*latent)-beta/alpha)==0,
      'unobservable_common_gauge_wheel':s.simplify((k*alpha)*(latent/k)-alpha*latent)==0,
      'unobservable_common_gauge_teacher':s.simplify((k*beta)*(latent/k)-beta*latent)==0,
    }
    assert all(checks.values()),checks
    # Numeric oracle: the same two observed speeds admit different true speeds.
    worlds=[dict(true_speed=10.,wheel_gain=1.,teacher_gain=1.02),
            dict(true_speed=10.2,wheel_gain=1/1.02,teacher_gain=1.)]
    obs=[(w['true_speed']*w['wheel_gain'],w['true_speed']*w['teacher_gain']) for w in worlds]
    assert all(math.isclose(a,b,rel_tol=0,abs_tol=1e-12) for a,b in zip(*obs))
    return {'engine':'SymPy','version':s.__version__,'checks':checks,
            'weighted_ols_optimum':str(opt),'weighted_ols_is_huber_fit':False,
            'indistinguishable_worlds':worlds,'observations':obs,
            'assumptions':['positive constant multiplicative factors','matched timestamps and independent equation variables',
                           'OLS identity is an algebra check, not the planned robust solver',
                           'integral scaling describes input velocity, not nonlinear observer output'],
            'warnings':[],
            'limitations':['GNSS common systematic error and common wheel slip cannot be assigned to hardware scale here',
                           'teacher speed magnitude alone does not give reverse-motion sign',
                           'bounded factors do not prove stability, false-stop safety or real-data accuracy of switched clipped observer']}


if __name__=='__main__':
    print(json.dumps(run(),indent=2,ensure_ascii=False))
