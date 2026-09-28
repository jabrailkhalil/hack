Clear[q, f, p, w, m, c];
ass = f > 0 && p > 0 && w > 0 && m > 0 && 0 <= q <= 1;
a0 = q Min[f, p/w]/m;
a1 = Min[q f, p/w]/m;
delta = Piecewise[{{0, f <= p/w}, {q (f - p/w)/m, f > p/w && q f <= p/w}}, (1-q) p/(m w)];
<|"difference_identity" -> FullSimplify[PiecewiseExpand[a1-a0-delta, ass], ass],
"q0" -> FullSimplify[(a1-a0) /. q -> 0, ass],
"q1" -> FullSimplify[(a1-a0) /. q -> 1, ass],
"force_limited" -> FullSimplify[a1 == a0, ass && f <= p/w],
"nonnegative" -> FullSimplify[a1 >= a0, ass],
"upper_bound" -> FullSimplify[a1-a0 <= f/(4 m), ass],
"saturation_continuity" -> FullSimplify[(q f/m-p/(m w)) /. q -> p/(w f), ass],
"piecewise_difference" -> delta, "branch_slopes" -> {f/m, 0},
"peak_over_q_power_limited" -> FullSimplify[delta /. q -> p/(w f), f > p/w && p > 0 && w > 0 && m > 0],
"force_div_mass_units" -> UnitSimplify[\[FreeformPrompt]["1 newton"]/\[FreeformPrompt]["1 kilogram"]],
"power_div_speed_units" -> UnitSimplify[\[FreeformPrompt]["1 watt"]/\[FreeformPrompt]["1 meter per second"]]|>
