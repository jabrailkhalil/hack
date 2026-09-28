ClearAll[z,y,pp,rr,ss,ww];
prob=1/(1+Exp[-z]); loss=Log[1+Exp[z]]-y*z; kk=pp/(pp+rr);
<|"sigmoid_derivative_identity"->FullSimplify[D[prob,z]-prob*(1-prob)],
"binary_loss_gradient_identity"->FullSimplify[D[loss,z]-(prob-y)],
"loss_curvature"->FullSimplify[D[loss,{z,2}]],
"curvature_nonnegative"->FullSimplify[D[loss,{z,2}]>=0,Assumptions->Element[z,Reals]],
"gain_derivative"->D[kk,rr],
"inflated_gain_no_larger"->FullSimplify[pp/(pp+ss)<=kk,Assumptions->pp>0&&ss>=rr&&rr>0],
"Joseph_identity"->FullSimplify[(1-kk)^2*pp+kk^2*rr-(1-kk)*pp,Assumptions->pp>0&&rr>0],
"weighted_noise_floor"->FullSimplify[ss/ww>=rr,Assumptions->ss>=rr&&rr>0&&0<ww<=1]|>
