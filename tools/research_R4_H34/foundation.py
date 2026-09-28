"""H34 preregistered train-only foundation, no fitting/validation/database loader.

Input is the checksum-verified vehicle-only H24 window artifact, extracted from
all64 train bags. Metadata is checked against the unchanged split. No GNSS.
"""
import argparse
from collections import Counter
from dataclasses import asdict
import datetime
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from common import ROOT,D,BASE,np,make,Sample,profile,theta0,configuration,integrity,save,sha

EXPECTED={
 'train_windows.npz':'0f2303b11ebe327cbefe990e958b6d3d3e97db95684ca9d5cc7decd74bacaf37',
 'windows.json':'4a592f54b564873b08d1b374c62829f78a1b39545a48fa8da7209fb159944fc7',
 'coverage.json':'0efbb7e526c77c4271c17a4a03ba93be6886cab89a1b000ef60a6f333aeef6ac'}


def prepare(windows):
    return [[(float(row[0]),*(Sample(float(row[i]),float(row[i+1])) for i in (1,3,5)))
             for row in w] for w in windows]


def load_input(path):
    for p,h in EXPECTED.items():assert sha(path/p)==h,('input_hash',p)
    meta=json.loads((path/'windows.json').read_text())
    split=json.loads((ROOT/'research/split_v3.json').read_text());records={r['bag']:r for r in split['records']}
    plan=json.loads((ROOT/'research/plan_v3.json').read_text());train=set(plan['splits']['train'])
    assert len(train)==64
    access=json.loads((path/'access.json').read_text());assert len(access)==64
    allowed={'/vehicle/driver_position_cmd','/vehicle/front_bogie_velocity','/vehicle/rear_bogie_velocity'}
    assert {a['bag'] for a in access}==train
    for a in access:
        assert a['purpose']=='train' and set(a['topics'])==allowed
        assert a['sha256']==records[a['bag']]['sha256']
    groups=sorted({records[b]['group'] for b in train},key=lambda g:hashlib.sha256(('R3-H24-fit-check:'+g).encode()).hexdigest())
    partition={g:('check' if i%4==0 else 'fitting') for i,g in enumerate(groups)}
    for m in meta:
        assert m['bag'] in train and m['group']==records[m['bag']]['group']
        assert m['role']==partition[m['group']]
    w=np.load(path/'train_windows.npz',allow_pickle=False)['windows'];assert w.shape==(len(meta),141,7)
    assert np.all(np.isfinite(w));assert np.max(abs(np.diff(w[:,:,0],axis=1)-.05))<1e-8
    # Availability/source causality of all saved held inputs.
    for i in (1,3,5):assert np.all(w[:,:,i]<=w[:,:,0]+1e-9)
    targets=np.stack([.5*(w[:,110,4]+w[:,110,6]),.5*(w[:,140,4]+w[:,140,6])],axis=1)
    assert np.array_equal(targets,np.array([m['wheel_target'] for m in meta]))
    return meta,w,prepare(w),targets,dict(artifact_source='R3-H24-preflight-36220067112-1',
          upstream_train_bags=64,upstream_access_sha256=sha(path/'access.json'),input_hashes=EXPECTED,
          raw_database_reverified_here=False,upstream_database_hashes_match_split=True,
          train_gnss_opened=False,validation_opened=False,test_opened=False,
          interpretation='New H34 execution on verified cached train-only windows, not a fresh SQLite extraction.')


def scalar(prepared,scheme,theta=None):
    result=[];states=[]
    for w in prepared:
        o=make(scheme,theta)
        for row in w[:101]:o.step(*row)
        outputs=[]
        for row in w[101:]:
            e=o.step(row[0],row[1],None,None);outputs.append([e.v,e.s,o.drive_a])
        result.append(outputs)
    return np.asarray(result)


def vector(prepared,windows,scheme,theta=None):
    """Scalar actual warmup, independently vectorized across forecast windows."""
    initial=[]
    for w in prepared:
        o=make(scheme,theta)
        for row in w[:101]:e=o.step(*row)
        initial.append([o.v,o.drive_a,o.disturbance,e.s,o._velocity_correction])
    v,drive,d,s,cv=np.array(initial).T
    c=profile()[0] if theta is None else configuration(theta)
    out=[]
    def resistance(v):
        return (c.rolling_force_n*np.tanh(v/.2)+c.quadratic_drag_n_s2_m2*v*np.abs(v))/c.mass_kg
    def fraction(x):
        return np.where(x<1e-4,x*(.5+x*(-1/6+x*(1/24+x*(-1/120+x/720)))),1+np.expm1(-x)/x)
    for k in range(101,141):
        dt=windows[:,k,0]-windows[:,k-1,0]
        stamp=windows[:,k,1];u=windows[:,k,2]
        valid=(windows[:,k,0]-stamp>=-1e-9)&(windows[:,k,0]-stamp<=c.command_timeout_s)&(np.abs(u)<=1.000001)
        u=np.where(valid,np.clip(u,-1,1),0)
        q=np.clip((np.abs(u)-c.command_deadband)/(1-c.command_deadband),0,1)**c.command_exponent
        force=np.minimum(c.efficiency*c.gear_ratio*c.total_motor_torque_nm/c.wheel_radius_m,c.max_power_w/np.maximum(np.abs(v),1))
        target=np.where(u>=0,c.travel_direction*q*force/c.mass_kg,-np.tanh(v/.2)*q*c.max_brake_force_n/c.mass_kg)
        prev=v.copy();change=target-drive;x=dt/c.actuator_tau_s
        if scheme in ('A','baseline'):
            drive=drive+(1-np.exp(-x))*change
            a=np.clip(drive-resistance(v)+d,-c.max_accel_mps2,c.max_accel_mps2)
        else:
            mh=drive+change*fraction(.5*x)
            ah=np.clip(mh-resistance(v)+d,-c.max_accel_mps2,c.max_accel_mps2)
            mid=np.clip(v+.5*dt*ah,-c.max_speed_mps,c.max_speed_mps)
            a=np.clip(drive+change*fraction(x)-resistance(mid)+d,-c.max_accel_mps2,c.max_accel_mps2)
            drive=drive-np.expm1(-x)*change
        v=np.clip(v+dt*a,-c.max_speed_mps,c.max_speed_mps)
        v=np.where((u<=c.command_deadband)&(prev*v<0),0,v)
        s+=.5*dt*(prev+cv+v);cv=np.zeros_like(cv)
        out.append(np.stack([v,s,drive],axis=1))
    return np.stack(out,axis=1)


def group_summary(meta,values):
    # values: windows by horizons; group-balanced RMS, not macro of RMS.
    rows={g:np.mean(values[[i for i,m in enumerate(meta) if m['group']==g]]**2,axis=0)
          for g in sorted({m['group'] for m in meta})}
    return dict(group_balanced_rms=np.sqrt(np.mean(list(rows.values()),axis=0)).tolist(),
                per_group_rms={g:np.sqrt(a).tolist() for g,a in rows.items()})


def main():
    p=argparse.ArgumentParser();p.add_argument('--train',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    check=integrity();meta,w,prepared,target,receipt=load_input(args.train)
    save(args.output/'started.json',dict(baseline=BASE,plan_sha='b70706e20592dfe91450613dac3b4d82ee7d8509',
       source_ref=os.environ.get('GITHUB_SHA'),source_hashes={str(p.relative_to(ROOT)):sha(p) for p in sorted((ROOT/'tools/research_R4_H34').glob('*.py'))},
       runtime_module=str(sys.modules['reserve_odometry.integration_h34'].__file__),
       runtime_sha256=sha(ROOT/'src/reserve_odometry/reserve_odometry/integration_h34.py'),
       core_sha256=sha(ROOT/'src/reserve_odometry/reserve_odometry/core.py'),
       readout_sha256=sha(ROOT/'src/reserve_odometry/reserve_odometry/guarded_readout.py'),
       class_A='DiscretizationObserver(scheme=A)',class_B='DiscretizationObserver(scheme=B)',config=asdict(profile()[0]),
       readout=asdict(profile()[1]),theta0=theta0().tolist(),input=receipt,integrity=check,
       started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),diagnostic_only=True,
       fitting_started=False,validation_opened=False,test_opened=False))
    predictions={};parity={}
    for scheme in ('baseline','A','B'):
        a=scalar(prepared,scheme);predictions[scheme]=a
        if scheme!='baseline':
            b=vector(prepared,w,scheme)
            errors=np.max(abs(a-b),axis=(0,1));parity[scheme]=dict(v_max_abs_mps=float(errors[0]),s_max_abs_m=float(errors[1]),drive_max_abs_mps2=float(errors[2]))
            assert np.all(errors<=1e-9),(scheme,errors)
    assert np.array_equal(predictions['baseline'],predictions['A'])
    old=np.array([m['baseline_prediction'] for m in meta]);delta=float(np.max(abs(predictions['baseline'][:,[9,39],0]-old)))
    assert delta<=1e-10,delta
    diff=predictions['B'][:,[9,39],0]-predictions['A'][:,[9,39],0]
    stats=group_summary(meta,diff);ng=sum(v[1]>=.005 for v in stats['per_group_rms'].values())
    passed=stats['group_balanced_rms'][1]>=.005 and ng>=3 and len(meta)>=30
    rows=[dict(bag=m['bag'],group=m['group'],role=m['role'],phase=m['phase'],anchor=m['anchor'],
          mismatch_mps=diff[i].tolist(),target=target[i].tolist()) for i,m in enumerate(meta)]
    phases={ph:group_summary([m for m in meta if m['phase']==ph],diff[[i for i,m in enumerate(meta) if m['phase']==ph]])
            for ph in ('traction','braking','coast')}
    # Same-state first-step velocity mismatch after each A warmup.
    local=[]
    for window in prepared:
        a=make('A');b=make('B')
        for row in window[:101]:a.step(*row)
        # clone all common state exactly; only scheme-specific scalar differs.
        import copy
        for k,val in vars(a).items():
            if k not in ('scheme','_effective_acceleration_h34'):setattr(b,k,copy.deepcopy(val))
        row=window[101];ea=a.step(row[0],row[1],None,None);eb=b.step(row[0],row[1],None,None)
        local.append(eb.v-ea.v)
    decision=dict(foundation_passed=passed,scientific_verdict='FOUNDATION_PASS' if passed else 'INCONCLUSIVE',
       threshold_mps=.005,required_groups=3,groups_over_threshold=ng,window_count=len(meta),group_count=len(stats['per_group_rms']),
       **stats,per_phase=phases,scalar_vector_parity=parity,baseline_saved_window_reproduction_max_abs_mps=delta,
       one_step_same_state_rms_mps=float(np.sqrt(np.mean(np.array(local)**2))),
       candidate_implemented=False,fitting_started=False,accuracy_contract_evaluated=False,
       validation_opened=False,test_opened=False,
       reason='Foundation sufficient; exactly one A/B fit allowed' if passed else 'Registered practical discretization mismatch threshold not reached; no fit or validation')
    save(args.output/'decision.json',decision);save(args.output/'per_window.json',rows)
    np.savez_compressed(args.output/'predictions.npz',**predictions,one_step_same_state=np.array(local))
    print(json.dumps(decision,indent=2),flush=True)

if __name__=='__main__':main()
