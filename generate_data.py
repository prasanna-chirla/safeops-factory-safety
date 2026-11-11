from __future__ import annotations
import argparse, json
from pathlib import Path
from safety_app.core import generate, export, validate, analyze, summary, evaluate

ROOT=Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser(description='Generate and analyze synthetic factory safety events.')
    p.add_argument('--db',default=str(ROOT/'data'/'safety.db'))
    p.add_argument('--out',default=str(ROOT/'data'/'exports'))
    p.add_argument('--seed',type=int,default=20261022)
    p.add_argument('--plants',type=int,default=4); p.add_argument('--machines',type=int,default=60)
    p.add_argument('--definitions',type=int,default=200); p.add_argument('--events',type=int,default=50000)
    p.add_argument('--days',type=int,default=30)
    p.add_argument('--demo',action='store_true',help='Use a small quick demo dataset (2 plants, 12 machines, 40 alarm definitions, 2,000 events).')
    a=p.parse_args()
    if a.demo: a.plants,a.machines,a.definitions,a.events=2,12,40,2000
    db=Path(a.db); out=Path(a.out)
    result=generate(db,a.plants,a.machines,a.definitions,a.events,a.days,a.seed)
    files=export(db,out,result['ground_truth'])
    manifest_path=out/'source_manifest.json'
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    manifest.update({'seed':a.seed,'scale':{'plants':a.plants,'machines':a.machines,'alarm_definitions':a.definitions,'baseline_alarm_events':a.events-1,'total_alarm_events':a.events,'days':a.days}})
    manifest_path.write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    issues=validate(db); findings=analyze(db)
    (out/'validation_summary.json').write_text(json.dumps({'issue_count':len(issues),'issues_by_type':{k:sum(x['issue_type']==k for x in issues) for k in sorted({x['issue_type'] for x in issues})},'issues':issues},indent=2),encoding='utf-8')
    (out/'findings.json').write_text(json.dumps(findings,indent=2),encoding='utf-8')
    evaluation=evaluate(result['ground_truth'],issues,findings)
    (out/'evaluation_summary.json').write_text(json.dumps(evaluation,indent=2),encoding='utf-8')
    report={'seed':a.seed,'database':str(db),'counts':summary(db)['counts'],'findings':len(findings),'validation_issues':len(issues),'source_files_hashed':len(files),'anomaly_f1':evaluation['anomaly_detection']['f1'],'cluster_recall':evaluation['nuisance_cluster_coverage']['recall']}
    (out/'run_summary.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
if __name__=='__main__': main()
