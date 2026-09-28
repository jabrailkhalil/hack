# Sources and scope actually read

Baseline: complete user ZIP verified to 301-file tree eae49a504bc59b5c9b408445150bef32e111956f, independently bound to commit e3b0c9c039d2953fbfcda51231263d38ef9f1024 by GitHub git/commits GET. Entire core, guarded_readout, Timeline, node, guarded_node, canonical launch, full profile, loader/split, evaluator and relevant tests were read. Historical final-test measurements were not evaluated.

Previous negative results: PR30 (R2-H17, constant 50 ms command dead time, active but fault regression .647598%); PR44 (R3-H30 native wheel-time conditioning, fault regression2.95394%, common-mode2.57746%); PR25 (H08 exact actuator integral into velocity plus midpoint resistance, fault regression.588397%). These are historical results on their respective baselines, not new H32 measurements. Full returned PR descriptions were read. The low-speed predicate is reused from research/R3/H30/run.py at f1a940ebb8ea4694efcbc20d96b9062befdc4ab5, not inferred from its numbers.

Primary public source read at HTML method-definition level: https://www.mathworks.com/help/control/ref/c2doptions.html . The ZOH method assumes piecewise-constant inputs over the sampling interval. This supports the mathematical hold convention only; MATLAB was not run and the documentation does not prove H32 vehicle accuracy or physical timestamp semantics.

Wolfram input and actual response are stored beside this file. Verified two-segment exponential endpoint and differences, limiting cases and convex bound. No stability proof for the complete nonlinear switched/clipped observer. Source timestamps may differ from actual command actuation; existing calibration may compensate the legacy time convention.

Known Consensus/Scite quota stops were not bypassed or retried. No new claims based on unreturned citation contexts or paid papers.
