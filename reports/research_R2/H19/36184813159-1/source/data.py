"""Exact split gates before measurement IO. Test has no supported load path."""
import io
import json
import math
import sqlite3
import zipfile
from pathlib import Path
from factory import ROOT, ev, digest
np, ex = ev.np, ev.ex
EXPORT_SHA = '5a840289a44b90d118847b33cdab2d3820ede3d92678bef350ed475f40c47fce'

class Store(ex.Store):
    def __init__(self, export=None, journal=None):
        super().__init__(); self.export = Path(export) if export else None; self.journal = journal
        self.zip = None
        if export:
            if digest(self.export.read_bytes()) != EXPORT_SHA: raise ValueError('Development ZIP hash')
            self.zip = zipfile.ZipFile(self.export)
            self.export_access = {r['bag']:r for r in json.loads(self.zip.read('access.json'))}
            if set(self.export_access) != set(self.plan['splits']['development']): raise ValueError('Export membership')
    def load(self, bag, purpose):
        r = self.records[bag]
        if purpose not in ('train','development','validation') or r['split'] != purpose:
            raise PermissionError('No measurement access for '+purpose+'/'+bag)
        allowed = list(ex.CHANNELS)+(list(ex.REFS) if purpose != 'train' else [])
        row = dict(bag=bag,purpose=purpose,group=r['group'],sha256=r['sha256'],topics=allowed)
        self.access.append(row)
        if self.journal: ev.save(self.journal,self.access)
        if self.export:
            if purpose != 'development': raise PermissionError('Export is development only')
            old = self.export_access[bag]
            if old['purpose'] != purpose or old['sha256'] != r['sha256'] or old['group'] != r['group']:
                raise ValueError('Development export role/db hash')
            raw = self.zip.read('development/'+bag+'.npz')
            if digest(raw) != old['export_sha256']: raise ValueError('Export payload hash')
            with np.load(io.BytesIO(raw),allow_pickle=False) as a:
                events = a['events'].copy()
                refs = {k:a[k].tolist() for k in ('master','rover')}
            return events,refs
        if purpose != 'development':
            # The original gate forbids train GNSS, and refuses all test IO.
            self.access.pop()
            result = super().load(bag,purpose)
            if self.journal: ev.save(self.journal,self.access)
            return result
        path = self.root/bag/(bag+'_0.db3')
        if digest(path.read_bytes()) != r['sha256']: raise ValueError('DB hash '+bag)
        events = []; refs = {'master':[],'rover':[]}; origin = r['sensor_start_ns']
        with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as con:
            sql = ('SELECT t.name,t.type,m.data FROM messages m JOIN topics t ON t.id=m.topic_id '
                   'WHERE t.name IN ('+','.join('?' for _ in allowed)+') ORDER BY m.timestamp,m.id')
            for topic,typ,raw in con.execute(sql,allowed):
                stamp,values = ev.decode(raw,typ); t = (stamp-origin)/1e9
                if topic in ex.CHANNELS:
                    ch = ex.CHANNELS[topic]; events.append((t,ch,float(values[0])/(15 if ch==0 else 3.6)))
                else:
                    speed = math.hypot(float(values[0]),float(values[1]))
                    if math.isfinite(speed): refs[ex.REFS[topic]].append((t,speed))
        return np.asarray(events,float),refs
