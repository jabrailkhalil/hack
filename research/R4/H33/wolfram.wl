ClearAll[diff, cov, weights, h, sig, eps, d];
diff[n_] := Table[KroneckerDelta[j, i + 1] - KroneckerDelta[j, i], {i, n}, {j, n + 1}];
cov[n_] := diff[n].Transpose[diff[n]];
weights[m_, x_] := LinearSolve[m, x]/(x.LinearSolve[m, x]);
w4 = weights[cov[4], ConstantArray[h, 4]]; wu4 = ConstantArray[1/(4 h), 4];
variableH = {7/100, 11/100, 9/100, 13/100}; variableW = weights[cov[4], variableH];
regW = weights[cov[6] + IdentityMatrix[6]/10^6, ConstantArray[1/10, 6]];
ca = DiagonalMatrix[1/variableH].(sig^2 cov[4]).DiagonalMatrix[1/variableH];
<|"difference_covariance_n4" -> sig^2 cov[4],
"positive_leading_minors_n1to6" -> Table[Det[cov[n]], {n, 1, 6}],
"variable_dt_acceleration_covariance" -> ca,
"equal_dt_weights_n4" -> Simplify[w4],
"equal_dt_gls_variance" -> Simplify[sig^2 w4.cov[4].w4],
"equal_dt_unweighted_variance" -> Simplify[sig^2 wu4.cov[4].wu4],
"last_two_endpoint_variance" -> 2 sig^2/h^2,
"scale_cancels" -> Simplify[weights[sig^2 cov[4], ConstantArray[h, 4]] == w4, Assumptions -> sig > 0 && h > 0],
"affine_variable_dt_exact" -> Simplify[variableW.(d variableH) == d],
"n2_equal_dt_gls_equals_unweighted" -> Simplify[weights[cov[2], {h,h}] == {1/(2h),1/(2h)}],
"worst_n6_condition" -> N[Max[Eigenvalues[cov[6]]]/Min[Eigenvalues[cov[6]]]],
"regularized_n6_affine_exact" -> Simplify[regW.ConstantArray[d/10,6] == d],
"regularized_n6_variance_at_sigma01_dt01" -> N[(1/100) regW.cov[6].regW],
"normal_equation" -> HoldForm[dhat == (h.Inverse[C].y)/(h.Inverse[C].h)]|>
