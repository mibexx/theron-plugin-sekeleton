# Task lists & runs – data shapes

All dicts are copies; change them freely and write back with the `update_*` methods.

## Project

```python
{"id": 3, "name": "Website relaunch", "workspace": "/Users/ada/projects/relaunch"}
```

`ctx.tasklists.projects()`. (`project.saved` events add `description` and `process_id`.)

## Task list

```python
{"id": 12, "project_id": 3, "name": "Sprint 4", "description": "", "process_id": None, "template": False}
```

| Key | Meaning |
|---|---|
| `project_id` | the project it belongs to |
| `process_id` | the process its epics run through – `None`: the project's process |
| `template` | a reusable template (with parameters) – usually leave templates alone |

`ctx.tasklists.get(id)` adds `"temporary"` (a list a process created for one run – it is removed with the run) and
`"epics"`: the epics, each with `"requirements"`.

## Epic

```python
{"id": 7, "tasklist_id": 12, "name": "Checkout", "description": "", "status": "open", "closed": False,
 "depends_on": [6], "order": 2}
```

| Key | Meaning |
|---|---|
| `depends_on` | ids of epics that must be done before this one starts |
| `closed` | closed epics get no new requirements, are hidden and count as done |
| `order` | position in the list |

## Requirement

```python
{"id": 42, "epic_id": 7, "title": "Payment with PayPal", "description": "…", "acceptance": "- …",
 "tech_rules": "", "status": "open", "result": "", "depends_on": [], "order": 1}
```

| Key | Meaning |
|---|---|
| `title`, `description` | what to do |
| `acceptance` | acceptance criteria – the agents check against them |
| `tech_rules` | technical rules for this requirement |
| `status` | see below |
| `result` | Theron's summary after working on it |
| `depends_on` | ids of requirements that must be done first |

Statuses:

| Status | Meaning |
|---|---|
| `open` | not started |
| `in_progress` | an agent works on it |
| `hitl` | waits for an answer of the user |
| `done` | finished successfully |
| `failed` | finished without success |
| `skipped` | skipped by the user |
| `closed` | closed by the user – not worked on |

When Theron works through a task list it takes the open requirements in dependency order and sets their status and
`result` – which fires `requirement.saved` events a sync can push to another service.

## Run

```python
{"id": 88, "project_id": 3, "title": "Build the checkout", "status": "done", "summary": "…",
 "goal_reached": True, "tasklist_id": 12, "parent_run": None}
```

| Key | Meaning |
|---|---|
| `status` | `idle`, `running`, `waiting_input`, `done`, `failed`, `stopped` |
| `summary` | Theron's summary at the end |
| `goal_reached` | `True` / `False` / `None` |
| `tasklist_id` | the task list the run works through, if any |
| `parent_run` | for sub-process runs: the run that started it (`ctx.runs.list` only returns top-level runs) |
