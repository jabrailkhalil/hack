"""Baseline-only foundation. No candidate comparison, no GNSS, no fitting."""
import argparse,datetime,json,math,os,time
from collections import Counter
from pathlib import Path
from common import *

def sign(u):return (u>.04)-(u<-.04)
def releasing(x,r):
 return x!=0 and ((x>0 and r<0) or (x<0 and r>0) or abs(r)<abs(x))
class Probe(GuardedReadoutObserver):
 def reset(self,**kw):
  super().reset(**kw);self.episodes=[];self.old_u=0.;self.sign_since=None;self.previous_sign=0;self.last_episode=-math.inf
 def step(self,t,command=None,front=None,rear=None):
  valid=self._valid(command,t,self.c.command_timeout_s) and abs(command.value)<=1.000001
  u=max(-1.,min(1.,command.value)) if valid else 0.
  sg=sign(u);r=self.drive_target(u,self.v);old=self.old_u;oldsg=self.previous_sign
  sustained=self.sign_since is not None and t-self.sign_since>=.5
  good=(self._valid(front,t,self.c.max_age_s) and self._valid(rear,t,self.c.max_age_s) and abs(front.t-rear.t)<=self.c.pair_skew_s and abs(front.value-rear.value)<=.15 and (front.value+rear.value)/2>2)
  if valid and sustained and oldsg and good and abs(self.drive_a)>=.15 and abs(u-old)>=.15 and releasing(self.drive_a,r) and t-self.last_episode>=2:
   kind=('traction_to_coast' if oldsg>0 else 'brake_to_coast') if sg==0 else ('sign_change' if sg!=oldsg else 'amplitude_release')
   self.episodes.append(dict(t=t,old_u=old,new_u=u,drive=self.drive_a,target=r,kind=kind,potential_mps=abs(self.drive_a)*self.c.actuator_tau_s/2))
   self.last_episode=t
  if not valid or sg!=oldsg:self.sign_since=t if valid and sg else None
  self.previous_sign=sg if valid else 0;self.old_u=u
  return super().step(t,command,front,rear)
def episodes(events):
 c,r=profile();obs=Probe(c,readout=r);old=ev.Observer
 try:
  ev.Observer=lambda cfg:obs;array,info=ev.replay(events,c,OPS)
 finally:ev.Observer=old
 end=float(events[:,0].max());cmd=events[events[:,1]==0]
 good=[]
 for e in obs.episodes:
  if e['t']+.25>end:continue
  future=cmd[(cmd[:,0]>e['t'])&(cmd[:,0]<=e['t']+.25)]
  e['false_transition_proxy']=any(sign(float(u))==sign(e['old_u']) and abs(u)>=.9*abs(e['old_u']) for u in future[:,2])
  good.append(e)
 return good,array,info

def run(out):
 out.mkdir(parents=True,exist_ok=False);pins=verify_sources();store=Store()
 save(out/'started.json',dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),baseline_sha=BASELINE,source_sha256=pins,diagnostic_sha256=sha(__file__),measured_source_sha=os.environ.get('H35_SOURCE_SHA'),stage='train_foundation',test_opened=False,validation_opened=False))
 rows=[]
 for bag in store.plan['splits']['train']:
  events,_=store.load(bag,'train');es,a,info=episodes(events);c,r=profile();old=ev.Observer
  try:ev.Observer=lambda cfg:GuardedReadoutObserver(cfg,readout=r);b,bi=ev.replay(events,c,OPS)
  finally:ev.Observer=old
  assert np.array_equal(a,b,equal_nan=True) and info==bi,bag
  row=dict(bag=bag,group=store.records[bag]['group'],outputs=len(a),runtime=info,episodes=es,exact_probe_parity=True)
  rows.append(row);save(out/'bags'/f'{bag}.json',row);save(out/'access.json',store.access)
  print('FOUNDATION',bag,len(es),flush=True)
 es=[e for row in rows for e in row['episodes']];groups={r['group'] for r in rows if r['episodes']}
 potential=float(np.median([e['potential_mps'] for e in es])) if es else None
 fpr=sum(e['false_transition_proxy'] for e in es)/len(es) if es else None
 reasons=[]
 if len(es)<30 or len(groups)<3:reasons.append('insufficient_release_coverage')
 if potential is None or potential<.01:reasons.append('insufficient_potential')
 if fpr is not None and fpr>.25:reasons.append('false_transition_proxy_exceeds_25_percent')
 verdict='PASS' if not reasons else ('REJECTED' if 'false_transition_proxy_exceeds_25_percent' in reasons else 'INCONCLUSIVE')
 result=dict(verdict=verdict,reasons=reasons,episodes=len(es),groups=len(groups),median_potential_mps=potential,false_transition_proxy_rate=fpr,kinds=dict(Counter(e['kind'] for e in es)),bags=len(rows),published_outputs=sum(r['outputs'] for r in rows),rows=rows,train_gnss_opened=False,validation_opened=False,test_opened=False)
 save(out/'results.json',result);print(json.dumps({k:v for k,v in result.items() if k!='rows'},indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);run(p.parse_args().output)
