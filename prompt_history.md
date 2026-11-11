# SafeOps — Prompt History

**Project:** Factory Safety Intelligence  
**Workspace:** `C:\CandidateWorkspace`  
**Purpose:** Record the project-related requests, decisions, and current status in one place.

> This is an organized summary of the prompts used during the project. It is not a verbatim copy of the entire chat.

## 1. Original problem

The hackathon asks for a working solution that analyzes factory safety events, machine states, acknowledgements, incidents, and corrective actions to find repeated unsafe conditions. Findings must be traceable, data must be validated, and results must be measurable.

## 2. Prompt timeline

| Step | User request | Project direction or result |
|---|---|---|
| 1. Understand the task | Explain the problem, requirements, constraints, and expected outcome in simple language, including Telugu-English mix. | Keep explanations beginner-friendly and connect technical terms to simple examples. |
| 2. Choose an architecture | Recommend engineering practices; explain three-layer architecture and whether frontend, backend, and database are needed. | Use a Streamlit frontend, Python application logic, and SQLite database. |
| 3. Build the project | Create an organized project that covers the hackathon requirements and edge cases. | Implement the generator, relational schema, validation, analysis, evaluation, exports, and dashboard. |
| 4. Choose the project location | Create the project at `C:\CandidateWorkspace`. | Keep the SafeOps project in that folder. |
| 5. Help run it | Explain how to run the project in VS Code and address the PowerShell activation-policy issue. | Use the virtual-environment Python executable directly, so activation is optional. |
| 6. Clarify dataset size | Explain whether the generated scale can change and how to use the volume in the problem statement. | Use the requested full scale by default: 4 plants, 60 machines, 200 alarm definitions, 50,000 alarm events, and 30 days. |
| 7. Make the event total exact | Clarify whether the replay duplicate makes the count 50,001. | Count the replay duplicate inside the 50,000 total: 49,999 baseline alarm events plus 1 replay row. |
| 8. Explain the project files | Explain the project structure, database, relationships, frontend/backend, and exports for a beginner. | Document the files, tables, relationships, and how to view the generated data. |
| 9. Review problem coverage | Check the project against requirements, constraints, edge cases, traceability, and evaluation metrics. | Compare the implementation and generated run results to the hackathon checklist. |
| 10. Explain the dashboard | Explain the screenshots and clarify what evidence the dashboard provides for an alarm. | The app displays timestamped alarm records and operator responses; it does not record or prove an audible machine beep. |
| 11. Fix review findings | Keep ground-truth labels separate and prepare the project files for a future public GitHub submission. | Remove label columns from source tables, keep labels in `ground_truth.json`, and allow the database and exports to be tracked by Git. |
| 12. Record this history | Create a prompt history file in the project. | Save this document as `prompt_history.md` in the project root. |

## 3. Requirements used to guide the build

- Generate parent/master records before dependent event records, and preserve valid IDs and relationships.
- Keep event history and timestamps so an alarm can be traced through machine state, acknowledgement, incident, and corrective action.
- Include the five required negative cases: acknowledgement before alarm, impossible interlock state, incident without trigger context, replayed alarm duplicate, and action closed without verification.
- Keep expected labels in a separate `ground_truth.json`; do not put those labels in source database tables or source CSV/JSON exports.
- Validate keys, relationships, event ordering, and corrective-action timelines.
- Export CSV, JSON, and SQL data, and document the schema, generator, fixed seed, and validation results.
- Regenerate with the same seed and compare counts and checksums to demonstrate reproducibility.

## 4. Current project status

- Full-scale generated data contains 4 plants, 60 machines, 200 alarm definitions, and exactly 50,000 alarm events over 30 days.
- The five intended data-quality edge cases are detected by the validator.
- The saved full-scale run reports anomaly F1 of 1.0 and nuisance-cluster recall of 1.0 for the planted synthetic cases. These scores do not establish real factory performance.
- The repeatability check passed with matching counts and CSV checksums.
- The project, database, and exports are local in `C:\CandidateWorkspace`.
- The user plans to make more changes before pushing the project to GitHub; no public repository has been published yet.
