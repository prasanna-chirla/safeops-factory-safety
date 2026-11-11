# SafeOps — Factory Safety Intelligence

A reproducible, explainable demo for finding repeated unsafe conditions in factory event histories. This project uses fully synthetic data; it does not use external or personal data.

## Outcome

SafeOps links machine states, alarms, operator acknowledgements, incidents, and corrective actions into a timestamped history. It highlights repeated alarm patterns, slow acknowledgement, alarm clusters, severe incidents, and data exceptions. A reviewer can inspect the records supporting each result.

## Architecture

```text
Streamlit UI (app.py)
        ↓ calls
Python application/core (safety_app/core.py)
        ↓ reads/writes
SQLite (data/safety.db)  →  CSV/JSON exports + separate ground truth
```

The layers are separate by responsibility while remaining easy to run as one local hackathon app. `core.py` is UI-independent and can also be called from a CLI or later API.

## Quick start

Use Python 3.10 or newer.

```powershell
cd C:\CandidateWorkspace
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe generate_data.py --demo
.\.venv\Scripts\python.exe -m streamlit run app.py
```

These commands call the virtual-environment Python directly, so PowerShell script activation is not required.

The quick demo uses 2 plants, 12 machines, 40 alarm definitions, 2,000 total alarm events (1,999 valid baseline + 1 replay duplicate), two generated 12-alarm nuisance bursts, and 30 days.

## Full requested scale

```powershell
.\.venv\Scripts\python.exe generate_data.py
```

Defaults: 4 plants, 60 machines, 200 alarm definitions, 50,000 total alarm events over 30 days (49,999 valid baseline + 1 replay duplicate), seed `20261022`. Five labelled data-quality exception scenarios are injected after valid baseline records; the replay duplicates one of the generated flood events and is included in the 50,000 total alarm rows. Boundary cases at exactly the SLA and one minute beyond it are also included. Existing database and export files at the chosen paths are regenerated.

Run `.\.venv\Scripts\python.exe repro_check.py --demo` to regenerate twice and compare all table counts and CSV SHA-256 checksums. Omit `--demo` to check the full scale using `.\.venv\Scripts\python.exe repro_check.py`.

Scale and seed are configurable:

```powershell
.\.venv\Scripts\python.exe generate_data.py --plants 4 --machines 60 --definitions 200 --events 50000 --days 30 --seed 20261022
```

## What the analysis reports

- **Repeated alarm:** at least 3 occurrences of a machine/alarm-definition pair.
- **Late acknowledgement:** acknowledgement later than the alarm definition's SLA (15 minutes for high/critical, 60 otherwise).
- **Alarm flood / nuisance cluster:** 8 or more same machine/alarm events in one hour. Generator plants two labeled 12-event clusters for coverage.
- **High-severity incident:** reports linked machine state, interlock state, action status, and verification.
- **Data exceptions:** acknowledgement before alarm; unsafe interlock state; incident without triggering alarm; repeated source key/replay; closed action without verification; plus primary/foreign-key and timeline checks.

These thresholds are transparent demo rules, not validated plant safety standards. Tune them with plant safety/OT professionals before any operational use.

## Files generated

`data/safety.db` is the relational source. `data/exports/` contains one CSV and JSON per table, `schema.sql`, `seed_data.sql` (SQLite SQL dump), `ground_truth.json`, `validation_summary.json`, `findings.json`, `run_summary.json`, `evaluation_summary.json` (precision, recall, F1, cluster coverage and boundary decisions), and a SHA-256 source manifest. Ground-truth labels exist only in `ground_truth.json`; source tables and their CSV/JSON exports contain no anomaly-label column. The detector analyzes timestamps, relationships, and event states without reading ground truth; evaluation compares detector results with the separate labels afterward. All seed data is generated locally.

## Reproducibility

The fixed seed controls random choices. Generate to a fresh output path twice with the same arguments and compare `run_summary.json`, CSV row counts, and hashes recorded in `source_manifest.json`. The manifest generation timestamp naturally differs; compare its per-file row counts and SHA-256 values. Note that database file bytes can vary by SQLite build; exported CSV checksums are the reproducibility measure.

## Data model

Master records are generated before dependent records. Bridge tables capture machine-to-zone and machine-to-interlock relationships with effective dates. Alarm events retain source keys, state references, and shift references. Known edge-case labels are stored only in the separate ground-truth file. History is append-only during a run; derived findings are calculated from stored source events.

See `DATA_DICTIONARY.md` for fields, types, constraints, cardinality, and lifecycle notes.

## Scope and sensible next steps

This is a hackathon starter with a usable end-to-end flow. For a production deployment, add authentication/authorization, audit logging, backup/retention policy, ingestion idempotency, plant-specific safety review, alert delivery, and load/performance evaluation. Do not connect to control systems or change machine behavior from this demo.
