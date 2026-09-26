ClearAll[d0,t0,t1,h,s,tau,x,y,z];
f[d_,q_,a_]:=q+(d-q) Exp[-a/tau];
assumptions=Element[{d0,t0,t1,h,s,tau},Reals]&&tau>0&&h>=0&&0<=s<=h;
event=f[f[d0,t0,s],t1,h-s];legacy=f[d0,t1,h];
difference=(t0-t1)(1-Exp[-s/tau]) Exp[-(h-s)/tau];
<|"twoSegmentEndpoint"->event,
"differenceIdentity"->FullSimplify[event-legacy-difference,assumptions],
"constantCommandParity"->FullSimplify[(event-legacy)/.t1->t0,assumptions],
"leftBoundaryParity"->FullSimplify[(event-legacy)/.s->0,assumptions],
"rightBoundaryOldCommandOnly"->FullSimplify[(event-f[d0,t0,h])/.s->h,assumptions],
"zeroStep"->FullSimplify[(event-d0)/.{h->0,s->0},assumptions],
"convexCounterexample"->Reduce[0<=z<=1&&-1<=x<=1&&-1<=y<=1&&Abs[z*x+(1-z)*y]>1,{x,y,z},Reals]|>
