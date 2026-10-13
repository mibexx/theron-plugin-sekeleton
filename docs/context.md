# The context `ctx` – API reference

`register(ctx)` receives one `ctx` per plugin. It is the plugin's only interface to Theron. This page lists every
attribute and method of plugin API v1.

- [Identity & environment](#identity--environment)
- [`ctx.settings`](#ctxsettings)
- [`ctx.storage`](#ctxstorage)
- [`ctx.data_dir`](#ctxdata_dir)
- [`ctx.nodes`](#ctxnodes)
- [`ctx.tools`](#ctxtools)
- [`ctx.ui`](#ctxui)
- [`ctx.events`](#ctxevents)
- [Background work: `schedule`, `on_start`, `on_stop`, `spawn`](#background-work)
- [`ctx.tasklists`](#ctxtasklists)
- [`ctx.runs`](#ctxruns)
- [`ctx.ai`](#ctxai)
- [`ctx.http`](#ctxhttp)
- [Logging & notifications](#logging--notifications)
- [Translations: `ctx.tr`](#translations-ctxtr)
- [Errors](#errors)

---

## Identity & environment

| Attribute | Type | Value |
|---|---|---|
| `ctx.id` | `str` | the plugin's id from `plugin.toml` |
| `ctx.name` | `str` | its name |
| `ctx.version` | `str` | its version |
| `ctx.dir` | `pathlib.Path` | the installed plugin folder (read-only by convention – it is replaced on update) |
| `ctx.host` | `str` | `"desktop"`, `"slave"` or `"cli"` – see [lifecycle](lifecycle.md#hosts) |
| `ctx.language` | `str` | Theron's language: `"en"` or `"de"` |
| `ctx.theron_version` | `str` | e.g. `"0.14.0"` |
| `ctx.api_version` | `int` | `1` |
| `ctx.source` | `str` | `"plugin:<id>"` – how the plugin's own changes are marked in [events](events.md) |

---

## `ctx.settings`

The values of the settings declared in [`plugin.toml`](manifest.md#settings). Stored values win over the manifest's
defaults.

| Method | Returns | Description |
|---|---|---|
| `ctx.settings.all()` | `dict` | every setting: defaults merged with stored values |
| `ctx.settings.get(key, default=None)` | value | the value; `default` if the value is `None` or `""` and a default was given |
| `ctx.settings[key]` | value | the value (`None` for unknown keys) |
| `key in ctx.settings` | `bool` | whether the key is declared or stored |
| `ctx.settings.set(key, value)` | `None` | store one value |
| `ctx.settings.update({key: value, …})` | `None` | store several values; emits `settings.changed` to this plugin |
| `ctx.settings.missing()` | `list[str]` | labels of `required` settings that are still empty |
| `ctx.settings.on_change(fn)` | `fn` | shorthand for `ctx.events.on("settings.changed", fn)`; usable as a decorator |

A plugin may store values that aren't declared in the manifest (e.g. an OAuth refresh token); they just don't appear
in the dialog.

```python
if ctx.settings.missing():
    ctx.log(f"not configured yet: {', '.join(ctx.settings.missing())}")

@ctx.settings.on_change
def changed(event):
    if "board" in event["keys"]:
        restart_watch()
```

---

## `ctx.storage`

A small persistent key → value store for the plugin's own data – mappings, cursors, cached ids. Values are anything
JSON can hold (`dict`, `list`, `str`, numbers, `bool`, `None`); you get copies back. Separate per plugin, kept across
updates, deleted with “remove with its data”.

| Method | Returns | Description |
|---|---|---|
| `ctx.storage.get(key, default=None)` | value | stored value or `default` |
| `ctx.storage.set(key, value)` | `None` | store (replaces) |
| `ctx.storage.delete(key)` | `None` | remove one key |
| `ctx.storage.items(prefix="")` | `list[tuple[str, value]]` | all entries whose key starts with `prefix`, sorted by key |
| `ctx.storage.keys(prefix="")` | `list[str]` | the keys only |

Use prefixes to organise keys: `"card:abc123"`, `"req:42"`, `"cursor:board"`. Meant for thousands of small entries,
not for large files – use `ctx.data_dir` for those.

---

## `ctx.data_dir`

`pathlib.Path` – `plugin-data/<id>/` in Theron's data folder, created on first access. For files the plugin writes:
caches, exports, downloaded attachments. Kept across updates. The plugin's log `plugin.log` lives here too.

---

## `ctx.nodes`

### `ctx.nodes.register(kind, *, label, run, description="", icon="⬢", fields=None, outputs="success_failure", ai_hint="")`

Registers a process node. Returns its `NodeType`. Full guide: [Process nodes](nodes.md).

| Parameter | Type | Meaning |
|---|---|---|
| `kind` | `str` | id within the plugin: letters, digits, `-`, `_`. The node's full id is `"<plugin id>/<kind>"`. |
| `label` | `str` | name in the palette and on the node |
| `run` | callback `run(node)` | does the work; see [the `node` object](nodes.md#the-node-object) |
| `description` | `str` | tooltip / properties panel, also told to the orchestrator |
| `icon` | `str` | one character or emoji shown before the label |
| `fields` | `list[dict]` | the node's settings in the editor – see [fields](nodes.md#fields) |
| `outputs` | `str` | `"success_failure"` (✔ and ✖) or `"success"` (✔ only) |
| `ai_hint` | `str` | when Theron's AI designer and the orchestrator should use the node |

Raises `PluginError` for an invalid `kind`, `outputs` or field definition.

---

## `ctx.tools`

### `ctx.tools.register(name, *, description, run, params=None)`

Registers a tool for Claude agents. Returns its `ToolSpec`. Full guide: [Tools for agents](tools.md).

| Parameter | Type | Meaning |
|---|---|---|
| `name` | `str` | letters, digits, `_` |
| `description` | `str` | what the tool does – the agent decides by it |
| `run` | callback `run(args: dict) -> str` | the tool's work; its return value is the agent's result |
| `params` | `dict` | the arguments – see [parameter schemas](tools.md#parameters) |

---

## `ctx.ui`

Desktop only – check `ctx.ui.available` first. Full guide: [Pages & settings UI](ui.md).

| Member | Description |
|---|---|
| `ctx.ui.available` | `True` in the desktop app (`ctx.host == "desktop"`) |
| `ctx.ui.add_page(title, factory, *, icon="", id="")` | a navigation entry; `factory(ctx)` returns a `QWidget`, called once when the window is built (on the UI thread). Ignored outside the desktop app. |
| `ctx.ui.settings_page(factory)` | extra settings UI below the generated fields; `factory(ctx)` returns a `QWidget`, optionally with a `save()` method called when the user saves |
| `ctx.ui.call(fn, *args)` | run `fn(*args)` on the UI thread (asynchronously, returns immediately). Raises `PluginError` without a window. |
| `ctx.ui.open_url(url)` | open a link in the user's browser (falls back to the system browser module without a window) |

---

## `ctx.events`

### `ctx.events.on(name, fn=None, *, include_own=False)`

Calls `fn(event)` for every event `name` – or for all events with `"*"`. Without `fn` it returns a decorator.
Changes made by this plugin itself are not delivered unless `include_own=True`. Raises `PluginError` for unknown
event names. All names and payloads: [Events](events.md).

```python
@ctx.events.on("run.finished")
async def finished(event): ...

ctx.events.on("requirement.saved", on_requirement)
```

Events are delivered only while Theron runs as the app or a slave (after `app.started`).

---

## Background work

| Method | Returns | Description |
|---|---|---|
| `ctx.schedule(every, fn, *, first=None)` | `Job` | call `fn()` every `every` seconds (minimum 5), the first time after `first` seconds (default: `every`). Runs in the app and on a slave only. Raises `PluginError` below 5 seconds. |
| `ctx.on_start(fn)` | `fn` | call `fn()` once Theron runs (window shown / slave listening). Usable as a decorator. |
| `ctx.on_stop(fn)` | `fn` | call `fn()` when Theron quits (all stop callbacks together get 5 seconds). Usable as a decorator. |
| `ctx.spawn(fn, *args)` | `concurrent.futures.Future` | run `fn(*args)` (async or plain) in the background now – e.g. after a button click. Exceptions are logged; the future then has the result `None`. Works in every host. |

`Job`:

| Member | Description |
|---|---|
| `job.cancel()` | stop the schedule |
| `job.every`, `job.first` | the intervals (seconds) |
| `job.last_run` | time of the last run (`time.time()`) or `None` |
| `job.last_error` | text of the last exception, `""` after a successful run |

A job's next run starts `every` seconds after the previous one finished – runs never overlap. An exception is logged
and doesn't stop the schedule.

---

## `ctx.tasklists`

Projects → task lists → epics → requirements. Data shapes: [Task lists & runs](data.md). Changes made here appear in
Theron's TASKS page at once and fire events for everyone except this plugin.

| Method | Returns | Description |
|---|---|---|
| `projects()` | `list[dict]` | all projects: `{"id", "name", "workspace"}` |
| `list(project_id=None)` | `list[dict]` | task lists (of one project or all), temporary lists left out |
| `get(tasklist_id)` | `dict \| None` | one list with `"epics"`, each with `"requirements"` |
| `find(project_id, name)` | `dict \| None` | a list of the project by name (case-insensitive) |
| `create(project_id, name, description="")` | `int` | new task list; `PluginError` if the project doesn't exist |
| `update(tasklist_id, **fields)` | `dict` | change `name`, `description`, `process_id` (other fields are ignored) |
| `delete(tasklist_id)` | `None` | delete the list with its epics and requirements |
| `epic(epic_id)` | `dict \| None` | one epic |
| `add_epic(tasklist_id, name, description="", depends_on=None)` | `int` | new epic; `depends_on` = ids of epics that must be done first |
| `update_epic(epic_id, **fields)` | `dict` | change `name`, `description`, `depends_on`, `closed`, `status` |
| `delete_epic(epic_id)` | `None` | delete the epic with its requirements |
| `requirement(requirement_id)` | `dict \| None` | one requirement |
| `add_requirement(epic_id, title, description="", acceptance="", status="open", depends_on=None)` | `int` | new requirement; `PluginError` for an unknown epic or status |
| `update_requirement(requirement_id, **fields)` | `dict` | change `title`, `description`, `acceptance`, `tech_rules`, `status`, `result`, `depends_on` |
| `delete_requirement(requirement_id)` | `None` | delete it |

`update*` raise `KeyError` for an unknown id; `PluginError` for an unknown status. Statuses: `open`, `in_progress`,
`hitl`, `done`, `failed`, `skipped`, `closed`.

---

## `ctx.runs`

Tasks (“runs”) – what Theron works on with a project's process.

| Method | Returns | Description |
|---|---|---|
| `get(run_id)` | `dict \| None` | one run – [shape](data.md#run) |
| `list(project_id=None)` | `list[dict]` | top-level runs (of one project or all) |
| `start(project_id, text, title="", process_id=None)` | `int` | start a task: `text` is the user's request, `process_id` another process than the project's. Needs the engine (app or slave; not in the app while it controls a slave). Raises `PluginError` if the project doesn't exist or has no process. |
| `message(run_id, text)` | `None` | a message to Theron in that run, as if the user typed it |

The request of a run started by a plugin is marked with the source `plugin:<id>` (the run's `user` event).

---

## `ctx.ai`

### `await ctx.ai.ask(prompt, system="", model="haiku") -> str`

One answer of the AI model, without tools. Uses Theron's core model: Claude via the user's subscription (`model`:
`"haiku"`, `"sonnet"`, `"opus"`) – or, if the user set a local core model, that model (then `model` is ignored). On a
slave the slave's login is used. Raises on errors (no login, network) – catch them.

Each call counts against the user's Claude usage – prefer `"haiku"` and short prompts.

---

## `ctx.http`

An async HTTP client built on Python's standard library (works in every Theron build). It never raises for HTTP error
statuses – check `response.ok` or call `raise_for_status()`; it raises for network errors (`urllib.error.URLError`,
`TimeoutError`).

| Method | Description |
|---|---|
| `await ctx.http.request(method, url, *, params=None, headers=None, json=None, data=None, timeout=None)` | any request |
| `await ctx.http.get(url, **kw)` / `post` / `put` / `patch` / `delete` | shorthands |

| Argument | Meaning |
|---|---|
| `params` | query parameters (`None` values left out; lists repeat the key) |
| `headers` | extra headers; default `User-Agent: Theron/<version> <plugin id>/<version>`, `Accept: application/json, */*` |
| `json` | body as JSON (sets `Content-Type: application/json`) |
| `data` | body: `dict` → form-encoded, `str` → UTF-8, `bytes` as they are |
| `timeout` | seconds (default 30) |

`Response`:

| Member | Description |
|---|---|
| `status` | HTTP status (`int`) |
| `ok` | `True` for 2xx |
| `headers` | `dict` |
| `content` | body (`bytes`) · `text` – body as text · `json()` – parsed JSON |
| `url` | the final URL |
| `raise_for_status()` | returns the response for 2xx, raises `HttpError` (with `.response`) otherwise |

TLS certificates are checked against the certificates bundled with Theron. You may use another client instead
(e.g. from `lib/`), but `ctx.http` needs no dependencies.

---

## Logging & notifications

| Member | Description |
|---|---|
| `ctx.log(text)` | a line in the plugin's log |
| `ctx.log.error(text)` | a line marked `ERROR` |
| `ctx.log.exception(text="")` | `ERROR` plus the current traceback – call it in an `except` block |
| `ctx.notify(text, level="info")` | a short note for the user: a toast in the app (bottom right, 7 s; 12 s for warnings/errors), the log elsewhere. `level`: `"info"`, `"warning"`, `"error"` |

The log: Settings → Plugins → *Log* (last 300 lines) and `plugin-data/<id>/plugin.log` (rotated at 2 MB). On a slave and
in console runs the lines are also printed to the console. Unhandled exceptions in callbacks, nodes, tools and jobs are
logged automatically with their traceback.

---

## Translations: `ctx.tr`

### `ctx.tr(text, **values) -> str`

Write texts in English and translate them in `i18n/<language>.json` (`{"English": "Deutsch"}`). `ctx.tr` returns the
translation for `ctx.language` (or the text itself) and fills `{placeholders}` with `str.format`:

```python
ctx.tr("Synced {count} cards", count=12)      # "12 Karten synchronisiert" with i18n/de.json
```

The labels and descriptions of the manifest's settings and of node fields shown in the editor are translated the same
way. Theron's language changes only with a restart, so you may translate once in `register`.

---

## Errors

| Exception | When |
|---|---|
| `PluginError` (a `RuntimeError`) | invalid registrations, unknown ids/statuses in `ctx.tasklists`, `ctx.runs.start` without engine, `ctx.ui.call` without a window |
| `HttpError` (a `RuntimeError`) | `Response.raise_for_status()` for non-2xx |
| `KeyError` | `ctx.tasklists.update_*` with an unknown id |

You don't need to import them – catch `RuntimeError` / `Exception`. Exceptions escaping from your callbacks never break
Theron: they are logged, a failing node asks the user, a failing tool returns an error text to the agent.
