ClearAll[v, aa, d, h, rho, tf, rf, p, c, a, kv, ka, r, qv, qa, n, da];
xp = {v + h (rho aa + (1-rho) tf[v] - rf[v] + d), rho aa + (1-rho) tf[v]};
f = Table[D[xp[[i]], x], {i,2}, {x,{v,aa}}];
frozen = {{1,h rho},{0,rho}}; hh = {{1,0}};
pp = {{p,c},{c,a}}; kk={{kv},{ka}}; m=IdentityMatrix[2]-kk.hh;
j = Simplify[m.pp.Transpose[m]+r kk.Transpose[kk]];
expected={{(1-kv)^2 p+kv^2 r,(1-kv)(c-ka p)+kv ka r},{(1-kv)(c-ka p)+kv ka r,a-2 ka c+ka^2 (p+r)}};
qq=qa {{h^2,h},{h,1}}+{{qv,0},{0,0}};
out=<|"jacobian"->f,"frozen_observability_determinant"->Det[Join[hh,hh.frozen]],"joseph_formula_difference"->Simplify[j-expected],"joseph_ka_zero"->Simplify[j/.ka->0],"optimal_Kv_cross"->Simplify[j[[1,2]]/.kv->p/(p+r)],"process_Q_determinant"->Factor[Det[qq]],"stationary_A_identity"->Simplify[rho^2 a+a(1-rho^2)-a],"initial_A_velocity_sensitivity"->Sum[h da rho^k,{k,1,n}],"actual_Kv_example"->(1/5)/(1/5+1/100),"wrong_legacy_reconstruction_example"->1-((1/5)(1/100)/(1/5+1/100))/(1/10+1/200),"persistent_d_variance_ratio"->Simplify[(n h)^2/(n h^2)],"assumptions"->"For PSD: pp positive semidefinite and r>=0. Joseph is PSD for ANY finite effective K, including Ka=0 or clipping. F is local away from clips/switches. Step-local d uncertainty does not bound persistent d bias. No true-data accuracy claim."|>;
ToString[out,InputForm]
