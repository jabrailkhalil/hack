Clear[c0,del,f,r,k,v,a,h];
ass=c0>0&&f!=0&&r/f>0&&Element[{c0,del,f,r,k,v,a,h},Reals]&&k>0;
<|"product"->FullSimplify[(c0 Exp[del]) (c0 Exp[-del]),ass],
"relative_equality"->FullSimplify[(Exp[del] f-Exp[-del] r)/.del->Log[r/f]/2,ass],
"sensitivities"->{D[Log[r/f]/2,f],D[Log[r/f]/2,r]},
"near_zero_sensitivity"->Limit[1/(2 r),r->0,Direction->"FromAbove"],
"common_gain_invisible"->FullSimplify[Log[(k r)/(k f)]/2-Log[r/f]/2,ass],
"agreement_not_truth"->FullSimplify[{Log[(k v)/(k v)]/2,(k v+k v)/2},k>0&&v>0],
"mean_error_on_equal_inputs"->FullSimplify[(v Exp[del]+v Exp[-del])/2-v,ass],
"mean_series"->Series[(v Exp[del]+v Exp[-del])/2-v,{del,0,2}],
"async_first_order_bias"->Normal[Series[Log[(v+a h)/v]/2,{h,0,1}]],
"cap_factors"->N[Exp[{-1/100,1/100}],15],
"scope"->"Algebra only: equality presumes same true longitudinal velocity, simultaneous nonzero same-sign readings and negligible slip. Product constraint is a gauge; does not validate c0=1/3.6. No stability or accuracy proof for switched observer."|>
