Clear[b,da,h,t,n,dt,m,f,p,r,c,v,lam,x];
ass=Element[{b,da,h,t,m,f,p,r,c,v,lam},Reals]&&h>0&&m>0&&v>0&&lam>0;
bias=Integrate[b,{t,0,h}];
accel=Integrate[da*t,{t,0,h}];
discrete=FullSimplify[Sum[((b+da*(j-1)*dt)+(b+da*j*dt))/2*dt,{j,1,n}]/.dt->h/n,Element[n,Integers]&&n>0];
speedScale=\[FreeformPrompt]["1 meter per second"];
timeScale=\[FreeformPrompt]["1 second"];
lengthScale=\[FreeformPrompt]["1 meter"];
unitV=UnitSimplify[speedScale/speedScale];unitS=UnitSimplify[lengthScale/(timeScale*speedScale)];
a=(Min[f,p/v]-r-c*v^2)/m;
gauge=FullSimplify[(a/.{m->lam*m,f->lam*f,p->lam*p,r->lam*r,c->lam*c})-a,ass];
jac=Table[D[f/m,z],{z,{f,m}}];
robust=FullSimplify[(x*Sqrt[2/(Sqrt[1+x^2]+1)])^2-2*(Sqrt[1+x^2]-1),Element[x,Reals]];
<|"constantVelocityBiasDistance"->bias,"accelerationBiasDistance"->accel,"trapezoidalAffineBias"->discrete,"sensitivityToBias"->D[bias,b],"sensitivityToAccelBias"->D[accel,da],"dimensionlessVelocity"->unitV,"dimensionlessPrefix"->unitS,"gaugeDifference"->gauge,"gaugeNullSensitivity"->Simplify[jac.{f,m}],"robustResidualIdentity"->robust,"assumptions"->"Constant-bias examples and positive mass/speed/scaling only; no nonlinear observer stability claim."|>
