# Original measured local script. Paths identify the actual exported-data run.
# This evidence file is not a portable runtime entry point.
import sys, time, json, resource, platform, statistics
from pathlib import Path
import numpy as np
sys.path.insert(0,'/mnt/data/hack-h09/tools/research_h09')
import compare as h
models,hashes=h.source_state(Path('/mnt/data/h09-baseline'))
with np.load('/mnt/data/h09-inputs/development/30618_0652866c.npz') as z:events=z['events']
window=events[events[:,0]<=180.]
for c in models.values():h.ev.replay(window,c,h.OPS)
rows=[]
for repeat in range(6):
 order=list(models) if repeat%2==0 else list(reversed(models))
 for name in order:
  begin=time.perf_counter();a,info=h.ev.replay(window,models[name],h.OPS);elapsed=time.perf_counter()-begin
  with np.load('/mnt/data/h09-development-run1/traces/30618_0652866c.npz') as z:
   full=z[name]; prefix=full[:len(a)]
   assert np.array_equal(a,prefix,equal_nan=True),name
  rows.append(dict(repeat=repeat,model=name,seconds=elapsed,outputs=len(a),us_per_output=elapsed/len(a)*1e6,causal_errors=info['causal_errors'],prefix_exact=True))
result=dict(bag='30618_0652866c',input_cutoff_s=180.,scope='Accelerated offline core+Timeline replay; NOT ROS transport latency or hardware real-time certification',python=platform.python_version(),numpy=np.__version__,hashes=hashes,measurements=rows,
 median_us_per_output={k:statistics.median(r['us_per_output'] for r in rows if r['model']==k) for k in models},process_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024)
Path('/mnt/data/h09-work/offline_benchmark.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result['median_us_per_output'],indent=2), result['process_peak_rss_bytes'])
