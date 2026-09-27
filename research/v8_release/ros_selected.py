"""Explicit installed-profile smoke checks; execute inside the supplied ROS image.

Does not edit canonical YAML, test files or default launch. A source-checked copy
of the current fault probe is executed with only its parameter-file expression
replaced. Success is an integration smoke result, not a real-time guarantee.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
PARAM_EXPR="str(Path(subprocess.check_output(['ros2','pkg','prefix','reserve_odometry'],text=True).strip())/'share/reserve_odometry/config/champion_v8.yaml')"


def fault_probe_source(source, yaml_path):
    if source.count(PARAM_EXPR)!=1 or "'guarded_odometry_node'" not in source:
        raise ValueError('Unexpected installed fault probe; inspect instead of running the wrong profile')
    return source.replace(PARAM_EXPR,repr(str(Path(yaml_path).resolve())))


def clock_yaml(text):
    token='    clock_mode: input_stamp'
    if text.count(token)!=1:raise ValueError('Unexpected input_stamp YAML')
    return text.replace(token,'    clock_mode: ros_clock')


def run(output):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    yaml_path=ROOT/'research/v8_targeted/v8_residual070.yaml'
    expected=ROOT/'research/v8_targeted/selected.json'
    pins=json.loads((ROOT/'research/v8_targeted/BASELINE_PINS.json').read_text())
    from reserve_odometry import core, guarded_readout, timeline
    modules={m.__name__:Path(m.__file__).resolve() for m in (core,guarded_readout,timeline)}
    prefix=Path(subprocess.check_output(['ros2','pkg','prefix','reserve_odometry'],text=True).strip()).resolve()
    checked={}
    for name,path in modules.items():
        if prefix not in path.parents:raise ValueError('Module is not loaded from installed prefix: '+str(path))
        key='src/reserve_odometry/reserve_odometry/'+path.name
        actual=hashlib.sha256(path.read_bytes()).hexdigest()
        if actual!=pins[key]:raise ValueError('Installed numerical source mismatch: '+name)
        checked[name]={'path':str(path),'sha256':actual}
    runner=ROOT/'tests/ros_calibrated_smoke.py'
    for mode in ('input_stamp','ros_clock'):
        path=yaml_path
        if mode=='ros_clock':
            path=output/'ros_clock.yaml';path.write_text(clock_yaml(yaml_path.read_text()))
        subprocess.run([sys.executable,str(runner),'--params-file',str(path),'--expected-json',str(expected)],check=True)
    source=ROOT/'tests/ros_fault_smoke.py'
    ns={'__name__':'release_selected_fault_probe','__file__':str(source)}
    exec(compile(fault_probe_source(source.read_text(),yaml_path),str(source),'exec'),ns)
    ns['main']()
    subprocess.run([sys.executable,str(ROOT/'tests/cdr_roundtrip.py')],check=True)
    record={'status':'INSTALLED_SELECTED_SMOKE_PASS','modules':checked,
            'yaml_sha256':hashlib.sha256(yaml_path.read_bytes()).hexdigest(),
            'json_sha256':hashlib.sha256(expected.read_bytes()).hexdigest(),
            'clock_modes':['input_stamp','ros_clock'],'fault_pause_seek':True,
            'canonical_default_changed':False,'latency_benchmark':False}
    (output/'RESULT.json').write_text(json.dumps(record,indent=2)+'\n')
    return record


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    print(json.dumps(run(a.output),indent=2))
