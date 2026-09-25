"""Additional guard audit after development; algorithm and thresholds unchanged."""
import json,sys,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(sys.argv[1])/'tools/research_h19'))
from factory import Factory,plain,equal_baseline,ev,Config
F=Factory();Sample=F.candidate['core'].Sample
results={}
for name in ('h03','h06','off'):
 a=F.make(name);b=F.make('baseline');a.reset(velocity=1);b.reset(velocity=1)
 count=0;first=None
 for k in range(80):
  t=k*.05;args=(t,Sample(t,0),Sample(t,7),Sample(t,7))
  x=a.step(*args);y=b.step(*args)
  assert plain(x)==plain(y),(name,k,x,y)
  if y.mode=='REACQUIRING':
   count+=1
   if first is None:first=t
 assert count>0,(name,'The test did not actually enter reacquisition')
 results[name]={'actual_reacquiring_ticks':count,'first_reacquisition_s':first,'all_outputs_equal':True}
# Epoch expiry on a prediction-only tick, followed by a same-stamp held sample.
a=F.make('h03');d=a._h19_detector;c=Config()
for k in range(40):
 t=round(k*.1,8);d.update(t,c,[Sample(t,5.2),Sample(t,5)],['CANDIDATE']*2,[0,1],5,.01,False)
assert d.positive[0]>.3
d.update(4.,c,[None,None],['DUPLICATE_OR_OLD']*2,[],5,.01,False)
assert d.positive==[0.,0.] and d.suspect==[False,False]
results['prediction_only_epoch_expiry']={'passed':True,'new_sample':d.new_sample}
print(json.dumps({'passed':True,'checks':results,'parameter_changes':False},indent=2))
