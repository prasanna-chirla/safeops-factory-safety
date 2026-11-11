from pathlib import Path
import json, sqlite3
import pandas as pd
import streamlit as st
from safety_app.core import analyze, validate, summary

ROOT=Path(__file__).resolve().parent
DB=ROOT/'data'/'safety.db'
st.set_page_config(page_title='SafeOps | Factory Safety Intelligence',page_icon='🛡️',layout='wide')
st.markdown('''<style>.block-container{padding-top:1.5rem}.hero{padding:1.4rem 1.8rem;border-radius:16px;background:linear-gradient(120deg,#10243a,#155e75);color:white;margin-bottom:1rem}.hero h1{margin:0;font-size:2rem}.hero p{margin:.4rem 0 0;color:#c7e7ee}.metric{border:1px solid #e4eaf0;padding:1rem;border-radius:12px}</style>''',unsafe_allow_html=True)
st.markdown('<div class="hero"><h1>🛡️ SafeOps</h1><p>Factory safety intelligence · Trace alarm events to response, incident, and verified action</p></div>',unsafe_allow_html=True)
if not DB.exists():
 st.warning(r'No safety database yet. Generate the quick demo from a terminal: `.\.venv\Scripts\python.exe generate_data.py --demo`, then refresh this page.'); st.stop()
counts=summary(DB)['counts']; findings=analyze(DB); issues=validate(DB)
metrics_path=ROOT/'data'/'exports'/'evaluation_summary.json'
evaluation=json.loads(metrics_path.read_text(encoding='utf-8')) if metrics_path.exists() else None
c1,c2,c3,c4=st.columns(4)
c1.metric('Alarm events',f"{counts['alarmevent']:,}"); c2.metric('Machines',counts['machine']); c3.metric('Incidents',counts['incident']); c4.metric('Data exceptions',len(issues))
st.caption('Synthetic dataset · Fixed seed · Every finding can be traced to its source records.')
tab1,tab2,tab3,tab4=st.tabs(['Safety overview','Trace a machine','Data quality','Data explorer'])
with tab1:
 st.subheader('What needs attention')
 if not findings: st.success('No findings for the current dataset.')
 else:
  df=pd.DataFrame(findings); order={'critical':0,'high':1,'medium':2,'low':3}; df['_rank']=df.priority.map(order).fillna(4); df=df.sort_values(['_rank','count'],ascending=[True,False]).drop(columns='_rank')
  kind=st.multiselect('Filter finding type',sorted(df.finding_type.unique()),default=sorted(df.finding_type.unique()))
  st.dataframe(df[df.finding_type.isin(kind)],use_container_width=True,hide_index=True)
 st.info('Rules: repeated alarm (3+ occurrences per machine/alarm), acknowledgement past its severity SLA, hourly cluster (8+ events), and every high/critical incident with linked state/action evidence.')
 st.subheader('Evaluation against generated ground truth')
 if evaluation:
  m=evaluation['anomaly_detection']; n=evaluation['nuisance_cluster_coverage']; ec1,ec2,ec3,ec4=st.columns(4)
  ec1.metric('Exception precision',f"{m['precision']:.0%}"); ec2.metric('Exception recall',f"{m['recall']:.0%}"); ec3.metric('Exception F1',f"{m['f1']:.0%}"); ec4.metric('Flood cluster recall',f"{n['recall']:.0%}")
  st.caption(evaluation['limitations'])
with tab2:
 conn=sqlite3.connect(DB); machines=pd.read_sql_query('SELECT machine_id,name FROM Machine ORDER BY machine_id',conn); machine=st.selectbox('Choose machine',machines.machine_id.tolist());
 st.subheader(f'Event history · {machine}')
 timeline=pd.read_sql_query('''SELECT e.occurred_at,e.alarm_event_id,d.code,d.severity,s.state,e.interlock_state,k.acknowledged_at,ROUND((julianday(k.acknowledged_at)-julianday(e.occurred_at))*1440,1) ack_minutes,i.incident_id,i.description,a.status action_status,a.verified_at FROM AlarmEvent e JOIN AlarmDefinition d USING(alarm_definition_id) LEFT JOIN MachineStateEvent s USING(state_event_id) LEFT JOIN Acknowledgement k USING(alarm_event_id) LEFT JOIN Incident i USING(alarm_event_id) LEFT JOIN CorrectiveAction a USING(incident_id) WHERE e.machine_id=? ORDER BY e.occurred_at LIMIT 500''',conn,params=(machine,)); conn.close()
 st.dataframe(timeline,use_container_width=True,hide_index=True); st.caption('Showing the first 500 events in timestamp order. An empty incident/action means none was linked to that event.')
with tab3:
 st.subheader('Exceptions and validation')
 if issues: st.dataframe(pd.DataFrame(issues),use_container_width=True,hide_index=True)
 else: st.success('No validation exceptions.')
 st.caption('Known synthetic edge cases are listed in data/exports/ground_truth.json, separate from the findings inputs.')
with tab4:
 conn=sqlite3.connect(DB); table=st.selectbox('Table',['Plant','Machine','SafetyZone','Interlock','AlarmDefinition','OperatorShift','MachineStateEvent','AlarmEvent','Acknowledgement','Incident','CorrectiveAction']); df=pd.read_sql_query(f'SELECT * FROM "{table}" LIMIT 1000',conn); conn.close(); st.dataframe(df,use_container_width=True,hide_index=True); st.caption('Showing up to 1,000 rows. CSV and JSON exports are in data/exports/.')
