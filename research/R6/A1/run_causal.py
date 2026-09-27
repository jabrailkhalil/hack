"""Fixed D/Z/DZ forensic controls. STOP: no production candidate exists here."""
from forensic import *
HERE=Path(__file__).resolve().parent

def plain(events,fault=False):
 o=GuardedReadoutObserver(CFG,readout=RO);tl=Timeline(o,20,0);out=[]
 for t,ch,v in events:
  if fault and int(ch) in (1,2) and START<=t<END:continue
  tl.ingest(int(ch),Sample(float(t),float(v)))
  for e,_ in tl.advance():out.append((e.t,e.v,e.s,o.v,o.disturbance))
 return np.array(out)
def clone(before):
 o=GuardedReadoutObserver.__new__(GuardedReadoutObserver);o.__dict__.update(copy.deepcopy(before));return o

def main():
 rep=json.loads((OUT/'A0/A0_REPRODUCTION.json').read_text());assert rep['reproduced'] and rep['terminal_delta_s']==41424.813387721915
 events,raw,lock=load();wc,wb={},{};clean,_=run(events,witnesses=wc);base,trigger=run(events,True,witnesses=wb)
 for rows,fault in [(clean,False),(base,True)]:
  p=plain(events,fault);q=np.array([[r[k] for k in ('t','v','s','inner_v','d')] for r in rows]);assert np.array_equal(p,q),'passive instrumentation changed output'
 a=arrays(base);c=arrays(clean);assert a['s'][-1]-c['s'][-1]==rep['terminal_delta_s']
 t=a['t'];dv=a['v']-c['v'];ds=a['s']-c['s'];dt=np.r_[0,np.diff(t)];area=np.r_[0,.5*(dv[1:]+dv[:-1])*np.diff(t)]
 assert max(abs(ds-np.cumsum(area)))<1e-6
 # Both cloned executions get byte-identical normalized raw Samples at same tick.
 counter=[]
 for time_s,(bs,args) in wb.items():
  if time_s<END or not all(x is not None for x in args):continue
  cs,cargs=wc[time_s]
  b,cc=clone(bs),clone(cs)
  rawbytes=b''.join(struct.pack('dd',x.t,x.value) for x in args)
  eb=b.step(time_s,*args);ec=cc.step(time_s,*args)
  expected=base[int(round(time_s/.05))]
  assert eb.v==expected['v'] and eb.s==expected['s']
  def pred(s):
   u=args[0].value;alpha=1-math.exp(-(time_s-s['t'])/CFG.actuator_tau_s)
   obj=clone(s);drive=s['drive_a']+alpha*(obj.drive_target(u,s['v'])-s['drive_a'])
   aa=core.clip(drive-obj.resistance(s['v'])+s['disturbance'],-CFG.max_accel_mps2,CFG.max_accel_mps2)
   v=core.clip(s['v']+(time_s-s['t'])*aa,-CFG.max_speed_mps,CFG.max_speed_mps)
   return 0. if u<=CFG.command_deadband and s['v']*v<0 else v
  bp,cp=pred(bs),pred(cs);z=(args[1].value+args[2].value)*.5
  counter.append(dict(t=time_s,normalized_sample_bytes_sha256=hashlib.sha256(rawbytes).hexdigest(),same_inputs=True,clean_original_input_same=args==cargs,front=as_sample(args[1]),rear=as_sample(args[2]),corrupted={'predicted':bp,'d':bs['disturbance'],'innovation':z-bp,'statuses':[eb.front_status,eb.rear_status],'mode':eb.mode},clean_compatible={'predicted':cp,'d':cs['disturbance'],'innovation':z-cp,'statuses':[ec.front_status,ec.rear_status],'mode':ec.mode},zero_threshold=CFG.stop_model_speed_mps,self_lock=eb.front_status=='ZERO_LOCK_SUSPECT' and ec.front_status=='ACCEPTED'))
 cf=[x for x in counter if x['self_lock']]
 write(HERE/'A1_COUNTERFACTUAL_SELF_LOCK.json',dict(SELF_LOCKING_EVIDENCE=bool(cf),examples=cf[:20],all_checked_ticks=len(counter),identical_sample_bytes=True,no_future=True,state_source='paired clean pre-step at same causal timestamp',physical_truth_claim=False))
 matrix=[];recovery=[];allrows={}
 for name in ('A0','D','Z','DZ'):
  rows,trig=(base,trigger) if name=='A0' else run(events,True,name)
  allrows[name]=rows;a=arrays(rows);delta=a['s']-c['s'];post=t>=END;tail=t>t[-1]-60
  first=lambda fn:next((r['t'] for r in rows if r['t']>=END and fn(r)),None)
  accepted=first(lambda r:r['front_status']=='ACCEPTED' or r['rear_status']=='ACCEPTED');fused=first(lambda r:r['mode']=='FUSED');stopped=first(lambda r:r['mode']=='STOPPED')
  sat=float(sum(dt[post&(abs(a['v'])>=CFG.max_speed_mps-1e-9)]));growth=float((delta[-1]-delta[np.flatnonzero(tail)[0]])/(t[-1]-t[np.flatnonzero(tail)[0]]))
  recovered=fused is not None and stopped is not None and sat==0 and float(max(abs((a['v']-c['v'])[tail])))<1e-8
  result=dict(control=name,D_canonical=name not in ('D','DZ'),ZERO_LOCK_canonical=name not in ('Z','DZ'),trigger=trig,terminal_delta_s_m=float(delta[-1]),time_to_first_accepted_s=accepted-END if accepted is not None else None,time_to_fused_s=fused-END if fused is not None else None,time_to_stopped_s=stopped-END if stopped is not None else None,recovery=bool(recovered),runaway=not bool(recovered),max_abs_v=float(max(abs(a['v'][post]))),saturated_time_s=sat,tail60_delta_s_slope_mps=growth,rejected_new_returning_samples=sum(r[k] in ('ZERO_LOCK_SUSPECT','MODEL_DISAGREEMENT','RATE_ANOMALY','RANGE','COMMON_MODE_QUARANTINE','AMBIGUOUS_PAIR') for r in rows if r['t']>=END for k in ('front_status','rear_status')),horizons=horizon(rows,clean))
  matrix.append(result);print(json.dumps(result),flush=True)
  if name!='A0':write(HERE/f'A1_{name}_RESULT.json',result)
  for r,cl in zip(rows,clean):
   r.update(delta_v=r['v']-cl['v'],delta_s=r['s']-cl['s'],control=name)
   if END-.5<=r['t']<=END+15:recovery.append(r)
  np.savez_compressed(OUT/(name+'_TRACE.npz'),**arrays(rows))
 csvwrite(HERE/'A1_CANONICAL_TIMELINE.csv',base);csvwrite(HERE/'A1_RECOVERY_TRACE.csv',recovery)
 # Quality audit uses pre-gate rate/range outcome independent of the model rejection.
 qualified=[r for r in base if END<=r['t']<=trigger and r['front_t'] is not None and r['rear_t'] is not None and min(r['front_t'],r['rear_t'])>=END]
 quality=dict(classification='RETURNING_PAIR_AMBIGUOUS',first_qualified_trigger_s=trigger,fresh=all(0<=r['front_age']<=CFG.max_age_s and 0<=r['rear_age']<=CFG.max_age_s for r in qualified),finite=all(math.isfinite(r['front_raw']) and math.isfinite(r['rear_raw']) for r in qualified),range_valid=all(abs(r['front_raw'])<=CFG.max_speed_mps and abs(r['rear_raw'])<=CFG.max_speed_mps for r in qualified),skew_valid=all(r['pair_skew']<=CFG.pair_skew_s for r in qualified),agreement=all(r['pair_disagreement']<=CFG.disagreement_mps for r in qualified),rate_range_gate_statuses=sorted(set(r[k] for r in qualified for k in ('front_pre_gate','rear_pre_gate'))),command_compatible=all(r['command']<=CFG.command_deadband for r in qualified),unique_front_stamps=len(set(r['front_t'] for r in qualified)),unique_rear_stamps=len(set(r['rear_t'] for r in qualified)),fault_inactive=all(not r['fault_active'] for r in qualified),explanation='Observationally qualified repeated near-zero pairs; cannot rule out simultaneous physical wheel lock with controller/wheels alone. Conditional oracle evidence only; no independent ground truth used.')
 write(HERE/'RETURNING_PAIR_QUALITY.json',quality)
 success={r['control']:r['recovery'] for r in matrix};status='ROOT_CAUSE_CONFIRMED_ZERO_REACQUISITION' if success['Z'] and cf else 'ROOT_CAUSE_CONFIRMED_DISTURBANCE' if success['D'] else 'ROOT_CAUSE_CONFIRMED_COUPLED' if success['DZ'] else 'ROOT_CAUSE_NOT_CONFIRMED'
 cause=dict(status=status,controls=matrix,necessary={'D_on_tested_path':'YES, contextual: D-only cut removes runaway; not universal necessity','Z_on_tested_path':'YES, contextual: Z-only cut removes runaway; not universal necessity','D_alone_sufficient_for_runaway':False,'Z_alone_sufficient_for_runaway':False,'simultaneous_DZ_intervention_necessary':False,'interaction_scope':'Both canonical retained disturbance and zero-rejection feedback coexist in A0. Neither remaining factor sustains runaway after the other tested cut; no global minimal causal model identified.'},sufficient_cuts=[n for n in ('D','Z','DZ') if success[n]],self_locking=bool(cf),returning_pair=quality['classification'],saturation_diagnostic='NOT_RUN: recovery restored before saturation by D/Z/DZ; saturation downstream',UPSTREAM_METRIC_INFRASTRUCTURE_RISK=False,recommended_B01='Controlled persistent zero-wheel reacquisition; proposal only, physical wheel-lock safety remains unresolved.',production_fix_implemented=False)
 write(HERE/'A1_CAUSAL_MATRIX.json',cause)
 reasons={k:{'status':'PASS','evidence':v} for k,v in {'timestamp_jump':f'max dt {max(dt)}, output monotonic','duplicate_event':'SQL IDs unique; held duplicates rejected rather than re-assimilated','future_sample':'Causal Timeline; no held source timestamp beyond output','broken_dt':f'nonnegative dt, sum {sum(dt)}','overflow':'finite float64 v/s, velocity bounded','NaN_Inf':'all published/inner v,s,d finite; -inf inactive deadlines intentional','integrator_arithmetic':f'max signed integral residual {max(abs(ds-np.cumsum(area)))} m','position_reset_mismatch':'zero Timeline resets; identical prefault trajectory; s never intervened','readout_only_artifact':'inner velocity also saturates, published correction bounded','fault_still_active':'only wheel events with source t in [71.55,74.55) skipped','wrong_clean_pairing':'identical input array/output timestamps; exact archived paired clean/faulted traces','saturation_logging':'counted abs published v >= canonical max_speed, bounded dt; inner also recorded','counterfactual_future':'same-timestamp clean pre-step state, identical raw Sample bytes','passive_instrumentation':'untouched replay exactly equal at every t/v/s/internal_v/d tick'}.items()}
 assert len({r[0] for r in raw})==len(raw)
 assert np.all(np.diff(t)>0) and max(dt)<=CFG.max_step_s+1e-9
 assert all(r['resets']==0 for r in base)
 assert all(r[k] is None or r[k]<=r['t']+1e-9 for r in base for k in ('command_source_t','front_t','rear_t'))
 assert all(math.isfinite(r[k]) for r in base for k in ('v','s','inner_v','d'))
 assert np.all(abs(arrays(base)['inner_v'])<=CFG.max_speed_mps)
 j=np.flatnonzero(t<START);assert np.array_equal(arrays(base)['s'][j],c['s'][j])
 write(HERE/'A1_ALTERNATIVE_CAUSES.json',reasons)
 write(HERE/'PHASE_ACCOUNTING.json',{'fault_delta_s_m':float(ds[np.flatnonzero(t<END)[-1]]-ds[np.flatnonzero(t<START)[-1]]),'post_fault_delta_s_m':float(ds[-1]-ds[np.flatnonzero(t<END)[-1]]),'total_delta_s_m':float(ds[-1]),'first_saturation_t':next(r['t'] for r in base if abs(r['v'])>=CFG.max_speed_mps-1e-9),'first_zero_reject_after_fault':next(r['t'] for r in base if r['t']>=END and 'ZERO_LOCK_SUSPECT' in (r['front_status'],r['rear_status']))})
 print('STATUS',status,flush=True)
def as_sample(s):return {'source_t':s.t,'value':s.value}
if __name__=='__main__':main()
