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

## Process

What `ctx.processes.get` returns (and `create` / `update` take):

```python
{"id": 5, "name": "Development", "description": "…", "goal": "Definition of done …", "folder": "",
 "orchestrator_instructions": "", "orchestrator_model": "", "max_agent_calls": 20,
 "inputs": [{"name": "Repository", "hint": "…", "kind": "url", "required": True}],
 "start": "s1a2b3c4",
 "steps": [
   {"id": "s1a2b3c4", "type": "agent", "agent_id": 3, "name": "", "instructions": "…", "success_criteria": "…",
    "on_success": "s9f8e7d6", "on_failure": "ask_user", "max_iterations": 3, "on_max": "ask_user",
    "backend": "", "model": "", "description": "", "pos": [120, 80], …},
   …]}
```

Every step has an `id` (unique in the process), a `type` and its outputs; `pos` is its place on the canvas. Targets
are step ids or `"end"`, failure targets also `"ask_user"` / `"abort"`. Step types and their fields:

| `type` | Main fields |
|---|---|
| `agent` | `agent_id`, `instructions`, `success_criteria`, `on_success`, `on_failure`, `max_iterations`, `on_max` |
| `parallel` | `name`, `members` (`[{"agent_id", "instructions"}]`), outputs as `agent` |
| `switch` | `name`, `branches` (`[{"condition", "target"}]`), `else_target`; `decider: "user"` + `question` = a ✋ user decision |
| `fork` / `join` | `targets` / `on_success` |
| `foreach` | `name`, `split_rule`, `item_target` (the loop body), `on_success` (result), `parallel`, `max_parallel`, `max_items`, `item_failure` |
| `subprocess` | `process_id`, outputs as `agent` |
| `message` | `level`, `text`, `mode`, `on_success` |
| `tasklist` | `tl_mode`, `tasklist_id`, `tl_new_name`, `on_success` |
| `memory` / `database` | `memory_mode`, `memory_name` / `db_mode`, `db_name`, `db_filter`, `on_success` |
| `plugin` | `plugin_node`, `plugin_config`, `plugin_outputs`, outputs as `agent` |

`ctx.processes.problems(doc)` tells whether a document is a complete graph.

## Process draft

The format the AI designer writes – and `process.design.after`, `ctx.processes.create_from_draft` and `to_draft`
use. Steps have `key`s instead of ids and name their agents:

```python
{"name": "Shop", "description": "…", "goal": "…", "start": "s1",
 "inputs": [],
 "new_agents": [{"name": "Shop developer", "task": "…", "rules": "- …", "model": "sonnet"}],
 "steps": [
   {"key": "s1", "type": "agent", "agent": "Shop developer", "instructions": "…", "on_success": "s2",
    "on_failure": "ask_user", "description": "what happens here, for the user"},
   {"key": "s2", "type": "hitl", "question": "Ship it?", "branches": [{"condition": "Yes", "target": "end"},
                                                                       {"condition": "Fix", "target": "s1"}]},
   {"key": "s3", "type": "plugin", "node": "trello-sync/push", "config": {"board": "Sprint"}, "on_success": "end"}]}
```

Types: `agent`, `parallel` (`members`: agent names), `switch`, `hitl`, `fork` (`targets`), `join`, `foreach`
(`item`, `split_rule` …), `subprocess` (`process`: a process name), `message`, `tasklist`, `memory`, `database`,
`plugin` (`node`, `config`). Unknown agent names become new agents.

## Agent

What `ctx.agents.get` returns:

```python
{"id": 3, "name": "Developer", "task": "Implements …", "rules": "- …", "backend": "claude", "model": "sonnet",
 "permission_mode": "bypassPermissions", "load_user_settings": True, "max_turns": 80, "color": "", "knowledge": [],
 "folder": "", "memory": False, "memory_dir": "", "memory_ttl_days": 7}
```

`backend`: `"claude"` (Claude Code) or `"opencode"` (local models); `model` empty = the backend's default.

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
