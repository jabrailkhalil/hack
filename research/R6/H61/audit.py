"""Single execution of frozen H61; no upstream fit/check entrypoints called."""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[k]='1'
from pathlib import Path
import sys,json,csv,hashlib,time,importlib.util,subprocess,fcntl
import numpy as np
from scipy.optimize import minimize
ROOT=Path(__file__).resolve().parents[3]; CODE=Path(__file__).parent; IN=ROOT/'.h61_inputs'; OUT=ROOT/'reports/research_R6/H61'
sys.path[:0]=[str(ROOT/'src/reserve_odometry'),str(IN/'h44')]
import reserve_odometry.guarded_readout
import interface
interface.ROOT=ROOT
import fit as h44
spec=importlib.util.spec_from_file_location('h54',IN/'h54/study.py');h54=importlib.util.module_from_spec(spec);spec.loader.exec_module(h54)
from branch_audit import BranchAudit
OPTIONS={'xtol':1e-6,'ftol':1e-8,'maxfev':130}
def write(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
def table(p,rows):
 if not rows:return
 with p.open('w') as f:
  w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rows for k in r)));w.writeheader();w.writerows(rows)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def fingerprint(a):return hashlib.sha256(np.asarray(a,dtype='<f8').tobytes()).hexdigest()
def verify():
 lock=json.loads((CODE/'DEPENDENCIES.lock').read_text())
 for p,entry in lock['files'].items():assert sha(ROOT/p)==entry['sha256'],p
 assert sha(CODE/'FOLDS.json')==lock['folds_sha256']
 return lock
def load_fit():
 meta=json.loads((IN/'windows/windows.json').read_text());idx=np.array([i for i,m in enumerate(meta) if m['fold']=='fit']);mm=[meta[i] for i in idx]
 assert len(mm)==141 and len({m['group'] for m in mm})==15
 with np.load(IN/'windows/windows.npz',allow_pickle=False) as z:samples=z['samples'][idx];target=z['gnss'][idx]
 assert np.isfinite(samples).all() and np.isfinite(target).all()
 return samples,target,mm,idx
def parts(obj,ratios,x,prior=True):
 top=np.argsort(-ratios,kind='stable')[:obj.K];mean=float(np.mean(ratios));worst=float(np.mean(ratios[top]));pr=.01*float(np.mean(x*x)) if prior else 0.
 return {'J1':.5*mean+.5*worst+pr,'mean_Rg':mean,'worst_half_mean':worst,'prior':pr,'active_top_half_groups':[obj.groups[i] for i in top]}
def bound_check(x,lo,hi):
 if not np.isfinite(x).all() or np.any(x<lo) or np.any(x>hi):raise ValueError('Invalid theta/bounds')
def forbidden(path):
 s=str(path).lower()
 return any(v in s for v in ('check_results','development.csv','raw_predictions','r6_a1','r6_worktree','r6_h52','h43','h53','h57')) or s.endswith(('.db3','.sqlite','.sqlite3'))
class Audit:
 def __init__(self):
  self.lock=verify();self.samples,self.target,self.meta,self.original_idx=load_fit();self.contract=json.loads((IN/'h54/OBJECTIVE_CONTRACT.json').read_text());self.den={r['group']:r['denominator'] for r in self.contract['groups']};self.theta0=np.array(self.contract['theta0']);self.lo,self.hi=np.log(np.array(self.contract['absolute_bounds'])/self.theta0);self.calls=0;self.results=[];self.contexts={}
  self.groups=sorted(self.den);self.register('full',self.groups)
  self.folds=json.loads((CODE/'FOLDS.json').read_text())['folds']
  for f in self.folds:self.register('fold'+str(f['fold']),f['train_groups'])
 def register(self,name,groups):
  ids=np.array([i for i,m in enumerate(self.meta) if m['group'] in groups]);meta=[self.meta[i] for i in ids];assert set(groups)=={m['group'] for m in meta}
  self.contexts[name]=(ids,h44.Predictor(self.samples[ids]),h54.Objective(meta,self.den))
 def call(self,x,context,label,instrument=False,prior=True):
  x=np.array(x,dtype=float);bound_check(x,self.lo,self.hi)
  if self.calls>=900:raise RuntimeError('H61 physical budget exhausted')
  self.calls+=1;ids,predictor,obj=self.contexts[context]
  row={'call':self.calls,'context':context,'label':label,'x':x.tolist(),'groups':obj.groups,'original_window_indices':self.original_idx[ids].tolist()}
  with (OUT/'CALL_LEDGER.jsonl').open('a') as f:f.write(json.dumps(row)+'\n');f.flush()
  start=time.monotonic();tr=None
  if instrument:
   with BranchAudit(len(ids)) as tr:pred=predictor.predict(x)
  else:pred=predictor.predict(x)
  e=h54.six(pred,self.target[ids],self.samples[ids]);r,loss,ratios,top=obj.residual(e,x,True)
  assert all(np.isfinite(a).all() for a in (pred,e,r,loss,ratios))
  result={**row,**parts(obj,ratios,x,prior), 'group_losses':loss.tolist(),'group_ratios':ratios.tolist(),'prediction_hash':fingerprint(pred),'six_hash':fingerprint(e),'loss_hash':fingerprint(loss),'residual_hash':fingerprint(r),'seconds':time.monotonic()-start}
  assert abs(parts(obj,ratios,x)['J1']-r@r)<1e-12
  if tr:
   from collections import Counter
   counters=Counter()
   for c in tr.rows:counters.update(c)
   result['branch_counters']=dict(counters)
   table(OUT/'evidence'/f'BRANCH_{label}.csv',[{'original_window_index':int(self.original_idx[ids[i]]),**dict(c)} for i,c in enumerate(tr.rows)])
  (OUT/'evidence').mkdir(exist_ok=True)
  np.savez_compressed(OUT/'evidence'/f'call_{self.calls:04d}.npz',prediction=pred,six=e,losses=loss,ratios=ratios,residual=r)
  with (OUT/'CALL_RESULTS.jsonl').open('a') as f:f.write(json.dumps(result)+'\n');f.flush()
  self.results.append(result)
  if self.calls%10==0 or label.startswith(('A_','final','heldout')):print(self.calls,label,result['J1'],flush=True)
  return result
 def fit(self,name):
  before=self.calls
  result=minimize(lambda x:self.call(x,name,'powell_'+name)['J1'],np.zeros(3),method='Powell',bounds=list(zip(self.lo,self.hi)),options=OPTIONS)
  assert self.calls-before==result.nfev and result.nfev<=130
  obj={'context':name,'groups':self.contexts[name][2].groups,'x':result.x.tolist(),'theta':(self.theta0*np.exp(result.x)).tolist(),'J1':float(result.fun),'success':bool(result.success),'status':int(result.status),'message':str(result.message),'nfev':int(result.nfev),'nit':int(result.nit),'options':OPTIONS,'start':[0,0,0],'frozen_before_heldout':True}
  write(OUT/(name.upper()+'_FREEZE.json'),obj);print('FROZEN',name,obj['J1'],obj['nfev'],obj['message'],flush=True);return obj
def same(rows):
 return all(all(r[k]==rows[0][k] for k in ('prediction_hash','six_hash','loss_hash','residual_hash')) for r in rows)
def main():
 OUT.mkdir(parents=True,exist_ok=True);(OUT/'evidence').mkdir(exist_ok=True)
 guard=(OUT/'EXECUTION.lock').open('a');fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
 if (OUT/'CALL_LEDGER.jsonl').exists():raise RuntimeError('Execution already started; no restart permitted')
 a=Audit();c0=np.array(json.loads((IN/'h54/CONTROL_FIT.json').read_text())['logratio']);zeros=np.zeros(3)
 opened=[]
 def hook(event,args):
  if event=='open' and isinstance(args[0],(str,bytes)):
   p=os.fsdecode(args[0])
   if forbidden(p):raise RuntimeError('Forbidden data access: '+p)
   if '.h61_inputs' in p:opened.append(p)
 sys.addaudithook(hook)
 rep={n:[a.call(x,'full','A_'+n+str(i)) for i in range(2)] for n,x in [('baseline',zeros),('C0',c0)]}
 gateA=all(same(v) for v in rep.values()) and abs(rep['baseline'][0]['J1']-1)<=1e-12 and abs(rep['C0'][0]['J1']-.9919358040775982)<=1e-9
 write(OUT/'OBJECTIVE_REPRODUCTION.json',{'PASS':gateA,'repeats':rep})
 if not gateA:
  write(OUT/'SUMMARY.json',{'status':'INVALID_OBJECTIVE_REPRODUCTION','calls':a.calls});return
 scan=[]
 for i in range(21):
  alpha=i/20;r=a.call(alpha*c0,'full','line_'+str(i),True)
  if i in (0,20):assert same([r,rep['baseline' if i==0 else 'C0'][0]])
  scan.append({'alpha':alpha,**{k:r[k] for k in ('J1','mean_Rg','worst_half_mean','prior')},'active_top_half_groups':json.dumps(r['active_top_half_groups']),'branch_counters':json.dumps(r['branch_counters'])})
 table(OUT/'LINE_SCAN.csv',scan)
 full=a.fit('full');folds=[a.fit('fold'+str(i)) for i in range(5)]
 write(OUT/'ALL_FITS_FREEZE.json',{'full':full,'folds':folds,'calls_before_any_heldout':a.calls})
 repeats=[a.call(full['x'],'full','final_full'+str(i)) for i in range(2)];assert same(repeats);assert abs(full['J1']-repeats[0]['J1'])<1e-14
 full['final_repeats']=repeats;write(OUT/'FULL_OPTIMIZATION.json',full)
 transfer=[]
 for f,result in zip(a.folds,folds):
  name='fold'+str(f['fold']);reps=[a.call(result['x'],name,'final_'+name+'_'+str(i)) for i in range(2)];assert same(reps);assert abs(result['J1']-reps[0]['J1'])<1e-14;result['final_repeats']=reps
  held=name+'_heldout';a.register(held,f['heldout_groups']);base=a.call(zeros,held,'heldout_base_'+name,prior=False);rr=[a.call(result['x'],held,'heldout_'+name+'_'+str(i),prior=False) for i in range(2)];assert same(rr)
  transfer.append({'fold':f['fold'],'groups':json.dumps(f['heldout_groups']),'baseline_H':base['J1'],'optimized_H':rr[0]['J1'],'gain_pct':100*(1-rr[0]['J1']/base['J1']),'improved':rr[0]['J1']<base['J1'],'active_top_half_groups':json.dumps(rr[0]['active_top_half_groups'])})
 write(OUT/'FOLD_OPTIMIZATIONS.json',folds);table(OUT/'HELDOUT_TRANSFER.csv',transfer)
 xs=np.array([f['x'] for f in folds]);theta=a.theta0*np.exp(xs)
 stability=[{'fold':i,'parameter':p,'logratio':float(xs[i,j]),'theta':float(theta[i,j]),'distance_to_log_lower':float(xs[i,j]-a.lo[j]),'distance_to_log_upper':float(a.hi[j]-xs[i,j]),'fold_min':float(theta[:,j].min()),'fold_max':float(theta[:,j].max()),'fold_std':float(theta[:,j].std())} for i in range(5) for j,p in enumerate(('F/m','P/m','B/m'))]
 table(OUT/'PARAMETER_STABILITY.csv',stability);dist=np.linalg.norm(xs[:,None,:]-xs[None,:,:],axis=2);write(OUT/'PARAMETER_DISTANCES.json',{'logratio_distances':dist.tolist()})
 gains=[r['gain_pct'] for r in transfer];gateB=full['J1']<=.9920 and full['J1']<=rep['C0'][0]['J1']+1e-4;gateC=sum(r['improved'] for r in transfer)>=4 and np.median(gains)>=.5 and min(gains)>=-5
 verify();diff=subprocess.check_output(['git','diff','b2783206000091ab11a1c11ac3ff79082188a4fb','--name-only'],cwd=ROOT,text=True);assert all(p.startswith(('research/R6/H61/','reports/research_R6/H61/')) for p in diff.splitlines())
 integrity={'PASS':True,'finite':True,'bounds_respected':True,'repeats_exact':True,'fit_windows':141,'fit_groups':15,'fit_only':True,'forbidden_data_opened':False,'check_development_validation_final_opened':False,'claim_verified':True,'calls':a.calls,'runtime_modified':False,'dependency_files_opened_after_loading':sorted(set(opened))}
 write(OUT/'INTEGRITY.json',integrity)
 status='SOLVER_FAILED_TO_REPRODUCE_KNOWN_DESCENT' if not gateB else 'TRAIN_OBJECTIVE_OPTIMIZABLE_BUT_NOT_TRANSFERABLE' if not gateC else 'TRAIN_OPTIMIZATION_AUDIT_PASSED'
 summary={'status':status,'gates':{'A':True,'B':bool(gateB),'C':bool(gateC),'D':True},'baseline_J1':rep['baseline'][0]['J1'],'C0_J1':rep['C0'][0]['J1'],'full_J1':full['J1'],'full_gain_pct':100*(1-full['J1']/rep['baseline'][0]['J1']),'heldout_improved':sum(r['improved'] for r in transfer),'median_heldout_gain_pct':float(np.median(gains)),'worst_heldout_regression_pct':max(0.,-min(gains)),'theta_min':theta.min(axis=0).tolist(),'theta_max':theta.max(axis=0).tolist(),'max_fold_log_distance':float(dist.max()),'actual_evaluations':a.calls,'forbidden_data_opened':False,'check_development_validation_final_opened':False,'accuracy_candidate':False,'runtime_modified':False,'full_solver_success':full['success'],'fold_solver_success':[r['success'] for r in folds],'physical_seconds':sum(r['seconds'] for r in a.results)}
 write(OUT/'SUMMARY.json',summary);print(json.dumps(summary),flush=True)
if __name__=='__main__':main()
