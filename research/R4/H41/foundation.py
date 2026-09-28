"""R4-H41 passive premise check. Never changes the canonical observer.

No candidate fitting or validation. Train wheels are pseudo-observations, not
independent truth; +/- initial-A shadows test sensitivity, not true A error.
"""
from __future__ import annotations
import argparse
import csv
import datetime
import gzip
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT/'tools/finalization'), str(ROOT/'src/reserve_odometry')]
import evaluate as ev
from reserve_odometry.core import Config, Sample, clip
from reserve_odometry.guarded_readout import GuardedReadoutObserver, ReadoutConfig
from reserve_odometry.timeline import Timeline

BASELINE = 'e3b0c9c039d2953fbfcda51231263d38ef9f1024'
TREE = 'eae49a504bc59b5c9b408445150bef32e111956f'
ZIP_SHA = 'a8e0bfa033e0a02c460c30b02f34a5c64ece85b05003512941387d3cf1f319a2'
DATA_SHA = 'd0b2483e13990edb8219b0d7bbcafc7ed001cce549a4d3af467069b2472e7d52'
PROFILE_PATH = ROOT/'src/reserve_odometry/config/champion_v8.json'
OPS = {'rate_hz': 20., 'alignment_delay_s': 0.}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1024*1024), b''): h.update(b)
    return h.hexdigest()


def profile():
    p = json.loads(PROFILE_PATH.read_text())
    actual = {}
    for line in (ROOT/'src/reserve_odometry/config/champion_v8.yaml').read_text().splitlines():
        key, sep, value = line.strip().partition(':')
        if key.startswith('model.') and sep: actual[key[6:]] = float(value)
    if actual != p['config']: raise AssertionError('JSON/YAML effective model mismatch')
    c = Config(**actual)
    if c.common_mode_quarantine_s != 1.5 or c.wheel_time_compensation != 0:
        raise AssertionError('Not champion v8')
    return c, ReadoutConfig(**p['readout'])


def check_source(receipt=None):
    """Check every original path/byte/mode, not merely selected runtime files."""
    if receipt:
        r = json.loads(Path(receipt).read_text())
        if r['source_status'] != 'VERIFIED' or r['actual_git_tree'] != TREE:
            raise AssertionError('Unverified source receipt')
        expected = {x['path']: (x['mode'], x['git_blob']) for x in r['files']}
    else:
        tree = subprocess.check_output(['git', 'rev-parse', BASELINE+'^{tree}'], cwd=ROOT, text=True).strip()
        if tree != TREE: raise AssertionError('Baseline tree mismatch')
        listing = subprocess.check_output(['git', 'ls-tree', '-rz', BASELINE], cwd=ROOT)
        expected = {}
        for item in listing.split(b'\0'):
            if not item: continue
            info, path = item.split(b'\t', 1)
            mode, kind, blob = info.decode().split()
            if kind != 'blob': raise AssertionError('Unexpected baseline object')
            expected[path.decode()] = (mode, blob)
    if len(expected) != 301: raise AssertionError('Incomplete source')
    hashes = {}
    for relative, (mode, blob) in expected.items():
        path = ROOT/relative
        data = path.read_bytes()
        actual = hashlib.sha1(f'blob {len(data)}\0'.encode()+data).hexdigest()
        actual_mode = '100755' if path.stat().st_mode & 0o111 else '100644'
        if (actual_mode, actual) != (mode, blob): raise AssertionError('Source mismatch: '+relative)
        hashes[relative] = hashlib.sha256(data).hexdigest()
    return {'source_status':'VERIFIED', 'baseline_sha':BASELINE, 'baseline_tree':TREE,
            'zip_sha256':ZIP_SHA, 'original_files_verified':len(hashes), 'source_sha256':hashes}


class Store(ev.ex.Store):
    """The same decoder/order/units, with explicit development role support."""
    def __init__(self, root, journal=None):
        super().__init__(root)
        self.journal = journal

    def load(self, bag, purpose):
        if purpose not in ('train', 'development'):
            raise PermissionError('H41 train/development only; validation/test closed')
        row = self.records[bag]
        if row['split'] != purpose or bag not in self.plan['splits'][purpose]:
            raise PermissionError('Role mismatch before measurement IO')
        path = self.root/bag/(bag+'_0.db3')
        if sha(path) != row['sha256']: raise ValueError('Bag checksum: '+bag)
        allowed = list(ev.ex.CHANNELS)+(list(ev.ex.REFS) if purpose == 'development' else [])
        self.access.append(dict(bag=bag, purpose=purpose, topics=allowed, sha256=row['sha256']))
        if self.journal: ev.save(self.journal, {'test_opened':False, 'validation_opened':False, 'access':self.access})
        events, refs = [], {'master':[], 'rover':[]}
        with sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True) as con:
            query = ('SELECT t.name,t.type,m.data FROM messages m JOIN topics t ON t.id=m.topic_id '
                     'WHERE t.name IN ('+','.join('?' for _ in allowed)+') ORDER BY m.timestamp,m.id')
            for topic, typ, raw in con.execute(query, allowed):
                stamp, values = ev.decode(raw, typ)
                t = (stamp-row['sensor_start_ns'])/1e9
                if topic in ev.ex.CHANNELS:
                    ch = ev.ex.CHANNELS[topic]
                    events.append((t, ch, float(values[0])/(15 if ch == 0 else 3.6)))
                else:
                    speed = math.hypot(float(values[0]), float(values[1]))
                    if math.isfinite(speed): refs[ev.ex.REFS[topic]].append((t,speed))
        return ev.np.asarray(events, float), refs


def obtain_data(directory, roles=('train','development')):
    """Same pinned download as get_dataset.py; extract ONLY authorized roles."""
    if not roles or any(r not in ('train','development') for r in roles):
        raise PermissionError('No validation/test extraction')
    directory.mkdir(parents=True, exist_ok=True)
    (directory/'COLCON_IGNORE').touch()
    archive = directory/'dataset.zip'
    if not archive.exists():
        spec = importlib.util.spec_from_file_location('h41_dataset', ROOT/'tools/get_dataset.py')
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        query = urllib.parse.urlencode(dict(public_key=mod.KEY, path='/dataset.zip'))
        with urllib.request.urlopen(mod.API+'?'+query, timeout=30) as response:
            url = json.load(response)['href']
        partial = archive.with_suffix('.part')
        try:
            with urllib.request.urlopen(url, timeout=60) as inp, partial.open('wb') as out:
                total = 0
                while block := inp.read(1024*1024):
                    total += len(block)
                    if total > 300*1024*1024: raise ValueError('Archive size')
                    out.write(block)
            partial.replace(archive)
        except Exception:
            partial.unlink(missing_ok=True); raise
    if sha(archive) != DATA_SHA: raise ValueError('Dataset archive checksum mismatch')
    nested = directory/'data-role-source.zip'
    with zipfile.ZipFile(archive) as z, z.open('data.zip') as inp, nested.open('wb') as out:
        shutil.copyfileobj(inp, out, 1024*1024)
    store = Store(directory/'data')
    selected = [x for x in store.records.values() if x['split'] in roles]
    extracted = []
    with zipfile.ZipFile(nested) as z:
        for row in selected:
            relative = row['bag']+'/'+row['bag']+'_0.db3'
            choices = [n for n in z.namelist() if n == relative or n.endswith('/'+relative)]
            if len(choices) != 1: raise ValueError('Nonunique bag member: '+relative)
            target = directory/'data'/relative
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(choices[0]) as inp, target.open('xb') as out:
                    shutil.copyfileobj(inp, out, 1024*1024)
            if sha(target) != row['sha256']: raise ValueError('Extracted bag checksum')
            extracted.append(dict(bag=row['bag'], role=row['split'], sha256=row['sha256']))
    ev.save(directory/'extraction.json', dict(archive_sha256=DATA_SHA, extracted=extracted,
        test_extracted=False, validation_extracted=False, test_measurements_opened=False))
    nested.unlink()
    return directory/'data'


def effective_u(o, command, t):
    if not o._valid(command, t, o.c.command_timeout_s) or abs(command.value)>1.000001:
        return 0.
    return clip(command.value, -1., 1.)


def predict(o, v, drive, d, u, h):
    """Exactly legacy held-command drive-before-Euler mean; wheels never used."""
    drive += (1.-math.exp(-h/o.c.actuator_tau_s))*(o.drive_target(u,v)-drive)
    a = clip(drive-o.resistance(v)+d, -o.c.max_accel_mps2, o.c.max_accel_mps2)
    v_next = clip(v+h*a, -o.c.max_speed_mps, o.c.max_speed_mps)
    if u <= o.c.command_deadband and v*v_next < 0: v_next = 0.
    return v_next, drive, a


def moments(rows):
    if not rows: return dict(n=0, rms=None, mean=None, lag_correlation=None)
    a = ev.np.asarray(rows, float)
    corr = float(ev.np.corrcoef(a.T)[0,1]) if len(a)>2 and all(ev.np.std(a,axis=0)>1e-12) else None
    return dict(n=len(a), rms=float(ev.np.sqrt(ev.np.mean(a[:,0]**2))),
                mean=float(ev.np.mean(a[:,0])), lag_correlation=corr)


def probe(events):
    c, readout = profile(); o = GuardedReadoutObserver(c, readout=readout)
    timeline = Timeline(o, rate_hz=20., delay_s=0.)
    old = None; episode = None; last_anchor = -math.inf
    buckets = {'transient':[], 'steady':[]}; episodes = []; output_count=0; causal=0
    bound = max(c.efficiency*c.gear_ratio*c.total_motor_torque_nm/c.wheel_radius_m,
                c.max_brake_force_n)/c.mass_kg
    for t, ch, value in events:
        timeline.ingest(int(ch), Sample(float(t),float(value)))
        for e, held in timeline.advance():
            if e.mode != 'WAITING_FOR_INITIALIZATION': output_count += 1
            causal += sum(x is not None and x.t>e.t+1e-9 for x in held)
            current = (e.t, o.v, o.drive_a, o.disturbance)
            if old is None or e.mode in ('INITIALIZED','WAITING_FOR_INITIALIZATION'):
                episode=None; old=current; continue
            h=e.t-old[0]; u=effective_u(o,held[0],e.t)
            predicted, drive_prior, acceleration = predict(o,old[1],old[2],old[3],u,h)
            f,r = held[1:]
            trusted = (e.mode=='FUSED' and not e.command_stale
                and e.front_status==e.rear_status=='ACCEPTED'
                and f is not None and r is not None
                and abs(f.value-r.value)<=.15 and abs(f.t-r.t)<=.05
                and 0<=e.t-f.t<=.20 and 0<=e.t-r.t<=.20
                and abs((f.value+r.value)/2)>.5
                and abs((f.value+r.value)/2-predicted)<=.3)
            lag = o.drive_target(u,old[1])-drive_prior
            if trusted:
                buckets['transient' if abs(lag)>=.1 else 'steady'].append(((f.value+r.value)/2-predicted,lag))
            if episode is not None:
                episode['states'] = [predict(o,v,a,episode['d'],u,h)[:2] for v,a in episode['states']]
                if e.t-episode['t']>=1.-1e-9:
                    v0,vp,vm=[s[0] for s in episode['states']]
                    episodes.append(dict(anchor=episode['t'], end=e.t, u_anchor=episode['u'],
                        initial_drive=episode['a'], sensitivity_mps=max(abs(vp-v0),abs(vm-v0)),
                        nominal_endpoint_mps=v0, trusted_endpoint=bool(trusted),
                        endpoint_pseudo_residual_mps=(f.value+r.value)/2-v0 if trusted else None))
                    episode=None
            if episode is None and trusted and abs(lag)>=.1 and e.t>2 and e.t-last_anchor>=1.25:
                episode=dict(t=e.t,u=u,a=o.drive_a,d=o.disturbance,
                    states=[(o.v,clip(o.drive_a+delta,-bound,bound)) for delta in (0.,.1,-.1)])
                last_anchor=e.t
            old=current
    return dict(outputs=output_count, causal_errors=causal, resets=timeline.resets,
                episodes=episodes, buckets=buckets, dropped=timeline.dropped,
                catchups=timeline.catchup_events)


def run_foundation(data_root, output, receipt=None):
    output.mkdir(parents=True, exist_ok=False)
    manifest = check_source(receipt); c,r = profile()
    from dataclasses import asdict
    source_sha = os.environ.get('GITHUB_SHA', 'LOCAL_NO_REMOTE_CANDIDATE_COMMIT')
    ev.save(output/'started.json', dict(**manifest, diagnostic_source_sha=source_sha,
        candidate_implemented=False, observer=type(GuardedReadoutObserver(c)).__name__,
        module_file=sys.modules[GuardedReadoutObserver.__module__].__file__,
        config=asdict(c), readout=asdict(r), operational=OPS, python=platform.python_version(),
        numpy=ev.np.__version__, stage='foundation_train_only', test_opened=False))
    store=Store(data_root,output/'access.json'); groups={}; bags=[]; all_episodes=[]
    started=time.perf_counter()
    for bag in store.plan['splits']['train']:
        events,refs=store.load(bag,'train')
        if any(refs.values()): raise AssertionError('Train reference leak')
        result=probe(events); group=store.records[bag]['group']
        g=groups.setdefault(group,dict(transient=[],steady=[],episodes=[]))
        for key in ('transient','steady'): g[key].extend(result['buckets'][key])
        g['episodes'].extend(result['episodes'])
        for x in result['episodes']: all_episodes.append(dict(bag=bag,group=group,**x))
        compact=dict(bag=bag,group=group,**{k:v for k,v in result.items() if k not in ('buckets','episodes')},
            transient=moments(result['buckets']['transient']), steady=moments(result['buckets']['steady']),
            completed_episodes=len(result['episodes']))
        bags.append(compact); ev.save(output/'bags'/(bag+'.json'),compact)
        print('FOUNDATION',bag,compact['transient']['n'],compact['completed_episodes'],flush=True)
    rows=[]
    for key,g in groups.items():
        rows.append(dict(group=key,transient=moments(g['transient']),steady=moments(g['steady']),
                         episodes=len(g['episodes']),
                         material_episodes=sum(x['sensitivity_mps']>=.01 for x in g['episodes'])))
    n=sum(x['transient']['n'] for x in rows); ep=len(all_episodes)
    active_groups=sum(x['transient']['n']>0 for x in rows)
    ep_groups=sum(x['episodes']>0 for x in rows)
    residual_groups=sum(x['transient']['rms'] is not None and x['transient']['rms']>=.01 for x in rows)
    fraction=sum(x['sensitivity_mps']>=.01 for x in all_episodes)/ep if ep else None
    passed=n>=100 and active_groups>=5 and ep>=30 and ep_groups>=5 and residual_groups>=5 and fraction>=.5
    if any(x['causal_errors'] or x['resets'] for x in bags): raise AssertionError('Passive replay integrity')
    result=dict(stage='foundation', baseline_sha=BASELINE, diagnostic_source_sha=source_sha,
        candidate_implemented=False, status='FOUNDATION_PLAUSIBLE_NOT_IDENTIFIED' if passed else 'INCONCLUSIVE',
        candidate_authorized=passed, trusted_transient_pairs=n, transient_groups=active_groups,
        completed_episodes=ep, episode_groups=ep_groups, material_fraction=fraction,
        residual_groups=residual_groups, outputs=sum(x['outputs'] for x in bags),
        bags=bags, groups=rows, elapsed_wall_s=time.perf_counter()-started,
        test_opened=False, validation_opened=False,
        limitations=['Latent actuator error is NOT directly observed or identified',
                     'Wheel residuals are pseudolabels and contain d/timestamp/common-bias error',
                     'Perturbation sensitivity is a conditional model calculation on real commands'])
    ev.save(output/'results.json',result)
    if all_episodes:
        with gzip.open(output/'episodes.csv.gz','wt',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(all_episodes[0]));w.writeheader();w.writerows(all_episodes)
    print(json.dumps({k:v for k,v in result.items() if k not in ('bags','groups')},indent=2),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stage',choices=['data','foundation','source'],required=True)
    p.add_argument('--data-root',type=Path,default=ROOT/'dataset/data')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--source-receipt',type=Path)
    a=p.parse_args()
    if a.stage=='data': obtain_data(a.output)
    elif a.stage=='source': ev.save(a.output,check_source(a.source_receipt))
    else: run_foundation(a.data_root,a.output,a.source_receipt)

if __name__=='__main__': main()
