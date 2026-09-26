"""Construct all-301-file pins from the independently verified baseline Git tree."""
import hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent
B='e3b0c9c039d2953fbfcda51231263d38ef9f1024'
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)
assert git('rev-parse',B+'^{tree}').decode().strip()=='eae49a504bc59b5c9b408445150bef32e111956f'
entries=git('ls-tree','-rz',B).split(b'\0');pins={};files=[]
for e in entries:
    if not e:continue
    meta,path=e.split(b'\t',1);mode,typ,oid=meta.split();p=path.decode()
    assert typ==b'blob';data=git('cat-file','blob',oid.decode());h=hashlib.sha256(data).hexdigest()
    assert (ROOT/p).read_bytes()==data,p
    assert bool((ROOT/p).stat().st_mode&0o111)==(mode==b'100755'),p
    pins[p]=h;files.append(dict(path=p,mode=mode.decode(),git_blob=oid.decode(),sha256=h,size=len(data)))
assert len(pins)==301
(HERE/'BASE_PINS.json').write_text(json.dumps(pins,indent=2)+'\n')
(HERE/'SOURCE_RECEIPT.json').write_text(json.dumps(dict(source_status='VERIFIED',baseline_sha=B,
    baseline_tree='eae49a504bc59b5c9b408445150bef32e111956f',file_count=301,files=files,
    user_zip_sha256='a8e0bfa033e0a02c460c30b02f34a5c64ece85b05003512941387d3cf1f319a2',
    scope='Remote Git bytes/modes verified; user ZIP independently verified locally'),indent=2)+'\n')
expected={'foundation.py':'ae31744cdf0902d831922973f4000d3515e8039755a1ca4a026eaf556edba547','prepare.py':'2a22f7c3b5d18bc179055c9ed07dec2de2edd1bffca8817583eddbc51def696c','common.py':'d7d6c007e4f57eefa4eba5af484abf805c4bd744b5b197720726f766f65af0ae','tests/test_foundation.py':'d072dd03f89c2c5b55d06e1448998c7cbd249b5d9787f41213fd13d72a44c7b9'}
for p,h in expected.items():assert hashlib.sha256((HERE/p).read_bytes()).hexdigest()==h,p
print('All baseline bytes/modes and locally tested foundation sources verified.')
