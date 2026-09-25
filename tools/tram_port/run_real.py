"""NEW, NOT-EXECUTED real-data validation entry point using a pinned hack checkout.

It opens only the upstream 'validation' role through upstream Store; never test.
No upstream FREEZE, source, config or promotion file is changed. This loader is
syntax-checked but could not be exercised against the unavailable dataset.
"""
from pathlib import Path
import argparse,importlib.util,json,subprocess,sys
import numpy as np
ROOT=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT/'vendor/hack'),str(ROOT/'vendor/ours')]
import run_native as audit
from run_native import factory,score,dump

PIN='e3b0c9c039d2953fbfcda51231263d38ef9f1024'

def main(checkout,data,output,bags=None):
    checkout=Path(checkout).resolve();output=Path(output)
    sha=subprocess.check_output(['git','-C',str(checkout),'rev-parse','HEAD'],text=True).strip()
    if sha!=PIN:raise ValueError('Use the exact pinned hack checkout: '+PIN)
    # Import the complete, unchanged upstream loader/evaluator from its checkout.
    location=checkout/'tools/finalization/evaluate.py'
    spec=importlib.util.spec_from_file_location('native_validation_evaluator',location)
    ev=importlib.util.module_from_spec(spec);spec.loader.exec_module(ev)
    store=ev.ex.Store(Path(data).resolve())
    selected=list(bags) if bags else list(store.plan['splits']['validation'])
    if not set(selected)<=set(store.plan['splits']['validation']):
        raise PermissionError('This new comparison permits upstream validation only')
    # Fail closed if the stand-alone function bodies differ from the real checkout.
    import ast,inspect
    import native_functions as nf
    for a,b in [(nf.replay,ev.replay),(nf.distance_surrogate,ev.distance_surrogate),
                (nf.match,ev.ex.match),(nf.metrics,ev.ex.metrics)]:
        if ast.dump(ast.parse(inspect.getsource(a)))!=ast.dump(ast.parse(inspect.getsource(b))):
            raise ValueError('Native function mismatch: '+a.__name__)
    output.mkdir(parents=True,exist_ok=False);all_rows=[]
    methods=audit.METHODS
    for bag in selected:
        events,refs=store.load(bag,'validation');arrays={};runtime={}
        for method in methods:
            ctor,config=factory(method);previous=ev.Observer
            try:
                ev.Observer=ctor
                arrays[method],runtime[method]=ev.replay(events,config,audit.OPS)
            finally:ev.Observer=previous
        common=None
        for a in arrays.values():
            keys=np.rint(a[:,0]*1e9).astype('int64')
            common=keys if common is None else np.intersect1d(common,keys)
        for method,a in arrays.items():
            if not len(a):
                all_rows.append({'bag':bag,'method':method,'status':'NO_PREDICTIONS'})
                continue
            for receiver,ref in refs.items():
                m,target=score(a,ref,None,common)
                row={'bag':bag,'group':store.records[bag]['group'],'role':'validation','receiver':receiver,
                     'method':method,'runtime':runtime[method],**m}
                all_rows.append(row)
                np.savez_compressed(output/f'{bag}__{method}__{receiver}.npz',prediction=a,reference=target)
        dump(output/'access.json',store.access)
        dump(output/'results.json',all_rows)
    # This entry point currently measures CLEAN validation only; no hidden training
    # or automatic selection and no claim of full fault-suite reproduction.
    dump(output/'scope.json',{'phase':'clean_validation_only','source_commit':PIN,'test_opened':False,'models_retrained':False})

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--hack-checkout',required=True);p.add_argument('--data-root',required=True)
    p.add_argument('--output',required=True);p.add_argument('--bags',nargs='+')
    args=p.parse_args();main(args.hack_checkout,args.data_root,args.output,args.bags)
