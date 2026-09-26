"""Independent NumPy batch conditioning versus pure-Python retained joint state."""
import json, random, sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent/'tests'))
from test_h30 import gaussian_batch
from joint import JointHistory
rng=random.Random(3001);max_mu=max_cov=0.;min_eigen=1.;checks=0
for case in range(30):
    bank=JointHistory(0,2,.7,1.)
    for t in (.08,.2,.4):bank.append(t,bank.means[-1]+.4*(t-bank.times[-1]),.13)
    observations=[]
    for num,t in enumerate(rng.sample([i/1000 for i in range(1,399)],12)):
        z=2+.4*t+rng.gauss(0,.12);r=.02+.03*rng.random()
        bank.observe(bank.index(t),z,r,(case,num));observations.append((t,z,r))
        m,p=gaussian_batch(bank.times,observations)
        max_mu=max(max_mu,float(np.max(abs(np.asarray(bank.means)-m))))
        max_cov=max(max_cov,float(np.max(abs(np.asarray(bank.p)-p))))
        min_eigen=min(min_eigen,float(np.linalg.eigvalsh(bank.p).min()));checks+=1
result=dict(assumptions='known additive drift=.4 m/s^2, q=.13, independent fixed measurement R, Gaussian initial state',
    seed=3001,streams=30,updates=checks,max_mean_error=max_mu,max_covariance_error=max_cov,
    minimum_eigenvalue=min_eigen,mean_cov_tolerance=1e-9,psd_tolerance=-1e-10,
    passed=max_mu<=1e-9 and max_cov<=1e-9 and min_eigen>=-1e-10,
    nonlinear_stability_proven=False,real_accuracy_proven=False)
print(json.dumps(result,indent=2))
if not result['passed']:raise SystemExit(1)
