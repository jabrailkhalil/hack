(* Executed through WolframLanguageEvaluator before H18 measurements. *)
Clear[t,s,p,c,d,qv,qd,k,r];
f[x_] := {{1,x},{0,1}};
p0={{p,c},{c,d}};
noise=Integrate[f[s].{{qv,0},{0,qd}}.Transpose[f[s]],{s,0,t}];
prior=Expand[f[t].p0.Transpose[f[t]]+noise];
a=IdentityMatrix[2]-{{k},{0}}.{{1,0}};
joseph=Simplify[a.p0.Transpose[a]+{{k},{0}}.{{r}}.{{k,0}}];
assumptions=p>=0&&d>=0&&r>=0&&c^2<=p*d&&0<=k<=1&&t>=0&&qv>=0&&qd>=0;
checks={Simplify[prior[[1,1]]==(p+2*t*c+t^2*d+qv*t+qd*t^3/3)],
 Simplify[prior[[1,2]]==(c+t*d+qd*t^2/2)],
 Simplify[prior[[2,2]]==d+qd*t],
 Simplify[Det[joseph]==(1-k)^2*(p*d-c^2)+k^2*r*d],
 FullSimplify[p+2*t*Sqrt[p*d]+t^2*d >= p+2*t*c+t^2*d,assumptions]};
ExportString[<|"F"->ToString[f[t],InputForm],"Q"->ToString[noise,InputForm],
 "prior"->ToString[prior,InputForm],"SchmidtJoseph"->ToString[joseph,InputForm],
 "checks"->checks,"constantD_limit"->ToString[prior/.qd->0,InputForm],
 "zeroPrior"->ToString[(prior/.{t->0}),InputForm]|>,"JSON"]
