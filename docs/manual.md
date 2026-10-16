# The Theron plugin manual

Step-by-step guides for the things plugins do most. Each chapter starts from an empty `register(ctx)` and ends with
working code; the complete reference of every call is in [context.md](context.md). Needs Theron **0.16.0** or newer
for chapters 3, 8 and 9, **0.17.0** for chapter 10 (`min_theron` in `plugin.toml`).

1. [Add a page](#1-add-a-page)
2. [Add a process node](#2-add-a-process-node)
3. [Add windows to Theron's pages](#3-add-windows-to-therons-pages)
4. [Extend buttons and forms](#4-extend-buttons-and-forms)
5. [Work with task lists](#5-work-with-task-lists)
6. [React to events](#6-react-to-events)
7. [Emit events of your own](#7-emit-events-of-your-own)
8. [React to transactions](#8-react-to-transactions)
9. [Read the running agents and their logs](#9-read-the-running-agents-and-their-logs)
10. [Extend the chat](#10-extend-the-chat)

Two rules apply everywhere:

- **UI only in the app.** Pages, panels, windows, buttons and dialogs exist in the desktop app only. Wrap them in
  `if ctx.ui.available:` and import PySide6 inside that branch – a slave and the headless Docker image have no PySide6.
- **The UI thread.** Widgets, button callbacks and dialogs run on the UI thread. Never block it: start slow work with
  `ctx.spawn(fn, …)` and hand results back with `ctx.ui.call(fn, …)`.

---

## 1. Add a page

A page is an entry in Theron's navigation with a PySide6 widget of its own.

```python
# my_plugin/__init__.py
def register(ctx):
    if ctx.ui.available:
        from .pages import BoardPage
        ctx.ui.add_page(ctx.tr("Board"), BoardPage, icon="▦", id="board")
```

```python
# my_plugin/pages.py
from PySide6.QtWidgets import QLabel, QListWidget, QPushButton, QVBoxLayout, QWidget


class BoardPage(QWidget):
    def __init__(self, ctx):                       # the factory gets ctx
        super().__init__()
        self.ctx = ctx
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 28, 28, 28)
        title = QLabel(ctx.tr("Board").upper())
        title.setObjectName("h1")                  # Theron's styles: h1, h2, dim, mono; buttons primary, ghost, danger
        self.items = QListWidget()
        load = QPushButton(ctx.tr("Load"))
        load.setObjectName("primary")
        load.clicked.connect(self.load)
        for w in (title, self.items, load):
            lay.addWidget(w)

    def load(self):
        future = self.ctx.spawn(fetch_cards, self.ctx)                      # background thread / loop
        future.add_done_callback(lambda f: self.ctx.ui.call(self.show, f.result() or []))

    def show(self, cards):                                                  # back on the UI thread
        self.items.clear()
        self.items.addItems([c["name"] for c in cards])
```

- `title` is the navigation entry (shown in capitals after Theron's pages), `icon` one character before it.
- `id` names the page for panels and buttons of other plugins: `"<plugin id>/<id>"`, here `"my-plugin/board"`.
- The factory runs once when the window is built. If it raises, the page shows the error; the traceback is in the
  plugin's log (Settings → Plugins → *Log*).

---

## 2. Add a process node

A node appears in the process editor's palette like Theron's own and runs when a process reaches it.

```python
def register(ctx):
    async def check(node):
        text = "\n\n".join(h["text"] for h in node.handovers)   # what the previous steps handed over
        node.progress(ctx.tr("Checking …"))                    # shown in the cockpit
        verdict = await ctx.ai.ask(f"Does this contain a price? Answer YES or NO.\n\n{text}", model="haiku")
        if verdict.strip().upper().startswith("YES"):
            return node.success(text)                           # → the ✔ output, the text goes along
        return node.failure(ctx.tr("No price found."))          # → the ✖ output

    ctx.nodes.register("check-price", label=ctx.tr("Check price"), icon="€", run=check,
                       description=ctx.tr("Goes on via ✔ if the input contains a price."),
                       ai_hint="Checks a text for a price – use after research steps")
```

**Fields.** `fields=[{"key": "rule", "type": "text", "label": "Rule", "default": "…"}]` adds settings to the node
(types `text`, `textarea`, `number`, `bool`, `choice`, `tasklist`, `project`); read them as `node.config["rule"]`.

**More outputs and inputs** – a switch that routes, a merge that waits:

```python
def cases(config):                       # outputs from the node's own settings
    return [{"id": c.strip().lower(), "label": c.strip()} for c in config["cases"].split(",")] + ["other"]

async def route(node):
    text = " ".join(h["text"] for h in node.handovers).lower()
    hit = next((o["id"] for o in node.outputs if o["id"] in text), "other")
    return node.route(hit, f"matched {hit}")                    # one id or a list of ids

ctx.nodes.register("switch", label="Keyword switch", run=route, outputs=cases,
                   fields=[{"key": "cases", "type": "text", "default": "Bug, Feature"}])

ctx.nodes.register("merge", label="Merge", outputs="success", wait="all",
                   inputs=[{"id": "code", "label": "Code"}, {"id": "docs", "label": "Docs"}],
                   run=lambda node: node.success(node.inputs["code"][0]["text"] + "\n\n" + node.inputs["docs"][0]["text"]))
```

`outputs`: `"success_failure"` (✔/✖, default), `"success"` (✔ only), a list of ids / `{"id", "label"}` or a function of
the settings. `inputs`: none (one input) or a list – `wait="all"` waits for every connected input, `"any"` runs on the
first. Everything about nodes: [nodes.md](nodes.md).

---

## 3. Add windows to Theron's pages

### Panels – a window next to or below a page

```python
def register(ctx):
    if ctx.ui.available:
        from .panels import RunInfo
        ctx.ui.add_panel("cockpit", ctx.tr("Run info"), RunInfo, id="run-info", icon="ⓘ")
        ctx.ui.add_panel(["processes", "agents"], ctx.tr("Hints"), Hints, area="bottom", collapsed=True)
```

```python
class RunInfo(QWidget):
    def __init__(self, view):                     # a panel's factory gets the view
        super().__init__()
        self.view, self.ctx = view, view.ctx
        self.label = QLabel()
        QVBoxLayout(self).addWidget(self.label)
        view.on_context(self.show)                # the page shows something else
        self.show(view.context)

    def show(self, context):
        run = self.ctx.runs.get(context["run_id"]) if context.get("run_id") else None
        self.label.setText(run["title"] if run else self.ctx.tr("No task open."))
```

- **Pages:** `cockpit`, `theron`, `projects`, `processes`, `agents`, `tasks`, `databases`, `jobs` *(0.23)*, a plugin's page
  (`"my-plugin/board"`), a list of them or `"*"` for every page.
- **`area`:** `"right"` (a column next to the page) or `"bottom"` (a row below it). Several panels stack, sorted by
  `order`; the user drags the splitters and folds panels (▾/▸) – Theron remembers both.
- **`view.context`** – what the page shows:

| Page | `view.context` |
|---|---|
| `cockpit`, `theron` | `{"page", "project_id", "run_id"}` |
| `projects` | `{"page", "project_id"}` |
| `processes` | `{"page", "process_id"}` |
| `agents` | `{"page", "agent_id"}` |
| `tasks` | `{"page", "project_id", "tasklist_id"}` |
| `databases` | `{"page", "database"}` |
| `jobs` | `{"page", "job_id"}` *(0.23)* |
| a plugin page | `{"page"}` |

- `view.on_context(fn)` – `fn(context)` whenever that changes. `view.set_title(text)`, `view.set_visible(bool)`.

### Windows of their own

```python
ctx.ui.open_window(ctx.tr("Live log"), lambda view: LiveLog(view, run_id), id=f"log-{run_id}", width=760, height=520)
ctx.ui.close_window(f"log-{run_id}")
```

A plugin window is not modal and stays open next to Theron. Opening the same `id` again brings it to the front.
`open_window` works from any thread (an event, a schedule); `view.context` is what the page in front shows.

---

## 4. Extend buttons and forms

### Buttons on pages – `ctx.ui.add_action`

```python
def register(ctx):
    if not ctx.ui.available:
        return

    def export(context):                                   # on the UI thread
        tl = ctx.tasklists.get(context["tasklist_id"])
        ...

    ctx.ui.add_action("tasks", lambda c: ctx.tr("Export") if c.get("tasklist_id") else None, export,
                      id="export", icon="⇩", style="primary")
```

| `place` | Where | Pages |
|---|---|---|
| `"top"` (default) | the page's tool bar – or a bar above the page | every page |
| `"chat"` | next to “Send” | `cockpit`, `theron` |
| `"new"` | next to “+ New …” | `agents`, `processes`, `projects` |
| `"lists"` | below the task lists | `tasks` |
| `"items"` | next to “+ Epic / + Requirement” | `tasks` |
| `"sidebar"` | Theron's sidebar, one button for all pages | `"*"` |

- `label` is text or `label(context)` → text, or `None` to hide the button. Theron asks again when the page shows
  something else and after a click; `ctx.ui.refresh_actions()` asks right away (e.g. when background work is done).
- `run(context)` gets the same context as panels; in the chat also `context["input"]` – the text typed so far.
- `style`: `ghost`, `primary` or `danger`.

**Small dialogs** (UI thread): `ctx.ui.ask_text(title, text, default="", suggestions=None)` → str or None (`suggestions`: a list to pick from, typing stays possible – 0.19.1),
`ctx.ui.ask_choice(title, text, options)` → the chosen option or None, `ctx.ui.message(title, text, level)`.
**The chat input:** `ctx.ui.chat_input(page="cockpit")`, `ctx.ui.set_chat_input(text, page="cockpit", append=False)`.

A complete flow – ask, work in the background, ask again, finish:

```python
def clicked(context):
    tid = context["tasklist_id"]
    board = ctx.ui.ask_text("Sync with Trello", "Board id or link:")
    if not board:
        return
    future = ctx.spawn(inspect_board, tid, board)                       # network: not on the UI thread
    future.add_done_callback(lambda f: ctx.ui.call(inspected, tid, f.result()))

def inspected(tid, found):                                              # UI thread again
    choice = ctx.ui.ask_choice("Sync with Trello", found["text"], ["Read", "Write"])
    if choice:
        ctx.storage.set(f"link:{tid}", {"board": found["id"], "direction": choice.lower()})
        ctx.ui.refresh_actions()                                        # the button becomes “⟳ Sync”
```

The *Trello Sync* plugin in [theron-plugins](https://github.com/mibexx/theron-plugins) is this flow in full.

### Fields in Theron's forms – `ctx.fields`

```python
ctx.fields.add("agent", "jira_user", label=ctx.tr("Jira user"), description="…")
ctx.fields.add("project", "customer", label="Customer", type="choice", options=["internal", "A", "B"])
ctx.fields.add("process", "cost_center", label="Cost center", type="number", default=0)
```

Forms: `agent`, `process`, `project`. Types: `text`, `textarea`, `number`, `bool`, `choice`. The fields appear in a
section of the plugin in the form and are saved with it. Read and write them anywhere (also on a slave):

```python
user = ctx.fields.get("agent", agent_id, "jira_user")
ctx.fields.all("project", project_id)              # {key: value} with defaults
ctx.fields.set("agent", agent_id, "jira_id", 4711)  # also keys without a form field
```

### Buttons in the forms – `ctx.ui.add_form_button`

```python
def check(form):
    if not form.get("jira_user"):
        form.set("jira_user", "bot." + form.values()["name"].lower())   # in the form, saved with “Save”

ctx.ui.add_form_button("agent", lambda form: "Check Jira" if form.id else None, check, icon="✓")
```

`form` has `kind`, `id` (None for a new, unsaved one), `data` (as stored), `values()` (as edited, with
`plugin_fields`), `get(key)` / `set(key, value)` for the plugin's own fields, `save()` and `reload()`.

---

## 5. Work with task lists

Theron's task lists hold epics, epics hold requirements. Permission: `tasklists`.

```python
projects = ctx.tasklists.projects()                         # [{"id", "name", "workspace"}]
tl_id = ctx.tasklists.create(projects[0]["id"], "Sprint 12", description="…")
epic = ctx.tasklists.add_epic(tl_id, "Login")
req = ctx.tasklists.add_requirement(epic, "Login form", description="…", acceptance="works with SSO",
                                    status="open", depends_on=[])
ctx.tasklists.update_requirement(req, status="done", result="merged")
tl = ctx.tasklists.get(tl_id)                               # the list with "epics" → "requirements"
for e in tl["epics"]:
    for r in e["requirements"]:
        print(e["name"], r["title"], r["status"])
```

| Call | Does |
|---|---|
| `projects()`, `list(project_id=None)`, `get(id)`, `find(project_id, name)` | read |
| `create`, `update(id, name=, description=, process_id=)`, `delete` | task lists |
| `add_epic`, `update_epic(id, name=, description=, depends_on=, closed=, status=)`, `delete_epic`, `epic(id)` | epics |
| `add_requirement`, `update_requirement(id, title=, description=, acceptance=, tech_rules=, status=, result=, depends_on=)`, `delete_requirement`, `requirement(id)` | requirements |

Statuses: `open`, `in_progress`, `hitl`, `done`, `failed`, `skipped`, `closed`. The app shows changes at once. To let
Theron work through a list, start it as a task: `ctx.runs.start(project_id, "Implement the list", …)` with a process
that has a task-list node – or let the user press “▶ Task-Liste”. Shapes: [data.md](data.md).

---

## 6. React to events

Events are notifications: Theron tells the plugin what happened and doesn't wait. They are delivered in the app and on
a slave (from `app.started` on), not in console runs.

```python
@ctx.events.on("run.finished")
def finished(event):
    if event["goal_reached"]:
        ctx.notify(ctx.tr("“{title}” is done.", title=event["title"]))

@ctx.events.on("hitl.asked")
async def asked(event):
    await send_to_phone(event["question"], event["options"])

ctx.events.on("*", lambda e: ctx.log(e["name"]))      # every event
```

The most used ones (all with payloads in [events.md](events.md)):

| Event | When |
|---|---|
| `app.started`, `app.stopping`, `settings.changed` | Theron starts / quits, the plugin's settings changed |
| `run.status`, `run.finished`, `run.event` | a task changes its status, ends, or writes anything to its log |
| `agent.started`, `agent.finished`, `agent.status` | an agent starts / ends a turn, reports its progress |
| `node.transition`, `run.reset` | the process moves from node to node, is restarted from a node |
| `hitl.asked`, `hitl.answered` | Theron asks the user, the question is answered |
| `tasklist.created` | a task-list node created or filled a list |
| `<kind>.saved`, `<kind>.deleted` | data changed – see [chapter 8](#8-react-to-transactions) |

Callbacks can be `async def` or plain functions (they run in a worker thread). Each event comes as one `dict` with
`"name"`; exceptions are logged and don't affect Theron.

---

## 7. Emit events of your own

A plugin's own events start with its id. Other plugins (and the plugin itself, with `include_own=True`) subscribe to
them like to Theron's.

```python
# plugin "whatsapp"
ctx.events.emit("whatsapp.sent", {"to": number, "text": text})

# any other plugin
@ctx.events.on("whatsapp.sent")
def sent(event):
    ctx.log(f"{event['source']} sent a WhatsApp to {event['to']}")   # source: "plugin:whatsapp"
```

When others should be able to **change** something before the plugin acts, offer a hook instead – the plugin waits for
their answer:

```python
msg = await ctx.hooks.call("whatsapp.before_send", {"to": number, "text": text})
await send(msg["to"], msg["text"])

# another plugin
@ctx.hooks.on("whatsapp.before_send")
def sign(hook):
    hook.data["text"] += "\n– sent by Theron"
```

Names: `<plugin id>.<name>` with letters, digits, `_`, `-`, `.`; Theron's prefixes (`run.`, `agent.` …) are reserved.

---

## 8. React to transactions

Every change of Theron's data is a transaction with an event *after* it was stored, whoever made it – the user, the
engine (e.g. a requirement's status while a task list runs), the local API, the server sync or another plugin:

| Event | Payload |
|---|---|
| `project.saved`, `process.saved`, `agent.saved`, `tasklist.saved`, `epic.saved`, `requirement.saved` | `{"name", "kind", "id", "data", "source"}` – `data` the stored entity |
| `….deleted` (same kinds) | `{"name", "kind", "id", "data": None, "source"}` |

```python
@ctx.events.on("requirement.saved")
async def changed(event):
    req = event["data"]
    if req["status"] == "done":
        await close_ticket(req["title"])

@ctx.events.on("agent.deleted")
def gone(event):
    ctx.storage.delete(f"jira:{event['id']}")
```

- **Own changes don't come back**: what the plugin changes through `ctx.tasklists`, `ctx.processes`, `ctx.agents`,
  `ctx.fields` carries `"source": "plugin:<id>"` and isn't delivered to the same plugin – no endless sync loops. Pass
  `include_own=True` to get them anyway. Other plugins get them with that source.
- `source` tells who changed it: `"plugin:<id>"` for a plugin, `"app"` for everything else (the user, the engine, the
  local API, the server sync).

**Before a transaction** – to check or change something before Theron does it, use a [hook](hooks.md):
`agent.before_start` (prompt and rules of an agent), `agent.after_end` (its result and verdict), `hitl.question` (a
question – or answer it yourself), `message.user`, `process.design.before/after`, `agent.design.before/after`,
`tasklist.before_create`, `assistant.process.before_create`. Handlers run in the plugin order the user set and may
change `hook.data`.

---

## 9. Read the running agents and their logs

`ctx.runs` reads what Theron works on right now – in the app and on a slave (where the tasks run). Permission: `runs`.

```python
for run in ctx.runs.active():                          # tasks running or waiting for an answer
    state = ctx.runs.state(run["id"])
    print(run["title"], state["status"], state["question"])
    for step in state["steps"]:
        print(" ", step["agent"], step["status"], step["status_note"])

for w in ctx.runs.workers():                           # the agents working right now
    minutes = (time.time() - w["started"]) / 60
    print(w["agent"], w["step_id"], f"{minutes:.0f} min", w["status_note"])
```

| Call | Returns |
|---|---|
| `active(project_id=None)` | the runs with status `running` / `waiting_input` |
| `state(run_id)` | status, phase, process, `question` (the open question), `agent_calls`, `cost_usd`, `steps` (status, activity, `status_note` – the agent's last progress report, calls, failures, loop), `workers` |
| `workers(run_id=None)` | working agents: `key`, `run_id`, `step_id`, `step`, `agent`, `engine`, `started`, `loop`/`item`, `status_note`, `activity` |
| `events(run_id, since=0, types=None, limit=200)` | the log as events after event id `since` – remember the last `id` to read only what is new |
| `log(run_id, last=100, agent=None)` | the last lines as text: `12:03:10 Developer ⚙ Bash: pytest` |
| `watch(fn, run_id=None, types=None, agent=None)` | `fn(event)` for every new log event (with `"line"`); `.cancel()` stops it |
| `await ask_worker(run_id, key, question)` | asks a working agent on the side – it keeps working; returns its short answer |

The log's event types: `agent_start`, `agent_text`, `agent_tool` (`summary`), `agent_log`, `agent_status`, `agent_end`
(`result`, `verdict`, `error`), `orchestrator`, `user`, `input_request` (`question`, `options`), `input_resolved`,
`handover`, `routing`, `decision`, `error`, `alert`, `status`, `complete` – each with `step` and `agent` where it fits.

**React to it:**

```python
async def on_output(event):
    if "Traceback" in (event.get("text") or event.get("summary") or ""):
        worker = next((w for w in ctx.runs.workers(event["run_id"]) if w["agent"] == event["agent"]), None)
        if worker:
            hint = await ctx.runs.ask_worker(event["run_id"], worker["key"], "What fails and why?")
            ctx.notify(f"{event['agent']}: {hint}", "warning")

ctx.on_start(lambda: ctx.runs.watch(on_output, types=["agent_tool", "agent_text"]))
```

| Call | Does |
|---|---|
| `message(run_id, text)` | tells THERON something, like a chat message |
| `answer(run_id, text)` | answers the open question (`state(run_id)["question"]`) |
| `stop(run_id, soon=False)` | stops the task – `soon`: lets the working agents finish |
| `reset(run_id, step_id)` | restarts the process from a node (like ↺) |
| `start(project_id, text, …)` | starts a new task |

`ask_worker` uses the user's Claude subscription (a copy of the agent's session answers once, like the progress
reports every few minutes); agents of other engines answer with a summary of their last steps.

The skeleton's `monitor.py` and `ui_monitor.py` are a complete example: a watch that notifies on errors, a check for
agents that work too long, a panel next to the cockpit and a live log window.

---

## 10. Extend the chat

Theron's chat only offers the hooks – what appears in it is up to the plugin: a player for audio, a document preview,
a diagram, buttons. Four pieces, all in `ctx.chat` (`my_plugin/chat.py` uses each of them):

| You want … | Use |
|---|---|
| text in **any** message to look different (a colour code, a file path, a ticket number) | `ctx.chat.add_format(pattern, render)` |
| a node to post something of its own (a list with buttons, a chart, a player) | `node.say(text, kind=..., data=...)` + `ctx.chat.add_renderer(kind, render)` |
| something clickable in your rich text | `ctx.chat.link(name, text, **params)` + `ctx.chat.on_link(name, fn)` |
| the chat to show a new state (▶ → ■, a new count) | `ctx.chat.refresh()` |
| a node to ask the user and wait | `await node.ask(question, options)` |

**Formatting.** `render(match)` returns Qt rich text for the matched text, or `None` to leave it. It runs for every
message whenever a chat is drawn – keep it quick; escape what comes from the match:

```python
import html, re
from pathlib import Path

AUDIO = re.compile(r"(?<![\w/])(/[^\s<>\"']+?\.(?:mp3|wav))\b")

def audio_path(m):
    path = m.group(1)
    if not Path(path).is_file():
        return None                                   # not there: plain text
    return html.escape(path) + " " + ctx.chat.link("play", "▶", src=path)

ctx.chat.add_format(AUDIO, audio_path)
```

**Blocks.** A node posts `node.say(text, kind="chart", data={...})`; Theron stores the event with the run and asks
your renderer every time the chat is drawn (also after a restart). `text` is the fallback where the block can't be
drawn – the web, Telegram, or when the plugin is switched off. Without `kind`, `node.say("**Markdown**")` is a plain
message.

```python
ctx.chat.add_renderer("chart", lambda data: f'<p><b>{html.escape(data["title"])}</b></p>'
                                            f'<img src="{html.escape(data["png"])}" width="440">')

async def plot(node):
    png = await render_chart(node.input, ctx.data_dir / f"chart-{node.run_id}.png")
    node.say("A chart of the numbers: " + str(png), kind="chart", data={"title": "Sales", "png": str(png)})
    return node.success(str(png))
```

**Buttons and clicks.** `ctx.chat.link(...)` makes an `<a href="theron-plugin://<plugin>/<name>?…">`; a click calls
your `on_link` handler with the params (in the background, not on the UI thread). Change your state, then
`ctx.chat.refresh()` – renderers and formats are asked again:

```python
def play(params):
    player.toggle(params["src"])     # your own player – e.g. afplay / winsound / ffplay via subprocess
    ctx.chat.refresh()               # ▶ becomes ■

ctx.chat.on_link("play", play)
```

**Asking in the chat.** `await node.ask(question, options=None, recommended=None, details="")` shows the question
like Theron's own (✋ on the run, answer buttons, web and Telegram work too) and returns the answer. Check it and ask
again when it doesn't fit:

```python
async def pick(node):
    voices = await load_voices()
    node.say("\n".join(f"{i}. {v}" for i, v in enumerate(voices, 1)), kind="voices", data={"voices": voices})
    for _ in range(3):
        answer = await node.ask("Which voice? (number or name)")
        if answer.isdigit() and 1 <= int(answer) <= len(voices):
            return node.success(voices[int(answer) - 1])
    return node.failure("No voice chosen.")
```

**Node fields that follow the node.** `options` may be a function of the node's settings, and `show_if` hides a field
until another one has a value – e.g. a voice list only for the mode “fixed”:

```python
fields=[{"key": "mode", "type": "choice", "default": "manual",
         "options": [{"value": "manual", "label": "Manual"}, {"value": "fixed", "label": "Fixed"}]},
        {"key": "voice", "type": "choice", "show_if": {"mode": "fixed"},
         "options": lambda config: [{"value": v["id"], "label": v["name"]} for v in cached_voices()]}]
```

The function runs on the UI thread – return what you have cached and refresh the cache in the background.

**Buttons in the settings.** `ctx.settings.add_button("Test", run)` puts a button into the plugin's settings dialog;
`run(values)` gets what the dialog shows right now (saved or not), runs in the background and returns a text or
`(ok, text)` – ✔ green or ✖ red below the buttons.

**Testing.** The devkit renders and clicks like the chat: `ctx.chat.render(kind, data)`, `ctx.chat.format(text)`,
`await ctx.chat.click(href)`, answers for `node.ask` from `ctx.chat.answers` – see [testing.md](testing.md).

A complete plugin built on all of this: **ElevenLabs** in the [plugin catalog](https://www.theron-ai.de/plugins.html)
– voices listed with ▶ samples in the chat, a voice picked by number or in your own words, the generated audio files
playable right there.

