ClearAll[x,lim];
accelerationUnit=UnitSimplify[\[FreeformPrompt]["1 meter per second"]/\[FreeformPrompt]["1 second"]];
dimensionlessTime=UnitSimplify[\[FreeformPrompt]["0.1 seconds"]/\[FreeformPrompt]["0.5 seconds"]];
clipped=FullSimplify[-lim<=Min[lim,Max[-lim,x]]<=lim,Assumptions->lim>0&&Element[x,Reals]];
{accelerationUnit,dimensionlessTime,clipped}
