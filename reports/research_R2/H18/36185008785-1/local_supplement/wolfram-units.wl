Clear[l,s,T,p,c,d,qv,qd];
dims={p->l^2/s^2,c->l^2/s^3,d->l^2/s^4,qv->l^2/s^3,qd->l^2/s^5,T->s};
terms={p,T*c,T^2*d,T*qv,T^3*qd};
unitChecks=Simplify[(#/.dims)/(l^2/s^2)]& /@terms;
F={{1,T},{0,1}}; H={{1,0}}; observability=Join[H,H.F];
ExportString[<|"varianceTermDimensionRatios"->unitChecks,
"observabilityDeterminantWithTwoMeasurements"->ToString[Det[observability],InputForm],
"outageObservationMatrixRank"->0,"finiteHorizonEigenvalues"->ToString[Eigenvalues[F],InputForm],
"interpretation"->"Units agree; two distinct ideal velocity observations locally observe constant d when T!=0. No observations during outage: no identification. Unit eigenvalues imply polynomial covariance growth, not asymptotic stability."|>,"JSON"]
