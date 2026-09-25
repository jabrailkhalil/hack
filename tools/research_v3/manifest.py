"""Metadata-only inventory and immutable grouped split; no target values read."""
import hashlib
import json
import sqlite3
import struct
from pathlib import Path

SMOKE = {'30618_0652866c','30618_1551d0a9','30618_27e994fc','30618_e151d6e4',
         '30639_0ab96c59','30639_9c362687','30639_c31df386','30639_e4379d7f'}
SEED = 'tram-v3-20260925'


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1048576), b''): h.update(b)
    return h.hexdigest()


def build(root):
    rows = []
    for path in sorted(Path(root).glob('*/*.db3')):
        with sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True) as con:
            counts = list(con.execute('SELECT t.name,COUNT(m.id),MIN(m.timestamp),MAX(m.timestamp) '
                'FROM topics t LEFT JOIN messages m ON m.topic_id=t.id GROUP BY t.id'))
            sensor_start, sensor_end = None, None
            wire_hash = hashlib.sha256()
            for topic, raw in con.execute("SELECT t.name,m.data FROM messages m JOIN topics t ON t.id=m.topic_id "
                    "WHERE t.name LIKE '/vehicle/%' ORDER BY m.timestamp,m.id"):
                if raw[:2] not in (b'\x00\x00',b'\x00\x01'): raise ValueError('Unexpected CDR header')
                sec, ns = struct.unpack_from('<iI' if raw[1] else '>iI', raw, 4)
                stamp = sec*1000000000+ns
                sensor_start=stamp if sensor_start is None else min(sensor_start,stamp)
                sensor_end=stamp if sensor_end is None else max(sensor_end,stamp)
                # Fingerprint only: do not deserialize measurements or GNSS labels.
                wire_hash.update(topic.encode()+b'\0'+raw[12:])
        times = [(a,b) for _,n,a,b in counts if n]
        rows.append(dict(bag=path.parent.name, vehicle=path.parent.name.split('_')[0],
            sha256=digest(path), bytes=path.stat().st_size,
            start_ns=min(a for a,b in times),end_ns=max(b for a,b in times),
            counts={name:n for name,n,_,_ in counts},sensor_start_ns=sensor_start,
            sensor_end_ns=sensor_end,vehicle_wire_sha256=wire_hash.hexdigest()))
    # Overlapping or adjacent (<60s) recordings of one vehicle are one session.
    # Exact duplicate DBs are also joined. Transitive closure prevents splitting fragments.
    parent = list(range(len(rows)))
    def find(i):
        while parent[i]!=i: parent[i]=parent[parent[i]]; i=parent[i]
        return i
    def union(i,j): parent[find(j)]=find(i)
    for i,a in enumerate(rows):
        for j,b in enumerate(rows[:i]):
            if (a['sha256']==b['sha256'] or a['vehicle_wire_sha256']==b['vehicle_wire_sha256'] or (a['vehicle']==b['vehicle'] and (
                max(a['start_ns'],b['start_ns']) <= min(a['end_ns'],b['end_ns'])+60_000_000_000 or
                max(a['sensor_start_ns'],b['sensor_start_ns']) <= min(a['sensor_end_ns'],b['sensor_end_ns'])+60_000_000_000))):
                union(i,j)
    groups = {}
    for i,r in enumerate(rows): groups.setdefault(find(i),[]).append(r)
    sessions = []
    for group in groups.values():
        names = sorted(r['bag'] for r in group)
        gid=hashlib.sha256('|'.join(names).encode()).hexdigest()[:16]
        dev=bool(SMOKE.intersection(names))
        sessions.append(dict(group=gid,bags=names,vehicle=group[0]['vehicle'],development=dev))
        for r in group: r['group']=gid
    # Stratify only by vehicle, not model errors or target statistics.
    split = {}
    for vehicle in sorted(set(r['vehicle'] for r in rows)):
        eligible = [g for g in sessions if g['vehicle']==vehicle and not g['development']]
        eligible.sort(key=lambda g:hashlib.sha256((SEED+g['group']).encode()).hexdigest())
        n=len(eligible); n_test=max(1,round(n*.2)); n_val=max(1,round(n*.2))
        if n < 3: raise ValueError('Not enough independent sessions for '+vehicle)
        for k,g in enumerate(eligible):
            split[g['group']]='test' if k<n_test else 'validation' if k<n_test+n_val else 'train'
    for r in rows: r['split']=split.get(r['group'],'development')
    return dict(schema_version=1,seed=SEED,grouping='vehicle record/source-time overlap + adjacency 60s + exact DB/wire fingerprint',
                metadata_only=True,records=rows,groups=sessions)


def freeze(root, output):
    data=build(root); text=json.dumps(data,ensure_ascii=False,sort_keys=True,indent=2)+'\n'
    output=Path(output)
    if output.exists() and output.read_text()!=text:
        raise ValueError('Frozen manifest differs; refusing silent resplit')
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(text)
    return data

if __name__=='__main__':
    import argparse,collections
    p=argparse.ArgumentParser();p.add_argument('data');p.add_argument('output');a=p.parse_args()
    d=freeze(a.data,a.output)
    print('bags',len(d['records']),'groups',len(d['groups']),
          collections.Counter((r['vehicle'],r['split']) for r in d['records']))
