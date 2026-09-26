(* Executed with WolframLanguageEvaluator. This is an open-loop actuator model,
   not a proof of stability/accuracy of the nonlinear odometry observer. *)
ClearAll[s,t,L,tau,k,w,w1,w2,dt];
ass=tau>0&&L>=0&&k>0&&w>0;
h=k Exp[-L s]/(1+tau s);
stepLaplace=FullSimplify[Integrate[k(1-Exp[-(t-L)/tau]) Exp[-s t],{t,L,Infinity},Assumptions->tau>0&&L>=0&&s>0&&k>0]-h/s,Assumptions->tau>0&&L>=0&&s>0&&k>0];
magnitude=FullSimplify[ComplexExpand[Abs[h/.s->I w]],Assumptions->ass];
phase=-w L-ArcTan[w tau];
jac={{D[phase,L],D[phase,tau]}/.w->w1,{D[phase,L],D[phase,tau]}/.w->w2};
det=Factor[Det[jac]];
(* The service interpreted the natural-language prompts as seconds/radians.
   Resolved units below make this worksheet executable in a plain WL kernel. *)
qtau=Quantity[.3927619145850434,"Seconds"];
qdt=Quantity[.05,"Seconds"];qfreq=Quantity[2,"Radians"/"Seconds"];
<|"step_transform_residual"->stepLaplace,"unit_step_response"->k(1-Exp[-(t-L)/tau]) UnitStep[t-L],"frequency_magnitude"->magnitude,"unwrapped_phase"->phase,"low_frequency_phase"->Series[phase,{w,0,3}],"two_frequency_phase_sensitivity_determinant"->det,"stable_actuator_pole"->Solve[1+tau s==0,s],"discrete_pole_bound"->FullSimplify[0<Exp[-dt/tau]<1,Assumptions->tau>0&&dt>0],"L_zero_limit"->Limit[h,L->0],"tau_zero_limit"->Limit[h,tau->0,Direction->"FromAbove"],"dt_over_tau_units"->UnitSimplify[qdt/qtau],"delay_phase_units"->UnitSimplify[qfreq qdt],"alpha_20Hz"->N[1-Exp[-.05/.3927619145850434]],"additional_delay_phases_at_2_rad_s"->N[-2{.05,.1,.2}]|>
