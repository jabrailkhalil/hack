"""Packaging/reproduction only: fixed measured coefficients, never refit or validate."""
import argparse
from dataclasses import asdict
import hashlib
import io
import json
from pathlib import Path
import subprocess
import urllib.parse
import urllib.request
import zipfile
from model import ROOT, BASE, TREE, FIELDS, Config, profile, save, sha
from fit import yaml_text

THETA = {'profiled':[1.4431384776192366,8.539592014957336,.7797233699048588],
         'control_no_nuisance':[1.1117412748779552,7.084173603327819,.7887928857012503]}
COEFFICIENTS = {'profiled':[3527.671834180356,341583.68059829343,31188.934796194353],
               'control_no_nuisance':[2717.589783035002,283366.94413311273,31551.71542805001]}
EXPECTED = {'main':[.09266814298282507,.2375486120563008,.1293056944774334,5.310295004801444],
            'candidate':[.09248988094018253,.19330671305745648,.12887189815219607,5.409728932108304],
            'control':[.09251950865173568,.24187022618239448,.1290240287650368,5.335704345759274]}


def receipt():
    output=Path(__file__).parent/'SOURCE_RECEIPT.json'
    if output.exists():
        from foundation import integrity
        return integrity()
    actual=subprocess.check_output(['git','rev-parse',BASE+'^{tree}'],cwd=ROOT,text=True).strip()
    assert actual==TREE
    entries=subprocess.check_output(['git','ls-tree','-r','-z',BASE],cwd=ROOT).split(b'\0')
    files=[]
    for entry in filter(None,entries):
        header,path=entry.split(b'\t',1);mode,kind,blob=header.decode().split();name=path.decode()
        assert kind=='blob'
        p=ROOT/name;b=p.read_bytes();digest=hashlib.sha1(f'blob {len(b)}\0'.encode()+b).hexdigest()
        assert digest==blob and bool(p.stat().st_mode & 0o111)==(mode=='100755'),name
        files.append(dict(path=name,mode=mode,sha256=hashlib.sha256(b).hexdigest(),git_blob=blob,size=len(b)))
    assert len(files)==301
    save(output,dict(source_status='VERIFIED',actual_git_tree=TREE,baseline_commit_binding=BASE,
         verification_scope='All 301 original tracked baseline files/modes; newly added research files separate',
         archive_verification=False,zip_sha256=None,files=files))
    return dict(passed=True,files=len(files))


def fixture(output):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    cfg=asdict(profile()[0]);models={'baseline':dict(config=cfg)}
    for name,theta in THETA.items():
        c=cfg|dict(zip(FIELDS,COEFFICIENTS[name]));Config(**c)
        models[name]=dict(config=c,theta=theta,selectable=name=='profiled')
        (output/(name+'.yaml')).write_text(yaml_text(theta))
    save(output/'models.json',dict(models=models,prerequisite_passed=False,
         prerequisite_failures=['check_profiled_objective_regression'],control_selectable=False,
         provenance='Exact already measured local fit; this is not a validation freeze',
         local_fit_source='8a10093a59c9b1d2ffdbe2105521ace4855a873a',fitting_calls_in_reproduction=0))


def prepare(output):
    # Only permitted development DB members are extracted; train/validation/test
    # SQLite payloads are not opened. Archive metadata/hash IO is separate.
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    manifest=json.loads((ROOT/'research/split_v3.json').read_text())
    rows=[r for r in manifest['records'] if r['split']=='development']
    query=urllib.parse.urlencode(dict(public_key='https://disk.yandex.ru/d/DdnscmWTBtzkOQ',path='/dataset.zip'))
    api='https://cloud-api.yandex.net/v1/disk/public/resources/download?'+query
    with urllib.request.urlopen(api,timeout=30) as f:url=json.load(f)['href']
    archive=output/'dataset.zip'
    with urllib.request.urlopen(url,timeout=60) as inp,archive.open('xb') as dst:
        total=0
        while block:=inp.read(1024*1024):
            total+=len(block)
            if total>300*1024*1024:raise ValueError('Oversized archive')
            dst.write(block)
    assert sha(archive)=='d0b2483e13990edb8219b0d7bbcafc7ed001cce549a4d3af467069b2472e7d52'
    with zipfile.ZipFile(archive) as outer:
        inner=outer.read('data.zip')
    selected=[]
    with zipfile.ZipFile(io.BytesIO(inner)) as z:
        for r in rows:
            suffix=r['bag']+'/'+r['bag']+'_0.db3'
            names=[n for n in z.namelist() if n.endswith(suffix)]
            assert len(names)==1
            b=z.read(names[0]);assert hashlib.sha256(b).hexdigest()==r['sha256']
            p=output/'data'/suffix;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
            selected.append(dict(bag=r['bag'],role='development',sha256=r['sha256']))
    save(output/'prepared.json',dict(archive_sha256=sha(archive),selected=selected,
         validation_extracted=False,test_extracted=False))


def verify(path):
    r=json.loads(Path(path).read_text());delta={}
    for n,expected in EXPECTED.items():
        delta[n]={k:r['summary'][n][k]-v for k,v in zip(('clean_rmse','fault_rmse','pooled_rmse','distance_rmse'),expected)}
        assert all(abs(v)<1e-10 for v in delta[n].values()),(n,delta[n])
        assert r['summary'][n]['samples']==394221
    assert r['decisions']['candidate']['rejection_reasons']==['aggregate_regression:distance_rmse','check_profiled_objective_regression']
    save(Path(path).parent/'local_remote_aggregate_reproduction.json',dict(passed=True,absolute_deltas=delta,
         fitting_repeated=False,validation_opened=False,test_opened=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['receipt','fixture','prepare','verify'])
    p.add_argument('--path',type=Path);a=p.parse_args()
    if a.stage=='receipt':print(receipt())
    else:
        if a.path is None:p.error('--path required')
        {'fixture':fixture,'prepare':prepare,'verify':verify}[a.stage](a.path)
