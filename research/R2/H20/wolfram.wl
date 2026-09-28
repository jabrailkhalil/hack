ClearAll[x,b,al,p,r,c,w,k,psi,a,ww,dc,h];
w[x_,al_,b_]:=1/(1+al Max[0,x]^2/(b^2+Max[0,x]^2));
wp=(b^2+x^2)/(b^2+(1+al)x^2);
checks=<|"weightBounds"->FullSimplify[1/(1+al)<=wp<=1,Assumptions->{x>=0,b>0,al>=0}],
"alphaZero"->FullSimplify[wp/.al->0],
"originRight"->Limit[wp,x->0,Direction->"FromAbove"],
"originDerivativeRight"->Limit[D[wp,x],x->0,Direction->"FromAbove"],
"tailPositiveCorrection"->FullSimplify[Limit[p*x/(p+r*x/c/wp),x->Infinity],Assumptions->{b>0,al>=0,p>0,r>0,c>0}],
"josephIdentity"->FullSimplify[(1-p/(p+r))^2*p+(p/(p+r))^2*r==p*r/(p+r)],
"commonModeMeasurementRank"->MatrixRank[{{1,1,0},{1,0,1}}],
"commonModeNullSpace"->NullSpace[{{1,1,0},{1,0,1}}]|>;
ww[x_,a_]:=1/(1+a Max[0,x]^2/((3/10)^2+Max[0,x]^2));
dc[x_,a_]:=(1/100)*x/((1/100)+(4/100)*Max[1,Abs[x]/(3/10)]/ww[x,a]);
bias=Table[{al,If[al==0,0,NIntegrate[(dc[x,al]+dc[-x,al])*Exp[-x^2/(2*(1/10)^2)]/((1/10)*Sqrt[2*Pi]),{x,0,3/10,Infinity},WorkingPrecision->30,AccuracyGoal->18,PrecisionGoal->15,MaxRecursion->20]]},{al,{0,1/4,1/2}}];
pos=(b^2+x^2)/(b^2+(1+a)*x^2);
deriv=FullSimplify[D[x*pos,x],Assumptions->{b>0,x>=0,0<=a<=1/2}];
<|"checks"->checks,"pairedIntegralCorrectionBias_mps"->bias,
"positiveDerivative"->FullSimplify[deriv>0,Assumptions->{b>0,x>=0,0<=a<=1/2}],
"weightScalingInvariant"->FullSimplify[pos==((h*b)^2+(h*x)^2)/((h*b)^2+(1+a)*(h*x)^2),Assumptions->{h>0,b>0,x>=0,a>=0}]|>
