ClearAll[v0,a,tf,tr,df,dr,tau,h1,h2,sigma,rho,d,b,w,L];
affine=FullSimplify[((v0+a tf)+(v0+a tr))/2-(v0+a (tf+tr)/2)];
mono=FullSimplify[((tf+df)+(tr+dr))/2>(tf+tr)/2,Assumptions->df>0&&dr>0];
causal=FullSimplify[(tf+tr)/2<=Max[tf,tr],Assumptions->Element[{tf,tr},Reals]];
weight=FullSimplify[1-Exp[-h1/tau] Exp[-h2/tau]-(1-Exp[-(h1+h2)/tau]),Assumptions->tau>0&&h1>0&&h2>0];
ema=FullSimplify[Exp[-h2/tau](Exp[-h1/tau]d+(1-Exp[-h1/tau])b)+(1-Exp[-h2/tau])b-(Exp[-(h1+h2)/tau]d+(1-Exp[-(h1+h2)/tau])b)];
stable=FullSimplify[0<Exp[-h1/tau]<1,Assumptions->h1>0&&tau>0];
convex=FullSimplify[-L<=(1-w)d+w b<=L,Assumptions->L>0&&0<=w<=1&&-L<=d<=L&&-L<=b<=L];
cov=Simplify[({1/2,1/2}.(sigma^2 {{1,rho},{rho,1}}).{1/2,1/2})];
ExportString[<|"affinePairError"->affine,"strictPairMonotonicity"->mono,"pairTimeNotAfterLatestSource"->causal,"uniqueIntervalsLearningWeightError"->weight,"twoStepEMAErrorConstantTarget"->ema,"scalarEMAStable"->stable,"boundedConvexUpdate"->convex,"pairNoiseVarianceInputForm"->ToString[cov,InputForm],"fullyCorrelatedVariance"->ToString[cov/.rho->1,InputForm],"dt0Weight"->(1-Exp[-h1/tau]/.h1->0),"duplicateLearningWarning"->"Reusing one pair twice adds 1-exp(-2 h/tau) instead of 1-exp(-h/tau); unique consumption is a software invariant, not a covariance independence assumption.","units"->"z:m/s; pair dt:s; measured acceleration, drive_a, resistance, d:m/s^2; dt/tau dimensionless; raw EMA does not certify switched observer closed-loop stability."|>,"RawJSON"]
