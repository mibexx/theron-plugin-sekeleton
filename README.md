# Theron Plugin Skeleton

A starting point for your own [Theron](https://theron.mibexx.de) plugin – with working examples for everything a plugin
can add to Theron: a page in the navigation, settings, process nodes, a tool for agents, event handlers and a two-way
**task-list ↔ Trello** sync you can adapt to Jira, GitHub Issues, Linear or any other service.

**Theron** orchestrates AI agents (Claude Code, OpenCode) in visual processes. Plugins extend it without waiting for a
new release.

📖 Full documentation: **[theron.mibexx.de/docs-plugins.html](https://theron.mibexx.de/docs-plugins.html)** ·
⬇ Download Theron: **[theron.mibexx.de](https://theron.mibexx.de/#download)**

---

## Contents

- [What a plugin can do](#what-a-plugin-can-do)
- [Quick start](#quick-start)
- [Layout of this skeleton](#layout-of-this-skeleton)
- [Make it yours](#make-it-yours)
- [Examples](#examples)
  - [Process nodes](#process-nodes)
  - [A page in the navigation](#a-page-in-the-navigation)
  - [Settings](#settings)
  - [Integrations: syncing task lists](#integrations-syncing-task-lists)
  - [Tools for agents](#tools-for-agents)
  - [Events and schedules](#events-and-schedules)
- [The plugin API at a glance](#the-plugin-api-at-a-glance)
- [Test without Theron](#test-without-theron)
- [Pack, sign and install](#pack-sign-and-install)
- [Security](#security)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## What a plugin can do

| Extension | What it is | In this skeleton |
|---|---|---|
| **Navigation entry with UI** | A page of its own in Theron's sidebar (a PySide6 widget). | [`my_plugin/pages.py`](my_plugin/pages.py) |
| **Settings** | Declared in `plugin.toml`; Theron builds the dialog. Optional custom UI below it. | [`plugin.toml`](plugin.toml), [`my_plugin/settings_page.py`](my_plugin/settings_page.py) |
| **Process nodes** | New nodes in the process editor – with fields, ✔ / ✖ outputs, used by Theron's AI process designer. | [`my_plugin/nodes.py`](my_plugin/nodes.py) |
| **Integrations** | Talk to other services: read and change task lists, react to events, run on a schedule, HTTP. | [`my_plugin/integrations/`](my_plugin/integrations) |
| **Tools for agents** | Extra tools every Claude agent can call while it works. | [`my_plugin/tools.py`](my_plugin/tools.py) |
| **Events** | React to finished tasks, changed requirements, settings … | [`my_plugin/events.py`](my_plugin/events.py) |

Plugins run in the Theron desktop app, on a Theron slave (`theron --listen`), in the headless Docker worker and in
console runs (`theron execute`). Pages and settings UI exist only in the desktop app; nodes, tools, events and
schedules work everywhere a process runs.

## Quick start

You need **Theron 0.14.0 or newer** and Python 3.11+ for development.

```bash
git clone https://github.com/mibexx/theron-plugin my-plugin
cd my-plugin
pip install pytest            # tests run without Theron (devkit/)
python -m pytest              # all green? then:
python scripts/pack.py        # → dist/my-plugin-0.1.0.theronplugin
```

Install the package in Theron: **Settings → Plugins → “Upload plugin …”** and pick the file – or in a terminal:

```bash
theron plugin install dist/my-plugin-0.1.0.theronplugin
```

Restart Theron. You'll find **MY PLUGIN** in the navigation, three new nodes in the process editor under **TOOLS**
(Summarize, Check, Import from Trello) and the plugin's settings under **Settings → Plugins → Settings …**.

## Layout of this skeleton

```
my-plugin/
├── plugin.toml                manifest: id, version, permissions, settings
├── my_plugin/                 the plugin's Python package
│   ├── __init__.py            register(ctx) – wires everything together
│   ├── nodes.py               process nodes
│   ├── pages.py               a navigation page (desktop only)
│   ├── settings_page.py       extra settings UI (desktop only)
│   ├── tools.py               tools for agents
│   ├── events.py              event handlers
│   └── integrations/
│       ├── adapter.py         Adapter interface + RemoteItem
│       ├── sync.py            TaskListSync – generic two-way sync
│       ├── trello.py          Trello adapter (complete)
│       └── template.py        placeholders for your own service
├── i18n/de.json               translations of the plugin's texts (English is the source)
├── lib/                       pure-Python dependencies (pip install --target lib …)
├── devkit/                    a stand-in Theron for tests        ┐
├── tests/                     pytest                              │ not packed
├── scripts/pack.py            pack and sign without Theron        │ (.theronignore)
└── .theronignore              what stays out of the package       ┘
```

## Make it yours

1. **Rename** – in `plugin.toml` set `id` (lower case, digits, `-`), `name`, `author`, `homepage`; rename the folder
   `my_plugin/` and set `entry` to the new folder name.
2. **Delete what you don't need** – every part in `register()` is independent. A plugin may be as small as one node.
3. **Permissions** – list what your plugin uses (`network`, `tasklists`, `runs`, `agent-tools`, `ui`, `files`, `ai`).
   Theron shows them before installing.
4. **Version** – raise `version` for every release; installing a higher version replaces the old one, settings and
   data stay.

A minimal plugin is just two files:

```toml
# plugin.toml
id = "hello"
name = "Hello"
version = "0.1.0"
theron_api = 1
entry = "hello"
```

```python
# hello/__init__.py
def register(ctx):
    ctx.nodes.register("hello", label="Say hello", outputs="success",
                       run=lambda node: f"Hello – {len(node.handovers)} hand-overs came in.")
```

## Examples

### Process nodes

A node gets the incoming hand-overs and its configuration and reports success (✔) or failure (✖). Its fields appear
in the editor's properties panel; `ai_hint` tells Theron's AI process designer when to use it.

```python
async def check(node):
    rule = node.config["rule"]
    answer = await ctx.ai.ask(f"Rule: {rule}\n\n{node.input}\n\nAnswer YES or NO.")
    return node.success(answer) if answer.upper().startswith("YES") else node.failure(answer)

ctx.nodes.register(
    "check", label=ctx.tr("Check"), icon="✓", run=check,
    description=ctx.tr("Checks the hand-overs against a rule – ✔ if it holds, ✖ if not."),
    ai_hint="A yes/no gate, e.g. 'the result contains a price'",
    fields=[{"key": "rule", "type": "textarea", "label": ctx.tr("Rule")}],
    outputs="success_failure")          # or "success" for a node with ✔ only
```

What `node` brings:

| | |
|---|---|
| `node.config` | the field values set in the editor (with defaults) |
| `node.input` | everything that came in as one text (hand-overs + the current requirement) |
| `node.handovers` | the hand-overs one by one: `[{"from", "text", "verdict"}]` |
| `node.task`, `node.instructions` | the run's task, the step's instructions |
| `node.project` | `{"id", "name", "workspace"}` – the folder the agents work in |
| `node.tasklist_id` | a task list handed over by the previous step |
| `node.progress(text)` | status line on the node's card |
| `node.success(text, tasklist_id=None)` / `node.failure(text)` | the result – `tasklist_id` hands a list on, e.g. to a loop |

Field types: `text`, `textarea`, `number`, `bool`, `choice` (with `options`), `tasklist`, `project`.

### A page in the navigation

```python
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

class BoardPage(QWidget):
    def __init__(self, ctx):
        super().__init__()
        lay = QVBoxLayout(self)
        title = QLabel("MY BOARD")
        title.setObjectName("h1")                       # Theron's styles: h1, h2, dim, mono; buttons: primary, ghost, danger
        lay.addWidget(title)
        button = QPushButton("Refresh")
        button.clicked.connect(lambda: ctx.spawn(refresh))   # work in the background …
        lay.addWidget(button)

async def refresh():
    data = await ctx.http.get("https://example.com/api/items")
    ctx.ui.call(show, data.json())                      # … and back on the UI thread

if ctx.ui.available:                                    # desktop app only – no PySide6 on a slave
    ctx.ui.add_page("Board", BoardPage, icon="▦")
```

### Settings

Declare them in `plugin.toml` – Theron builds the dialog, stores the values and passes them to the plugin:

```toml
[[settings]]
key = "trello_board"
type = "text"                 # text, secret, textarea, number, bool, choice, tasklist, project
label = "Trello board id"
description = "The id in the board URL: trello.com/b/<id>/…"
required = true
```

```python
board = ctx.settings["trello_board"]
ctx.settings.on_change(lambda event: ctx.log(f"changed: {event['keys']}"))
```

Need more than fields (a “Test connection” button, an OAuth login …)? Add a widget below them with
`ctx.ui.settings_page(factory)` – see [`settings_page.py`](my_plugin/settings_page.py).

### Integrations: syncing task lists

[`integrations/sync.py`](my_plugin/integrations/sync.py) keeps a Theron task list and a service in step – in both
directions or one way, with change detection and a mapping stored in `ctx.storage`. Service items become
requirements, their groups (Trello lists) become epics. A service only needs an **adapter**:

```python
class JiraAdapter(Adapter):
    name = "jira"

    def configured(self):
        return bool(self.ctx.settings.get("jira_url") and self.ctx.settings.get("jira_token"))

    async def fetch(self):
        resp = await self.ctx.http.get(f"{self.ctx.settings['jira_url']}/rest/api/3/search",
                                       params={"jql": self.ctx.settings["jira_jql"]}, headers=self._auth())
        return [RemoteItem(id=i["key"], title=i["fields"]["summary"], status=status_of(i), group=epic_of(i))
                for i in resp.raise_for_status().json()["issues"]]

    async def create(self, title, description, status, group): ...
    async def update(self, item_id, title, description, status): ...
    async def test(self): ...
```

```python
sync = TaskListSync(ctx, JiraAdapter(ctx))
ctx.schedule(5 * 60, sync.run_if_configured)                   # service → Theron every 5 minutes
ctx.events.on("requirement.saved", lambda e: sync.push_requirement(e["id"]))   # Theron → service right away
```

[`trello.py`](my_plugin/integrations/trello.py) is a complete adapter; [`template.py`](my_plugin/integrations/template.py)
has placeholders (`TODO`) for your own service. Changes the plugin makes through `ctx.tasklists` don't fire events back
at it, so a sync never loops.

### Tools for agents

```python
async def add_requirement(args):
    rid = ctx.tasklists.add_requirement(args["epic_id"], args["title"], args.get("description", ""))
    return f"requirement {rid} added"

ctx.tools.register("add_requirement", description="Add follow-up work to a Theron task list",
                   params={"epic_id": "integer", "title": "string",
                           "description": {"type": "string", "optional": True}},
                   run=add_requirement)
```

Claude agents see it as `mcp__theron_plugins__my_plugin__add_requirement`.

### Events and schedules

```python
@ctx.events.on("run.finished")
def finished(event):
    ctx.notify(f"Task “{event['title']}” finished")      # a toast in the app

ctx.schedule(15 * 60, poll_inbox, first=30)            # every 15 minutes, first after 30 s
ctx.on_start(lambda: ctx.log("running"))
ctx.on_stop(close_connections)
```

Events: `app.started`, `app.stopping`, `settings.changed`, `run.event`, `run.status`, `run.finished` and
`<kind>.saved` / `<kind>.deleted` for `project`, `process`, `agent`, `tasklist`, `epic`, `requirement`.
Schedules, `on_start` and events run in the app and on a slave – not in a single `theron execute` run.

## The plugin API at a glance

Everything a plugin does goes through `ctx` – the only interface to Theron, stable within an API version
(`theron_api = 1`).

| `ctx.…` | |
|---|---|
| `settings` | `get(key)`, `[key]`, `set(key, value)`, `update({…})`, `on_change(fn)` |
| `storage` | small persistent key → JSON store: `get`, `set`, `delete`, `keys(prefix)`, `items(prefix)` |
| `data_dir` | a folder of its own for files, kept across updates |
| `nodes.register(…)` | a process node |
| `tools.register(…)` | a tool for Claude agents |
| `ui` | `available`, `add_page`, `settings_page`, `call(fn)` (UI thread), `open_url` |
| `events.on(name, fn)` | react to events (decorator or call) |
| `schedule(seconds, fn, first=)`, `on_start`, `on_stop`, `spawn(fn)` | background work |
| `tasklists` | `projects`, `list`, `get`, `find`, `create`, `update`, `delete`, `add_epic`, `update_epic`, `delete_epic`, `add_requirement`, `update_requirement`, `delete_requirement`, `epic`, `requirement` |
| `runs` | `start(project_id, text, title=)`, `get`, `list`, `message` |
| `ai.ask(prompt, system=, model="haiku")` | one answer of the AI model – the user's Claude subscription or Theron's local core model |
| `http` | async `get`, `post`, `put`, `patch`, `delete` → `.status`, `.json()`, `.text`, `.raise_for_status()` |
| `log(text)`, `log.error`, `log.exception`, `notify(text, level)` | log (Settings → Plugins → Log) and toasts |
| `tr(text, **values)` | translation from `i18n/<language>.json` |
| `id`, `name`, `version`, `host`, `language`, `theron_version`, `dir` | environment – `host` is `desktop`, `slave` or `cli` |

Callbacks can be `async` or plain functions; plain ones run in a worker thread and may block.
Reference with all details: [theron.mibexx.de/docs-plugins.html](https://theron.mibexx.de/docs-plugins.html#en-pl-api).

**Python & dependencies:** plugins ship as source and run on the Python inside Theron (3.12+), the whole standard
library included. There is no `pip` inside Theron – put pure-Python libraries into `lib/`
(`pip install --target lib PACKAGE`); libraries with native code don't work. Use relative imports inside the plugin
(`from .integrations.sync import TaskListSync`).

## Test without Theron

[`devkit/fake_theron.py`](devkit/fake_theron.py) is a stand-in `ctx` that behaves like Theron's API – in memory, with
a fake HTTP client, a fake AI and an in-memory task-list store:

```python
from devkit import FakeContext, load_plugin

ctx = FakeContext.from_plugin(ROOT)            # settings defaults from plugin.toml
load_plugin(ctx, ROOT)                         # imports my_plugin and calls register(ctx)

ctx.ai.answer = lambda prompt, system, model: "YES – it has a price"
result = await ctx.run_node("check", config={"rule": "contains a price"}, handovers=[{"text": "… 49 € …"}])
assert result.ok

ctx.http.route("GET", "/cards", [{"id": "C1", "name": "Login", "idList": "L1"}])
await ctx.emit("requirement.saved", {"id": 3, "data": {...}})
```

```bash
python -m pytest
```

## Pack, sign and install

**Pack** – files listed in [`.theronignore`](.theronignore) (tests, devkit, scripts …) stay out:

```bash
python scripts/pack.py --check      # which files go in
python scripts/pack.py              # → dist/<id>-<version>.theronplugin
# or with Theron installed:
theron plugin pack .
```

**Sign** (recommended) – Theron then shows who built the plugin and refuses it if anything was changed afterwards:

```bash
pip install cryptography
python scripts/pack.py --keygen ~/.theron-signing.key      # once – keep the .key file secret
python scripts/pack.py --sign ~/.theron-signing.key
# on every machine that should trust your plugins:
theron plugin trust "<your public key>" --name "Your name"
```

**Install**

| Where | How |
|---|---|
| Desktop app | Settings → Plugins → “Upload plugin …” |
| Terminal / slave | `theron plugin install dist/<file>.theronplugin` |
| Headless Docker worker | put the file into `/data/plugin-packages/` (installed at every start) or `docker exec <container> theron plugin install /data/<file> --yes` |

Restart Theron afterwards. A plugin node runs where the process runs – if your app controls a slave, install the
plugin on the slave too. Manage plugins with `theron plugin list | info | enable | disable | remove`.

## Security

Plugins run **inside** Theron with the same rights as Theron itself – Python can't be sandboxed. The permissions in
`plugin.toml` are shown to the user before installing, but they are information, not a lock. So:

- sign your releases and publish your public key,
- keep secrets in `type = "secret"` settings, never in the code,
- only talk to the services your plugin is about.

Theron shows a plugin as **✔ verified** (trusted key), **signed** (unknown key, unchanged), **not signed**, or refuses
it as **invalid** (changed after signing). A plugin that fails while loading is switched off; Theron keeps running.

## Troubleshooting

- **Log:** Settings → Plugins → Log, or `plugin-data/<id>/plugin.log` in Theron's data folder. On a slave the lines go
  to the console, too.
- **“doesn't fit this Theron version”** – `theron_api` / `min_theron` in `plugin.toml` don't match: update Theron.
- **Theron won't start because of a plugin** – start it with `--no-plugins` (or `THERON_NO_PLUGINS=1`) and switch the
  plugin off. A plugin that crashed Theron while loading is switched off automatically at the next start.
- **ImportError on a slave or in Docker** – PySide6 only exists in the desktop app; import UI modules inside
  `if ctx.ui.available:` as this skeleton does.

## License

MIT – see [LICENSE](LICENSE). Your plugin may use any license you like.
