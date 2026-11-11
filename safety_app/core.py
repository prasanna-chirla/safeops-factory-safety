from __future__ import annotations

import csv
import hashlib
import json
import random
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SEED = 20261022
START = datetime(2026, 10, 1, tzinfo=timezone.utc)
SCHEMA = '''
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS Plant(plant_id TEXT PRIMARY KEY,name TEXT NOT NULL,region TEXT NOT NULL,lifecycle_state TEXT NOT NULL CHECK(lifecycle_state IN ('active','inactive')));
CREATE TABLE IF NOT EXISTS Machine(machine_id TEXT PRIMARY KEY,plant_id TEXT NOT NULL REFERENCES Plant(plant_id),name TEXT NOT NULL,machine_type TEXT NOT NULL,commissioned_at TEXT NOT NULL,lifecycle_state TEXT NOT NULL CHECK(lifecycle_state IN ('active','maintenance','retired')));
CREATE TABLE IF NOT EXISTS SafetyZone(safety_zone_id TEXT PRIMARY KEY,plant_id TEXT NOT NULL REFERENCES Plant(plant_id),name TEXT NOT NULL,hazard_level TEXT NOT NULL CHECK(hazard_level IN ('low','medium','high','critical')));
CREATE TABLE IF NOT EXISTS MachineSafetyZone(machine_id TEXT NOT NULL REFERENCES Machine(machine_id),safety_zone_id TEXT NOT NULL REFERENCES SafetyZone(safety_zone_id),effective_from TEXT NOT NULL,effective_to TEXT,PRIMARY KEY(machine_id,safety_zone_id,effective_from));
CREATE TABLE IF NOT EXISTS Interlock(interlock_id TEXT PRIMARY KEY,plant_id TEXT NOT NULL REFERENCES Plant(plant_id),name TEXT NOT NULL,interlock_type TEXT NOT NULL,safe_state TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS MachineInterlock(machine_id TEXT NOT NULL REFERENCES Machine(machine_id),interlock_id TEXT NOT NULL REFERENCES Interlock(interlock_id),effective_from TEXT NOT NULL,effective_to TEXT,PRIMARY KEY(machine_id,interlock_id,effective_from));
CREATE TABLE IF NOT EXISTS AlarmDefinition(alarm_definition_id TEXT PRIMARY KEY,machine_id TEXT NOT NULL REFERENCES Machine(machine_id),code TEXT NOT NULL,severity TEXT NOT NULL CHECK(severity IN ('low','medium','high','critical')),ack_sla_minutes INTEGER NOT NULL CHECK(ack_sla_minutes>0),nuisance_candidate INTEGER NOT NULL CHECK(nuisance_candidate IN (0,1)),UNIQUE(machine_id,code));
CREATE TABLE IF NOT EXISTS OperatorShift(shift_id TEXT PRIMARY KEY,plant_id TEXT NOT NULL REFERENCES Plant(plant_id),operator_name TEXT NOT NULL,starts_at TEXT NOT NULL,ends_at TEXT NOT NULL,shift_name TEXT NOT NULL CHECK(shift_name IN ('day','evening','night')),CHECK(ends_at>starts_at));
CREATE TABLE IF NOT EXISTS MachineStateEvent(state_event_id TEXT PRIMARY KEY,machine_id TEXT NOT NULL REFERENCES Machine(machine_id),occurred_at TEXT NOT NULL,state TEXT NOT NULL CHECK(state IN ('running','idle','stopped','fault','maintenance')));
CREATE TABLE IF NOT EXISTS AlarmEvent(alarm_event_id TEXT PRIMARY KEY,machine_id TEXT NOT NULL REFERENCES Machine(machine_id),alarm_definition_id TEXT NOT NULL REFERENCES AlarmDefinition(alarm_definition_id),occurred_at TEXT NOT NULL,state_event_id TEXT REFERENCES MachineStateEvent(state_event_id),shift_id TEXT REFERENCES OperatorShift(shift_id),interlock_state TEXT NOT NULL CHECK(interlock_state IN ('safe','unsafe','unknown')),source_event_key TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS Acknowledgement(acknowledgement_id TEXT PRIMARY KEY,alarm_event_id TEXT NOT NULL UNIQUE REFERENCES AlarmEvent(alarm_event_id),acknowledged_at TEXT NOT NULL,operator_name TEXT NOT NULL,status TEXT NOT NULL CHECK(status IN ('acknowledged','unacknowledged')));
CREATE TABLE IF NOT EXISTS Incident(incident_id TEXT PRIMARY KEY,plant_id TEXT NOT NULL REFERENCES Plant(plant_id),machine_id TEXT NOT NULL REFERENCES Machine(machine_id),alarm_event_id TEXT REFERENCES AlarmEvent(alarm_event_id),created_at TEXT NOT NULL,severity TEXT NOT NULL CHECK(severity IN ('low','medium','high','critical')),description TEXT NOT NULL,lifecycle_state TEXT NOT NULL CHECK(lifecycle_state IN ('open','investigating','resolved')));
CREATE TABLE IF NOT EXISTS CorrectiveAction(action_id TEXT PRIMARY KEY,incident_id TEXT NOT NULL REFERENCES Incident(incident_id),description TEXT NOT NULL,opened_at TEXT NOT NULL,closed_at TEXT,verified_at TEXT,status TEXT NOT NULL CHECK(status IN ('open','in_progress','closed','closed_unverified')));
CREATE INDEX IF NOT EXISTS idx_alarm_machine_time ON AlarmEvent(machine_id,occurred_at);
CREATE INDEX IF NOT EXISTS idx_ack_event ON Acknowledgement(alarm_event_id);
CREATE INDEX IF NOT EXISTS idx_incident_machine ON Incident(machine_id,created_at);
'''

TABLES = ['Plant','Machine','SafetyZone','MachineSafetyZone','Interlock','MachineInterlock','AlarmDefinition','OperatorShift','MachineStateEvent','AlarmEvent','Acknowledgement','Incident','CorrectiveAction']

def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')

def make_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists(): path.unlink()
    conn=sqlite3.connect(path)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.executescript(SCHEMA)
    return conn

def generate(db_path: Path, plants_n: int=4, machines_n: int=60, definitions_n: int=200, events_n: int=50_000, days: int=30, seed: int=SEED) -> dict[str, Any]:
    """Generate a reproducible synthetic safety history with exactly events_n alarm rows including one replay."""
    if min(plants_n,machines_n,definitions_n,events_n,days)<1: raise ValueError('All scale values must be positive.')
    if events_n < 65: raise ValueError('At least 65 total alarm events are needed for all labelled edge cases and two flood clusters.')
    baseline_events_n=events_n-1  # reserve the final requested row for the labelled replay duplicate
    if definitions_n < machines_n: raise ValueError('Alarm definitions must be at least equal to machines so every machine has a definition.')
    rng=random.Random(seed); conn=make_db(db_path); cur=conn.cursor()
    plants=[]
    for i in range(1,plants_n+1):
        pid=f'PLT-{i:03d}'; plants.append(pid); cur.execute('INSERT INTO Plant VALUES(?,?,?,?)',(pid,f'Plant {i}',['North','South','East','West'][(i-1)%4],'active'))
    zones=[]; interlocks=[]; machines=[]
    for i in range(1,machines_n+1):
        mid=f'MCH-{i:03d}'; pid=plants[(i-1)%plants_n]; machines.append((mid,pid))
        cur.execute('INSERT INTO Machine VALUES(?,?,?,?,?,?)',(mid,pid,f'Machine {i:03d}',['press','conveyor','robot','cutter','filler'][(i-1)%5],iso(START-timedelta(days=365)), 'active'))
        # Two machines in the same plant share two zones/interlocks: the bridges exercise N:M relationships.
        relation_group=(i-1)//(plants_n*2)
        for rel_offset in (1,2):
            rel_number=relation_group*2+rel_offset
            zid=f'SAFE-{pid}-{rel_number:03d}'
            if zid not in zones:
                zones.append(zid); cur.execute('INSERT INTO SafetyZone VALUES(?,?,?,?)',(zid,pid,f'Safety Zone {rel_number:03d}',rng.choice(['medium','high','critical'])))
            cur.execute('INSERT INTO MachineSafetyZone VALUES(?,?,?,NULL)',(mid,zid,iso(START-timedelta(days=365))))
            iid=f'INT-{pid}-{rel_number:03d}'
            if iid not in interlocks:
                interlocks.append(iid); cur.execute('INSERT INTO Interlock VALUES(?,?,?,?,?)',(iid,pid,f'Guard interlock {rel_number:03d}','guard_door','closed'))
            cur.execute('INSERT INTO MachineInterlock VALUES(?,?,?,NULL)',(mid,iid,iso(START-timedelta(days=365))))
    alarm_defs=[]; severity_weights=[('low',.40),('medium',.32),('high',.20),('critical',.08)]
    for i in range(1,definitions_n+1):
        mid,_=machines[(i-1)%len(machines)]; aid=f'ALD-{mid}-{((i-1)//len(machines))+1:03d}'
        sev=rng.choices([x[0] for x in severity_weights],weights=[x[1] for x in severity_weights])[0]
        alarm_defs.append((aid,mid,sev,15 if sev in ('critical','high') else 60, int(i%4==0)))
        cur.execute('INSERT INTO AlarmDefinition VALUES(?,?,?,?,?,?)',(aid,mid,f'AL-{i:04d}',sev,15 if sev in ('critical','high') else 60,int(i%4==0)))
    # Shift coverage is generated for each plant and day; records are UTC and non-overlapping.
    shifts=[]; shift_names=['day','evening','night']; operators=['Asha','Ravi','Meera','Kiran','Noah','Ira']
    for pidx,pid in enumerate(plants):
        for day in range(days):
            for si,sname in enumerate(shift_names):
                st=START+timedelta(days=day,hours=si*8); end=st+timedelta(hours=8)
                sid=f'SHF-{pid}-{day+1:03d}-{si+1}'
                shifts.append((sid,pid,operators[(pidx+day+si)%len(operators)],st,end,sname))
                cur.execute('INSERT INTO OperatorShift VALUES(?,?,?,?,?,?)',(sid,pid,operators[(pidx+day+si)%len(operators)],iso(st),iso(end),sname))
    byplant=defaultdict(list)
    for x in shifts: byplant[x[1]].append(x)
    # A small set of machines has a recurring unsafe condition for clear, explainable findings.
    recurrence_machines={m[0] for m in machines[:max(1,min(5,len(machines)))]}
    recurrence_defs={m: next(a for a in alarm_defs if a[1]==m and a[2] in ('high','critical')) if any(a[1]==m and a[2] in ('high','critical') for a in alarm_defs) else next(a for a in alarm_defs if a[1]==m) for m in recurrence_machines}
    states=['running','idle','stopped','fault','maintenance']; event_rows=[]; state_rows=[]; ack_rows=[]; incident_rows=[]; action_rows=[]; ground=[]; machine_counts=Counter()
    duration=timedelta(days=days); t0=START
    # Edge-case labels live only in ground truth; analysis rules infer cases from source event fields.
    edge_ix={0:'ACK_BEFORE_ALARM',1:'IMPOSSIBLE_INTERLOCK_STATE'}
    nuisance_alarm=next((a for a in alarm_defs if a[4]==1),alarm_defs[0])
    flood_machine=next(m for m in machines if m[0]==nuisance_alarm[1])
    def flood_start_at(fraction: float) -> int:
        candidate=max(20,int(baseline_events_n*fraction))
        while candidate+12<baseline_events_n:
            candidate_time=t0+duration*(candidate/baseline_events_n)
            if candidate_time.minute<=50: return candidate  # all 12 events stay in one hour window
            candidate+=1
        raise ValueError('Could not place a flood cluster inside the event window.')
    flood_starts=[flood_start_at(0.10),flood_start_at(0.50)]
    flood_lookup={start+offset:(start,offset) for start in flood_starts for offset in range(12) if start+offset<baseline_events_n}
    edge_event_ids={}; edge_incident_ids={}; edge_action_ids={}
    for n in range(baseline_events_n):
        machine,pid=machines[n%len(machines)]
        # Spread baseline events over the interval; deterministic bursts model nuisance/flood clusters.
        occurred=t0+duration*(n/baseline_events_n)+timedelta(seconds=rng.randrange(0,30))
        if n in flood_lookup:
            burst_start,burst_offset=flood_lookup[n]
            machine,pid=flood_machine
            ad=nuisance_alarm
            occurred=t0+duration*(burst_start/baseline_events_n)+timedelta(seconds=burst_offset*45)
        elif machine in recurrence_machines and (n//len(machines))%max(1,(baseline_events_n//len(machines))//18)==0:
            ad=recurrence_defs[machine]
        else:
            options=[a for a in alarm_defs if a[1]==machine]
            if not options: options=[a for a in alarm_defs if a[1]==machines[0][0]]
            ad=rng.choice(options)
        aid,_,sev,sla,nuisance=ad
        state=rng.choices(states,weights=[.68,.12,.08,.08,.04])[0]
        machine_counts[machine]+=1; sid=f'STE-{n+1:07d}'; eventid=f'ALM-{machine}-{machine_counts[machine]:06d}'
        if n in (0,1): edge_event_ids[n]=eventid
        cur.execute('INSERT INTO MachineStateEvent VALUES(?,?,?,?)',(sid,machine,iso(occurred-timedelta(minutes=rng.randint(1,5))),state))
        plant_shifts=byplant[pid]; sh=next((s for s in plant_shifts if s[4]>occurred and s[3]<=occurred),plant_shifts[min(len(plant_shifts)-1,max(0,int((occurred-START).total_seconds()//28800)))])
        interlock='safe'
        cur.execute('INSERT INTO AlarmEvent VALUES(?,?,?,?,?,?,?,?)',(eventid,machine,aid,iso(occurred),sid,sh[0],interlock,eventid))
        ack_delay=rng.choices([2,8,25,90,240],[.38,.30,.16,.10,.06])[0]
        if n==5: ack_delay=sla       # exactly at the allowed SLA boundary
        if n==6: ack_delay=sla+1     # one minute beyond SLA
        ack_time=occurred+timedelta(minutes=ack_delay)
        ackid=f'ACK-{eventid}-01'; cur.execute('INSERT INTO Acknowledgement VALUES(?,?,?,?,?)',(ackid,eventid,iso(ack_time),sh[2],'acknowledged'))
        if n==5: ground.append({'case_id':'GT-BND-001','record_id':eventid,'issue_type':'ACK_AT_SLA_THRESHOLD','expected_detection':False,'rule':'Exactly-at-SLA acknowledgement is on time.'})
        if n==6: ground.append({'case_id':'GT-BND-002','record_id':eventid,'issue_type':'ACK_JUST_OVER_SLA','expected_detection':True,'rule':'Acknowledgement one minute beyond SLA must be flagged.'})
        if n in flood_lookup and flood_lookup[n][1]==0:
            ground.append({'case_id':'GT-FLOOD-'+str(flood_starts.index(flood_lookup[n][0])+1).zfill(3),'record_id':eventid,'issue_type':'ALARM_FLOOD_NUISANCE_CLUSTER','machine_id':machine,'alarm_definition_id':aid,'window_hour':iso(occurred)[:13],'expected_detection':True,'rule':'12 same nuisance alarm events occur within 9 minutes.'})
        if n in (2,4) or (sev in ('high','critical') and (interlock=='unsafe' or state in ('fault','stopped'))) or (machine in recurrence_machines and (n//len(machines))%max(1,(baseline_events_n//len(machines))//18)==0):
            incid=f'INC-2026-{len(incident_rows)+1:06d}'; created=occurred+timedelta(minutes=1)
            cur.execute('INSERT INTO Incident VALUES(?,?,?,?,?,?,?,?)',(incid,pid,machine,eventid,iso(created),sev,f'{sev.title()} safety condition associated with {aid}','investigating'))
            opened=created+timedelta(minutes=5); closed=opened+timedelta(hours=2); verified=closed+timedelta(minutes=10)
            status='closed'; itype=None
            actid=f'ACT-{incid}-01'; cur.execute('INSERT INTO CorrectiveAction VALUES(?,?,?,?,?,?,?)',(actid,incid,'Inspect guard, repair sensor, and verify safe stop',iso(opened),iso(closed),iso(verified) if verified else None,status))
            if status=='closed' and verified: cur.execute("UPDATE Incident SET lifecycle_state='resolved' WHERE incident_id=?",(incid,))
            incident_rows.append(incid)
            if n in (2,4): edge_incident_ids[n]=incid; edge_action_ids[n]=actid
    # Valid baseline is complete. Now inject labelled exceptions as a separate deterministic pass.
    ack_alarm=edge_event_ids[0]
    ack_occurred=cur.execute('SELECT occurred_at FROM AlarmEvent WHERE alarm_event_id=?',(ack_alarm,)).fetchone()[0]
    early=iso(datetime.fromisoformat(ack_occurred.replace('Z','+00:00'))-timedelta(minutes=2))
    cur.execute('UPDATE Acknowledgement SET acknowledged_at=? WHERE alarm_event_id=?',(early,ack_alarm))
    ground.append({'case_id':'GT-001','record_id':ack_alarm,'issue_type':'ACK_BEFORE_ALARM','expected_detection':True,'rule':'Acknowledgement timestamp precedes alarm timestamp.'})
    impossible_alarm=edge_event_ids[1]
    state_id,=cur.execute('SELECT state_event_id FROM AlarmEvent WHERE alarm_event_id=?',(impossible_alarm,)).fetchone()
    cur.execute("UPDATE MachineStateEvent SET state='running' WHERE state_event_id=?",(state_id,))
    cur.execute("UPDATE AlarmEvent SET interlock_state='unsafe' WHERE alarm_event_id=?",(impossible_alarm,))
    ground.append({'case_id':'GT-002','record_id':impossible_alarm,'issue_type':'IMPOSSIBLE_INTERLOCK_STATE','expected_detection':True,'rule':'Machine is running while the safety interlock is unsafe.'})
    missing_incident=edge_incident_ids[2]
    cur.execute("UPDATE Incident SET alarm_event_id=NULL WHERE incident_id=?",(missing_incident,))
    ground.append({'case_id':'GT-003','record_id':missing_incident,'issue_type':'INCIDENT_MISSING_TRIGGER_CONTEXT','expected_detection':True,'rule':'Incident has no triggering alarm context.'})
    unverified_incident=edge_incident_ids[4]; unverified_action=edge_action_ids[4]
    cur.execute("UPDATE CorrectiveAction SET verified_at=NULL,status='closed_unverified' WHERE action_id=?",(unverified_action,))
    cur.execute("UPDATE Incident SET lifecycle_state='investigating' WHERE incident_id=?",(unverified_incident,))
    ground.append({'case_id':'GT-005','record_id':unverified_action,'issue_type':'ACTION_CLOSED_WITHOUT_VERIFICATION','expected_detection':True,'rule':'Closed corrective action has no verification timestamp.'})
    # Replay is also injected only after valid baseline rows have been written.
    # Flood/replay anomaly is a separate duplicate source key pair, preserving the original valid alarm.
    if events_n>=65:
        replay_source_id=next(g['record_id'] for g in ground if g['issue_type']=='ALARM_FLOOD_NUISANCE_CLUSTER')
        src=cur.execute('SELECT alarm_event_id,machine_id,alarm_definition_id,occurred_at,state_event_id,shift_id,interlock_state FROM AlarmEvent WHERE alarm_event_id=?',(replay_source_id,)).fetchone()
        oldid,mid,aid,at,stateid,shiftid,istate=src
        replayid=f'ALM-{mid}-{machine_counts[mid]+1:06d}'
        cur.execute('INSERT INTO AlarmEvent VALUES(?,?,?,?,?,?,?,?)',(replayid,mid,aid,at,stateid,shiftid,istate,oldid))
        cur.execute('INSERT INTO Acknowledgement VALUES(?,?,?,?,?)',(f'ACK-{replayid}-01',replayid,at,'Asha','acknowledged'))
        ground.append({'case_id':'GT-004','record_id':replayid,'issue_type':'ALARM_FLOOD_REPLAY_DUPLICATE','expected_detection':True,'rule':'Repeated source_event_key identifies replay duplicate.'})
    conn.commit()
    counts={t:cur.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in TABLES}
    conn.close()
    return {'seed':seed,'days':days,'counts':counts,'ground_truth':ground,'database':str(db_path)}

def validate(db_path: Path) -> list[dict[str,str]]:
    c=sqlite3.connect(db_path); c.row_factory=sqlite3.Row; issues=[]
    primary_keys=[
      ('Plant','plant_id','plant_id','plant_id'),
      ('Machine','machine_id','machine_id','machine_id'),
      ('SafetyZone','safety_zone_id','safety_zone_id','safety_zone_id'),
      ('MachineSafetyZone','machine_id,safety_zone_id,effective_from',"machine_id || '|' || safety_zone_id || '|' || effective_from",'machine_id,safety_zone_id,effective_from'),
      ('Interlock','interlock_id','interlock_id','interlock_id'),
      ('MachineInterlock','machine_id,interlock_id,effective_from',"machine_id || '|' || interlock_id || '|' || effective_from",'machine_id,interlock_id,effective_from'),
      ('AlarmDefinition','alarm_definition_id','alarm_definition_id','alarm_definition_id'),
      ('OperatorShift','shift_id','shift_id','shift_id'),
      ('MachineStateEvent','state_event_id','state_event_id','state_event_id'),
      ('AlarmEvent','alarm_event_id','alarm_event_id','alarm_event_id'),
      ('Acknowledgement','acknowledgement_id','acknowledgement_id','acknowledgement_id'),
      ('Incident','incident_id','incident_id','incident_id'),
      ('CorrectiveAction','action_id','action_id','action_id'),
    ]
    for table,group_by,record_id,columns in primary_keys:
        duplicates=c.execute(f'SELECT {record_id} AS record_id,COUNT(*) n FROM {table} GROUP BY {group_by} HAVING COUNT(*)>1').fetchall()
        for row in duplicates: issues.append({'severity':'error','issue_type':'DUPLICATE_PRIMARY_KEY','record_id':str(row['record_id']),'detail':f'{table} key appears {row["n"]} times'})
    for row in c.execute('PRAGMA foreign_key_check'):
        issues.append({'severity':'error','issue_type':'FOREIGN_KEY','record_id':str(row[1]),'detail':f'Invalid reference in {row[0]}'})

    # Validate every timestamp column as an ISO-8601 UTC value before relying on string ordering.
    timestamp_fields=[
      ('Machine','machine_id','machine_id','commissioned_at'),
      ('MachineSafetyZone','machine_id || \'|\' || safety_zone_id || \'|\' || effective_from','machine_id,safety_zone_id,effective_from','effective_from'),
      ('MachineSafetyZone','machine_id || \'|\' || safety_zone_id || \'|\' || effective_from','machine_id,safety_zone_id,effective_from','effective_to'),
      ('MachineInterlock','machine_id || \'|\' || interlock_id || \'|\' || effective_from','machine_id,interlock_id,effective_from','effective_from'),
      ('MachineInterlock','machine_id || \'|\' || interlock_id || \'|\' || effective_from','machine_id,interlock_id,effective_from','effective_to'),
      ('OperatorShift','shift_id','shift_id','starts_at'),('OperatorShift','shift_id','shift_id','ends_at'),
      ('MachineStateEvent','state_event_id','state_event_id','occurred_at'),
      ('AlarmEvent','alarm_event_id','alarm_event_id','occurred_at'),
      ('Acknowledgement','acknowledgement_id','acknowledgement_id','acknowledged_at'),
      ('Incident','incident_id','incident_id','created_at'),
      ('CorrectiveAction','action_id','action_id','opened_at'),
      ('CorrectiveAction','action_id','action_id','closed_at'),
      ('CorrectiveAction','action_id','action_id','verified_at'),
    ]
    for table,record_expr,_,column in timestamp_fields:
        for row in c.execute(f'SELECT {record_expr} AS record_id,{column} AS value FROM {table} WHERE {column} IS NOT NULL'):
            try:
                parsed=datetime.fromisoformat(str(row['value']).replace('Z','+00:00'))
                if parsed.tzinfo is None or parsed.utcoffset()!=timedelta(0): raise ValueError('timestamp is not UTC')
            except (TypeError,ValueError):
                issues.append({'severity':'error','issue_type':'INVALID_TIMESTAMP','record_id':str(row['record_id']),'detail':f'{table}.{column} must be an ISO-8601 UTC timestamp.'})

    relational_checks=[
      ("SELECT e.alarm_event_id FROM AlarmEvent e JOIN AlarmDefinition d USING(alarm_definition_id) WHERE e.machine_id<>d.machine_id",'ALARM_MACHINE_MISMATCH','Alarm definition belongs to a different machine.'),
      ("SELECT e.alarm_event_id FROM AlarmEvent e JOIN MachineStateEvent s USING(state_event_id) WHERE e.machine_id<>s.machine_id OR s.occurred_at>e.occurred_at",'STATE_LINK_OR_ORDER','Alarm state link is for another machine or occurs after the alarm.'),
      ("SELECT e.alarm_event_id FROM AlarmEvent e JOIN OperatorShift o USING(shift_id) JOIN Machine m USING(machine_id) WHERE o.plant_id<>m.plant_id OR e.occurred_at<o.starts_at OR e.occurred_at>=o.ends_at",'SHIFT_LINK_OR_ORDER','Event shift is for another plant or outside the shift window.'),
      ("SELECT i.incident_id FROM Incident i JOIN Machine m USING(machine_id) WHERE i.plant_id<>m.plant_id",'INCIDENT_PLANT_MISMATCH','Incident plant does not match its machine plant.'),
      ("SELECT i.incident_id FROM Incident i JOIN AlarmEvent e USING(alarm_event_id) WHERE i.machine_id<>e.machine_id",'INCIDENT_MACHINE_MISMATCH','Incident and triggering alarm refer to different machines.'),
      ("SELECT i.incident_id FROM Incident i JOIN AlarmEvent e USING(alarm_event_id) WHERE i.created_at<e.occurred_at",'INCIDENT_BEFORE_TRIGGER','Incident was created before its triggering alarm.'),
      ("SELECT i.incident_id FROM Incident i JOIN AlarmEvent e USING(alarm_event_id) JOIN AlarmDefinition d USING(alarm_definition_id) WHERE i.severity<>d.severity",'INCIDENT_SEVERITY_MISMATCH','Incident severity does not match its triggering alarm definition.'),
      ("SELECT z.machine_id FROM MachineSafetyZone z JOIN Machine m USING(machine_id) JOIN SafetyZone s USING(safety_zone_id) WHERE m.plant_id<>s.plant_id",'ZONE_PLANT_MISMATCH','Machine and safety zone belong to different plants.'),
      ("SELECT x.machine_id FROM MachineInterlock x JOIN Machine m USING(machine_id) JOIN Interlock i USING(interlock_id) WHERE m.plant_id<>i.plant_id",'INTERLOCK_PLANT_MISMATCH','Machine and interlock belong to different plants.'),
      ("SELECT machine_id || '|' || safety_zone_id || '|' || effective_from FROM MachineSafetyZone WHERE effective_to IS NOT NULL AND effective_to<=effective_from",'ZONE_ASSIGNMENT_DATE_ORDER','Safety-zone assignment ends at or before it starts.'),
      ("SELECT machine_id || '|' || interlock_id || '|' || effective_from FROM MachineInterlock WHERE effective_to IS NOT NULL AND effective_to<=effective_from",'INTERLOCK_ASSIGNMENT_DATE_ORDER','Interlock assignment ends at or before it starts.'),
      ("SELECT a.shift_id || ' / ' || b.shift_id FROM OperatorShift a JOIN OperatorShift b ON a.plant_id=b.plant_id AND a.shift_id<b.shift_id AND a.starts_at<b.ends_at AND b.starts_at<a.ends_at",'OVERLAPPING_OPERATOR_SHIFTS','Two operator shifts overlap within the same plant.'),
    ]
    for sql,kind,msg in relational_checks:
        for r in c.execute(sql): issues.append({'severity':'error','issue_type':kind,'record_id':str(r[0]),'detail':msg})
    ack_counts=c.execute("SELECT e.alarm_event_id,COUNT(a.acknowledgement_id) n FROM AlarmEvent e LEFT JOIN Acknowledgement a USING(alarm_event_id) GROUP BY e.alarm_event_id HAVING n<>1").fetchall()
    for r in ack_counts: issues.append({'severity':'error','issue_type':'ACK_RECONCILIATION','record_id':r['alarm_event_id'],'detail':f'Expected exactly one acknowledgement, found {r["n"]}.'})
    checks=[
      ("SELECT a.alarm_event_id FROM AlarmEvent a JOIN Acknowledgement k USING(alarm_event_id) WHERE k.acknowledged_at<a.occurred_at",'ACK_BEFORE_ALARM','Acknowledgement timestamp precedes its alarm.'),
      ("SELECT e.alarm_event_id FROM AlarmEvent e JOIN MachineStateEvent s USING(state_event_id) WHERE e.interlock_state='unsafe' AND s.state='running'",'IMPOSSIBLE_INTERLOCK_STATE','Running machine has an unsafe interlock state.'),
      ("SELECT incident_id FROM Incident WHERE alarm_event_id IS NULL",'INCIDENT_MISSING_TRIGGER_CONTEXT','Incident has no triggering alarm context.'),
      ("SELECT e.alarm_event_id FROM AlarmEvent e WHERE e.alarm_event_id<>e.source_event_key AND EXISTS (SELECT 1 FROM AlarmEvent prior WHERE prior.alarm_event_id=e.source_event_key)",'ALARM_FLOOD_REPLAY_DUPLICATE','Source event key refers to an already-seen alarm event.'),
      ("SELECT action_id FROM CorrectiveAction WHERE closed_at IS NOT NULL AND verified_at IS NULL",'ACTION_CLOSED_WITHOUT_VERIFICATION','Closed action has no verification timestamp.'),
    ]
    for sql,kind,msg in checks:
        for row in c.execute(sql):
            rid=str(row[0]); issues.append({'severity':'warning','issue_type':kind,'record_id':rid,'detail':msg})
    for r in c.execute("SELECT i.incident_id FROM Incident i WHERE i.lifecycle_state='resolved' AND NOT EXISTS (SELECT 1 FROM CorrectiveAction a WHERE a.incident_id=i.incident_id AND a.closed_at IS NOT NULL AND a.verified_at IS NOT NULL)"):
        issues.append({'severity':'error','issue_type':'INCIDENT_RESOLVED_WITHOUT_VERIFIED_ACTION','record_id':r['incident_id'],'detail':'Resolved incident has no closed, verified corrective action.'})
    missing_ack=c.execute("SELECT e.alarm_event_id FROM AlarmEvent e LEFT JOIN Acknowledgement a USING(alarm_event_id) WHERE a.alarm_event_id IS NULL").fetchall()
    for r in missing_ack: issues.append({'severity':'error','issue_type':'MISSING_ACKNOWLEDGEMENT','record_id':r[0],'detail':'Alarm event has no acknowledgement record.'})
    # Timeline and lifecycle rules for incidents and actions.
    for r in c.execute("SELECT a.action_id,a.opened_at,i.created_at,a.closed_at,a.verified_at,a.status FROM CorrectiveAction a JOIN Incident i USING(incident_id)"):
        if r['opened_at']<r['created_at']: issues.append({'severity':'error','issue_type':'ACTION_BEFORE_INCIDENT','record_id':r['action_id'],'detail':'Action opened before its incident.'})
        if r['closed_at'] and r['closed_at']<r['opened_at']: issues.append({'severity':'error','issue_type':'ACTION_DATE_ORDER','record_id':r['action_id'],'detail':'Action closed before it opened.'})
        if r['verified_at'] and not r['closed_at']: issues.append({'severity':'error','issue_type':'VERIFICATION_WITHOUT_CLOSURE','record_id':r['action_id'],'detail':'Action is verified without a closure timestamp.'})
        if r['verified_at'] and r['closed_at'] and r['verified_at']<r['closed_at']: issues.append({'severity':'error','issue_type':'VERIFICATION_DATE_ORDER','record_id':r['action_id'],'detail':'Verification precedes closure.'})
        invalid_status=(r['status']=='closed' and (not r['closed_at'] or not r['verified_at'])) or (r['status']=='closed_unverified' and (not r['closed_at'] or r['verified_at'])) or (r['status'] in ('open','in_progress') and (r['closed_at'] or r['verified_at']))
        if invalid_status: issues.append({'severity':'error','issue_type':'ACTION_STATUS_TIMESTAMP_MISMATCH','record_id':r['action_id'],'detail':'Action status does not match its close and verification timestamps.'})
    c.close(); return issues

def analyze(db_path: Path) -> list[dict[str,Any]]:
    c=sqlite3.connect(db_path); c.row_factory=sqlite3.Row; findings=[]
    recurring=c.execute('''SELECT e.machine_id, e.alarm_definition_id, COUNT(DISTINCT e.source_event_key) n, MIN(e.occurred_at) first_seen, MAX(e.occurred_at) last_seen, SUM(CASE WHEN d.severity IN ('high','critical') THEN 1 ELSE 0 END) severe
      FROM AlarmEvent e JOIN AlarmDefinition d USING(alarm_definition_id) GROUP BY e.machine_id,e.alarm_definition_id HAVING COUNT(DISTINCT e.source_event_key)>=3 ORDER BY severe DESC,n DESC LIMIT 100''').fetchall()
    for r in recurring:
        findings.append({'finding_type':'Repeated alarm','priority':'high' if r['severe'] else 'medium','machine_id':r['machine_id'],'alarm_definition_id':r['alarm_definition_id'],'count':r['n'],'first_seen':r['first_seen'],'last_seen':r['last_seen'],'summary':f"{r['n']} occurrences of {r['alarm_definition_id']} on {r['machine_id']} ({r['severe']} high/critical)."})
    delays=c.execute('''SELECT e.machine_id,e.alarm_event_id,e.alarm_definition_id,d.severity,e.occurred_at,k.acknowledged_at,d.ack_sla_minutes,
      (julianday(k.acknowledged_at)-julianday(e.occurred_at))*1440 delay_min FROM AlarmEvent e JOIN AlarmDefinition d USING(alarm_definition_id) JOIN Acknowledgement k USING(alarm_event_id)
      WHERE delay_min>d.ack_sla_minutes+0.01 ORDER BY delay_min DESC''').fetchall()
    for r in delays: findings.append({'finding_type':'Late acknowledgement','priority':'critical' if r['severity']=='critical' else 'high','machine_id':r['machine_id'],'alarm_definition_id':r['alarm_definition_id'],'alarm_event_id':r['alarm_event_id'],'count':1,'first_seen':r['occurred_at'],'last_seen':r['acknowledged_at'],'summary':f"{r['severity']} alarm acknowledged after {r['delay_min']:.0f} min (SLA {r['ack_sla_minutes']} min)."})
    floods=c.execute('''SELECT machine_id,alarm_definition_id,COUNT(DISTINCT source_event_key) n,MIN(occurred_at) first_seen,MAX(occurred_at) last_seen FROM AlarmEvent GROUP BY machine_id,alarm_definition_id,strftime('%Y-%m-%dT%H',occurred_at) HAVING n>=8 ORDER BY n DESC LIMIT 100''').fetchall()
    for r in floods: findings.append({'finding_type':'Alarm flood / nuisance cluster','priority':'medium','machine_id':r['machine_id'],'alarm_definition_id':r['alarm_definition_id'],'count':r['n'],'first_seen':r['first_seen'],'last_seen':r['last_seen'],'summary':f"{r['n']} events for {r['alarm_definition_id']} in one hour; review nuisance potential."})
    risks=c.execute('''SELECT i.incident_id,i.machine_id,i.severity,i.created_at,i.description,e.alarm_event_id,e.alarm_definition_id,s.state,e.interlock_state,
      (SELECT a.status FROM CorrectiveAction a WHERE a.incident_id=i.incident_id ORDER BY a.opened_at DESC,a.action_id DESC LIMIT 1) AS action_status,
      (SELECT a.verified_at FROM CorrectiveAction a WHERE a.incident_id=i.incident_id ORDER BY a.opened_at DESC,a.action_id DESC LIMIT 1) AS verified_at
      FROM Incident i LEFT JOIN AlarmEvent e USING(alarm_event_id) LEFT JOIN MachineStateEvent s USING(state_event_id)
      WHERE i.severity IN ('high','critical') ORDER BY i.created_at DESC LIMIT 100''').fetchall()
    for r in risks:
        findings.append({'finding_type':'High-severity incident','priority':r['severity'],'machine_id':r['machine_id'],'alarm_definition_id':r['alarm_definition_id'],'incident_id':r['incident_id'],'alarm_event_id':r['alarm_event_id'],'count':1,'first_seen':r['created_at'],'last_seen':r['created_at'],'summary':f"{r['severity']} incident; machine state={r['state'] or 'unknown'}, interlock={r['interlock_state'] or 'unknown'}, action={r['action_status'] or 'missing'}, verified={'yes' if r['verified_at'] else 'no'}."})
    c.close(); return findings


def evaluate(ground_truth: list[dict[str,Any]], issues: list[dict[str,str]], findings: list[dict[str,Any]]) -> dict[str,Any]:
    expected=[g for g in ground_truth if g.get('expected_detection') and g['issue_type'] in {'ACK_BEFORE_ALARM','IMPOSSIBLE_INTERLOCK_STATE','INCIDENT_MISSING_TRIGGER_CONTEXT','ALARM_FLOOD_REPLAY_DUPLICATE','ACTION_CLOSED_WITHOUT_VERIFICATION'}]
    observed={(i['issue_type'],i['record_id']) for i in issues}
    matched=[g for g in expected if (g['issue_type'],g['record_id']) in observed]
    expected_keys={(g['issue_type'],g['record_id']) for g in expected}
    false_positives=[i for i in issues if (i['issue_type'],i['record_id']) not in expected_keys]
    tp=len(matched); fn=len(expected)-tp; fp=len(false_positives)
    precision=tp/(tp+fp) if tp+fp else 1.0
    recall=tp/(tp+fn) if tp+fn else 1.0
    f1=2*precision*recall/(precision+recall) if precision+recall else 0.0
    boundary={}
    for g in ground_truth:
        if g['issue_type'] in ('ACK_AT_SLA_THRESHOLD','ACK_JUST_OVER_SLA'):
            boundary[g['issue_type']]={'record_id':g['record_id'],'expected_detection':g['expected_detection'],'detected':any(x.get('alarm_event_id')==g['record_id'] and x.get('finding_type')=='Late acknowledgement' for x in findings)}
    cluster_cases=[g for g in ground_truth if g['issue_type']=='ALARM_FLOOD_NUISANCE_CLUSTER']
    cluster_detected=[g for g in cluster_cases if any(f.get('finding_type')=='Alarm flood / nuisance cluster' and f.get('machine_id')==g.get('machine_id') and f.get('alarm_definition_id')==g.get('alarm_definition_id') and str(f.get('first_seen',''))[:13]==g.get('window_hour') for f in findings)]
    priority_findings=[f for f in findings if f.get('finding_type') in ('Late acknowledgement','High-severity incident')]
    priority_compliance=sum(f.get('priority') in ('critical','high') for f in priority_findings)/len(priority_findings) if priority_findings else 1.0
    return {'anomaly_detection':{'true_positives':tp,'false_positives':fp,'false_negatives':fn,'precision':round(precision,4),'recall':round(recall,4),'f1':round(f1,4),'expected_cases':len(expected),'detected_case_ids':[g['case_id'] for g in matched]},'nuisance_cluster_coverage':{'detected':len(cluster_detected),'expected':len(cluster_cases),'recall':round(len(cluster_detected)/len(cluster_cases),4) if cluster_cases else 1.0,'detected_case_ids':[g['case_id'] for g in cluster_detected]},'boundary_decisions':boundary,'finding_counts_by_type':dict(Counter(f['finding_type'] for f in findings)),'validation_counts_by_type':dict(Counter(i['issue_type'] for i in issues)),'severe_priority_compliance':round(priority_compliance,4),'limitations':'Exception precision/recall measures planted data-quality cases only; nuisance cluster recall measures planted bursts only. Neither estimates real-plant performance.'}

def export(db_path: Path, out_dir: Path, ground_truth: list[dict[str,Any]]) -> dict[str,Any]:
    out_dir.mkdir(parents=True,exist_ok=True); c=sqlite3.connect(db_path); c.row_factory=sqlite3.Row; manifest={}
    for table in TABLES:
        rows=c.execute(f'SELECT * FROM {table}').fetchall(); dest=out_dir/f'{table.lower()}.csv'
        with dest.open('w',newline='',encoding='utf-8') as f:
            w=csv.writer(f); w.writerow([d[0] for d in c.execute(f'SELECT * FROM {table} LIMIT 0').description]); w.writerows([tuple(r) for r in rows])
        digest=hashlib.sha256(dest.read_bytes()).hexdigest(); manifest[dest.name]={'rows':len(rows),'sha256':digest}
        (out_dir/f'{table.lower()}.json').write_text(json.dumps([dict(r) for r in rows],indent=2),encoding='utf-8')
    (out_dir/'seed_data.sql').write_text('\n'.join(c.iterdump())+'\n',encoding='utf-8')
    c.close()
    gt_path=out_dir/'ground_truth.json'; gt_path.write_text(json.dumps(ground_truth,indent=2),encoding='utf-8')
    manifest[gt_path.name]={'rows':len(ground_truth),'sha256':hashlib.sha256(gt_path.read_bytes()).hexdigest()}
    (out_dir/'schema.sql').write_text(SCHEMA,encoding='utf-8')
    (out_dir/'source_manifest.json').write_text(json.dumps({'generated_at_utc':datetime.now(timezone.utc).isoformat(),'provenance':'Fully synthetic, generated locally; no external datasets used.','files':manifest},indent=2),encoding='utf-8')
    return manifest

def summary(db_path: Path) -> dict[str,Any]:
    c=sqlite3.connect(db_path); c.row_factory=sqlite3.Row
    totals={t.lower():c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in TABLES}
    severity={r[0]:r[1] for r in c.execute('SELECT severity,COUNT(*) FROM AlarmDefinition GROUP BY severity')}
    c.close(); return {'counts':totals,'alarm_definition_severity':severity}
