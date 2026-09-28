Clear[p,q,tt,h,r1,r2,a,z1,z2];
ass=p>0&&q>0&&tt>0&&0<h<tt&&r1>0&&r2>0;
ts={0,h,tt}; mu=a ts;
pp=Table[p+q Min[ts[[i]],ts[[j]]],{i,3},{j,3}]; pp=FullSimplify[pp,ass];
upd[{m_,c_},j_,z_,r_]:=Module[{v=c[[All,j]],s=c[[j,j]]+r},{m+v (z-m[[j]])/s,c-Outer[Times,v,v]/s}];
ab=upd[upd[{mu,pp},2,z1,r1],3,z2,r2];
ba=upd[upd[{mu,pp},3,z2,r2],2,z1,r1];
after=upd[{mu,pp},3,z2,r2]; ends=after[[2]][[{1,3},{1,3}]];
b={{1,0},{1-h/tt,h/tt},{0,1}};
bridge=b.ends.Transpose[b]+DiagonalMatrix[{0,q h (tt-h)/tt,0}];
<|"assumptions"->ass,
"orderIndependentMean"->FullSimplify[ab[[1]]==ba[[1]],ass],
"orderIndependentCovariance"->FullSimplify[ab[[2]]==ba[[2]],ass],
"conditionalBridgeExact"->FullSimplify[bridge==after[[2]],ass],
"bridgeIndependentVarianceNonnegative"->FullSimplify[q h (tt-h)/tt>=0,ass],
"zeroAgeGain"->FullSimplify[(p+q tt)/(p+q tt+r1),ass],
"warning"->"Exact only for scalar additive linear Gaussian dynamics with known deterministic drift and independent measurement noise. No nonlinear observer stability or real-data accuracy claim."|>
