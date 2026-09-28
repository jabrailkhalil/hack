(* Standalone bindings use the units actually resolved by the Wolfram service. *)
(* H21 actual Wolfram Language evaluation, 2026-09-25. No empirical guarantee. *)
a={{0,1,0},{0,0,0},{0,0,0}}; c={{1,0,1}}; o=Join[c,c.a,c.MatrixPower[a,2]];
rp=FullSimplify[D[rr*Tanh[v/b]+qq*v^2,v],Assumptions->{rr>=0,qq>=0,b>0,v>0}];
rn=FullSimplify[D[rr*Tanh[v/b]-qq*v^2,v],Assumptions->{rr>=0,qq>=0,b>0,v<0}];
clip[x_,m_]:=Min[m,Max[-m,x]];
res=<|"observability_matrix"->o,"rank"->MatrixRank[o],"nullspace"->NullSpace[o],"offset_invariance"->Simplify[c.({v+k,d,bias-k}-{v,d,bias})],"resistance_positive_derivative"->rp,"resistance_negative_derivative"->rn,"brake_derivative"->D[-q*bb*Tanh[v/b],v],"rho_between_zero_one"->FullSimplify[0<Exp[-h/tau]<=1,Assumptions->{h>=0,tau>0}],"drive_width"->Expand[rho*ahi+(1-rho)*thi-(rho*alo+(1-rho)*tlo)],"velocity_width_increment"->Expand[(vhi+h*ghi)-(vlo+h*glo)-(vhi-vlo)],"clip_preserves_order"->FullSimplify[clip[x,m]<=clip[y,m],Assumptions->{Element[{x,y,m},Reals],x<=y,m>0}],"dt_zero_drive"->Limit[Exp[-h/tau]*aa+(1-Exp[-h/tau])*tt,h->0],"drive_integral"->Integrate[tt+(aa-tt)*Exp[-s/tau],{s,0,h},Assumptions->{h>=0,tau>0}],"interval_sum_example"->(Interval[{-1,2}]+Interval[{-0.6,0.6}])|>;
Print[ToString[res,InputForm]];
vunit=Quantity[1,"Meters"/"Seconds"]; aunit=Quantity[1,"Meters"/"Seconds"^2]; tunit=Quantity[1,"Seconds"]; funit=Quantity[1,"Newtons"]; munit=Quantity[1,"Kilograms"];
Print[ToString[<|"acceleration_times_time"->UnitSimplify[aunit*tunit],"force_over_mass"->UnitSimplify[funit/munit],"velocity_plus_increment"->UnitSimplify[vunit+aunit*tunit],"velocity_integral"->UnitSimplify[vunit*tunit],"decay_argument"->UnitSimplify[tunit/tunit]|>,InputForm]];
