from __future__ import annotations

import inspect
import json
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from safety_app.core import analyze, summary, validate


ROOT = Path(__file__).resolve().parent
DB = ROOT / "data" / "safety.db"
SEVERITIES = ["critical", "high", "medium", "low"]
TABLES = [
    "Plant",
    "Machine",
    "SafetyZone",
    "MachineSafetyZone",
    "Interlock",
    "MachineInterlock",
    "AlarmDefinition",
    "OperatorShift",
    "MachineStateEvent",
    "AlarmEvent",
    "Acknowledgement",
    "Incident",
    "CorrectiveAction",
]

ISSUE_TITLES = {
    "ACK_BEFORE_ALARM": "Acknowledgement came before the alarm",
    "IMPOSSIBLE_INTERLOCK_STATE": "Machine ran while the interlock was unsafe",
    "INCIDENT_MISSING_TRIGGER_CONTEXT": "Incident has no linked trigger alarm",
    "ALARM_FLOOD_REPLAY_DUPLICATE": "Alarm event was duplicated by replay",
    "ACTION_CLOSED_WITHOUT_VERIFICATION": "Action was closed without verification",
}


def read_query(sql: str, params: tuple[Any, ...] = ()) -> pd.DataFrame:
    """Read a query and always close its SQLite connection."""
    connection = sqlite3.connect(DB)
    try:
        return pd.read_sql_query(sql, connection, params=params)
    finally:
        connection.close()


def show_dataframe(data: pd.DataFrame, **kwargs: Any) -> None:
    """Use the current Streamlit width API, with support for older versions."""
    if "width" in inspect.signature(st.dataframe).parameters:
        st.dataframe(data, width="stretch", **kwargs)
    else:
        st.dataframe(data, use_container_width=True, **kwargs)


def stretch_option(component: Any) -> dict[str, Any]:
    """Return the correct full-width option for this installed Streamlit version."""
    if "width" in inspect.signature(component).parameters:
        return {"width": "stretch"}
    return {"use_container_width": True}


def metric_card(column: Any, label: str, value: Any, help_text: str) -> None:
    with column.container(border=True):
        st.metric(label, value, help=help_text)


st.set_page_config(
    page_title="SafeOps | Factory Safety Intelligence",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    .block-container {max-width: 1500px; padding-top: 1.4rem; padding-bottom: 2.5rem;}
    .safeops-hero {
        padding: 1.5rem 1.8rem; border-radius: 18px; color: #fff;
        background: linear-gradient(118deg, #10243a 0%, #155e75 100%);
        margin-bottom: 1.2rem; box-shadow: 0 10px 28px rgba(16, 36, 58, .16);
    }
    .safeops-hero .eyebrow {font-size: .78rem; letter-spacing: .12em; text-transform: uppercase; color: #a9dce6;}
    .safeops-hero h1 {margin: .25rem 0; font-size: 2.15rem; color: #fff;}
    .safeops-hero p {margin: .4rem 0 0; color: #d9eef2; font-size: 1rem;}
    div[data-testid="stMetric"] {padding: .25rem .1rem;}
    div[data-testid="stVerticalBlockBorderWrapper"] {border-radius: 14px;}
    div[data-testid="stTabs"] button {font-weight: 600;}
    .small-note {color: #64748b; font-size: .9rem;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="safeops-hero">
      <div class="eyebrow">Factory safety intelligence</div>
      <h1>🛡️ SafeOps</h1>
      <p>Spot repeated risks. Trace every alarm from machine state to verified action.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

if not DB.exists():
    st.warning("The safety database has not been created yet.")
    st.write("Run the demo generator in the VS Code terminal, then refresh this page:")
    st.code(r".\.venv\Scripts\python.exe generate_data.py --demo", language="powershell")
    st.stop()

counts = summary(DB)["counts"]
findings = analyze(DB)
issues = validate(DB)

metrics_path = ROOT / "data" / "exports" / "evaluation_summary.json"
evaluation = json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.exists() else None

kpi_columns = st.columns(4)
metric_card(kpi_columns[0], "Alarm events", f"{counts['alarmevent']:,}", "Total alarm records in this dataset.")
metric_card(kpi_columns[1], "Machines", f"{counts['machine']:,}", "Machines represented in the dataset.")
metric_card(kpi_columns[2], "Incidents", f"{counts['incident']:,}", "Generated incident records linked to safety conditions.")
metric_card(kpi_columns[3], "Data exceptions", f"{len(issues):,}", "Intentional edge cases detected by validation.")

manifest_path = ROOT / "data" / "exports" / "source_manifest.json"
manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
seed = manifest.get("seed", 20261022)
st.caption(f"Synthetic demonstration data  ·  Fixed seed {seed}  ·  Findings are traceable to source records")

overview_tab, trace_tab, quality_tab, explorer_tab = st.tabs(
    ["Safety overview", "Machine trace", "Data quality", "Data explorer"]
)

with overview_tab:
    st.subheader("Findings that need attention")
    if not findings:
        st.success("No findings for the current dataset.")
    else:
        findings_df = pd.DataFrame(findings)
        priority_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        findings_df["_rank"] = findings_df["priority"].map(priority_rank).fillna(4)
        findings_df = findings_df.sort_values(["_rank", "count"], ascending=[True, False])

        filter_col1, filter_col2, filter_col3 = st.columns([1.5, 1, 1])
        finding_types = sorted(findings_df["finding_type"].dropna().unique().tolist())
        priorities = [p for p in SEVERITIES if p in findings_df["priority"].values]
        with filter_col1:
            selected_types = st.multiselect("Finding type", finding_types, default=finding_types)
        with filter_col2:
            selected_priorities = st.multiselect("Priority", priorities, default=priorities)
        with filter_col3:
            row_limit = st.selectbox("Rows to display", [100, 250, 500], index=1)

        filtered = findings_df[
            findings_df["finding_type"].isin(selected_types)
            & findings_df["priority"].isin(selected_priorities)
        ].copy()
        st.caption(f"Showing {min(len(filtered), row_limit):,} of {len(filtered):,} matching findings.")

        display = filtered.drop(columns="_rank").head(row_limit).rename(
            columns={
                "finding_type": "Finding",
                "priority": "Priority",
                "machine_id": "Machine",
                "alarm_definition_id": "Alarm definition",
                "alarm_event_id": "Alarm event ID",
                "incident_id": "Incident ID",
                "count": "Count",
                "first_seen": "First seen",
                "last_seen": "Last seen",
                "summary": "Explanation",
            }
        )
        if "Priority" in display.columns:
            priority_icons = {"critical": "🔴 Critical", "high": "🟠 High", "medium": "🟡 Medium", "low": "🟢 Low"}
            display["Priority"] = display["Priority"].map(priority_icons).fillna(display["Priority"])
        show_dataframe(
            display,
            hide_index=True,
            height=430,
            column_config={
                "Finding": st.column_config.TextColumn("Finding", width="medium"),
                "Priority": st.column_config.TextColumn("Priority", width="small"),
                "Explanation": st.column_config.TextColumn("Explanation", width="large"),
            },
        )

    with st.expander("How SafeOps decides what needs attention"):
        st.markdown(
            """
            - **Repeated alarm:** 3 or more events for the same machine and alarm definition.
            - **Late acknowledgement:** response time exceeds that alarm's severity-based SLA.
            - **Alarm flood / nuisance cluster:** 8 or more matching events in one hour.
            - **High-severity incident:** shows its machine state, interlock, and corrective-action status.
            """
        )

    if evaluation:
        st.divider()
        st.subheader("Evaluation on generated test cases")
        metrics = evaluation["anomaly_detection"]
        clusters = evaluation["nuisance_cluster_coverage"]
        eval_cols = st.columns(4)
        metric_card(eval_cols[0], "Exception precision", f"{metrics['precision']:.0%}", "Of detected planted exceptions, how many were expected.")
        metric_card(eval_cols[1], "Exception recall", f"{metrics['recall']:.0%}", "Of planted exceptions, how many the validator found.")
        metric_card(eval_cols[2], "Exception F1", f"{metrics['f1']:.0%}", "Combined precision and recall for planted test cases.")
        metric_card(eval_cols[3], "Flood-cluster recall", f"{clusters['recall']:.0%}", "Share of planted nuisance clusters detected.")
        st.caption(evaluation.get("limitations", "These scores cover the generated test cases only."))

with trace_tab:
    st.subheader("Follow one machine's event history")
    machine_list = read_query("SELECT machine_id, name FROM Machine ORDER BY machine_id")
    if machine_list.empty:
        st.info("No machines are available in the database.")
    else:
        machine_names = dict(zip(machine_list["machine_id"], machine_list["name"]))
        machine_id = st.selectbox(
            "Choose a machine",
            machine_list["machine_id"].tolist(),
            format_func=lambda value: f"{value}  ·  {machine_names[value]}",
        )
        st.markdown(f"### {machine_id}  ·  {machine_names[machine_id]}")

        events = read_query(
            """
            SELECT e.occurred_at, e.alarm_event_id, d.code, d.severity, d.ack_sla_minutes,
                   s.state, e.interlock_state, k.acknowledged_at,
                   ROUND((julianday(k.acknowledged_at) - julianday(e.occurred_at)) * 1440, 1) AS ack_minutes,
                   i.incident_id, i.description AS incident_description,
                   a.status AS action_status, a.verified_at
            FROM AlarmEvent e
            JOIN AlarmDefinition d USING (alarm_definition_id)
            LEFT JOIN MachineStateEvent s USING (state_event_id)
            LEFT JOIN Acknowledgement k USING (alarm_event_id)
            LEFT JOIN Incident i USING (alarm_event_id)
            LEFT JOIN CorrectiveAction a USING (incident_id)
            WHERE e.machine_id = ?
            ORDER BY e.occurred_at DESC
            LIMIT 1000
            """,
            (machine_id,),
        )

        if events.empty:
            st.info("No alarm events are recorded for this machine.")
        else:
            events["ack_minutes"] = pd.to_numeric(events["ack_minutes"], errors="coerce")
            events["ack_sla_minutes"] = pd.to_numeric(events["ack_sla_minutes"], errors="coerce")
            events["is_late"] = events["ack_minutes"] > events["ack_sla_minutes"]

            selected_severities = st.multiselect(
                "Show severities",
                SEVERITIES,
                default=SEVERITIES,
                key="trace_severities",
            )
            visible_events = events[events["severity"].isin(selected_severities)].copy()

            event_cols = st.columns(4)
            metric_card(event_cols[0], "Events shown", f"{len(visible_events):,}", "Events for this machine and selected severities.")
            metric_card(
                event_cols[1],
                "High / critical",
                f"{visible_events['severity'].isin(['high', 'critical']).sum():,}",
                "More serious alarms in the visible events.",
            )
            metric_card(event_cols[2], "Late acknowledgements", f"{visible_events['is_late'].fillna(False).sum():,}", "Acknowledgements later than the configured SLA.")
            metric_card(event_cols[3], "Linked incidents", f"{visible_events['incident_id'].notna().sum():,}", "Incidents linked to the visible events.")

            st.markdown("#### Event list")
            event_table = visible_events[
                ["occurred_at", "alarm_event_id", "code", "severity", "state", "interlock_state", "ack_minutes", "incident_id"]
            ].rename(
                columns={
                    "occurred_at": "Time",
                    "alarm_event_id": "Alarm event ID",
                    "code": "Alarm code",
                    "severity": "Severity",
                    "state": "Machine state",
                    "interlock_state": "Interlock",
                    "ack_minutes": "Ack minutes",
                    "incident_id": "Incident ID",
                }
            )
            show_dataframe(
                event_table,
                hide_index=True,
                height=360,
                column_config={
                    "Time": st.column_config.TextColumn("Time", width="medium"),
                    "Alarm event ID": st.column_config.TextColumn("Alarm event ID", width="medium"),
                    "Ack minutes": st.column_config.NumberColumn("Ack minutes", format="%.1f"),
                },
            )
            st.caption("Showing up to 1,000 events for the selected machine, newest first.")

            if not visible_events.empty:
                event_lookup = visible_events.set_index("alarm_event_id", drop=False)
                selected_event = st.selectbox(
                    "Inspect an event",
                    visible_events["alarm_event_id"].tolist(),
                    format_func=lambda value: (
                        f"{event_lookup.loc[value, 'occurred_at']}  ·  "
                        f"{value}  ·  {str(event_lookup.loc[value, 'severity']).title()}"
                    ),
                )
                detail = event_lookup.loc[selected_event]
                with st.container(border=True):
                    st.markdown("#### Event details")
                    detail_cols = st.columns(4)
                    detail_cols[0].markdown(f"**Alarm**\n\n{detail['code']} · {str(detail['severity']).title()}")
                    detail_cols[1].markdown(f"**Machine state**\n\n{detail['state'] or 'Unknown'}")
                    detail_cols[2].markdown(f"**Interlock**\n\n{detail['interlock_state'] or 'Unknown'}")
                    ack_value = "Not recorded" if pd.isna(detail["acknowledged_at"]) else str(detail["acknowledged_at"])
                    detail_cols[3].markdown(f"**Acknowledged**\n\n{ack_value}")
                    if pd.notna(detail["incident_id"]):
                        st.markdown(f"**Incident:** `{detail['incident_id']}` — {detail['incident_description']}")
                        action = detail["action_status"] if pd.notna(detail["action_status"]) else "No action recorded"
                        verified = detail["verified_at"] if pd.notna(detail["verified_at"]) else "Not verified"
                        st.markdown(f"**Corrective action:** {action}  ·  **Verified:** {verified}")
                    else:
                        st.info("No incident or corrective action is linked to this alarm.")

with quality_tab:
    st.subheader("Data quality and validation")
    st.caption("These checks look for broken links, impossible timelines, and known demo edge cases.")
    error_count = sum(issue["severity"] == "error" for issue in issues)
    warning_count = sum(issue["severity"] == "warning" for issue in issues)
    quality_cols = st.columns(3)
    metric_card(quality_cols[0], "Total exceptions", f"{len(issues):,}", "All validation issues found in the database.")
    metric_card(quality_cols[1], "Errors", f"{error_count:,}", "Structural or relationship problems.")
    metric_card(quality_cols[2], "Warnings", f"{warning_count:,}", "Known timeline or safety-rule exceptions.")

    if not issues:
        st.success("All validation checks passed. No exceptions were found.")
    else:
        st.markdown("#### Exceptions found")
        for issue in issues:
            title = ISSUE_TITLES.get(issue["issue_type"], issue["issue_type"].replace("_", " ").title())
            with st.container(border=True):
                icon = "🛑" if issue["severity"] == "error" else "⚠️"
                st.markdown(f"**{icon} {title}**")
                st.write(issue["detail"])
                st.caption(f"Record: `{issue['record_id']}`  ·  Rule: `{issue['issue_type']}`")
    st.info("The five planned edge cases are intentional test data. They are shown so a reviewer can confirm that validation catches them.")

with explorer_tab:
    st.subheader("Explore database tables")
    st.caption("Choose a table to inspect its records. Download the full selected table as CSV when needed.")
    control_col, limit_col = st.columns([1.4, 1])
    with control_col:
        selected_table = st.selectbox("Database table", TABLES, format_func=lambda value: value)
    with limit_col:
        display_limit = st.selectbox("Rows to display", [100, 500, 1000], index=2, key="explorer_limit")

    total_rows = int(read_query(f'SELECT COUNT(*) AS n FROM "{selected_table}"').iloc[0]["n"])
    table_data = read_query(f'SELECT * FROM "{selected_table}" LIMIT ?', (display_limit,))
    st.caption(f"Showing {len(table_data):,} of {total_rows:,} rows in `{selected_table}`.")
    show_dataframe(table_data, hide_index=True, height=440)

    all_rows = read_query(f'SELECT * FROM "{selected_table}"')
    st.download_button(
        label=f"Download all {total_rows:,} rows as CSV",
        data=all_rows.to_csv(index=False).encode("utf-8"),
        file_name=f"{selected_table.lower()}.csv",
        mime="text/csv",
        **stretch_option(st.download_button),
    )
