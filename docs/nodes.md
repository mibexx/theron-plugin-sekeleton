# Process nodes

A plugin node is a step in a Theron process, like the built-in agent, decision or database nodes. Users drag it from
the editor's **TOOLS** list onto the canvas, connect it and fill in its fields. When a task reaches the node, Theron
calls the plugin's `run(node)` and routes on along the node's outputs.

```python
def register(ctx):
    async def push(node):
        board = node.config["board"]
        if not board:
            return node.failure("No board chosen")
        for h in node.handovers:
            await create_card(board, h["text"])
        return node.success(f"{len(node.handovers)} cards created on {board}")

    ctx.nodes.register(
        "push", label=ctx.tr("Push to Trello"), icon="▦", run=push,
        description=ctx.tr("Creates a Trello card per hand-over"),
        ai_hint="Use after results that should become Trello cards",
        fields=[{"key": "board", "type": "text", "label": ctx.tr("Board"), "default": "Main"},
                {"key": "list", "type": "choice", "label": ctx.tr("List"), "options": ["To do", "Doing"]}],
        outputs="success_failure")
```

## Registration

`ctx.nodes.register(kind, *, label, run, description="", icon="⬢", fields=None, outputs="success_failure", ai_hint="", inputs=None, wait="all")`
– see the [parameter table](context.md#ctxnodes). The node's id is `"<plugin id>/<kind>"`; it is stored in every
process that uses the node, so **never rename `kind` (or the plugin id) after release** – processes would lose the
node.

## Outputs

| `outputs` | Node shape | Routing |
|---|---|---|
| `"success_failure"` | ✔ and ✖ outputs, like an agent step | `node.success()` → ✔, `node.failure()` → ✖. The ✖ edge may loop back (e.g. to an agent that fixes something) – the user sets *max. iterations* in the properties panel. Without a ✖ edge, Theron asks the user. |
| `"success"` | one ✔ output | `node.success()` → ✔. `node.failure()` stops there and Theron asks the user what to do. |
| a list / a function | one output per entry, labelled | `node.route("id")` → that output (or several: `node.route(["a", "b"])`). See [named outputs](#named-outputs-a-switch). |

## Named outputs (a switch)

A node can have as many outputs as it needs – like Theron's decision node. Give them as a list, or as a function of
the node's settings when they depend on what the user configured:

```python
def register(ctx):
    def routes(config):                       # called by the editor whenever the settings change
        names = [ln.strip() for ln in config["routes"].splitlines() if ln.strip()]
        return [{"id": f"r{k}", "label": n} for k, n in enumerate(names)] + [{"id": "other", "label": "Other"}]

    async def route(node):
        text = node.input.lower()
        hit = next((o for o in node.outputs if o["label"].lower() in text), None)
        return node.route(hit["id"] if hit else "other", f"matched {hit['label'] if hit else 'nothing'}")

    ctx.nodes.register("route", label=ctx.tr("Keyword router"), icon="◇", run=route, outputs=routes,
                       fields=[{"key": "routes", "type": "textarea", "default": "Bug\nFeature"}])
```

- **Ports:** each output is `{"id", "label"}` (a plain string is both). The id is what `node.route()` takes and what
  the process stores – keep ids stable; the label is what the editor shows next to the port.
- **Colours:** `"color"` decides how the port, its label and its edges are drawn – `"success"` (green),
  `"error"` (red, dashed edges), `"neutral"` (amber), `"info"` (cyan) or any hex colour (`"#8a2be2"`). Inputs take
  it too (default cyan). Without a colour, an output called `error` / `failure` is red and – next to it – a single
  other output green; everything else is amber. With a function, the colour may follow the settings
  (`{"id": "done", "color": "error" if config["strict"] else "success"}`). *(Theron ≥ 0.18; older versions ignore it.)*
- **Dynamic:** with a function, the editor asks it again whenever a field of the node changes and redraws the ports.
  Edges of outputs that still exist stay; the edge of an output that's gone is removed. When a process is opened,
  the ports are worked out again (an update of the plugin may have changed them). The function gets the full config
  (defaults merged) and must be quick and side-effect free; if it raises, the editor keeps the old ports.
- **Routing:** `node.route(id, text="", tasklist_id=None)` – the hand-over (`text`, plus the hand-overs that came in)
  goes to the step behind that output. `node.route([id1, id2])` goes on via several outputs at once, like an AND
  split. An output without an edge, `node.failure(...)`, or a result without an output makes Theron ask the user.
  A node with exactly one named output may simply return `node.success()`.
- **Flow & chat:** the cockpit shows which output was taken; the orchestrator sees each output with its target.
- **AI designer:** knows the outputs (and that they depend on the settings) and writes
  `{"type": "plugin", "node": "my-plugin/route", "config": {…}, "routes": {"r0": "<key>", "other": "end"}}`.

## Named inputs

A node can also have several labelled inputs – e.g. one for code and one for documentation:

```python
def merge(node):
    code = node.inputs["code"]      # the hand-overs that came in at “Code”
    docs = node.inputs["docs"]
    return node.success(f"{len(code)} code and {len(docs)} doc hand-overs merged")

ctx.nodes.register("merge", label="Merge", run=merge, outputs="success",
                   inputs=[{"id": "code", "label": "Code"}, {"id": "docs", "label": "Docs"}], wait="all")
```

- In the editor, an edge ends at the input port it is dropped on (dropped on the node itself: the first input).
- `wait="all"`: the node waits until every **connected** input has a hand-over (like a join), then runs once with all
  of them. `wait="any"`: it runs as soon as something arrives; `node.inputs` then only has hand-overs for the inputs
  that got one.
- `node.handovers` still contains all hand-overs together. `inputs` may be a function of the config, too.
- Inputs take a `"color"` like outputs: `{"id": "code", "label": "Code", "color": "#ff00aa"}`.
- AI designer: `"input_map": {"<key of the source step>": "<input id>"}`.

## Fields

Each field is a `dict`; the editor shows them in the properties panel, the values arrive as `node.config`.

| Key | Required | Meaning |
|---|---|---|
| `key` | ✔ | name in `node.config` |
| `type` | | `text` (default), `textarea`, `number`, `bool`, `choice`, `tasklist`, `project` |
| `label` | | label in the panel (default: the key); translated with the plugin's i18n |
| `description` | | hint below the input; translated |
| `default` | | value of a new node (`node.config` always contains every field: default or the user's value) |
| `options` | for `choice` | the values to choose from: plain values (`["mp3", "wav"]`, shown as they are), `{"value", "label"}` dicts (the label is shown and translated, the value lands in `node.config`) – or a function `options(config) -> list` the editor asks whenever the node is shown, e.g. the voices of an account *(dicts and functions: 0.17)*. A function is called on the UI thread: return a cached list, refresh it in the background (`ctx.spawn`). A value the options don't list (any more) stays selected. |
| `buttons` | | buttons next to the field: `[{"label": "▶ Sample" or label(config), "run": run(config), "tooltip": "…"}]` – `run` (sync or async) runs in the plugins' loop with the node's current settings (saved or not); return nothing, a text, or `(ok, text)` – shown below the buttons (green / red). A label function is asked again every ~0.7 s, e.g. `"■ Stop" if playing else "▶ Sample"` *(0.18; older versions ignore it)* |
| `show_if` | | show the field only when other fields match: `{"mode": "fixed"}`, `{"mode": ["a", "b"]}` (one of) or a function `show_if(config) -> bool` *(0.17)* – hidden fields keep their value |

Values: `number` → `int` (or `float`), `bool` → `bool`, `tasklist`/`project` → id or `None`, others → `str`.
Besides the fields, every plugin node has a **name** (shown on the node) and **instructions** (free text, arrives as
`node.instructions`).

## The `node` object

What `run(node)` receives:

| Member | Type | Description |
|---|---|---|
| `node.config` | `dict` | the field values (defaults merged with the user's values) |
| `node.input` | `str` | everything that reached the node as one text: the hand-overs (“### Hand-over from … – RESULT: …”), the current requirement's briefing when the run works through a task list, and the process's confirmed inputs |
| `node.handovers` | `list[dict]` | the hand-overs one by one: `{"from": step name, "text": text, "verdict": "success" \| "failure" \| ""}` |
| `node.task` | `str` | what the orchestrator asked **this step** to do – often where the user's wishes for the step end up (“speak this sentence”). It is **not** part of `node.input`: a node that works on “the material” should look at both (see the tip below) |
| `node.instructions` | `str` | the step's instructions from the editor |
| `node.project` | `dict` | `{"id", "name", "workspace"}` – `workspace` is the folder the agents work in |
| `node.run_id` | `int` | the run (task) |
| `node.step_name` | `str` | the step's name in this process |
| `node.tasklist_id` | `int \| None` | a task list handed over by a previous step (task-list node, an import …) |
| `node.inputs` | `dict[str, list[dict]]` | named inputs: the hand-overs per input id (`{}` for a node with one plain input) |
| `node.outputs` | `list[dict]` | named outputs of this step: `[{"id", "label"}]` (`[]` for ✔ / ✖ nodes) |
| `node.ctx` | `ctx` | the plugin's context |
| `node.started` | `float` | `time.time()` when the node started |
| `node.progress(text)` | | the status line on the node's card in the cockpit and the flow (max. 140 characters) |
| `await node.ask(question, options=None, *, recommended=None, details="")` | `str` | ask the user in the chat and wait for the answer – the run shows ✋ and every answer channel works (app, web, Telegram …). `options`: answer buttons (the user may still type something else), `recommended`: index of the suggested option, `details`: Markdown below the question (chat formats of plugins apply). The question is prefixed with the step's name. *(0.17)* |
| `node.say(text="", *, kind="", data=None)` | | a message of the node in the chat: Markdown `text` – or a block of the plugin's own `kind` drawn by `ctx.chat.add_renderer(kind, …)` from `data` (JSON). With a block, `text` is the fallback where it can't be drawn (web, Telegram, plugin off). *(0.17)* |
| `node.success(text="", tasklist_id=None)` | `NodeResult` | ✔ – `text` becomes the hand-over to the next step; `tasklist_id` hands a task list on (e.g. to a loop, which then works through its requirements) |
| `node.failure(text)` | `NodeResult` | ✖ – `text` explains what went wrong; it goes to the step behind ✖ |
| `node.route(output, text="", tasklist_id=None)` | `NodeResult` | named outputs: go on via `output` (an id, or a list of ids for several paths); raises `PluginError` for an unknown id |

> **Tip – `task` and `input` together.** `node.input` is what the steps before handed over – behind a node that only
> passes something on (e.g. “Choose voice”) that may be a single line. `node.task` is the orchestrator's assignment
> for this step. `node.input or node.task` silently drops the assignment as soon as anything was handed over; give
> both to the AI instead:
>
> ```python
> material = "\n\n".join(x for x in (f"ASSIGNMENT:\n{node.task}" if node.task else "",
>                                     f"HAND-OVERS:\n{node.input}" if node.input else "") if x)
> ```
>
> And a node in the middle of a chain should hand on what it got (plus its own result), so the steps after it still
> see the material.

## Results

`run` may return:

| Return value | Meaning |
|---|---|
| `node.success(...)` / `node.failure(...)` | ✔ / ✖ as above |
| a `str` | ✔ with this text |
| `None` | ✔ with “Done.” |
| a `dict` `{"ok": bool, "text": str, "tasklist_id": int, "output": str \| list}` | ✔ or ✖ – or, with named outputs, the output(s) |
| `node.route(...)` | named outputs: the chosen output(s) |

On ✔, the incoming hand-overs travel on together with the node's own text – a plugin node in the middle of a chain
doesn't swallow the results before it. On ✖, only the node's failure text goes on.

If `run` raises, the step is marked as failed (with the exception's text on its card), the traceback goes to the
plugin's log and Theron asks the user how to continue.

`run` may take as long as it needs; the user can stop the task meanwhile. Async is preferred; a plain function runs in
a worker thread.

## What Theron does around the node

- **Cockpit & chat:** the node shows up with its icon and label; its result appears as `⬢ <name> ✔ <text>` (or ✖).
- **Orchestrator:** Theron's orchestrator sees the node with its `ai_hint` (or `description`) and its settings, and runs
  it like any other step.
- **AI process designer:** “✦ Create with AI” and “✦ Refine” know every installed plugin node with its fields and
  `ai_hint`, and use a node when it fits. In a draft it looks like
  `{"type": "plugin", "node": "trello-sync/push", "config": {"board": "Sprint"}, "on_success": "…"}`.
- **Missing plugin:** a process keeps its plugin nodes when the plugin is removed, switched off or not installed on
  another machine. The editor shows them in red (“PLUGIN MISSING”); a run that reaches one asks the user.
- **Export / sync:** processes with plugin nodes can be exported (`.theron`) and synced via the Theron server; the
  plugin itself is not part of that – install it on every machine that runs the process.

## In the process document

For reference – how a plugin node is stored in a process (`.theron` exports, the local API):

```json
{"id": "s3f9a1c2", "type": "plugin", "name": "", "plugin_node": "trello-sync/push",
 "plugin_config": {"board": "Sprint", "list": "To do"}, "plugin_outputs": "success_failure",
 "instructions": "", "on_success": "s8b21e07", "on_failure": "ask_user", "max_iterations": 3, "on_max": "ask_user"}
```

With named ports, the step keeps the ports it was drawn with and where they lead:

```json
{"id": "s1c0ffee", "type": "plugin", "plugin_node": "my-plugin/route", "plugin_config": {"routes": "Bug\nFeature"},
 "plugin_outputs": "ports",
 "plugin_ports": {"inputs": [], "outputs": [{"id": "r0", "label": "Bug"}, {"id": "r1", "label": "Feature"},
                                            {"id": "other", "label": "Other"}]},
 "plugin_routes": {"r0": "s8b21e07", "r1": "s77aa010", "other": "end"},
 "plugin_input_map": {}, "plugin_wait": "all"}
```

`plugin_input_map` maps a source step id to the input its edge ends at (`{"s8b21e07": "docs"}`).

### Choices that follow the other fields (0.20)

A `choice` whose `options` is a function of the settings is asked again whenever another field of the node changes
and when a field button is done – e.g. the files of a folder named in another field:

```python
{"key": "template_dir", "type": "text", "label": "Template folder",
 "buttons": [{"label": "＋", "run": add_templates}]},       # add_templates may await ctx.ui.run(ctx.ui.ask_files, …)
{"key": "template", "type": "choice", "label": "Template",
 "options": lambda cfg: [{"value": f.name, "label": f.name} for f in Path(cfg["template_dir"]).glob("*.html")]},
```

The selection stays, even if the new list doesn't have it.
