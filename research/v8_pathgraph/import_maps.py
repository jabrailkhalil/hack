"""Exact ordered JSON points to legacy route_csv, without invented CRS/start."""
import argparse
import hashlib
import json
from pathlib import Path
from pathgraph import Pathgraph


def run(inputs,output):
    routes=[Pathgraph.load(p) for p in inputs]
    output=Path(output);output.mkdir(parents=True,exist_ok=False);receipt=[]
    for i,(p,r) in enumerate(zip(inputs,routes)):
        target=output/('route_'+str(i)+'.csv');r.write_csv(target)
        receipt.append({'source_name':Path(p).name,'source_sha256':r.source_sha256,
                        'point_count':len(r.points),'length_3d_m':r.length,'first':r.points[0],'last':r.points[-1],
                        'csv':target.name,'csv_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
                        'crs':'UNSPECIFIED_IN_INPUT','initial_s':'NOT_SET','closed':False})
    (output/'MANIFEST.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('maps',nargs='+',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();print(json.dumps(run(a.maps,a.output),ensure_ascii=False,indent=2))
