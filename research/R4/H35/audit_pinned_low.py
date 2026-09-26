"""Post-rejection coverage correction, not tuning or replacement of original results.

The first preregistered H35 low suite used an incomplete predicate/durations.
This reproduces the existing PR13 / R3-H24 low-speed suite on the SAME candidates.
No original benchmark is rerun, no algorithm/configuration/threshold is changed.
"""
import argparse,datetime,json,os
from pathlib import Path
from common import *
from run import paired,safety_reasons,exceeds
from factory import enabled_identity

# Verbatim function from R3-H24 source 6b3a11a68b83ee7b680b3b283f4800726c7b84cd,
# tools/research_R3_H24/develop.py, blob 2141a444fd72a71277b8e8223c3ec235f6b999e9.
def low_speed_windows(events):
    grid=ev.ex.grid_channels(events)
    if grid is None:return
    t,u,f,r,valid=grid
    # Exact anchor predicate from PR13 low_speed.py (blob7705f88), identical windows.
    idx=np.flatnonzero(valid & (abs(f-r)<.15) & ((f+r)/2>1) & ((f+r)/2<2) & (u>=0) & (t>max(25,.1*t[-1])) & (t<t[-1]-25))
    if len(idx):
        anchor=float(t[idx[0]])
        for duration in (3.,5.):
            window=events[(events[:,0]>=anchor-20)&(events[:,0]<=anchor+duration+10.1)]
            yield dict(kind='lock',start=anchor,end=anchor+duration),window

def run(out):
 out.mkdir(parents=True,exist_ok=False);store=Store();verify_sources();rows=[]
 save(out/'started.json',dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),audit_source_sha=os.environ.get('H35_AUDIT_SHA'),algorithm_source_sha='c75384cda3fb77de508c2d4128f38c17ed24613b',audit_sha256=sha(__file__),identity=enabled_identity(),purpose='Exact existing low suite, supplemental post-rejection; no tuning',validation_opened=False,test_opened=False))
 for bag in store.plan['splits']['development']:
  events,refs=store.load(bag,'development')
  for f,w in low_speed_windows(events):
   rows.append(dict(bag=bag,group=store.records[bag]['group'],suite='pinned_low_speed',fault=f,**paired(w,refs,f)))
  save(out/'access.json',store.access)
 summary={n:dict(event_rmse=legacy.macro(rows,n,'event_rmse'),false_stops=legacy.total(rows,n,'false_stop_samples'),unrecovered=legacy.unrecovered(rows,n)) for n in ('v8','off','H35_R050','H35_R200')}
 assert abs(summary['v8']['event_rmse']-.368545673)<1e-9,'pinned suite fingerprint differs'
 gates={}
 for n in ('H35_R050','H35_R200'):
  reasons=safety_reasons(rows,n)
  if exceeds(summary[n]['event_rmse'],summary['v8']['event_rmse'],.005):reasons.append('pinned_low_speed_regression')
  gates[n]=dict(passed=not reasons,reasons=reasons,relative_rmse_change=summary[n]['event_rmse']/summary['v8']['event_rmse']-1)
 result=dict(summary=summary,gates=gates,scenarios=len(rows),reference_comparisons=sum(s['v8']['event_rmse'] is not None for r in rows for s in r['receivers'].values()),rows=rows,validation_opened=False,test_opened=False)
 save(out/'results.json',result);print(json.dumps({k:v for k,v in result.items() if k!='rows'},indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);run(p.parse_args().output)
