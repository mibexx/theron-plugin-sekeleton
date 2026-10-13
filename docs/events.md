# Events

```python
@ctx.events.on("requirement.saved")
async def changed(event):
    ...

ctx.events.on("run.finished", on_finished)
ctx.events.on("*", log_everything)          # every event
```

## Delivery rules

- Events are delivered while Theron runs as the **app or a slave** – from `app.started` on. Console runs
  (`theron execute`) deliver none.
- Every callback gets **one `dict`** (a copy – change it freely). Every event has `"name"`.
- Callbacks run on the plugins' background loop (async) or in a worker thread (plain functions), one task per event –
  they may arrive in parallel. Exceptions are logged.
- **Own changes are not delivered back:** what the plugin changes through `ctx.tasklists` carries
  `"source": "plugin:<id>"` and doesn't reach the same plugin – unless it subscribed with `include_own=True`. Other
  plugins do get it (with that source).

## App

| Event | Payload | When |
|---|---|---|
| `app.started` | `{"name", "host"}` | Theron runs (window shown / slave listening), after the `on_start` callbacks were started |
| `app.stopping` | `{"name"}` | Theron quits, before the `on_stop` callbacks |
| `settings.changed` | `{"name", "keys": [changed keys]}` | the user saved the plugin's settings, or the plugin called `ctx.settings.update()`. Only delivered to the plugin the settings belong to. |

## Data changes

`<kind>.saved` and `<kind>.deleted` for `project`, `process`, `agent`, `tasklist`, `epic`, `requirement` – whoever made
the change: the user in the app, Theron's engine (e.g. a requirement's status while a task list runs), the local API,
the server sync or another plugin.

```python
{"name": "requirement.saved", "kind": "requirement", "id": 42, "source": "app",
 "data": {"id": 42, "epic_id": 7, "title": "Login page", "description": "…", "acceptance": "…", "tech_rules": "",
          "status": "in_progress", "result": "", "depends_on": [], "order": 3}}
```

| Key | Meaning |
|---|---|
| `kind` | `project`, `process`, `agent`, `tasklist`, `epic` or `requirement` |
| `id` | the entity's id |
| `data` | after `.saved`: the entity – see below; after `.deleted`: `None` |
| `source` | `"app"` (anyone but a plugin) or `"plugin:<id>"` |

`data` shapes:

| Kind | `data` |
|---|---|
| `tasklist`, `epic`, `requirement` | as returned by `ctx.tasklists` – see [Task lists & runs](data.md) |
| `project` | `{"id", "name", "description", "workspace", "process_id"}` |
| `process`, `agent` | `{"id", "name", "folder"}` |

`.saved` comes for new and changed entities alike – compare with what you stored if you need to know what changed.
Deleting a task list also deletes its epics and requirements; each of them fires its own `.deleted`.

## Runs (tasks)

| Event | Payload | When |
|---|---|---|
| `run.event` | `{"name", "run_id", "type", "event": {…}}` | every event of every run – what the cockpit shows; `event` is the original event with `id`, `run_id`, `ts`, `type` and its fields |
| `run.status` | `{"name", "run_id", "status", "phase"}` | a run's status changed |
| `run.finished` | `run.status` keys + `"summary"`, `"goal_reached"`, `"project_id"`, `"title"` | a run ended: status `done`, `failed` or `stopped` |

```python
@ctx.events.on("run.event")
def on_event(e):
    if e["type"] == "input_request":                 # Theron waits for the user
        forward_question(e["run_id"], e["event"]["question"], e["event"]["options"])
```

Run statuses: `idle`, `running`, `waiting_input`, `done`, `failed`, `stopped`. `goal_reached` is `True`, `False` or
`None` (not decided).

`run.event` `type`s and the main fields of `event` (other fields may be added at any time):

| `type` | Main fields |
|---|---|
| `user` | `text`, `source` – a message to Theron (the user, the API, a plugin `plugin:<id>`) |
| `orchestrator` | `text` – what Theron says in the chat |
| `status` | `status`, `phase` |
| `agent_start` / `agent_end` | `step`, `agent`, `task` / `result`, `verdict`, `error`, `cost_usd` |
| `agent_tool` | `step`, `agent`, `summary` – a tool call of an agent |
| `handover` | `step`, `name`, `items` |
| `routing`, `decision` | `text` / `name`, `condition` |
| `input_request` | `request_id`, `question`, `options`, `kind`, `recommended`, `details` – Theron waits for the user |
| `input_resolved` | `request_id`, `answer`, `source` |
| `alert` | `name`, `level`, `text`, `stop` – a ⚑ message node fired |
| `plugin` | `step`, `node`, `name`, `ok`, `text` – a plugin node finished |
| `requirement_start` / `requirement_done` / `requirement_status` | `title`, `requirement_id`, … |
| `complete` | `summary`, `goal_reached` |
| `error` | `text` |

`run.event` is busy (dozens of events per minute while agents work) – subscribe to `run.status` / `run.finished` when
they're enough.
