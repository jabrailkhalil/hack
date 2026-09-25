#!/usr/bin/env python3
"""Causal core smoke replay; GNSS is collected separately and used AFTER inference.

Input is the audit/export_bags.py CSV. This is NOT a ROS end-to-end latency test
or a substitute for held-out evaluation. Only three vehicle topics drive state/time.
"""
import argparse
import csv
import gzip
import json
import math
import sys
import time
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/reserve_odometry'))
from reserve_odometry.core import Config, Observer, Sample
from reserve_odometry.timeline import Timeline

CHANNELS = {'/vehicle/driver_position_cmd': 0, '/vehicle/front_bogie_velocity': 1,
            '/vehicle/rear_bogie_velocity': 2}


def infer(rows, config=None, wheel_scale=1/3.6):
    timeline = Timeline(Observer(config), rate_hz=20, delay_s=.06)
    predictions, reference = [], {'master': [], 'rover': []}
    timings = []
    for row in rows:
        topic = row['topic']
        stamp = int(row['stamp_ns']) / 1e9
        if topic in CHANNELS:
            channel = CHANNELS[topic]
            value = float(row['v0']) * (1/15 if channel == 0 else wheel_scale)
            start = time.perf_counter_ns()
            timeline.ingest(channel, Sample(stamp, value))
            for e, held in timeline.advance():
                if e.mode == 'WAITING_FOR_INITIALIZATION':
                    continue
                f = held[1].value if held[1] and 0 <= e.t-held[1].t <= .25 else None
                r = held[2].value if held[2] and 0 <= e.t-held[2].t <= .25 else None
                avg = (f+r)/2 if f is not None and r is not None else None
                predictions.append((e.t,e.v,e.s,f,avg,e.mode,e.variance_v))
            timings.append((time.perf_counter_ns()-start)/1000)
        else:
            for receiver in reference:
                if topic == f'/sensing/gnss/{receiver}/vel':
                    v = math.hypot(float(row['v0']), float(row['v1']))
                    if math.isfinite(v):
                        reference[receiver].append((stamp,v))
    return predictions, reference, timings, timeline


def evaluate(path, config=None, wheel_scale=1/3.6):
    import numpy as np  # offline-only dependency
    opener = gzip.open if str(path).endswith('.gz') else open
    with opener(path, 'rt', newline='') as source:
        predictions, reference, timings, timeline = infer(csv.DictReader(source), config, wheel_scale)
    report = {'bag':Path(path).name.removesuffix('.csv.gz'), 'predictions':len(predictions),
              'clock_resets':timeline.resets, 'dropped_inputs':timeline.dropped,
              'mode_counts':dict(Counter(p[5] for p in predictions)),
              'inference_input_callback_us':{str(p):float(np.percentile(timings,p)) for p in (50,95,99)},
              'receiver_metrics':{}}
    if not predictions:
        return report
    pt=np.array([p[0] for p in predictions]); estimates=np.array([p[1] for p in predictions])
    for receiver, refs in reference.items():
        if not refs:
            continue
        refs=sorted(dict(refs).items()); rt=np.array([r[0] for r in refs]); rv=np.array([r[1] for r in refs])
        j=np.clip(np.searchsorted(rt,pt),0,len(rt)-1); prev=np.maximum(0,j-1)
        j=np.where(np.abs(rt[prev]-pt)<np.abs(rt[j]-pt),prev,j)
        mask=np.abs(rt[j]-pt)<=.05
        baseline_f=np.array([p[3] if p[3] is not None else np.nan for p in predictions])
        baseline_avg=np.array([p[4] if p[4] is not None else np.nan for p in predictions])
        mask &= np.isfinite(baseline_f)&np.isfinite(baseline_avg)
        metrics={'matched_common_samples':int(mask.sum()),'prediction_coverage':float(mask.mean()),
                 'nearest_tolerance_s':.05,'speed_reference':'hypot(linear.x, linear.y)',
                 'comparison_mask':'same matched timestamps for all three estimators'}
        for name, values in (('front_scaled',baseline_f),('mean_scaled',baseline_avg),('observer',estimates)):
            errors=values[mask]-rv[j][mask]
            if len(errors):
                metrics[name]={'rmse_mps':float(np.sqrt(np.mean(errors**2))),
                               'mae_mps':float(np.mean(abs(errors))),
                               'bias_mps':float(np.mean(errors)),
                               'p95_abs_mps':float(np.quantile(abs(errors),.95))}
        # Integrate only contiguous matched spans. NOT a 3D terminal position error.
        valid_edges=mask[1:]&mask[:-1]&((pt[1:]-pt[:-1])<=.10)
        dt=(pt[1:]-pt[:-1])[valid_edges]
        ev=estimates-rv[j]
        distance=float(np.sum(.5*(rv[j][1:]+rv[j][:-1])[valid_edges]*dt))
        delta=float(np.sum(.5*(ev[1:]+ev[:-1])[valid_edges]*dt))
        metrics['covered_reference_distance_m']=distance
        metrics['integrated_speed_error_m_NOT_3D_POSITION']=delta
        report['receiver_metrics'][receiver]=metrics
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv',nargs='+',type=Path)
    parser.add_argument('--output',type=Path,default=Path('reports/real_smoke.json'))
    parser.add_argument('--wheel-scale',type=float,default=1/3.6)
    args=parser.parse_args()
    results=[evaluate(path,wheel_scale=args.wheel_scale) for path in args.csv]
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps({'status':'development smoke, NOT held-out',
          'wheel_scale':args.wheel_scale,'physical_parameters':'illustrative, not identified',
          'results':results},ensure_ascii=False,indent=2))
    print(args.output)
    for row in results:
        print(row['bag'], 'outputs',row['predictions'],'resets',row['clock_resets'],
              {k:v.get('observer') for k,v in row['receiver_metrics'].items()})


if __name__=='__main__':
    main()
