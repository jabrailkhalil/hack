(* Executable analytic worksheet: ideal constant evidence INSIDE one 4s epoch.
   No guarantee of odometry closed-loop stability or statistical false alarms. *)
ClearAll[x, tau, dt, q, k, cap, n];
a = Exp[-dt/tau];
next = Min[cap, Max[0, a*x + dt*(q-k)]];
bounded = FullSimplify[0 <= next <= cap,
  Assumptions -> {0 <= x <= cap, cap > 0, dt > 0, tau > 0,
                 Element[{q,k,x,cap,dt,tau},Reals]}];
fixed = dt*(q-k)/(1-Exp[-dt/tau]);
Print[<|"bounded"->bounded,
 "continuousLimit"->Limit[fixed,dt->0,Assumptions->tau>0],
 "zeroElapsed"->FullSimplify[next/.dt->0,Assumptions->0<=x<=cap],
 "poleStable"->FullSimplify[0<Exp[-dt/tau]<1,Assumptions->{dt>0,tau>0}],
 "measurementRank"->MatrixRank[{{1,1,0},{1,0,1}}],
 "unidentifiableNullspace"->NullSpace[{{1,1,0},{1,0,1}}]|>];
Module[{pole=Exp[-0.05], rise, fall, hs={0.3,0.6}},
 rise=NestList[Function[y,Min[2.,Max[0.,pole*y+0.075]]],0.,100];
 fall=NestList[Function[y,Max[0.,pole*y-0.025]],2.,100];
 Print[<|"riseFirst12"->Take[rise,12],"fallFirst5"->Take[fall,5],
 "detectionSamples"->Table[{h,First[Select[Range[0,100],rise[[#+1]]>=h&]]},{h,hs}],
 "recoverySamples"->Table[{h,First[Select[Range[0,100],fall[[#+1]]<=h/4&]]},{h,hs}],
 "fixedPointForEvidence1"->0.075/(1-pole),"pole"->pole|>]];
(* dt,tau,C,threshold,cap: seconds. Innovations and k are dimensionless.
   Simultaneous wheel observations = [v+b_front, v+b_rear]: rank 2<3.
   A common bias cannot be identified from two wheels alone.
   Time-aware update doesn't imply independence of consecutive residuals. *)
