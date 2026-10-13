# Hooks

Hooks let a plugin **step into what Theron does** and change the outcome: a prompt before an agent starts, an agent's
result, a question to the user (or its answer), what the AI designs, a task list before it is created, the temporary
process of the THERON assistant.

```python
@ctx.hooks.on("agent.before_start")
def house_rules(hook):
    hook.data["system_prompt"] += "\nAlways write tests for what you build."
```

## Hooks and events

| | Hooks (`ctx.hooks.on`) | Events (`ctx.events.on`) |
|---|---|---|
| Theron waits | yes – the flow continues with the result | no – fire and forget |
| Can change something | yes, `hook.data` | no |
| Order | one after another in the **plugin order** | in plugin order, but concurrently |
| Runs in | app, slave **and** console runs | app and slave |
| Typical use | inject prompts, check or rewrite results, answer questions, adjust drafts | notify (WhatsApp, Slack), sync, log |

## The `hook` object

| Member | Description |
|---|---|
| `hook.name` | the hook's name |
| `hook.context` | what it is about – read-only (a copy; changing it has no effect) |
| `hook.data` | what the plugins may change – a `dict`; change it in place or **return** a new `dict` |
| `hook.source` | who called the hook: `"theron"` or `"plugin:<id>"` (for plugins' own hooks) |
| `hook.handled_by` | ids of the plugins whose handlers already ran |
| `hook.stop()` | no further plugin handles this hook; the changes so far count |

## How Theron runs a hook

1. The handlers of all plugins run **one after another in the plugin order** – the user sets it in Settings → Plugins
   (▲ ▼) or with `theron plugin order ID …`; within one plugin in the order they were registered.
2. Each handler gets a **copy** of the data as the previous handler left it.
3. A handler that **raises** or doesn't finish within its **timeout** (default 60 s, `ctx.hooks.on(name, fn,
   timeout=…)`) changes nothing – its error is logged and the next handler gets the data from before.
4. Theron reads back **only the documented keys** of `data` and checks their types; everything else in `data` is
   information.
5. Without any handler a hook costs nothing.

Handlers may be `async` or plain (plain ones run in a worker thread). Keep them fast where Theron waits often
(`agent.before_start` runs for every agent turn); use a timeout that fits slow work (an AI call: `timeout=180`).

## Built-in hooks

### `agent.before_start`
Before an agent starts working on a step – alone, in a parallel group or for one item of a loop.

| `context` | `run`, `project`, `process`, `requirement` (if the run works through a task list), `step`, `agent`, `handovers` (what reached the step: `[{"from", "text", "verdict"}]`), `item` (in a loop: `{"n", "total", "title"}`), `parallel` (`bool`) |
|---|---|
| **`data` – changeable** | `prompt` (`str` – the agent's task including the hand-overs), `system_prompt` (`str` – the agent's briefing: role, rules, process), `result` (`None` – set a `str` to **skip the agent**: Theron takes it as the agent's hand-over; end it with `RESULT: SUCCESS` / `RESULT: FAILURE` to choose the exit) |

### `agent.after_end`
After an agent's turn, before Theron routes on.

| `context` | as `agent.before_start`, plus `session_id` |
|---|---|
| **`data` – changeable** | `result` (`str` – the hand-over), `verdict` (`"success"`, `"failure"` or `None` = let Theron's orchestrator judge) |
| `data` – information | `error` (`bool`), `cost_usd`, `prompt`, `system_prompt` |

### `hitl.question`
Before Theron asks the user something – a ✋ user decision in the process or a question of the orchestrator.

| `context` | `run`, `project`, `process`, `requirement`; `kind`: `"decision"` (a ✋ node – then also `step`) or `"orchestrator"`; `sub_run` when a sub-process asks |
|---|---|
| **`data` – changeable** | `question` (`str`), `options` (`list[str]`), `recommended` (index or `None`), `details` (`str` – background shown with the question), `answer` (`None` – set a `str` to **answer it yourself**: the user isn't asked; the chat shows the answer with the source `plugin:<id>`) |
| `data` – information | `questions` (a multi-part question, if any) |

For a ✋ decision, an `answer` equal to one of the `options` picks that exit; any other text is a comment and takes the
“else” exit.

### `message.user`
A message to Theron (the user in the chat or the web UI, the API, a plugin) before the orchestrator gets it.

| `context` | `run`, `project`, `process`, `source` (`"app"`, `"web:<user>"`, `"api"`, `"plugin:<id>"` …), `shown` (the text as shown in the chat) |
|---|---|
| **`data` – changeable** | `text` (`str` – what the orchestrator receives; the chat keeps showing the original) |

### `orchestrator.prompt`
When Theron's orchestrator starts on a run (and when its session is rebuilt).

| `context` | `run`, `project`, `process` |
|---|---|
| **`data` – changeable** | `system_prompt` (`str` – the orchestrator's complete briefing: process graph, agents, rules, workflow) |

### `process.design.before` / `process.design.after`
“✦ Create with AI”, “✦ Refine” in the process editor and the THERON assistant's team drafts.

| `context` | `mode`: `"create"` or `"refine"`; `origin`: `"editor"` or `"assistant"`; `current` (refine: the process before, in [draft format](data.md#process-draft)) |
|---|---|
| **before – changeable** | `request` (`str` – what the user asked for), `system_prompt` (`str` – the designer's instructions), `prompt` (`str` or `None` – the complete prompt incl. existing agents/processes; `None` for `create` until it's built – set it to replace the prompt) |
| **after – changeable** | `draft` (`dict` – the AI's process in [draft format](data.md#process-draft)) |

A changed draft must still be a complete process (every step reachable, every output connected, a way to the end) –
otherwise Theron reports which plugin broke it and the design fails.

### `agent.design.before` / `agent.design.after`
“✦ Create with AI” for an agent.

| `context` | `existing_agents` (before: names in use), `request` (after) |
|---|---|
| **before – changeable** | `request`, `system_prompt`, `prompt` (as above) |
| **after – changeable** | `agent` (`dict`: `name`, `task`, `rules`, `model`, `backend`, `model_reason` …) |

### `tasklist.before_create`
Before a ☰ task-list node creates a temporary list from its input (`tl_mode` “new”) or fills a real one (“fill”).

| `context` | `run`, `project`, `process`, `step`, `mode` (`"new"` / `"fill"`), `task` |
|---|---|
| **`data` – changeable** | `draft` (`dict`: `{"name", "epics": [{"key", "name", "description", "depends_on", "requirements": [{"key", "title", "description", "acceptance", "tech_rules", "depends_on"}]}]}`) |

After it's created, the event `tasklist.created` follows.

### `assistant.process.before_create` / `assistant.process.created`
The THERON assistant (the THERON page) drafts a temporary team for a job.

| `context` | `run_id`, `folder` (the job's working folder), `title`, `follow_up` (`bool`); created: also `goal`, `agents` (`[{"id", "name"}]` – the temporary agents) |
|---|---|
| **before – changeable** | `goal`, `briefing`, `description` (`str` – what the designer gets) |
| **created – changeable** | `process` (`dict` – the temporary process document, before it is saved; must keep `steps`) |

The designer hooks (`process.design.*` with `origin: "assistant"`) run in between.

## A plugin's own hooks

A plugin can offer hooks of its own, so other plugins can step into what it does. Its hook names start with its id:

```python
# plugin "whatsapp"
msg = await ctx.hooks.call("whatsapp.before_send", {"to": number, "text": text}, context={"run_id": run_id})
await send(msg["to"], msg["text"])

# another plugin
@ctx.hooks.on("whatsapp.before_send")
def sign(hook):
    hook.data["text"] += "\n– sent by Theron"
```

`await ctx.hooks.call(name, data, context=None)` returns the data as the handlers left it (the calling plugin's own
handlers included). The same works for events: `ctx.events.emit("whatsapp.sent", {...})` – see [Events](events.md).

## Examples

**A base prompt for everything the AI designs**

```python
@ctx.hooks.on("process.design.before")
def base_prompt(hook):
    hook.data["system_prompt"] += "\n\nHOUSE RULES:\n" + ctx.settings["house_rules"]
```

**Answer questions with Claude when it is sure**

```python
@ctx.hooks.on("hitl.question", timeout=180)
async def answer(hook):
    reply = await ctx.ai.ask(f"Question: {hook.data['question']}\nOptions: {hook.data['options']}\n"
                             f"{hook.data['details']}\nReply with the option only, or UNSURE.", model="sonnet")
    if reply.strip() in hook.data["options"]:
        hook.data["answer"] = reply.strip()
```

**Check every result against a rule**

```python
@ctx.hooks.on("agent.after_end")
def no_secrets(hook):
    if "BEGIN PRIVATE KEY" in hook.data["result"]:
        hook.data["result"] += "\n\nThe hand-over contains a private key – remove it.\nRESULT: FAILURE"
        hook.data["verdict"] = "failure"
```

**Skip an agent when a cached answer exists**

```python
@ctx.hooks.on("agent.before_start")
def cached(hook):
    hit = ctx.storage.get("cache:" + sha(hook.data["prompt"]))
    if hit:
        hook.data["result"] = hit
```

More in this skeleton: [`my_plugin/hooks.py`](../my_plugin/hooks.py) (WhatsApp on node changes, a base prompt for AI
designs, questions answered by Claude).
