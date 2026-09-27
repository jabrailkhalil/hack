"""Explicit construction of the frozen v8 residual-cap research candidate."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import candidates as c


def make_observer(*, enabled=True):
    """No filenames, bag identifiers or GNSS; false is the exact canonical v8."""
    name='disturbance_070' if enabled else 'main'
    config,readout=c.configuration(name)
    if enabled:
        document=json.loads((HERE/'selected.json').read_text())
        if document['config']!=asdict(config) or document['readout']!=asdict(readout):
            raise ValueError('Frozen selected configuration changed')
    return c.GuardedReadoutObserver(config,readout=readout)


def verify():
    for file,expected in json.loads((HERE/'BASELINE_PINS.json').read_text()).items():
        if hashlib.sha256((c.ROOT/file).read_bytes()).hexdigest()!=expected:
            raise ValueError('Baseline pin changed: '+file)
    observer=make_observer()
    return dict(status='DEVELOPMENT_PASS_VALIDATION_PENDING',config=asdict(observer.c),
                readout=asdict(observer.readout),default_changed=False)


if __name__=='__main__':print(json.dumps(verify(),indent=2))
