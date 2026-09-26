"""Independent numeric sanity for [v,b]; NOT a nonlinear observer proof."""
import json
import numpy as np
rng=np.random.default_rng(2603)
max_joseph_error=0.;minimum_eigenvalue=float('inf')
for _ in range(5000):
    m=rng.normal(size=(2,2));p=m@m.T
    r=float(rng.uniform(.001,2.));h=np.array([[1.,1.]])
    s=float((h@p@h.T).item()+r);k=p@h.T/s
    j=(np.eye(2)-k@h)@p@(np.eye(2)-k@h).T+r*k@k.T
    direct=p-p@h.T@h@p/s
    max_joseph_error=max(max_joseph_error,float(np.max(abs(j-direct))))
    minimum_eigenvalue=min(minimum_eigenvalue,float(np.linalg.eigvalsh(j).min()))
    assert np.linalg.eigvalsh(j).min()>-1e-12
    a,c,d=p[0,0],p[0,1],p[1,1]
    assert abs(np.linalg.det(j)-r*(a*d-c*c)/s)<1e-10
    assert abs((1-j[0,0]/a)-k[0,0]-c*(a+c)/(a*s))<1e-11
rho=.7
h=np.array([[1.,1.]])
o=np.vstack([h,h@np.diag([1.,rho])])
assert abs(np.linalg.det(o)-(rho-1))<1e-14
p=np.array([[.02,.005],[.005,.01]]);r=.01
s=float((h@p@h.T).item()+r);k=p@h.T/s
post=p-p@h.T@h@p/s
out=dict(seed=2603,numeric_psd_cases=5000,max_joseph_vs_direct_error=max_joseph_error,
 minimum_posterior_eigenvalue=minimum_eigenvalue,
 actual_velocity_gain=float(k[0,0]),invalid_scalar_reconstruction=float(1-post[0,0]/p[0,0]),
 example_observability_determinant=float(np.linalg.det(o)),
 assumptions='P PSD, R positive; linear H=[1,1]. No nonlinear/global/runtime proof.')
print(json.dumps(out,indent=2,allow_nan=False))
