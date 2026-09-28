Clear[v,b,e1,e2,s1,s2,rho,a,dt,x,y];
meanError=Expand[((v+b+e1)+(v+b+e2))/2-v];
variance=Simplify[{1/2,1/2}.{{s1^2,rho*s1*s2},{rho*s1*s2,s2^2}}.{1/2,1/2}];
bound=Reduce[a>=0&&dt>=0&&-a*dt/2<=x<=a*dt/2&&-a*dt/2<=y<=a*dt/2&&Abs[(x+y)/2]>a*dt/2,{a,dt,x,y},Reals];
<|"commonBiasSurvives"->meanError,"varianceOfMean"->variance,"equalVarianceRho1"->Simplify[variance/.{s2->s1,rho->1}],"equalVarianceRho0"->Simplify[variance/.{s2->s1,rho->0}],"midpointBoundCounterexample"->bound|>
