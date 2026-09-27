"""Compact H61 delivery, excluding all upstream input payloads."""
from pathlib import Path
import json,hashlib,zipfile,subprocess
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'reports/research_R6/H61'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 s=json.loads((OUT/'SUMMARY.json').read_text());assert s['actual_evaluations']<=900 and not s['forbidden_data_opened']
 commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
 calls=[json.loads(line) for line in (OUT/'CALL_LEDGER.jsonl').read_text().splitlines()]
 intermediate={f"call_{r['call']:04d}.npz" for r in calls if r['label'].startswith('powell_')}
 allfiles=sorted(p for d in (ROOT/'research/R6/H61',OUT) for p in d.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc' and p.name!='EXECUTION.lock')
 omitted=[p for p in allfiles if p.parent.name=='evidence' and p.name in intermediate]
 files=[p for p in allfiles if p not in omitted]
 manifest={str(p.relative_to(ROOT)):{'sha256':sha(p),'bytes':p.stat().st_size} for p in files}
 dest=ROOT/'deliveries';dest.mkdir(exist_ok=True);stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');archive=dest/f'R6-H61_train_optimization_audit_{stamp}.zip'
 with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  for p in files:z.write(p,p.relative_to(ROOT))
  z.writestr('MANIFEST.json',json.dumps(manifest,indent=2)+'\n')
  z.writestr('LOCAL_ONLY_INTERMEDIATE_ARRAYS.json',json.dumps({str(p.relative_to(ROOT)):{'sha256':sha(p),'bytes':p.stat().st_size} for p in omitted},indent=2)+'\n')
 with zipfile.ZipFile(archive) as z:
  assert z.testzip() is None
  for name,v in manifest.items():assert hashlib.sha256(z.read(name)).hexdigest()==v['sha256']
 receipt={'artifact':archive.name,'sha256':sha(archive),'bytes':archive.stat().st_size,'files':len(files),'branch':'research/R6-H61','commit':commit,'status':s['status'],'calls':s['actual_evaluations'],'payload_verified':True,'upstream_inputs_included':False,'dependency_lock':'research/R6/H61/DEPENDENCIES.lock','compact_export':True,'local_only_intermediate_arrays':len(omitted),'all_call_metrics_and_fingerprints_included':True}
 rp=archive.with_suffix('.receipt.json');rp.write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({'zip':str(archive),'receipt':str(rp),**receipt},indent=2))
if __name__=='__main__':main()
