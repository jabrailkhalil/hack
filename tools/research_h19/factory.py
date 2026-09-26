"""Isolated R2-v7-fixed algorithm factory; never edits active sources or evaluator."""
from dataclasses import asdict, is_dataclass
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types

ROOT = Path(__file__).resolve().parents[2]
BASE = '65bba39ed05c781f3f69a65c02f69931152cbfd9'
PLAN_COMMIT = 'a6549707c07375ad5fd7f955c12e6d1a76c797db'
NOTE_COMMIT = '6c05cc423b5d5469fe86ce9454de297f6f114365'
RUNTIME = 'src/reserve_odometry/reserve_odometry/'
PROFILE = 'src/reserve_odometry/config/guarded_readout_v7.json'
sys.path[:0] = [str(ROOT/'src/reserve_odometry'), str(ROOT/'tools/finalization')]
import evaluate as ev
from reserve_odometry.guarded_readout import GuardedReadoutObserver, ReadoutConfig
from reserve_odometry.core import Config

PROTECTED = [RUNTIME+p for p in ['core.py','guarded_readout.py','timeline.py','node.py','guarded_node.py'] if (ROOT/(RUNTIME+p)).exists()] + [PROFILE,
 'src/reserve_odometry/config/guarded_readout_v7.yaml',
 'src/reserve_odometry/launch/odometry.launch.py',
 'tools/finalization/evaluate.py','tools/research_v3/experiment.py',
 'tools/research_v6/compare.py','tools/export_bags.py','research/plan_v3.json',
 'research/split_v3.json','requirements-research.txt']

def digest(data):
    return hashlib.sha256(data).hexdigest()

def git_bytes(path):
    return subprocess.check_output(['git','show',BASE+':'+path], cwd=ROOT)

def verify_sources():
    hashes = {}
    for p in PROTECTED:
        actual = (ROOT/p).read_bytes()
        if actual != git_bytes(p):
            raise ValueError('Fixed R2 source changed: '+p)
        hashes[p] = digest(actual)
    for d in [ROOT/'tools/research_h19',ROOT/'research/R2/H19']:
        for p in sorted(d.rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts:
                hashes[str(p.relative_to(ROOT))] = digest(p.read_bytes())
    p = ROOT/RUNTIME/'sequential_faults.py'
    hashes[str(p.relative_to(ROOT))] = digest(p.read_bytes())
    return hashes

def profile():
    data = json.loads((ROOT/PROFILE).read_text())
    yaml = {}
    for line in (ROOT/'src/reserve_odometry/config/guarded_readout_v7.yaml').read_text().splitlines():
        key, sep, value = line.strip().partition(':')
        if sep and (key.startswith('model.') or key.startswith('readout.') or key in ('rate_hz','alignment_delay_s')):
            yaml[key] = float(value)
    for k,v in data['config'].items():
        assert yaml['model.'+k] == v, k
    assert data['readout'] == {'gain':1.0,'holdoff_s':.5}
    assert all(yaml['readout.'+k] == v for k,v in data['readout'].items())
    assert yaml['rate_hz'] == 20 and yaml['alignment_delay_s'] == 0
    assert data['config']['adaptation_tau_s'] == .5
    assert data['config']['wheel_time_compensation'] == 0
    return data

def package(name, files):
    pkg = types.ModuleType(name); pkg.__path__ = []
    sys.modules[name] = pkg
    mods = {}
    for module, source in files:
        fullname = name+'.'+module
        obj = types.ModuleType(fullname); obj.__package__ = name
        obj.__file__ = '<isolated-'+fullname+'>'
        sys.modules[fullname] = obj
        exec(compile(source,obj.__file__,'exec'),obj.__dict__)
        mods[module] = obj
    return mods

class Factory:
    def __init__(self):
        self.hashes = verify_sources()
        self.params = profile()
        core = git_bytes(RUNTIME+'core.py')
        guarded = git_bytes(RUNTIME+'guarded_readout.py')
        self.pristine = package('_h19_pristine', [('core',core),('guarded_readout',guarded)])
        with tempfile.TemporaryDirectory(prefix='H19-core-') as tmp:
            p = Path(tmp)/RUNTIME/'core.py'; p.parent.mkdir(parents=True); p.write_bytes(core)
            subprocess.run(['git','apply','--check',str(ROOT/'research/R2/H19/core.patch')],cwd=tmp,check=True)
            subprocess.run(['git','apply',str(ROOT/'research/R2/H19/core.patch')],cwd=tmp,check=True)
            patched = p.read_bytes()
        self.patched_core = patched
        self.candidate = package('_h19_candidate',[('core',patched),('guarded_readout',guarded),
                             ('sequential_faults',(ROOT/RUNTIME/'sequential_faults.py').read_bytes())])

    def make(self, name='baseline', config=None):
        config = config or Config(**self.params['config'])
        if name == 'baseline':
            return GuardedReadoutObserver(config,readout=ReadoutConfig(**self.params['readout']))
        if name == 'pristine':
            mod = self.pristine['guarded_readout']
            return mod.GuardedReadoutObserver(config,readout=mod.ReadoutConfig(**self.params['readout']))
        mod = self.candidate['sequential_faults']
        options = mod.SequentialConfig(enabled=name!='off', monitor_only=name=='monitor',
                                       threshold_s=.6 if name=='h06' else .3)
        return mod.SequentialFaultObserver(config,readout=ReadoutConfig(**self.params['readout']),sequential=options)

# Comparable across independently loaded dataclass definitions.
def plain(x):
    if is_dataclass(x): return asdict(x)
    if isinstance(x,list): return [plain(v) for v in x]
    if isinstance(x,tuple): return tuple(plain(v) for v in x)
    if isinstance(x,dict): return {k:plain(v) for k,v in x.items()}
    return x

def equal_baseline(reference, other):
    for key,value in vars(reference).items():
        if plain(value) != plain(getattr(other,key)):
            raise AssertionError('R2 baseline/off state differs: '+key)

MODES = ['WAITING_FOR_INITIALIZATION','INITIALIZED','MODEL_ONLY','FUSED','SINGLE_WHEEL','REACQUIRING','STOPPED']
STATUSES = ['MISSING_OR_STALE','RANGE','DUPLICATE_OR_OLD','RATE_ANOMALY','CANDIDATE','MODEL_DISAGREEMENT',
            'ZERO_LOCK_SUSPECT','AMBIGUOUS_PAIR','ACCEPTED','REACQUIRE_ACCEPTED','SEQUENTIAL_DOWNWEIGHTED']
COLUMNS = ['t','v','s','disturbance','drive_a','variance_v','mode','front_status','rear_status',
 'front_positive','front_negative','rear_positive','rear_negative','front_suspect','rear_suspect',
 'front_weight','rear_weight','front_attribution','rear_attribution','front_new','rear_new',
 'front_evidence','rear_evidence','inner_v','inner_s']

class Recorded:
    def __init__(self, observer, factory=None, check=False, record=True):
        self.inner = observer; self.record = record
        self.references = [factory.make(n) for n in ('pristine','off')] if check else []
        self.rows = []; self.checked_ticks = 0
    def __getattr__(self,name): return getattr(self.inner,name)
    def reset(self,**kwargs):
        self.inner.reset(**kwargs)
        for obs in self.references: obs.reset(**kwargs)
    def step(self,*args,**kwargs):
        e = self.inner.step(*args,**kwargs)
        for obs in self.references:
            z = obs.step(*args,**kwargs)
            if plain(e) != plain(z): raise AssertionError('Published baseline/off Estimate differs')
            equal_baseline(self.inner,obs)
        if self.references: self.checked_ticks += 1
        if self.record and e.mode != 'WAITING_FOR_INITIALIZATION':
            d = getattr(self.inner,'_h19_detector',None)
            extras = ([d.positive[0],d.negative[0],d.positive[1],d.negative[1],*d.suspect,*d.weights,
                       *d.attribution,*d.new_sample,*d.evidence] if d else [0.]*6+[1.,1.]+[0.]*6)
            self.rows.append([e.t,e.v,e.s,e.disturbance,self.inner.drive_a,e.variance_v,
                              MODES.index(e.mode),STATUSES.index(e.front_status),STATUSES.index(e.rear_status),
                              *extras,self.inner.v,self.inner.s])
        return e
