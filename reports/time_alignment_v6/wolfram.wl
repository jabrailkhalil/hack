(* Symbolic verification performed with Wolfram Language Evaluator. *)
ClearAll[tau, h, target, a0, age, accel, err, v];
a[t_] := target + (a0 - target) Exp[-t/tau];
FullSimplify[Integrate[a[t], {t, 0, h}], tau > 0 && h >= 0]
(* h target + (a0-target) tau (1-Exp[-h/tau]) *)
Expand[(v - accel age) - v]
(* -accel age *)
Expand[(v - accel age + (accel + err) age) - v]
(* age err *)
