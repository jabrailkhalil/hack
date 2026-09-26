Clear[a,c,d,rr,rho,vb,rt]; pp={{a,c},{c,d}}; hh={{1,1}};
ss=(hh.pp.Transpose[hh])[[1,1]]+rr; kk=pp.Transpose[hh]/ss; ii=IdentityMatrix[2];
jj=FullSimplify[(ii-kk.hh).pp.Transpose[ii-kk.hh]+rr kk.Transpose[kk]];
kv=kk[[1,1]]; legacy=1-jj[[1,1]]/a; aa=DiagonalMatrix[{1,rho}];
out=<|"observability_determinant"->Factor[Det[Join[hh,hh.aa]]],
"joseph_equals_conditional_covariance"->Simplify[jj-(pp-pp.Transpose[hh].hh.pp/ss)],
"joseph_determinant"->Factor[Det[jj]],"effective_velocity_gain"->kv,
"scalar_reconstruction"->Factor[legacy],"scalar_reconstruction_error"->Factor[legacy-kv],
"numerical_P_is_positive_definite"->PositiveDefiniteMatrixQ[pp/.{a->2/100,c->5/1000,d->1/100}],
"numerical_actual_and_scalar_gain"->N[{kv,legacy}/.{a->2/100,c->5/1000,d->1/100,rr->1/100}],
"conditional_white_limit"->Simplify[kv/.{c->0,d->vb,rr->rt-vb}],
"stationary_variance_identity"->Simplify[rho^2 vb+(1-rho^2)vb==vb],
"stationary_process_noise_nonnegative"->FullSimplify[(1-rho^2)vb>=0,Assumptions->0<=rho<=9/10&&vb>=0]|>;
InputForm[out]
