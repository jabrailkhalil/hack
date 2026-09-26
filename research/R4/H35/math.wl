Clear[x0,r,t,tb,tr,z];
f[t_,tau_]:=r+(x0-r) Exp[-t/tau];
cross=tr Log[1-x0/r];
after[t_]:=r(1-Exp[-(t-cross)/tb]);
ass=x0>0&&r<0&&tr>0&&tb>0;
<|"ODE_residual"->FullSimplify[D[f[t,tr],t]-(r-f[t,tr])/tr],
"crossing"->cross,"zero_at_crossing"->FullSimplify[f[cross,tr],ass],
"continuity_right"->FullSimplify[after[cross],ass],
"ratio1_equivalence_after_crossing"->FullSimplify[(after[t]-f[t,tb])/.tr->tb,x0>0&&r<0&&tb>0],
"neutral_integral"->Integrate[x0 Exp[-t/tr],{t,0,z},Assumptions->tr>0&&z>=0],
"convex_weight"->FullSimplify[0<=1-Exp[-t/tr]<1,tr>0&&t>=0],
"neutral_total_impulse"->Integrate[x0 Exp[-t/tr],{t,0,Infinity},Assumptions->tr>0],
"scope"->"Piecewise constant target scalar actuator only. x is continuous; its derivative can jump at zero if tr != tb. Bounds follow by convex combination on each phase. No stability, accuracy or identifiability claim for the full observer. t/tau and x0/r dimensionless."|>
