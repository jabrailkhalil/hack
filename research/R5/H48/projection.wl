ClearAll[ax, ay, dx, dy, qx, qy, u, t];
a = {ax, ay}; d = {dx, dy}; q = {qx, qy};
asm = Element[{ax, ay, dx, dy, qx, qy, u, t}, Reals] && dx^2 + dy^2 > 0;
f = Expand[(a + u*d - q).(a + u*d - q)];
us = ((q - a).d)/(d.d); urs = ((q - (a + d)).(-d))/(d.d);
result = <|
 "stationary_derivative_zero" -> FullSimplify[(D[f, u] /. u -> us) == 0, asm],
 "strict_convexity" -> FullSimplify[D[f, {u, 2}] > 0, asm],
 "reversal_parameter" -> FullSimplify[urs == 1 - us, asm],
 "reversal_point" -> FullSimplify[a + u*d == a + d + (1 - u)*(-d), asm],
 "objective_decomposition" -> FullSimplify[f == (f /. u -> us) + (d.d)*(u - us)^2, asm],
 "clamped_reversal" -> FullSimplify[Min[1, Max[0, 1 - t]] == 1 - Min[1, Max[0, t]], Element[t, Reals]],
 "unconstrained_u" -> ToString[us, InputForm],
 "second_derivative" -> ToString[D[f, {u, 2}], InputForm],
 "assumptions" -> ToString[asm, InputForm],
 "scope" -> "Euclidean XY point-to-segment identities only; no frame conversion, topology inference, body heading, map fit or real-data accuracy proof."|>;
ExportString[result, "RawJSON"]
