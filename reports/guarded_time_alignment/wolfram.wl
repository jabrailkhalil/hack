(* Executed with WolframLanguageEvaluator during this iteration. *)
Clear[k,b,d,a,h,p,r,dt,dPrevious,dCurrent];
biasNext = (1-k)*b-k*a*h;
correctionNext = (1-k)*d+k*a*h;
<|"CorrectedBias" -> FullSimplify[biasNext+correctionNext],
  "ZeroInitialCorrectedBias" -> FullSimplify[biasNext+correctionNext /. b -> -d],
  "GainFromJosephVariance" -> FullSimplify[1-((1-k)^2*p+k^2*r)/p /. k -> p/(p+r), Assumptions -> {p>0,r>0}],
  "DistanceCorrection" -> dt*(dPrevious+dCurrent)/2|>
(* Results: (1-k)*(b+d), 0, p/(p+r), dt*(dPrevious+dCurrent)/2.
   Constant-acceleration, exact-model bias identity; not a general robustness proof. *)
