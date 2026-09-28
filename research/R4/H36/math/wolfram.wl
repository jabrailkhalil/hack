ClearAll[b,c,ee,h,ss];
h={h1,h2,h3}; ee={e1,e2,e3};
assumptions=Element[Join[h,ee,{c,ss}],Reals] && ss>0 && h.h>0;
bb=-(h.ee)/(h.h); proj=IdentityMatrix[3]-Outer[Times,h,h]/(h.h);
rho=2(Sqrt[1+((e1+h1*b)/ss)^2]-1);
<|"quadratic_stationary"->FullSimplify[D[(ee+b*h).(ee+b*h),b]/.b->bb,assumptions],
"projection_identity"->FullSimplify[ee+bb*h-proj.ee,assumptions],
"projection_null_load"->FullSimplify[proj.h,assumptions],
"shifted_optimum_difference"->FullSimplify[(-(h.(ee-c*h))/(h.h))-bb,assumptions],
"soft_l1_first_derivative"->FullSimplify[D[rho,b],Element[{e1,h1,b},Reals]&&ss>0],
"soft_l1_second_derivative"->FullSimplify[D[rho,{b,2}],Element[{e1,h1,b},Reals]&&ss>0],
"constant_regressor_projected"->FullSimplify[proj.(c*h),assumptions]|>
