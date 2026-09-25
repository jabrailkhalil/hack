Clear[tt,s,p,c,d,qv,qd,k,r];
f[x_]:={{1,x},{0,1}};
p0={{p,c},{c,d}};
q=Integrate[f[s].DiagonalMatrix[{qv,qd}].Transpose[f[s]],{s,0,tt}];
pp=Expand[f[tt].p0.Transpose[f[tt]]+q];
h={{1,0}}; gain={{k},{0}}; a=IdentityMatrix[2]-gain.h;
joseph=Expand[a.p0.Transpose[a]+gain.{{r}}.Transpose[gain]];
optimal=FullSimplify[joseph/.k->p/(p+r),Assumptions->{p>0,r>0}];
envelope=DiagonalMatrix[{2p,2d}]-p0;
<|"propagated"->pp,"processNoise"->q,
"constantBiasLimit"->Simplify[pp/.qd->0],"joseph"->joseph,
"optimalVelocityGain"->optimal,"PSDJosephDeterminant"->Factor[Det[joseph]],
"decorrelationEnvelopeDifference"->envelope,
"envelopeDifferenceDeterminant"->Factor[Det[envelope]],
"zeroTime"->Simplify[(pp/.tt->0)==p0],
"semigroup"->Simplify[f[tt].f[s]==f[tt+s]],
"observabilityDeterminant"->Det[Join[h,h.f[tt]]]|>
