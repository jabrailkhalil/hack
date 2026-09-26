"""Matched offline step/replay timing; no accuracy selection and no ROS claim."""
import argparse, datetime, json, os, time
from pathlib import Path
from common import *
from factory import build,enabled_identity
class Clocked:
 def __init__(self,o):self.o=o;self.step_cpu_ns=0;self.steps=0
 def __getattr__(self,k):return getattr(self.o,k)
 def step(self,t,*args,**kwargs):
  if t<10:return self.o.step(t,*args,**kwargs)
  start=time.process_time_ns();e=self.o.step(t,*args,**kwargs)
  self.step_cpu_ns+=time.process_time_ns()-start;self.steps+=1;return e

def trial(events,ratio,fault):
 c,_=profile();clock=Clocked(build(ratio));timeline=ev.Timeline(clock,rate_hz=20.,delay_s=0.)
 output=[];begin=None
 for t,ch,v in events:
  if t>190:break
  if begin is None and t>=10:begin=(time.process_time_ns(),time.perf_counter_ns())
  if fault and fault['start']<=t<fault['end'] and int(ch) in (1,2):continue
  timeline.ingest(int(ch),Sample(float(t),float(v)))
  for e,_ in timeline.advance():
   if e.t>=10:output.append((e.t,e.v,e.s))
 end=(time.process_time_ns(),time.perf_counter_ns())
 return dict(step_cpu_s=clock.step_cpu_ns/1e9,replay_cpu_s=(end[0]-begin[0])/1e9,replay_wall_s=(end[1]-begin[1])/1e9,steps=clock.steps,outputs=len(output),output_hash=hashlib.sha256(np.asarray(output,float).tobytes()).hexdigest())

def run(out):
 out.mkdir(parents=True,exist_ok=False);verify_sources();store=Store();bag=store.plan['splits']['development'][0];events,_=store.load(bag,'development')
 faults=[f for f,w in guarded.fault_windows(events) if f['kind']=='dropout' and f['end']-f['start']==10]
 assert len(faults)==1 and faults[0]['end']<190
 rows=[]
 for name,fault in (('healthy',None),('original_dropout10',faults[0])):
  for ratio in (.5,2.):
   for k in range(6):
    order=[None,ratio] if k%2==0 else [ratio,None];results={}
    for r in order:results['baseline' if r is None else 'candidate']=trial(events,r,fault)
    rows.append(dict(scenario=name,ratio=ratio,pair=k,order='AB' if k%2==0 else 'BA',**results))
 summary=[]
 for name in ('healthy','original_dropout10'):
  for ratio in (.5,2.):
   subset=[r for r in rows if r['scenario']==name and r['ratio']==ratio]
   entry=dict(scenario=name,ratio=ratio)
   for key in ('step_cpu_s','replay_cpu_s','replay_wall_s'):
    entry[key]=dict(baseline_median=float(np.median([r['baseline'][key] for r in subset])),candidate_median=float(np.median([r['candidate'][key] for r in subset])),median_paired_relative_change=float(np.median([r['candidate'][key]/r['baseline'][key]-1 for r in subset])))
   summary.append(entry)
 save(out/'results.json',dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),source_sha=os.environ.get('H35_SOURCE_SHA'),identity=enabled_identity(),bag=bag,warmup_s=10.,measured_s=180.,repetitions='3AB+3BA per ratio/scenario',threads=1,access=store.access,rows=rows,summary=summary,scope='Offline CPU wall; NOT ROS latency/RSS; identical collectors'))
 print(json.dumps(summary,indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);run(p.parse_args().output)
