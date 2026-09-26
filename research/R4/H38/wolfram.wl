ClearAll[nu,r0,p,e,c,re,k,scale,lam,j,raw];
a=nu>2&&r0>0&&p>0&&c>=0&&re>0&&Element[e,Reals];
scale=r0 (nu-2)/nu;
lam=(nu+1)/(nu+(e^2+c)/scale);
raw=FullSimplify[scale/lam,a];
k=p/(p+re);j=(1-k)^2 p+k^2 re;
ExportString[<|"raw_effective_R"->ToString[raw,InputForm],"scale_to_variance"->FullSimplify[scale nu/(nu-2)==r0,a],"raw_formula"->FullSimplify[raw==((nu-2)r0+e^2+c)/(nu+1),a],"joseph"->ToString[FullSimplify[j,a],InputForm],"gain_reconstruction"->FullSimplify[1-j/p==k,a],"positive_covariance"->FullSimplify[0<j<p,a],"lower_floor_condition"->FullSimplify[(raw<=r0)==(e^2+c<=3r0),a],"gaussian_limit"->ToString[Limit[raw,nu->Infinity],InputForm],"gain_bounds_with_clipped_R"->FullSimplify[p/(p+100 r0)<=k<=p/(p+r0),a&&r0<=re<=100r0],"assumptions"->ToString[a,InputForm],"scope"->"Scalar algebra for fixed final effective R, NOT true nonlinear Student posterior covariance; variance floor may break reconstructed-gain equality."|>,"RawJSON"]
