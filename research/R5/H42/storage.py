"""New role-locked read-only GNSS loader; legacy Store and scorer are untouched."""
from pathlib import Path, PurePosixPath
import hashlib, importlib.util, io, json, os, sqlite3, zipfile
import numpy as np
from decoder import decode, common_fields, VEL, FIX

ROOT = Path(__file__).resolve().parents[3]
SPLIT_SHA = '20928a29daad2b4178ddb92e2a4d9ddb347952f6c03845802a8d82fff7da5ae0'
DATA_SHA = 'd0b2483e13990edb8219b0d7bbcafc7ed001cce549a4d3af467069b2472e7d52'
BASE = 'b2783206000091ab11a1c11ac3ff79082188a4fb'
TOPICS = {f'/sensing/gnss/{r}/{k}':(r+'_'+k,VEL if k=='vel' else FIX)
          for r in ('master','rover') for k in ('vel','fix')}

def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def save_json(path, value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as f:
        json.dump(value,f,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False);f.write('\n')

def savez(path, arrays):
    """NPZ with deterministic timestamps/member order; no pickle objects."""
    with zipfile.ZipFile(path,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name,a in sorted(arrays.items()):
            b=io.BytesIO();np.lib.format.write_array(b,np.asarray(a),allow_pickle=False)
            info=zipfile.ZipInfo(name+'.npy',date_time=(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=0o100644 << 16;z.writestr(info,b.getvalue(),compresslevel=6)

def columns(rows,kind):
    fields={'message_id':np.int64,'record_ns':np.int64,'stamp_ns':np.int64,
            'frame_id':str,'wire_sha256':'S64'}
    if kind=='vel':fields.update(linear=float,angular=float)
    else:fields.update(position=float,covariance=float,status=np.int16,service=np.uint16,covariance_type=np.uint8)
    out={}
    for k,typ in fields.items():
        shape=3 if k in ('linear','angular','position') else 9 if k=='covariance' else None
        a=np.asarray([r[k] for r in rows],dtype=typ)
        if shape:a=a.reshape((-1,shape))
        out[k]=a
    return out

def same(a,b):
    if isinstance(a,(list,tuple)) and isinstance(b,(list,tuple)):
        return len(a)==len(b) and all(same(x,y) for x,y in zip(a,b))
    if isinstance(a,float) and isinstance(b,float) and np.isnan(a) and np.isnan(b):return True
    return a==b

class Store:
    def __init__(self,dataset,data_root,journal,role,freeze=None):
        if role not in ('train','development'):raise PermissionError('Role forbidden: '+role)
        if role=='development' and freeze is None:raise PermissionError('Published policy freeze required')
        split=ROOT/'research/split_v3.json'
        if sha(split)!=SPLIT_SHA:raise ValueError('Frozen split mismatch')
        self.records={r['bag']:r for r in json.loads(split.read_text())['records']}
        self.dataset=Path(dataset);self.root=Path(data_root);self.root.mkdir(parents=True,exist_ok=True)
        self.role=role;self.journal=Path(journal);self.journal.parent.mkdir(parents=True,exist_ok=True)
        if sha(self.dataset)!=DATA_SHA or self.dataset.stat().st_size!=256294592:raise ValueError('Dataset ZIP mismatch')
        spec=importlib.util.spec_from_file_location('h42_unchanged_export',ROOT/'tools/export_bags.py')
        self.legacy=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.legacy)
        self.inner=self.root/'data.zip'
        if not self.inner.exists():
            with zipfile.ZipFile(self.dataset) as z,z.open('data.zip') as src,self.inner.open('xb') as dst:
                import shutil;shutil.copyfileobj(src,dst)
        # Every source payload is still hash checked; an existing inner cache is not trusted by name.
    def event(self,row):
        with self.journal.open('a',encoding='utf-8') as f:f.write(json.dumps(row,sort_keys=True,ensure_ascii=False)+'\n')
    def path(self,bag):
        r=self.records.get(bag)
        if not r or r['split']!=self.role:raise PermissionError('Bag/role mismatch before ZIP or SQL: '+bag)
        p=self.root/bag/(bag+'_0.db3')
        if not p.exists():
            member=bag+'/'+bag+'_0.db3'
            with zipfile.ZipFile(self.inner) as z:
                if z.namelist().count(member)!=1:raise ValueError('Missing/duplicate authorized DB')
                raw=z.read(member)
            if hashlib.sha256(raw).hexdigest()!=r['sha256']:raise ValueError('DB mismatch before extraction')
            p.parent.mkdir(exist_ok=True)
            with p.open('xb') as f:f.write(raw)
        if sha(p)!=r['sha256']:raise ValueError('DB mismatch before SQL: '+bag)
        return p
    def load(self,bag):
        p=self.path(bag);r=self.records[bag]
        self.event(dict(event='SQL_OPEN',bag=bag,role=self.role,db_sha256=r['sha256'],
                        topics=list(TOPICS),vehicle_payload_allowed=False,reference_kind='raw_GNSS_proxy'))
        streams={v[0]:[] for v in TOPICS.values()};raw_by_id={};checks=0
        con=sqlite3.connect(p.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
        try:
            con.execute('PRAGMA query_only=ON')
            topics=list(con.execute('SELECT name,type FROM topics'))
            q=('SELECT m.id,m.timestamp,t.name,t.type,m.data FROM messages m JOIN topics t ON t.id=m.topic_id '
               'WHERE t.name IN ('+','.join('?' for _ in TOPICS)+') ORDER BY m.timestamp,m.id')
            for mid,record,topic,typ,raw in con.execute(q,list(TOPICS)):
                key,expected=TOPICS[topic]
                if typ!=expected:raise ValueError('Unexpected GNSS type')
                row=decode(raw,typ)
                if not same(common_fields(row,typ),self.legacy.decode(raw,typ)):
                    raise AssertionError('Extended decoder differs from canonical common fields')
                checks+=1;row.update(message_id=mid,record_ns=record,wire_sha256=hashlib.sha256(raw).hexdigest())
                streams[key].append(row);raw_by_id[mid]=(topic,typ,record,raw,row)
        finally:con.close()
        for topic,(key,_) in TOPICS.items():
            if len(streams[key])!=r['counts'].get(topic,0):raise AssertionError('Native count mismatch')
        self.event(dict(event='SQL_CLOSED',bag=bag,role=self.role,rows=checks,decoder_comparisons=checks))
        return {key:columns(rows,key.split('_')[-1]) for key,rows in streams.items()},raw_by_id,topics,checks
