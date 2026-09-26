"""Independent high-precision algebra/quadrature checks, NOT a runtime implementation."""
import json
from pathlib import Path
import mpmath as mp
mp.mp.dps=80
phi=lambda x:mp.exp(-x*x/2)/mp.sqrt(2*mp.pi)


def moments(a,b):
    # CDF via erfc avoids subtraction of two almost-one CDF values in right tail.
    if a>=0:Z=(mp.erfc(a/mp.sqrt(2))-mp.erfc(b/mp.sqrt(2)))/2
    elif b<=0:Z=(mp.erfc(-b/mp.sqrt(2))-mp.erfc(-a/mp.sqrt(2)))/2
    else:Z=(mp.erf(b/mp.sqrt(2))-mp.erf(a/mp.sqrt(2)))/2
    lam=(phi(a)-phi(b))/Z
    var=1+(a*phi(a)-b*phi(b))/Z-lam*lam
    return lam,var,Z


def quadrature(center,width):
    # Integrate in u in [-1/2,1/2]; common exp(-center^2/2) cancels.
    f=lambda u:mp.exp(-center*width*u-width*width*u*u/2)
    norm=mp.quad(f,[-mp.mpf('.5'),0,mp.mpf('.5')])
    eu=mp.quad(lambda u:u*f(u),[-mp.mpf('.5'),0,mp.mpf('.5')])/norm
    vu=mp.quad(lambda u:(u-eu)**2*f(u),[-mp.mpf('.5'),0,mp.mpf('.5')])/norm
    return center+width*eu,width*width*vu


rows=[];max_mean=max_var=max_deriv=mp.mpf(0)
for center in (-40,-8,-3,0,3,8,40):
    for width in ('1e-8','1e-4','.01','.1','1','3'):
        c,w=mp.mpf(center),mp.mpf(width);a,b=c-w/2,c+w/2
        lm,vt,Z=moments(a,b);qm,qv=quadrature(c,w)
        mean_error=abs(lm-qm);var_error=abs(vt-qv)
        derivative=mp.diff(lambda x:moments(x-w/2,x+w/2)[0],c)
        derivative_error=abs(derivative-(1-vt))
        assert Z>0 and -mp.mpf('1e-55')<=vt<=1+mp.mpf('1e-55')
        assert mean_error<mp.mpf('1e-50') and var_error<mp.mpf('1e-50') and derivative_error<mp.mpf('1e-50')
        max_mean=max(max_mean,mean_error);max_var=max(max_var,var_error);max_deriv=max(max_deriv,derivative_error)
        # P=.005, R=.01; check PSD/no spurious 1/N pair confidence.
        P,R=mp.mpf('.005'),mp.mpf('.01');S=P+R
        post=P-P*P/S*(1-vt);k=P/S*(1-vt)
        assert P*R/S-mp.mpf('1e-50')<=post<=P+mp.mpf('1e-50')
        assert abs((1-post/P)-k)<mp.mpf('1e-50')
        rows.append({'standardized_center':center,'standardized_width':width,'truncated_mean':str(lm),
          'truncated_variance':str(vt),'log_bin_probability':str(mp.log(Z)),
          'mean_quad_error':str(mean_error),'variance_quad_error':str(var_error),'sensitivity_error':str(derivative_error)})
# Tiny-bin agreement is one-step Gaussian point-conditioning limit.
P,R,mu,z=map(mp.mpf,['.005','.01','2','2.2']);S=P+R;q=mp.mpf('1e-9')
lm,vt,_=moments((z-q/2-mu)/mp.sqrt(S),(z+q/2-mu)/mp.sqrt(S))
mean=mu+P/mp.sqrt(S)*lm;post=P-P*P/S*(1-vt)
res={'cases':len(rows),'passed':True,'precision_digits':80,
 'maximum_mean_quad_error':str(max_mean),'maximum_variance_quad_error':str(max_var),
 'maximum_sensitivity_error':str(max_deriv),
 'q_1e_minus9_mean_delta_mps':str(mean-(mu+P/S*(z-mu))),
 'q_1e_minus9_variance_delta':str(post-P*R/S),
 'assumptions':'One Gaussian scalar prior; independent analog noise R fixed while differentiating; one bin; no multi-step runtime claim.',
 'runtime_candidate_implemented':False,'rows':rows}
p=Path(__file__).with_name('RESULTS.json');p.write_text(json.dumps(res,indent=2)+'\n')
print(json.dumps({k:v for k,v in res.items() if k!='rows'},indent=2))
