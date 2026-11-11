from __future__ import annotations
import argparse, json, tempfile
from pathlib import Path
from safety_app.core import generate, export

def main():
    p=argparse.ArgumentParser(description='Regenerate twice with the same seed and compare source export checksums.')
    p.add_argument('--seed',type=int,default=20261022); p.add_argument('--plants',type=int,default=4); p.add_argument('--machines',type=int,default=60)
    p.add_argument('--definitions',type=int,default=200); p.add_argument('--events',type=int,default=50000); p.add_argument('--days',type=int,default=30)
    p.add_argument('--demo',action='store_true')
    a=p.parse_args()
    if a.demo: a.plants,a.machines,a.definitions,a.events=2,12,40,2000
    with tempfile.TemporaryDirectory(prefix='safeops-repro-') as tmp:
        root=Path(tmp); runs=[]
        for n in (1,2):
            db=root/f'run{n}.db'; out=root/f'run{n}'
            result=generate(db,a.plants,a.machines,a.definitions,a.events,a.days,a.seed)
            hashes=export(db,out,result['ground_truth'])
            runs.append({'counts':result['counts'],'hashes':{k:v['sha256'] for k,v in hashes.items()}})
        passed=runs[0]==runs[1]
        print(json.dumps({'reproducible':passed,'seed':a.seed,'counts_match':runs[0]['counts']==runs[1]['counts'],'source_export_checksums_match':runs[0]['hashes']==runs[1]['hashes']},indent=2))
        if not passed: raise SystemExit(1)
if __name__=='__main__': main()
