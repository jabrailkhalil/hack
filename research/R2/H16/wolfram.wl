(* Executed via WolframLanguageEvaluator, 2026-09-25; idealized constant target and resistance. *)
ClearAll[h,tau,dt,n,a0,aa,dd,rr,v0,lam,k,mass,scale,force,power,brake,roll,drag];
vN=v0+dt*(n*aa+(a0-aa)*lam*(1-lam^n)/(1-lam)+n*(dd-rr));
vSum=v0+dt*Sum[aa+(a0-aa)*lam^k+dd-rr,{k,1,n}];
sA=h-tau*(1-Exp[-h/tau]);gauge={force/mass,power/mass,brake/mass,roll/mass,drag/mass};
<|"discrete_sum_identity"->FullSimplify[vN==vSum,Assumptions->(0<lam<1&&Element[n,Integers]&&n>0)],
"discrete_drive_sensitivity"->D[vN,aa],"bias_resistance_sensitivities"->{D[vN,dd],D[vN,rr]},
"continuous_drive_sensitivity"->sA,"short_horizon_series"->Normal[Series[sA,{h,0,3}]],
"long_horizon_normalized_limit"->Limit[sA/h,h->Infinity,Assumptions->tau>0],
"actuator_stability"->FullSimplify[0<Exp[-dt/tau]<1,Assumptions->dt>0&&tau>0],
"mass_force_gauge_invariant"->FullSimplify[(gauge/.{mass->scale*mass,force->scale*force,power->scale*power,brake->scale*brake,roll->scale*roll,drag->scale*drag})==gauge,Assumptions->mass>0&&scale>0],
"continuous_sensitivities_tau0393"->Table[{hh,N[sA/.{h->hh,tau->0.3927619145850434}],hh},{hh,{0.5,2,5}}],
"dimensionless_velocity_residual"->UnitSimplify[(\[FreeformPrompt]["1 meter per second"])/(\[FreeformPrompt]["0.2 meters per second"])],
"power_per_mass_unit"->UnitSimplify[(\[FreeformPrompt]["1 watt"])/(\[FreeformPrompt]["mass of 1 kilogram"])],
"quadratic_drag_per_mass_unit"->UnitSimplify[(\[FreeformPrompt]["1 newton"])/(\[FreeformPrompt]["mass of 1 kilogram"]*(\[FreeformPrompt]["1 meter per second"])^2)]|> // InputForm
