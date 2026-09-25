(* Executed through WolframLanguageEvaluator; see actual output file. *)
Clear[a0,j,t,h,s,n,k,d,b,x,y,K,g,M,L,ell];
exact=Integrate[a0+j*s,{s,t-h,t}];
endpoint=Expand[(a0+j*t)*h-exact];
composite=FullSimplify[Sum[(a0+j*(t-h+k*h/n))*h/n,{k,1,n}]-exact,Assumptions->{n>=1,Element[n,Integers]}];
partial=FullSimplify[(a0+j*b)*ell-Integrate[a0+j*s,{s,b-ell,b}]];
f[q_]:=Integrate[a0+j*s,{s,t-q,t}];
averageError=FullSimplify[(f[x]+f[y])/2-f[(x+y)/2]];
bounded=FullSimplify[Abs[(1-K)*d+K*g*x]<=M,Assumptions->{Element[{d,x,K,g,M},Reals],M>=0,-M<=d<=M,-M<=x<=M,0<=K<=1,0<=g<=1}];
cellBound=FullSimplify[Integrate[L*(b-s),{s,b-ell,b}],Assumptions->{L>=0,ell>=0}];
units=UnitSimplify[\[FreeformPrompt]["1 meter per second squared"]*\[FreeformPrompt]["1 second"]];
Print[<|"exactAffine"->exact,"endpointError"->endpoint,"compositeRightError"->composite,"partialRightCellError"->partial,"smallAgeLimit"->Limit[endpoint,h->0],"constantAccelerationError"->(endpoint/.j->0),"meanIndividualMinusMeanStamp"->averageError,"convexBound"->bounded,"cellLipschitzBound"->cellBound,"units"->units|>];
(* Second independent call: no violating tuple exists. *)
Clear[d,x,k,g,m];
Print[Reduce[m>=0 && -m<=d<=m && -m<=x<=m && 0<=k<=1 && 0<=g<=1 && (((1-k)*d+k*g*x)>m || ((1-k)*d+k*g*x)<-m),{d,x,k,g,m},Reals]];
