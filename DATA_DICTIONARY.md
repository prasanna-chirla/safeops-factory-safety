# SafeOps data dictionary and relational model

This dictionary covers every column in all 13 SQLite tables: the 10 business entities plus the two relationship tables and machine-state history. **Required** means the database column is `NOT NULL`; optional fields may be `NULL`. SQLite storage types are shown. Generated examples use ISO-8601 UTC timestamps ending in `Z`. Known anomaly labels are kept only in `data/exports/ground_truth.json`; they are not columns in the source tables.

## Plant

| Field | Type | Required? | Allowed values / format | Unit | Unique? | Validation rule |
|---|---|---:|---|---|---|---|
| `plant_id` | TEXT | Yes | `PLT-001` format | — | Primary key | Must be unique and referenced plant must exist. |
| `name` | TEXT | Yes | Generated `Plant 1`, etc. | — | No | Must not be NULL. |
| `region` | TEXT | Yes | North, South, East, West in generator | — | No | Must not be NULL; generator chooses from the listed regions. |
| `lifecycle_state` | TEXT | Yes | `active`, `inactive` | — | No | SQLite CHECK permits only these values. |

## Machine

| Field | Type | Required? | Allowed values / format | Unit | Unique? | Validation rule |
|---|---|---:|---|---|---|---|
| `machine_id` | TEXT | Yes | `MCH-001` format | — | Primary key | Must be unique and used consistently by child rows. |
| `plant_id` | TEXT | Yes | Existing Plant ID | — | No | Foreign key to Plant; machine and related safety assets must belong to the same plant. |
| `name` | TEXT | Yes | Generated `Machine 001`, etc. | — | No | Must not be NULL. |
| `machine_type` | TEXT | Yes | press, conveyor, robot, cutter, filler in generator | — | No | Must not be NULL; generator chooses from the listed types. |
| `commissioned_at` | TEXT | Yes | ISO-8601 UTC timestamp | Date/time | No | Must parse as a timestamp; generated commissioning time is before the event window. |
| `lifecycle_state` | TEXT | Yes | active, maintenance, retired | — | No | Must be one of the documented lifecycle states. |

## SafetyZone

| Field | Type | Required? | Allowed values / format | Unit | Unique? | Validation rule |
|---|---|---:|---|---|---|---|
| `safety_zone_id` | TEXT | Yes | `SAFE-<plant-id>-###` | — | Primary key | Must be unique; embedded plant ID must match `plant_id`. |
| `plant_id` | TEXT | Yes | Existing Plant ID | — | No | Foreign key to Plant. |
| `name` | TEXT | Yes | Generated `Safety Zone ###` | — | No | Must not be NULL. |
| `hazard_level` | TEXT | Yes | low, medium, high, critical | — | No | SQLite CHECK permits only these values. |

## MachineSafetyZone (relationship table)

| Field | Type | Required? | Allowed values / format | Unit | Unique? | Validation rule |
|---|---|---:|---|---|---|---|
| `machine_id` | TEXT | Yes | Existing Machine ID | — | Part of composite key | Foreign key to Machine; must be in the same plant as the zone. |
| `safety_zone_id` | TEXT | Yes | Existing SafetyZone ID | — | Part of composite key | Foreign key to SafetyZone. |
| `effective_from` | TEXT | Yes | ISO-8601 UTC timestamp | Date/time | Part of composite key | Start of assignment period. |
| `effective_to` | TEXT | No | ISO-8601 UTC timestamp or NULL | Date/time | No | If supplied, must be later than `effective_from`. |

Composite primary key: (`machine_id`, `safety_zone_id`, `effective_from`). Each machine is assigned to multiple zones and zones can be shared by machines, so this bridge implements N:M.

## Interlock

| Field | Type | Required? | Allowed values / format | Unit | Unique? | Validation rule |
|---|---|---:|---|---|---|---|
| `interlock_id` | TEXT | Yes | `INT-<plant-id>-###` | — | Primary key | Must be unique; embedded plant ID must match `plant_id`. |
| `plant_id` | TEXT | Yes | Existing Plant ID | — | No | Foreign key to Plant. |
| `name` | TEXT | Yes | Generated `Guard interlock ###` | — | No | Must not be NULL. |
| `interlock_type` | TEXT | Yes | `guard_door` in generator | — | No | Must not be NULL; generator currently uses the documented type. |
| `safe_state` | TEXT | Yes | `closed` in generator | — | No | Describes the safe interlock condition; compare event state against this rule. |

## MachineInterlock (relationship table)

| Field | Type | Required? | Allowed values / format | Unit | Unique? | Validation rule |
|---|---|---:|---|---|---|---|
| `machine_id` | TEXT | Yes | Existing Machine ID | — | Part of composite key | Foreign key to Machine; must be in the same plant as the interlock. |
| `interlock_id` | TEXT | Yes | Existing Interlock ID | — | Part of composite key | Foreign key to Interlock. |
| `effective_from` | TEXT | Yes | ISO-8601 UTC timestamp | Date/time | Part of composite key | Start of assignment period. |
| `effective_to` | TEXT | No | ISO-8601 UTC timestamp or NULL | Date/time | No | If supplied, must be later than `effective_from`. |

Composite primary key: (`machine_id`, `interlock_id`, `effective_from`). This bridge implements a time-effective N:M machine/interlock relationship.

## AlarmDefinition

| Field | Type | Required? | Allowed values / format | Unit | Unique? | Validation rule |
|---|---|---:|---|---|---|---|
| `alarm_definition_id` | TEXT | Yes | `ALD-<machine-id>-###` | — | Primary key | Must be unique and reference the machine used by its alarm events. |
| `machine_id` | TEXT | Yes | Existing Machine ID | — | No | Foreign key to Machine. |
| `code` | TEXT | Yes | `AL-0001` format | — | Unique with machine | Must be unique for a given machine. |
| `severity` | TEXT | Yes | low, medium, high, critical | — | No | SQLite CHECK permits only these values. |
| `ack_sla_minutes` | INTEGER | Yes | Positive integer | Minutes | No | SQLite CHECK requires value greater than zero; high/critical use 15, low/medium use 60 in this demo. |
| `nuisance_candidate` | INTEGER / BOOLEAN | Yes | 0 or 1 | — | No | SQLite CHECK permits only 0 or 1. |

## OperatorShift

| Field | Type | Required? | Allowed values / format | Unit | Unique? | Validation rule |
|---|---|---:|---|---|---|---|
| `shift_id` | TEXT | Yes | `SHF-<plant-id>-###-<shift-number>` | — | Primary key | Must be unique. |
| `plant_id` | TEXT | Yes | Existing Plant ID | — | No | Foreign key to Plant; must match the event machine's plant. |
| `operator_name` | TEXT | Yes | Synthetic names: Asha, Ravi, Meera, Kiran, Noah, Ira | — | No | Must not be NULL. |
| `starts_at` | TEXT | Yes | ISO-8601 UTC timestamp | Date/time | No | Must be earlier than `ends_at`. |
| `ends_at` | TEXT | Yes | ISO-8601 UTC timestamp | Date/time | No | SQLite CHECK requires end after start; events must fall within the shift. |
| `shift_name` | TEXT | Yes | day, evening, night | — | No | SQLite CHECK permits only these values. |

## MachineStateEvent

| Field | Type | Required? | Allowed values / format | Unit | Unique? | Validation rule |
|---|---|---:|---|---|---|---|
| `state_event_id` | TEXT | Yes | `STE-0000001` format | — | Primary key | Must be unique. |
| `machine_id` | TEXT | Yes | Existing Machine ID | — | No | Foreign key to Machine; must match the linked alarm's machine. |
| `occurred_at` | TEXT | Yes | ISO-8601 UTC timestamp | Date/time | No | Must parse as a timestamp; linked state event must not occur after its alarm. |
| `state` | TEXT | Yes | running, idle, stopped, fault, maintenance | — | No | SQLite CHECK permits only these values. |

## AlarmEvent

| Field | Type | Required? | Allowed values / format | Unit | Unique? | Validation rule |
|---|---|---:|---|---|---|---|
| `alarm_event_id` | TEXT | Yes | `ALM-<machine-id>-######` | — | Primary key | Must be unique; counter is zero-padded and local to the machine. |
| `machine_id` | TEXT | Yes | Existing Machine ID | — | No | Foreign key to Machine; must equal the alarm definition's machine. |
| `alarm_definition_id` | TEXT | Yes | Existing AlarmDefinition ID | — | No | Foreign key to AlarmDefinition. |
| `occurred_at` | TEXT | Yes | ISO-8601 UTC timestamp | Date/time | No | Must parse as a timestamp and fall inside the linked operator shift. |
| `state_event_id` | TEXT | No | Existing MachineStateEvent ID or NULL | — | No | Optional foreign key; if present, machine must match and state time must be at/before alarm time. |
| `shift_id` | TEXT | No | Existing OperatorShift ID or NULL | — | No | Optional foreign key; if present, plant and shift time window must match the event. |
| `interlock_state` | TEXT | Yes | safe, unsafe, unknown | — | No | SQLite CHECK permits only these values; running + unsafe is flagged by the safety rule. |
| `source_event_key` | TEXT | Yes | Original source alarm ID | — | Not unique by design | Required for replay detection; duplicate source keys identify a replay. |

## Acknowledgement

| Field | Type | Required? | Allowed values / format | Unit | Unique? | Validation rule |
|---|---|---:|---|---|---|---|
| `acknowledgement_id` | TEXT | Yes | `ACK-<alarm-event-id>-01` | — | Primary key | Must be unique and reference its alarm event. |
| `alarm_event_id` | TEXT | Yes | Existing AlarmEvent ID | — | Unique foreign key | Exactly one acknowledgement per alarm in this dataset; SQLite UNIQUE enforces this. |
| `acknowledged_at` | TEXT | Yes | ISO-8601 UTC timestamp | Date/time | No | Normally at/after alarm time; the before-alarm case is deliberately injected and must be detected. |
| `operator_name` | TEXT | Yes | Synthetic operator name | — | No | Must not be NULL. |
| `status` | TEXT | Yes | acknowledged, unacknowledged | — | No | SQLite CHECK permits only these values. |

## Incident

| Field | Type | Required? | Allowed values / format | Unit | Unique? | Validation rule |
|---|---|---:|---|---|---|---|
| `incident_id` | TEXT | Yes | `INC-2026-000001` format | — | Primary key | Must be unique and sequentially zero-padded. |
| `plant_id` | TEXT | Yes | Existing Plant ID | — | No | Foreign key to Plant; must match the machine's plant. |
| `machine_id` | TEXT | Yes | Existing Machine ID | — | No | Foreign key to Machine; if a trigger alarm exists, its machine must match. |
| `alarm_event_id` | TEXT | No | Existing AlarmEvent ID or NULL | — | No | Optional foreign key; NULL is deliberately used for the missing-context case. |
| `created_at` | TEXT | Yes | ISO-8601 UTC timestamp | Date/time | No | Must parse as a timestamp; normally follows its triggering alarm. |
| `severity` | TEXT | Yes | low, medium, high, critical | — | No | SQLite CHECK permits only these values; normally copied from triggering alarm definition. |
| `description` | TEXT | Yes | Human-readable explanation | — | No | Must not be NULL; generated from event severity and alarm code. |
| `lifecycle_state` | TEXT | Yes | open, investigating, resolved | — | No | SQLite CHECK permits only these values; resolved requires a closed, verified action. |

## CorrectiveAction

| Field | Type | Required? | Allowed values / format | Unit | Unique? | Validation rule |
|---|---|---:|---|---|---|---|
| `action_id` | TEXT | Yes | `ACT-<incident-id>-01` | — | Primary key | Must be unique and point to its incident. |
| `incident_id` | TEXT | Yes | Existing Incident ID | — | No | Foreign key to Incident. |
| `description` | TEXT | Yes | Human-readable corrective action | — | No | Must not be NULL. |
| `opened_at` | TEXT | Yes | ISO-8601 UTC timestamp | Date/time | No | Must be at/after incident creation. |
| `closed_at` | TEXT | No | ISO-8601 UTC timestamp or NULL | Date/time | No | If supplied, must be at/after `opened_at`. |
| `verified_at` | TEXT | No | ISO-8601 UTC timestamp or NULL | Date/time | No | If supplied, must be at/after `closed_at`; closed action should have verification. |
| `status` | TEXT | Yes | open, in_progress, closed, closed_unverified | — | No | SQLite CHECK permits only these values; closed-without-verification is deliberately injected and detected from dates. |

## Relationships and cardinality

- Plant 1:N Machine, SafetyZone, Interlock, and OperatorShift.
- Machine N:M SafetyZone through MachineSafetyZone; Machine N:M Interlock through MachineInterlock. Both bridges include effective dates.
- Machine 1:N AlarmDefinition, MachineStateEvent, AlarmEvent, and Incident.
- AlarmDefinition 1:N AlarmEvent; each AlarmEvent has exactly one AlarmDefinition.
- AlarmEvent 1:1 Acknowledgement in the generated dataset (UNIQUE foreign key); AlarmEvent 1:0..N Incident.
- OperatorShift 1:N AlarmEvent; each AlarmEvent's shift reference is optional in the schema.
- MachineStateEvent 1:0..N AlarmEvent references; each AlarmEvent's state reference is optional.
- Incident 1:N CorrectiveAction; each action belongs to one incident.

## IDs, derived values, lifecycle, and provenance

All IDs are immutable within a generated run. Counters use leading zeroes. Event timestamps are UTC; SLA and response durations use minutes. Derived acknowledgement delay is `acknowledged_at - occurred_at`; alarm counts and hourly clusters are calculated from event rows. Counts and summaries are calculated from stored tables, not independently randomized.

The generator uses seed `20261022` by default. It first creates valid baseline rows, then applies the labelled edge-case updates and replay. `ground_truth.json` is separate from analysis fields. Evaluation reports precision, recall, F1, planted-cluster recall, and exact-SLA boundary decisions; these scores apply only to the synthetic test cases. All generated data is synthetic; no external data source is used.

## Database-level and cross-table validation

SQLite enforces primary keys, foreign keys, CHECK-constrained enums, positive acknowledgement SLA, unique machine/alarm code pairs, unique alarm/acknowledgement pairs, and valid shift date order. The validator additionally checks primary-key duplication (including composite keys), ISO-8601 UTC timestamps, foreign-key integrity, cross-table machine/plant joins, non-overlapping shifts, effective-date ranges, shift coverage, state/incident/action time order, incident severity against its trigger, exactly one acknowledgement per alarm, safe interlock state, missing incident trigger, replay source-key duplicates, closed-action verification, action status/timestamp consistency, and resolved-incident lifecycle consistency.
