"""Vehicle-only measurement-age evidence, before candidate accuracy IO."""
import argparse, collections, hashlib, json, os
from pathlib import Path
import common as cm
from common import np

class Probe(cm.GuardedReadoutObserver):
    def __init__(self):
        c,r=cm.profile();super().__init__(c,readout=r)
        self.count=collections.Counter();self.ages=[];self.accepted_ages=[]
        self.seen=[set(),set(),set()];self.last_accepted=-float('inf')
    def step(self,t,command=None,front=None,rear=None):
        old_t=self.t;e=super().step(t,command,front,rear)
        self.count['output_ticks']+=1
        unique=[];accepted=[]
        for ch,s in enumerate((command,front,rear)):
            if s is None or s.t in self.seen[ch]:continue
            self.seen[ch].add(s.t);self.count['first_seen_'+str(ch)]+=1
            if ch==0:continue
            age=t-s.t;self.ages.append(age);unique.append(s)
            if old_t is not None and s.t<old_t-1e-9:self.count['new_wheel_before_previous_tick']+=1
            status=(e.front_status,e.rear_status)[ch-1]
            self.count['new_status_'+status]+=1
            if status=='ACCEPTED':
                accepted.append(s);self.accepted_ages.append(age)
                if s.t<self.last_accepted-1e-9:self.count['accepted_oosm_vs_latest_measurement']+=1
                if old_t is not None and s.t<old_t-1e-9:self.count['accepted_before_previous_tick']+=1
        if accepted:self.last_accepted=max(self.last_accepted,max(s.t for s in accepted))
        if len(accepted)==2 and abs(accepted[0].t-accepted[1].t)<=1e-9:
            self.count['accepted_same_stamp_pair']+=1
            age=t-accepted[0].t
            if 1e-6<age<=self.c.max_age_s:
                self.count['native_pair_opportunity']+=1
                if old_t is not None and accepted[0].t<old_t-1e-9:
                    self.count['native_pair_prior_tick_opportunity']+=1
        return e

def describe(values):
    a=np.asarray(values,float)
    if not len(a):return {'n':0}
    return dict(n=len(a),min=float(a.min()),mean=float(a.mean()),p50=float(np.quantile(a,.5)),
      p95=float(np.quantile(a,.95)),p99=float(np.quantile(a,.99)),max=float(a.max()),
      age_gt_50ms=int(np.sum(a>.050000001)),age_gt_100ms=int(np.sum(a>.100000001)),
      age_gt_250ms=int(np.sum(a>.250000001)))

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    pin=cm.verify();store=cm.ev.ex.Store();rows=[];all_age=[];all_acc=[]
    for bag in store.plan['splits']['development']:
        events,_,group=cm.load(bag,a.output/'access'/(bag+'.json'),reference=False)
        probe=Probe();output,info=cm.predict(events,probe)
        untouched,base_info=cm.predict(events,cm.baseline())
        assert np.array_equal(output,untouched,equal_nan=True) and info==base_info
        unique=[set(events[events[:,1]==ch,0].tolist()) for ch in range(3)]
        missing=[sorted(unique[ch]-probe.seen[ch]) for ch in range(3)]
        last_output=probe.t
        lost_before=[sum(t<=last_output+1e-9 for t in m) for m in missing]
        inversions=[int(np.sum(np.diff(events[events[:,1]==ch,0])< -1e-9)) for ch in range(3)]
        row=dict(bag=bag,group=group,input_events=len(events),channel_source_inversions=inversions,
          global_source_inversions=int(np.sum(np.diff(events[:,0]) < -1e-9)),
          never_visible_at_observer_before_last_output=lost_before,
          not_yet_visible_tail=[len(m)-lost_before[ch] for ch,m in enumerate(missing)],
          counts=dict(probe.count),first_seen_age_s=describe(probe.ages),
          accepted_age_s=describe(probe.accepted_ages),runtime=info,
          schedule_sha256=hashlib.sha256(output[:,0].tobytes()).hexdigest(),
          outputs_sha256=hashlib.sha256(output.tobytes()).hexdigest(),
          instrumented_baseline_exact=True)
        cm.save(a.output/'bags'/(bag+'.json'),row);rows.append(row)
        all_age+=probe.ages;all_acc+=probe.accepted_ages
        print(bag,row['counts'].get('native_pair_opportunity',0),flush=True)
    total=collections.Counter()
    for r in rows:total.update(r['counts'])
    cm.save(a.output/'SUMMARY.json',dict(baseline=cm.BASELINE,source=os.getenv('GITHUB_SHA'),
      purpose='vehicle-only diagnosis; no candidate accuracy',bags=len(rows),groups=len(set(r['group'] for r in rows)),
      input_events=sum(r['input_events'] for r in rows),counts=dict(total),
      accepted_age_s=describe(all_acc),first_seen_age_s=describe(all_age),
      opportunity_groups=len(set(r['group'] for r in rows if r['counts'].get('native_pair_opportunity',0)>0)),
      original_baseline_exact=True,reference_loaded=False,validation_opened=False,
      pinned_source=pin,per_bag=rows))
if __name__=='__main__':main()
