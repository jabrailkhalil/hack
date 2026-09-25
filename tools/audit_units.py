#!/usr/bin/env python3
from pathlib import Path
import pandas as pd,numpy as np,json
import argparse
parser=argparse.ArgumentParser(description='Offline source-units audit, not runtime GNSS fitting')
parser.add_argument('exports',type=Path)
parser.add_argument('--output',type=Path,default=Path('reports/smoke_data_audit.json'))
args=parser.parse_args()
out=[]
for path in sorted(args.exports.glob('*.csv.gz')):
 d=pd.read_csv(path); groups={k:g.sort_values('stamp_ns').drop_duplicates('stamp_ns') for k,g in d.groupby('topic')}
 row={'bag':path.name.removesuffix('.csv.gz'),'topics':list(groups),'record_duration_s':(int(d.record_ns.max())-int(d.record_ns.min()))/1e9,'samples':len(d),'unit_ratios':{}}
 for gpsname in ['/sensing/gnss/master/vel','/sensing/gnss/rover/vel']:
  if gpsname not in groups:continue
  g=groups[gpsname]; gs=np.hypot(g.v0.values,g.v1.values); gt=g.stamp_ns.values
  for wheelname in ['/vehicle/front_bogie_velocity','/vehicle/rear_bogie_velocity']:
   w=groups[wheelname]; wt=w.stamp_ns.values; wv=w.v0.values
   j=np.searchsorted(gt,wt);j=np.clip(j,0,len(gt)-1);k=np.maximum(0,j-1);j=np.where(np.abs(gt[k]-wt)<np.abs(gt[j]-wt),k,j)
   match=(np.abs(gt[j]-wt)<=50_000_000)&(gs[j]>2)&np.isfinite(gs[j])&(wv>2)
   ratios=wv[match]/gs[j][match]
   if len(ratios):
    row['unit_ratios'][gpsname.split('/')[-2]+'_'+wheelname.split('/')[-1]]={'n':int(len(ratios)),'median':float(np.median(ratios)),'p10':float(np.quantile(ratios,.1)),'p90':float(np.quantile(ratios,.9)),'mae_raw':float(np.mean(np.abs(wv[match]-gs[j][match]))),'mae_div3_6':float(np.mean(np.abs(wv[match]/3.6-gs[j][match])))}
 print(json.dumps(row,ensure_ascii=False))
 out.append(row)
args.output.write_text(json.dumps(out,ensure_ascii=False,indent=2))
