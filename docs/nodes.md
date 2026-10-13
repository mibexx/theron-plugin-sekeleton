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

`ctx.nodes.register(kind, *, label, run, description="", icon="⬢", fields=None, outputs="success_failure", ai_hint="")`
– see the [parameter table](context.md#ctxnodes). The node's id is `"<plugin id>/<kind>"`; it is stored in every
process that uses the node, so **never rename `kind` (or the plugin id) after release** – processes would lose the
node.

## Outputs

| `outputs` | Node shape | Routing |
|---|---|---|
| `"success_failure"` | ✔ and ✖ outputs, like an agent step | `node.success()` → ✔, `node.failure()` → ✖. The ✖ edge may loop back (e.g. to an agent that fixes something) – the user sets *max. iterations* in the properties panel. Without a ✖ edge, Theron asks the user. |
| `"success"` | one ✔ output | `node.success()` → ✔. `node.failure()` stops there and Theron asks the user what to do. |

## Fields

Each field is a `dict`; the editor shows them in the properties panel, the values arrive as `node.config`.

| Key | Required | Meaning |
|---|---|---|
| `key` | ✔ | name in `node.config` |
| `type` | | `text` (default), `textarea`, `number`, `bool`, `choice`, `tasklist`, `project` |
| `label` | | label in the panel (default: the key); translated with the plugin's i18n |
| `description` | | hint below the input; translated |
| `default` | | value of a new node (`node.config` always contains every field: default or the user's value) |
| `options` | for `choice` | the values to choose from |

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
| `node.task` | `str` | the run's current task (what the orchestrator asked this step to do) |
| `node.instructions` | `str` | the step's instructions from the editor |
| `node.project` | `dict` | `{"id", "name", "workspace"}` – `workspace` is the folder the agents work in |
| `node.run_id` | `int` | the run (task) |
| `node.step_name` | `str` | the step's name in this process |
| `node.tasklist_id` | `int \| None` | a task list handed over by a previous step (task-list node, an import …) |
| `node.ctx` | `ctx` | the plugin's context |
| `node.started` | `float` | `time.time()` when the node started |
| `node.progress(text)` | | the status line on the node's card in the cockpit and the flow (max. 140 characters) |
| `node.success(text="", tasklist_id=None)` | `NodeResult` | ✔ – `text` becomes the hand-over to the next step; `tasklist_id` hands a task list on (e.g. to a loop, which then works through its requirements) |
| `node.failure(text)` | `NodeResult` | ✖ – `text` explains what went wrong; it goes to the step behind ✖ |

## Results

`run` may return:

| Return value | Meaning |
|---|---|
| `node.success(...)` / `node.failure(...)` | ✔ / ✖ as above |
| a `str` | ✔ with this text |
| `None` | ✔ with “Done.” |
| a `dict` `{"ok": bool, "text": str, "tasklist_id": int}` | ✔ or ✖ |

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
