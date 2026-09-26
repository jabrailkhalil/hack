"""Prepare pinned source/evidence without changing any estimator.

Only the 19 existing validation databases are extracted. All generated runner
inputs must match the checksums published before local numerical measurement.
"""
from pathlib import Path
import argparse, hashlib, io, json, os, shutil, subprocess, urllib.parse, urllib.request, zipfile
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
WORK=ROOT/'.adjudication'
MAIN='e3b0c9c039d2953fbfcda51231263d38ef9f1024'
PEER='98accff0d97b2ff69a2307e30841d2dec788c1d3'
SCENARIOS='7b2734e8665896c43cf7aa567355cb9ab447e904'
PEERS={'A':PEER,'B':'46a81edf2a02ea170af5bde818746aea808e728a','C':'84342ac394f0de4e3f79e42e1b3a6526ebb6608a','D':'13c86f38e18d23ae964b23b0ee2ef63cca4a799a','H1_10':'b33d8b42262a5aabe0fdc22ac7b65b54d507798e','H2_050':'f76e4d729801a479b036a18a1bbe69cf47877e84'}
PIN_PATHS=['src/reserve_odometry/reserve_odometry/core.py','src/reserve_odometry/reserve_odometry/guarded_readout.py','src/reserve_odometry/reserve_odometry/timeline.py','src/reserve_odometry/config/champion_v8.json','tools/finalization/evaluate.py','tools/research_v3/experiment.py','tools/export_bags.py','research/plan_v3.json','research/split_v3.json']
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)
def save(path,data):path.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n')
def extract(archive,dest,allowed=None):
    dest=dest.resolve();dest.mkdir(parents=True,exist_ok=True)
    for ent in archive.infolist():
        if ent.is_dir() or (allowed is not None and ent.filename.split('/')[0] not in allowed):continue
        target=(dest/ent.filename).resolve()
        if dest not in target.parents:raise ValueError('unsafe archive path')
        target.parent.mkdir(parents=True,exist_ok=True)
        with archive.open(ent) as source,target.open('wb') as out:shutil.copyfileobj(source,out)
def source():
    WORK.mkdir(exist_ok=True)
    for name,sha,paths in [('ours',MAIN,[]),('peer',PEER,['tools/tram_port'])]:
        data=git('archive','--format=zip',sha,*paths)
        with zipfile.ZipFile(io.BytesIO(data)) as z:extract(z,WORK/name)
    save(HERE/'source_hashes.json',{p:hashlib.sha256((WORK/'ours'/p).read_bytes()).hexdigest() for p in PIN_PATHS})
    manifests={}
    for name,sha in PEERS.items():
        entries={}
        for line in git('ls-tree','-r',sha,'tools/tram_port').decode().splitlines():
            mode,kind,rest=line.split(' ',2);blob,path=rest.split('\t');path=path.removeprefix('tools/tram_port/')
            if path.endswith(('.py','.json')) and path not in ('variant.json','PUBLISH_CHECKS.json','SOURCES.json','PROTOCOL.json'):entries[path]=blob
        if name=='D':entries.pop('geometry_metrics.json',None)
        manifests[name]=entries
    if any(v!=manifests['A'] for v in manifests.values()):raise ValueError('Peer implementation changed between branch variants')
    save(HERE/'peer_source_hashes.json',manifests['A'])
    plan=json.loads((WORK/'ours/research/plan_v3.json').read_text());known=git('ls-tree','-r','--name-only',SCENARIOS).decode().splitlines();scenarios={}
    for bag in sorted(plan['splits']['validation']):
        matches=[p for p in known if p.endswith('/validation/bags/'+bag+'.json')]
        if len(matches)!=1:raise ValueError('ambiguous frozen evidence path '+bag)
        prior=json.loads(git('show',SCENARIOS+':'+matches[0]))
        scenarios[bag]={suite:[row['fault'] for row in prior[suite]] for suite in ('stress','abrupt','slow')}
    save(HERE/'scenarios.json',scenarios)
    freeze=json.loads((HERE/'FREEZE.json').read_text())
    for p,expected in freeze['files_sha256'].items():
        actual=hashlib.sha256((HERE/p).read_bytes()).hexdigest()
        if actual!=expected:raise ValueError('Frozen runner file mismatch '+p+' '+actual)
    print('FROZEN_SOURCE_PASS; peer implementations identical; final-test payloads not opened')
def data():
    WORK.mkdir(exist_ok=True)
    target=WORK/'dataset.zip';expected='d0b2483e13990edb8219b0d7bbcafc7ed001cce549a4d3af467069b2472e7d52'
    if not target.exists():
        query=urllib.parse.urlencode({'public_key':'https://disk.yandex.ru/d/DdnscmWTBtzkOQ','path':'/dataset.zip'})
        with urllib.request.urlopen('https://cloud-api.yandex.net/v1/disk/public/resources/download?'+query,timeout=30) as response:url=json.load(response)['href']
        with urllib.request.urlopen(url,timeout=60) as response,target.open('wb') as out:shutil.copyfileobj(response,out)
    if hashlib.sha256(target.read_bytes()).hexdigest()!=expected:raise ValueError('Dataset changed')
    with zipfile.ZipFile(target) as outer,outer.open('data.zip') as inp,(WORK/'data.zip').open('wb') as out:shutil.copyfileobj(inp,out)
    plan=json.loads((WORK/'ours/research/plan_v3.json').read_text());allowed=set(plan['splits']['validation'])
    with zipfile.ZipFile(WORK/'data.zip') as inner:extract(inner,WORK/'validation',allowed)
    print('ONLY_VALIDATION_EXTRACTED',len(allowed))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data',action='store_true');a=p.parse_args()
    if a.data:data()
    else:source()
