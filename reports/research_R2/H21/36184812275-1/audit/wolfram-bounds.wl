(* Additional symbolic check after code commit, without parameter changes. *)
Clear[vl,v,vh,gl,g,gh,h,r,dl,d,dh,tl,tt,th,ff,pp,aa,bb];
ordinary=Reduce[vl<=v<=vh && gl<=g<=gh && h>=0 && (v+h*g<vl+h*gl || v+h*g>vh+h*gh),{vl,v,vh,gl,g,gh,h},Reals];
actuator=Reduce[0<=r<=1 && dl<=d<=dh && tl<=tt<=th && (r*d+(1-r)*tt<r*dl+(1-r)*tl || r*d+(1-r)*tt>r*dh+(1-r)*th),{r,dl,d,dh,tl,tt,th},Reals];
power=FullSimplify[Min[ff,pp/Max[bb,1]]<=Min[ff,pp/Max[aa,1]],Assumptions->{ff>0,pp>0,0<=aa<=bb,Element[{ff,pp,aa,bb},Reals]}];
positive=FullSimplify[2*qq*v+rr*Sech[v/b]^2/b>=0,Assumptions->{qq>=0,rr>=0,b>0,v>0}];
negative=FullSimplify[-2*qq*v+rr*Sech[v/b]^2/b>=0,Assumptions->{qq>=0,rr>=0,b>0,v<0}];
Print[ToString[<|"velocity_interval_counterexample"->ordinary,"actuator_interval_counterexample"->actuator,"power_cap_nonincreasing"->power,"resistance_derivative_positive_side_nonnegative"->positive,"resistance_derivative_negative_side_nonnegative"->negative|>,InputForm]];
