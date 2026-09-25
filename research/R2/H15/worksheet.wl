Clear[n,sx,sxx,sy,sxy,lambda,b,g,vx,cxy,x0,d0,ell,delta];
gram={{n,sx},{sx,sxx}};
sol=Solve[{n b+sx g==sy,sx b+(sxx+n lambda)g==sxy},{b,g}];
centered=FullSimplify[g/.First[sol]/.{sxx->n(vx+(sx/n)^2),sxy->n cxy+sx sy/n},Assumptions->n>0&&vx>0&&lambda>=0];
clamp[z_]:=Min[ell,Max[-ell,z]];
output=<|"gram_determinant"->Det[gram],"centered_gamma"->centered,
"constant_drive_determinant"->Simplify[Det[gram]/.{sx->n x0,sxx->n x0^2}],
"ridge_solution"->sol,
"loss_continuity"->FullSimplify[clamp[d0+g(0)]==d0,Assumptions->ell>0&&-ell<=d0<=ell],
"correction_bound"->Resolve[ForAll[{d0,g,delta,ell},Implies[ell>0&&-ell<=d0<=ell,Abs[clamp[d0+g delta]-d0]<=Abs[g delta]]],Reals],
"ridge_noise_bias"->Together[(g vx+cxy)/(vx+lambda)-g],
"gamma_unit"->"dimensionless when x,y have acceleration units; lambda has acceleration-squared units",
"stability_scope"->"Clip bounds acceleration contribution only; no asymptotic velocity-error stability follows without wheels. If correction magnitude <=B for T seconds then relative velocity increment <=B T, distance <=B T^2/2 in unsaturated ideal integration."|>;
output
